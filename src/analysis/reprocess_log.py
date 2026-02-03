"""Reprocess Anderaa JSON/JSONL logs and add corrected/derived values.

This script reads the recorder output produced by the GUI (JSON Lines) and enriches
records with *post-processed* values using consistent formulas:

- Practical salinity from conductivity via PSS-78 (if not already present)
- Oxygen solubility via either:
    - Weiss (1970) at 1 atm, optionally scaled by barometric pressure, or
    - TEOS-10/GSW best practice (Garcia & Gordon 1992/1993) if `gsw` is installed.
- Oxygen concentration derived from % saturation using solubility
- Convenience conversions (e.g., µmol/L -> mg/L)
- Pressure conversions kPa -> dbar and optional sea pressure/depth from an air baseline

Input formats:
- .jsonl: one JSON object per line (the default recorder format)
- .json:  an array of objects in the same shape

Output:
- Writes an enriched .jsonl (default) or .json into `Log_corrected/` by default.

Usage (PowerShell):
    python src/analysis/reprocess_log.py --log Log/aanderaa_log_20260126_142957.jsonl

    # Provide a known barometric pressure for solubility scaling
  python src/analysis/reprocess_log.py --log Log/aanderaa_log_20260126_142957.jsonl --baro-kpa 95.5

    # Provide a known in-air baseline for the pressure sensor
  python src/analysis/reprocess_log.py --log Log/aanderaa_log_20260126_142957.jsonl --air-pressure-kpa 95.466

    # Prefer TEOS-10/GSW oxygen solubility (Garcia & Gordon) if available
    python src/analysis/reprocess_log.py --log Log/aanderaa_log_20260126_142957.jsonl --o2sol-model auto
"""

from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


def parse_iso_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Strip common unit suffixes.
        for suffix in ("%", "µmol/L", "umol/L", "°C", "mS/cm", "kPa", "dbar", "m"):
            s = s.replace(suffix, "")
        s = s.strip()
        try:
            f = float(s)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def o2_umol_l_to_mg_l(o2_umol_l: float) -> float:
    # Molar mass of O2 = 31.998 g/mol.
    return float(o2_umol_l) * 0.031998


def pressure_kpa_to_dbar(pressure_kpa: float) -> float:
    # 1 dbar = 10 kPa
    return float(pressure_kpa) / 10.0


def o2_sol_umol_per_l_weiss1970(temp_c: float, sal_psu: float) -> float:
    """O2 solubility at 1 atm (air-saturated), Weiss (1970).

    Returns oxygen solubility in µmol/L.

    Notes:
      - This matches the implementation used in the GUI but uses `math` instead of numpy.
      - Weiss (1970) returns ml/L at STP; conversion used: 1 ml O2 (STP) = 44.6596 µmol.
    """

    T = float(temp_c) + 273.15
    S = float(sal_psu)

    A1 = -173.4292
    A2 = 249.6339
    A3 = 143.3483
    A4 = -21.8492
    B1 = -0.033096
    B2 = 0.014259
    B3 = -0.0017000

    Ts = T / 100.0
    lnC = (
        A1
        + A2 * (100.0 / T)
        + A3 * (math.log(Ts))
        + A4 * Ts
        + S * (B1 + B2 * Ts + B3 * (Ts**2))
    )

    c_ml_per_l = math.exp(lnC)
    return c_ml_per_l * 44.6596


def o2_sol_umol_per_l_gsw(temp_c: float, sal_psu: float) -> Optional[float]:
    """O2 solubility from TEOS-10/GSW (Garcia & Gordon 1992/1993).

    Returns solubility as µmol/L (approx) by:
      1) using `gsw.O2sol_SP_pt(SP, pt)` (µmol/kg)
      2) converting to µmol/L using density computed from `gsw.rho(SA, CT, p)`.

    Notes:
      - In TEOS-10, `O2sol_SP_pt` expects Practical Salinity (SP) and potential temperature (pt).
        In near-surface tank work we approximate pt ≈ in-situ temperature.
      - `gsw.rho` expects Absolute Salinity (SA) and Conservative Temperature (CT).
        We use a pragmatic approximation SA ≈ SP and CT ≈ temperature (°C).
    """

    try:
        import gsw  # type: ignore
    except Exception:
        return None

    SP = float(sal_psu)
    pt = float(temp_c)
    try:
        o2_umol_per_kg = float(gsw.O2sol_SP_pt(SP, pt))
        rho_kg_m3 = float(gsw.rho(SP, pt, 0.0))
    except Exception:
        return None

    if (not math.isfinite(o2_umol_per_kg)) or (not math.isfinite(rho_kg_m3)) or rho_kg_m3 <= 0:
        return None

    # umol/kg * (kg/m^3) / 1000 = umol/L
    return o2_umol_per_kg * (rho_kg_m3 / 1000.0)


def o2_sol_umol_per_l(
    temp_c: float,
    sal_psu: float,
    *,
    model: str,
) -> tuple[Optional[float], str]:
    """Compute O2 solubility and report which model was used."""

    m = (model or "").strip().lower()
    if m not in {"auto", "weiss1970", "gsw"}:
        m = "auto"

    if m in {"auto", "gsw"}:
        v = o2_sol_umol_per_l_gsw(temp_c, sal_psu)
        if v is not None:
            return float(v), "gsw"
        if m == "gsw":
            return None, "gsw"

    try:
        return float(o2_sol_umol_per_l_weiss1970(temp_c, sal_psu)), "weiss1970"
    except Exception:
        return None, "weiss1970"


def scale_o2_solubility_for_pressure(o2sol_umol_l_at_1atm: float, baro_kpa: Optional[float]) -> float:
    if baro_kpa is None or (not math.isfinite(baro_kpa)) or baro_kpa <= 0:
        return float(o2sol_umol_l_at_1atm)
    return float(o2sol_umol_l_at_1atm) * (float(baro_kpa) / 101.325)


def pss78_salinity_from_conductivity_ms_cm(
    conductivity_ms_cm: float,
    temp_c: float,
    pressure_dbar: float = 0.0,
) -> Optional[float]:
    """Practical Salinity (PSS-78) from conductivity (mS/cm), temperature (°C), pressure (dbar)."""

    C = float(conductivity_ms_cm)
    if (not math.isfinite(C)) or C <= 0:
        return None

    T = float(temp_c)
    P = float(pressure_dbar)

    C35150 = 42.914
    R = C / C35150
    if (not math.isfinite(R)) or R <= 0:
        return None

    rt35 = 0.6766097 + 0.0200564 * T + 0.0001104259 * T**2 + (-6.9698e-7) * T**3 + 1.0031e-9 * T**4

    if P != 0.0 and math.isfinite(P):
        d1 = 0.03426
        d2 = 0.0004464
        d3 = 0.4215
        d4 = -0.003107
        e1 = 2.070e-5
        e2 = -6.370e-10
        e3 = 3.989e-15
        denom = 1.0 + d1 * T + d2 * T**2 + (d3 + d4 * T) * R
        Rp = 1.0 + (P * (e1 + e2 * P + e3 * P**2)) / denom
    else:
        Rp = 1.0

    Rt = R / (Rp * rt35)
    if (not math.isfinite(Rt)) or Rt <= 0:
        return None

    sqrtRt = math.sqrt(Rt)

    a0 = 0.0080
    a1 = -0.1692
    a2 = 25.3851
    a3 = 14.0941
    a4 = -7.0261
    a5 = 2.7081

    b0 = 0.0005
    b1 = -0.0056
    b2 = -0.0066
    b3 = -0.0375
    b4 = 0.0636
    b5 = -0.0144

    S = a0 + (a1 * sqrtRt) + (a2 * Rt) + (a3 * Rt * sqrtRt) + (a4 * Rt**2) + (a5 * Rt**2 * sqrtRt)

    dT = (T - 15.0) / (1.0 + 0.0162 * (T - 15.0))
    S += dT * (b0 + (b1 * sqrtRt) + (b2 * Rt) + (b3 * Rt * sqrtRt) + (b4 * Rt**2) + (b5 * Rt**2 * sqrtRt))

    if not math.isfinite(S):
        return None
    return float(S)


@dataclass
class Context:
    latest_sal_psu: Optional[float] = None
    latest_sal_at: Optional[datetime] = None

    latest_abs_pressure_kpa: Optional[float] = None
    latest_pressure_at: Optional[datetime] = None


def infer_sensor_type(measurements: dict[str, Any], name: str) -> str:
    product = str(measurements.get("ProductNumber", ""))
    if product.startswith("4117") or product.startswith("5217") or product.startswith("5218"):
        return "pressure"
    if product.startswith("4330") or product.startswith("4835") or product.startswith("4831"):
        return "oxygen"
    if product.startswith("5819") or product.startswith("5990"):
        return "conductivity"

    # Fallback heuristics.
    lname = (name or "").lower()
    if "4330" in lname or "optode" in lname or "oxygen" in lname:
        return "oxygen"
    if "5819" in lname or "conduct" in lname:
        return "conductivity"
    if "4117" in lname or "pressure" in lname:
        return "pressure"

    return "unknown"


def iter_records(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
        return

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield item
        return

    raise ValueError("Unsupported JSON input: expected .jsonl or a JSON array")


def write_records(path: Path, records: list[dict[str, Any]], *, as_jsonl: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if as_jsonl:
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    else:
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Reprocess Anderaa logs and add corrected derived values")
    ap.add_argument("--log", required=True, help="Path to input .jsonl (or .json array)")
    ap.add_argument(
        "--out",
        default="",
        help="Path to output file. Default: Log_corrected/<input_stem>_corrected.jsonl",
    )
    ap.add_argument(
        "--format",
        choices=["jsonl", "json"],
        default="jsonl",
        help="Output format (default: jsonl)",
    )
    ap.add_argument(
        "--o2sol-model",
        choices=["auto", "weiss1970", "gsw"],
        default="auto",
        help=(
            "O2 solubility model. 'auto' uses TEOS-10/GSW (Garcia & Gordon) if available, "
            "otherwise Weiss (1970)."
        ),
    )
    ap.add_argument(
        "--baro-kpa",
        type=float,
        default=None,
        help="Barometric pressure in kPa to scale O2 solubility (optional)",
    )
    ap.add_argument(
        "--air-pressure-kpa",
        type=float,
        default=None,
        help="Absolute air baseline pressure in kPa for sea-pressure/depth conversion (optional)",
    )
    ap.add_argument(
        "--match-window-s",
        type=float,
        default=2.0,
        help="Max time difference (seconds) when matching salinity/pressure across sensors (default: 2.0)",
    )
    args = ap.parse_args()

    in_path = Path(args.log)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    repo_root = Path(__file__).resolve().parents[2]
    default_out_dir = repo_root / "Log_corrected"
    default_out_name = in_path.stem + "_corrected" + (".jsonl" if args.format == "jsonl" else ".json")
    out_path = Path(args.out) if args.out else (default_out_dir / default_out_name)

    ctx = Context()

    # Load all records so we can process in timestamp order.
    raw_records = list(iter_records(in_path))

    # Build time series for cross-sensor matching.
    pressure_points: list[tuple[datetime, float]] = []  # absolute pressure (kPa)
    for rec in raw_records:
        ts_s = rec.get("timestamp")
        measurements = rec.get("measurements")
        if not isinstance(ts_s, str) or not isinstance(measurements, dict):
            continue
        st = infer_sensor_type(measurements, str(rec.get("name", "")))
        if st != "pressure":
            continue
        abs_kpa = to_float(measurements.get("Pressure")) or to_float(measurements.get("Value1"))
        if abs_kpa is None:
            continue
        try:
            ts = parse_iso_dt(ts_s)
        except Exception:
            continue
        pressure_points.append((ts, float(abs_kpa)))
    pressure_points.sort(key=lambda x: x[0])

    def nearest_point(points: list[tuple[datetime, float]], ts: datetime, window_s: float) -> Optional[float]:
        if not points:
            return None
        times = [p[0] for p in points]
        i = bisect_left(times, ts)
        best: Optional[tuple[float, float]] = None  # (abs_dt_s, value)
        if i < len(points):
            dt_s = abs((points[i][0] - ts).total_seconds())
            best = (dt_s, points[i][1])
        if i > 0:
            dt_s = abs((points[i - 1][0] - ts).total_seconds())
            if best is None or dt_s < best[0]:
                best = (dt_s, points[i - 1][1])
        if best is None:
            return None
        if window_s is not None and window_s >= 0 and best[0] > float(window_s):
            return None
        return float(best[1])

    salinity_points: list[tuple[datetime, float]] = []
    for rec in raw_records:
        ts_s = rec.get("timestamp")
        measurements = rec.get("measurements")
        if not isinstance(ts_s, str) or not isinstance(measurements, dict):
            continue
        st = infer_sensor_type(measurements, str(rec.get("name", "")))
        if st != "conductivity":
            continue
        try:
            ts = parse_iso_dt(ts_s)
        except Exception:
            continue

        sal = to_float(measurements.get("Salinity"))
        if sal is None:
            sal = to_float(measurements.get("Derived_Salinity_psu"))

        if sal is None:
            cond = to_float(measurements.get("Conductivity")) or to_float(measurements.get("Value1"))
            t_c = to_float(measurements.get("Temperature")) or to_float(measurements.get("Value2"))
            if cond is not None and t_c is not None:
                abs_kpa = nearest_point(pressure_points, ts, float(args.match_window_s))
                p_dbar = pressure_kpa_to_dbar(abs_kpa) if abs_kpa is not None else 0.0
                sal = pss78_salinity_from_conductivity_ms_cm(cond, t_c, p_dbar)

        if sal is not None:
            salinity_points.append((ts, float(sal)))
    salinity_points.sort(key=lambda x: x[0])

    # We keep the original record order for the output, but process in a
    # time-ordered pass so cross-sensor context is available.
    def priority_for(st: str) -> int:
        # For same timestamp, ensure context is available before oxygen.
        if st == "conductivity":
            return 0
        if st == "pressure":
            return 1
        if st == "oxygen":
            return 2
        return 3

    order: list[tuple[datetime, int, int]] = []
    for idx, rec in enumerate(raw_records):
        ts_s = rec.get("timestamp")
        measurements = rec.get("measurements")
        if not isinstance(ts_s, str) or not isinstance(measurements, dict):
            # Put malformed records at the end; we will copy them through.
            order.append((datetime.min, 3, idx))
            continue
        ts = parse_iso_dt(ts_s)
        st = infer_sensor_type(measurements, str(rec.get("name", "")))
        order.append((ts, priority_for(st), idx))

    order.sort(key=lambda t: (t[0], t[1], t[2]))

    # Pre-fill output with original objects; we will replace processed items.
    records_out: list[dict[str, Any]] = list(raw_records)

    # Stats
    n_total = len(raw_records)
    n_o2 = 0
    n_o2_with_sal = 0
    n_cond = 0
    n_pressure = 0

    for ts, _prio, idx in order:
        rec = raw_records[idx]

        ts_s = rec.get("timestamp")
        measurements = rec.get("measurements")
        if not isinstance(ts_s, str) or not isinstance(measurements, dict):
            continue

        name = str(rec.get("name", ""))
        st = infer_sensor_type(measurements, name)

        # Work on a shallow copy of the record to avoid mutating the input object.
        rec2 = dict(rec)
        meas2 = dict(measurements)
        rec2["measurements"] = meas2

        if st == "pressure":
            n_pressure += 1
            abs_kpa = to_float(meas2.get("Pressure")) or to_float(meas2.get("Value1"))
            if abs_kpa is not None:
                ctx.latest_abs_pressure_kpa = abs_kpa
                ctx.latest_pressure_at = ts

                p_dbar = pressure_kpa_to_dbar(abs_kpa)
                meas2["Reproc_Pressure_dbar"] = f"{p_dbar:.3f} dbar"

                base_kpa = args.air_pressure_kpa
                if base_kpa is None:
                    base_kpa = to_float(meas2.get("Derived_PressureAir_kPa"))

                if base_kpa is not None and math.isfinite(base_kpa):
                    sea_dbar = pressure_kpa_to_dbar(abs_kpa - float(base_kpa))
                    meas2["Reproc_PressureAir_kPa"] = f"{float(base_kpa):.3f} kPa"
                    meas2["Reproc_SeaPressure_dbar"] = f"{sea_dbar:.3f} dbar"
                    meas2["Reproc_Depth_m"] = f"{sea_dbar:.3f} m"

        elif st == "conductivity":
            n_cond += 1
            cond = to_float(meas2.get("Conductivity")) or to_float(meas2.get("Value1"))
            t_c = to_float(meas2.get("Temperature")) or to_float(meas2.get("Value2"))

            # Prefer the sensor/GUI value if present; else compute with best-effort pressure.
            sal = to_float(meas2.get("Salinity")) or to_float(meas2.get("Derived_Salinity_psu"))
            if sal is None and cond is not None and t_c is not None:
                abs_kpa = nearest_point(pressure_points, ts, float(args.match_window_s))
                p_dbar = pressure_kpa_to_dbar(abs_kpa) if abs_kpa is not None else 0.0
                sal = pss78_salinity_from_conductivity_ms_cm(cond, t_c, p_dbar)

            if sal is not None:
                ctx.latest_sal_psu = float(sal)
                ctx.latest_sal_at = ts
                meas2["Reproc_Salinity_psu"] = f"{float(sal):.3f}"

        elif st == "oxygen":
            n_o2 += 1

            temp_c = to_float(meas2.get("Temperature")) or to_float(meas2.get("Value3"))
            sat_pct = to_float(meas2.get("O2Saturation")) or to_float(meas2.get("Value2"))
            conc_umol_l = to_float(meas2.get("O2Concentration")) or to_float(meas2.get("Value1"))

            sal_used = nearest_point(salinity_points, ts, float(args.match_window_s))
            assumed_sal = sal_used is None
            if sal_used is None:
                sal_used = 0.0

            if temp_c is not None:
                try:
                    o2sol_1atm, o2sol_model_used = o2_sol_umol_per_l(
                        temp_c,
                        float(sal_used),
                        model=str(args.o2sol_model),
                    )
                    if o2sol_1atm is None:
                        raise ValueError("O2 solubility unavailable")
                    o2sol = scale_o2_solubility_for_pressure(o2sol_1atm, args.baro_kpa)

                    meas2["Reproc_O2Sol_umolL"] = f"{o2sol:.2f}"
                    meas2["Reproc_O2Sol_model_used"] = o2sol_model_used
                    meas2["Reproc_Salinity_psu_used"] = f"{float(sal_used):.3f}"
                    if assumed_sal:
                        meas2["Reproc_Salinity_assumed"] = "True"

                    if args.baro_kpa is not None:
                        meas2["Reproc_Baro_kPa_used"] = f"{float(args.baro_kpa):.2f}"

                    if sat_pct is not None:
                        o2_umol_l = (sat_pct / 100.0) * o2sol
                        meas2["Reproc_O2_umolL_from_sat"] = f"{o2_umol_l:.2f}"
                        meas2["Reproc_O2_mgL_from_sat"] = f"{o2_umol_l_to_mg_l(o2_umol_l):.3f}"

                    if conc_umol_l is not None and o2sol > 0:
                        meas2["Reproc_O2Sat_pct_from_conc"] = f"{(100.0 * conc_umol_l / o2sol):.2f}"

                    if not assumed_sal:
                        n_o2_with_sal += 1
                except Exception:
                    pass

        records_out[idx] = rec2

    write_records(out_path, records_out, as_jsonl=(args.format == "jsonl"))

    # Basic summary next to output.
    summary = {
        "input": str(in_path.as_posix()),
        "output": str(out_path.as_posix()),
        "records_total": n_total,
        "records_oxygen": n_o2,
        "records_conductivity": n_cond,
        "records_pressure": n_pressure,
        "oxygen_records_with_measured_salinity": n_o2_with_sal,
        "oxygen_records_with_assumed_salinity": max(0, n_o2 - n_o2_with_sal),
        "baro_kpa_used": args.baro_kpa,
        "air_pressure_kpa_used": args.air_pressure_kpa,
        "o2sol_model_requested": args.o2sol_model,
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {out_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
