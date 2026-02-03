"""Plot oxygen vs time from an Anderaa jsonl log, annotate events, and compute slopes.

Usage (PowerShell):
  python src/analysis/plot_o2_experiment.py --log Log/aanderaa_log_20260120_144905.jsonl

    # With external events (recommended for new experiments)
    python src/analysis/plot_o2_experiment.py --log Log/aanderaa_log_20260126_142957.jsonl \
        --events documentation/experiment_notes/2026-01-26_Test2_degazing_tank_mix_events.json \
        --summary

Outputs:
  documentation/experiment_notes/plots/<derived-name>.png
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


@dataclass(frozen=True)
class Event:
    time_hhmm: str
    label: str
    flow_lpm: Optional[float] = None


def load_events(events_path: Path) -> list[Event]:
    """Load events from JSON.

    Supported formats:
      - a JSON array of objects: [{"time": "15:12", "label": "Set helium", "flow_lpm": 1.0}, ...]
      - a JSON object with an "events" key containing such an array.
    """
    raw = json.loads(events_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("events"), list):
        raw_events = raw["events"]
    elif isinstance(raw, list):
        raw_events = raw
    else:
        raise ValueError("Events JSON must be an array, or an object with an 'events' array")

    events: list[Event] = []
    for idx, item in enumerate(raw_events):
        if not isinstance(item, dict):
            raise ValueError(f"Event #{idx} must be an object")

        time_val = item.get("time") or item.get("time_hhmm")
        label = item.get("label")
        if not isinstance(time_val, str) or not isinstance(label, str):
            raise ValueError(f"Event #{idx} must include string fields 'time' (or 'time_hhmm') and 'label'")

        flow_lpm = try_float(item.get("flow_lpm"))
        events.append(Event(time_val, label, flow_lpm))

    return events


def parse_iso_dt(value: str) -> datetime:
    # Example: 2026-01-20T14:49:06.573327
    return datetime.fromisoformat(value)


def try_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Handle "89.44 %" and similar.
        for suffix in ("%", "µmol/L", "°C", "mS/cm", "kPa", "dbar", "m"):
            s = s.replace(suffix, "")
        s = s.strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def iter_o2_saturation_points(log_path: Path) -> Iterable[tuple[datetime, float]]:
    """Yield (timestamp, O2Sat_pct) points from the 4330 sensor lines."""
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            measurements = rec.get("measurements") or {}
            if not isinstance(measurements, dict):
                continue

            # Prefer derived oxygen saturation if present, else O2Saturation, else Value2.
            o2_pct = (
                try_float(measurements.get("Derived_O2Sat_pct_from_conc"))
                or try_float(measurements.get("O2Saturation"))
                or try_float(measurements.get("Value2"))
            )

            product = str(measurements.get("ProductNumber", ""))
            name = str(rec.get("name", ""))

            # Guard to avoid accidentally using non-O2 sensors that also have "Value2".
            is_o2_sensor = (product == "4330") or ("4330" in name)
            if not is_o2_sensor:
                continue

            ts = rec.get("timestamp")
            if not isinstance(ts, str):
                continue

            dt = parse_iso_dt(ts)
            if o2_pct is None or math.isnan(o2_pct):
                continue

            yield dt, float(o2_pct)


def linear_slope_per_minute(times: list[datetime], values: list[float]) -> Optional[tuple[float, float]]:
    """Return (slope_%_per_min, r2)."""
    if len(times) < 2:
        return None

    t0 = times[0]
    x = [(t - t0).total_seconds() / 60.0 for t in times]
    y = values

    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)

    sxx = sum((xi - x_mean) ** 2 for xi in x)
    if sxx == 0:
        return None

    sxy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean

    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else float("nan")

    return slope, r2


def parse_hhmm_on_date(date_ref: datetime, hhmm: str) -> datetime:
    hhmm = hhmm.strip().replace("_", ":")
    parts = hhmm.split(":")
    if len(parts) == 2:
        hh, mm = parts
        ss = "00"
    elif len(parts) == 3:
        hh, mm, ss = parts
    else:
        raise ValueError(f"Invalid time: {hhmm!r}")

    return date_ref.replace(hour=int(hh), minute=int(mm), second=int(ss), microsecond=0)


def compute_segment(
    *,
    times: list[datetime],
    values: list[float],
    start: datetime,
    end: datetime,
    label: str,
    flow_lpm: Optional[float],
    target_o2_pct: float = 0.0,
    ignore_first_mins: float = 0.0,
) -> Optional[dict[str, object]]:
    start_fit = start
    if ignore_first_mins and ignore_first_mins > 0:
        start_fit = start + timedelta(minutes=float(ignore_first_mins))

    seg_times = [t for t in times if (t >= start_fit and t < end)]
    seg_vals = [v for t, v in zip(times, values) if (t >= start_fit and t < end)]

    fit = linear_slope_per_minute(seg_times, seg_vals)
    if fit is None:
        return None
    slope_per_min, r2 = fit
    eff = (-slope_per_min) / flow_lpm if flow_lpm else None

    start_o2 = seg_vals[0] if seg_vals else None
    end_o2 = seg_vals[-1] if seg_vals else None
    duration_min = (end - start_fit).total_seconds() / 60.0

    time_to_target_min: Optional[float] = None
    he_volume_L: Optional[float] = None
    if start_o2 is not None:
        if start_o2 <= target_o2_pct:
            time_to_target_min = 0.0
        elif slope_per_min < 0:
            time_to_target_min = (start_o2 - target_o2_pct) / (-slope_per_min)

    if time_to_target_min is not None and flow_lpm is not None and flow_lpm > 0:
        he_volume_L = flow_lpm * time_to_target_min

    return {
        "label": label,
        "start": start,
        "end": end,
        "start_fit": start_fit,
        "flow_lpm": flow_lpm,
        "start_o2_pct": start_o2,
        "end_o2_pct": end_o2,
        "duration_min": duration_min,
        "slope_pct_per_min": slope_per_min,
        "r2": r2,
        "eff_pct_per_L": eff,
        "target_o2_pct": float(target_o2_pct),
        "time_to_target_min": time_to_target_min,
        "he_volume_L": he_volume_L,
        "n": len(seg_times),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out: dict[str, Any] = {}
            for k in fieldnames:
                v = row.get(k)
                if isinstance(v, datetime):
                    out[k] = v.isoformat(timespec="seconds")
                else:
                    out[k] = v
            writer.writerow(out)


def save_table_png(*, path: Path, title: str, col_labels: list[str], cell_text: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, max(2.5, 0.35 * (len(cell_text) + 2))), dpi=200)
    ax.axis("off")
    ax.set_title(title, fontsize=12, pad=12)
    table = ax.table(cellText=cell_text, colLabels=col_labels, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.25)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot O2 saturation vs time from Anderaa jsonl logs")
    parser.add_argument("--log", type=Path, required=True, help="Path to *.jsonl log file")
    parser.add_argument(
        "--events",
        type=Path,
        default=None,
        help="Optional JSON file containing events (time/label/flow_lpm). When provided, flow is treated as state across intervals.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PNG path (default: documentation/experiment_notes/plots/<logstem>_O2Sat.png)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Also write CSV summaries and a printable table PNG (recommended when using --events)",
    )
    parser.add_argument(
        "--target-o2",
        type=float,
        default=0.0,
        help="Target O2 saturation (%) for time/volume extrapolation (default: 0)",
    )
    parser.add_argument(
        "--ignore-first-mins",
        type=float,
        default=0.0,
        help="Ignore the first N minutes of each segment when fitting slope (default: 0)",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Optional plot title override",
    )
    parser.add_argument("--no-show", action="store_true", help="Do not open a window (just save PNG)")
    args = parser.parse_args()

    log_path: Path = args.log
    if not log_path.exists():
        raise FileNotFoundError(str(log_path))

    points = sorted(iter_o2_saturation_points(log_path), key=lambda p: p[0])
    if not points:
        raise RuntimeError("No O2 saturation points found in log (expected ProductNumber=4330)")

    times = [t for t, _ in points]
    o2 = [v for _, v in points]

    date_ref = times[0]

    if args.events is not None:
        events = load_events(args.events)
    else:
        # Default: Test 1 hard-coded events
        events = [
            Event("14:50:00", "Experiment started / recording"),
            Event("14:55", "Started helium"),
            Event("14:58", "Moved inlet; diffuser broke; replaced"),
            Event("15:03", "Back to normal; set helium", flow_lpm=1.0),
            Event("15:09", "Set helium", flow_lpm=0.5),
            Event("15:11", "Set helium", flow_lpm=2.0),
            Event("15:13", "Set helium", flow_lpm=1.0),
            Event("15:17", "Closed tank (tap)"),
            Event("15:48", "Opened tank"),
            Event("15:49", "Sensors out of water"),
            Event("15:53", "Pump to other tank; switch sensors"),
        ]

    event_times: list[tuple[datetime, Event]] = []
    for e in events:
        try:
            et = parse_hhmm_on_date(date_ref, e.time_hhmm)
        except ValueError:
            continue
        event_times.append((et, e))

    # Compute slopes for:
    # - default mode: intervals that start with a known flow + requested special interval
    # - events mode (--events): flow is treated as a persistent state across intervals
    slope_rows: list[dict[str, object]] = []

    if args.events is not None:
        flow_state: Optional[float] = None
        for (t_start, e_start), (t_end, _e_end) in zip(event_times, event_times[1:]):
            if e_start.flow_lpm is not None:
                flow_state = e_start.flow_lpm

            row = compute_segment(
                times=times,
                values=o2,
                start=t_start,
                end=t_end,
                label=f"{e_start.label}",
                flow_lpm=flow_state,
                target_o2_pct=float(args.target_o2),
                ignore_first_mins=float(args.ignore_first_mins),
            )
            if row is not None:
                slope_rows.append(row)
    else:
        for (t_start, e_start), (t_end, _e_end) in zip(event_times, event_times[1:]):
            if e_start.flow_lpm is None:
                continue
            row = compute_segment(
                times=times,
                values=o2,
                start=t_start,
                end=t_end,
                label=f"{e_start.label}",
                flow_lpm=e_start.flow_lpm,
                target_o2_pct=float(args.target_o2),
                ignore_first_mins=float(args.ignore_first_mins),
            )
            if row is not None:
                slope_rows.append(row)

        # Requested: closed tank period 15:17 -> 15:48
        t_closed = parse_hhmm_on_date(date_ref, "15:17")
        t_opened = parse_hhmm_on_date(date_ref, "15:48")
        row = compute_segment(
            times=times,
            values=o2,
            start=t_closed,
            end=t_opened,
            label="Closed tank (tap)",
            flow_lpm=None,
            target_o2_pct=float(args.target_o2),
            ignore_first_mins=float(args.ignore_first_mins),
        )
        if row is not None:
            slope_rows.append(row)

    # ---- Plot ----
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)

    ax.plot(times, o2, lw=1.6, color="#1f77b4", label="O2 saturation (%)")

    # Event markers
    for et, e in event_times:
        ax.axvline(et, color="0.35", lw=0.8, alpha=0.5)
        txt = e.label
        if e.flow_lpm is not None:
            txt += f" (flow={e.flow_lpm:g} L/min)"
        ax.annotate(
            txt,
            xy=(et, ax.get_ylim()[0]),
            xycoords=("data", "data"),
            xytext=(5, 10),
            textcoords="offset points",
            rotation=90,
            va="bottom",
            ha="left",
            fontsize=8,
            color="0.2",
        )

    if args.title:
        ax.set_title(args.title)
    elif args.events is not None:
        ax.set_title(f"Oxygen saturation vs time ({log_path.stem})")
    else:
        ax.set_title("Test 1 — Degazing tank: Oxygen saturation vs time")
    ax.set_xlabel("Time")
    ax.set_ylabel("O2 saturation (%)")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=10))
    fig.autofmt_xdate()

    # Put slope summary on plot (top-left)
    if slope_rows:
        lines: list[str] = ["Slopes (%/min):"]
        for row in slope_rows:
            t0 = row["start"].strftime("%H:%M")
            t1 = row["end"].strftime("%H:%M")
            label = row.get("label")
            flow = row["flow_lpm"]
            slope = row["slope_pct_per_min"]
            eff = row["eff_pct_per_L"]
            n = row["n"]
            if flow is None:
                lines.append(f"{t0}-{t1}: {slope:+.4f}  (n={n}, {label})")
            else:
                lines.append(
                    f"{t0}-{t1} @ {flow:g} L/min: {slope:+.4f}  (n={n}, eff={eff:.4f} %/L, {label})"
                )
        ax.text(
            0.01,
            0.99,
            "\n".join(lines),
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8, edgecolor="0.8"),
        )

    out_path = args.out
    if out_path is None:
        out_path = Path("documentation") / "experiment_notes" / "plots" / f"{log_path.stem}_O2Sat.png"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")

    print(f"Saved plot: {out_path}")

    # ---- Summaries ----
    if args.summary or args.events is not None:
        base = out_path.with_suffix("")
        segments_csv = base.parent / f"{base.name}_segments.csv"
        flows_csv = base.parent / f"{base.name}_flow_summary.csv"
        table_png = base.parent / f"{base.name}_flow_summary.png"

        # Per-segment export
        seg_fields = [
            "label",
            "start",
            "end",
            "start_fit",
            "flow_lpm",
            "duration_min",
            "start_o2_pct",
            "end_o2_pct",
            "slope_pct_per_min",
            "r2",
            "eff_pct_per_L",
            "target_o2_pct",
            "time_to_target_min",
            "he_volume_L",
            "n",
        ]
        write_csv(segments_csv, slope_rows, seg_fields)

        # Per-flow aggregation
        flow_rows = [r for r in slope_rows if isinstance(r.get("flow_lpm"), (int, float)) and float(r["flow_lpm"]) > 0]
        grouped: dict[float, list[dict[str, Any]]] = {}
        for r in flow_rows:
            flow = float(r["flow_lpm"])  # type: ignore[arg-type]
            grouped.setdefault(flow, []).append(r)

        flow_summary: list[dict[str, Any]] = []
        for flow, rows in sorted(grouped.items()):
            slopes = [float(r["slope_pct_per_min"]) for r in rows if r.get("slope_pct_per_min") is not None]
            effs = [float(r["eff_pct_per_L"]) for r in rows if r.get("eff_pct_per_L") is not None]
            ttargets = [float(r["time_to_target_min"]) for r in rows if r.get("time_to_target_min") is not None]
            vols = [float(r["he_volume_L"]) for r in rows if r.get("he_volume_L") is not None]
            r2s = [float(r["r2"]) for r in rows if r.get("r2") is not None]

            def mean(xs: list[float]) -> Optional[float]:
                return sum(xs) / len(xs) if xs else None

            flow_summary.append(
                {
                    "flow_lpm": flow,
                    "n_segments": len(rows),
                    "slope_pct_per_min_mean": mean(slopes),
                    "r2_mean": mean(r2s),
                    "eff_pct_per_L_mean": mean(effs),
                    "time_to_target_min_mean": mean(ttargets),
                    "he_volume_L_mean": mean(vols),
                }
            )

        flow_fields = [
            "flow_lpm",
            "n_segments",
            "slope_pct_per_min_mean",
            "r2_mean",
            "eff_pct_per_L_mean",
            "time_to_target_min_mean",
            "he_volume_L_mean",
        ]
        write_csv(flows_csv, flow_summary, flow_fields)

        # Printable table (per-flow)
        col_labels = [
            "Flow (L/min)",
            "Segs",
            "Slope mean (%/min)",
            "R² mean",
            "Eff mean (%/L)",
            f"Time to {args.target_o2:g}% (min)",
            "He vol (L)",
        ]
        cell_text: list[list[str]] = []
        for r in flow_summary:
            slope = r.get("slope_pct_per_min_mean")
            r2 = r.get("r2_mean")
            eff = r.get("eff_pct_per_L_mean")
            ttarget = r.get("time_to_target_min_mean")
            vol = r.get("he_volume_L_mean")
            cell_text.append(
                [
                    f"{r['flow_lpm']:.3g}",
                    f"{r['n_segments']}",
                    f"{slope:+.4f}" if slope is not None else "n/a",
                    f"{r2:.3f}" if r2 is not None else "n/a",
                    f"{eff:.4f}" if eff is not None else "n/a",
                    f"{ttarget:.1f}" if ttarget is not None else "n/a",
                    f"{vol:.1f}" if vol is not None else "n/a",
                ]
            )

        save_table_png(
            path=table_png,
            title=f"Degassing summary ({log_path.stem}) — extrapolated to {args.target_o2:g}%",
            col_labels=col_labels,
            cell_text=cell_text,
        )

        print(f"Saved segment CSV: {segments_csv}")
        print(f"Saved flow summary CSV: {flows_csv}")
        print(f"Saved printable table: {table_png}")

    if slope_rows:
        print("\nSlope summary (negative means decreasing O2):")
        for row in slope_rows:
            label = row.get("label")
            flow = row.get("flow_lpm")
            eff = row.get("eff_pct_per_L")
            eff_str = f"{eff:.6f} %/L" if eff is not None else "n/a"
            print(
                f"  {row['start'].isoformat(timespec='seconds')} -> {row['end'].isoformat(timespec='seconds')}: "
                f"flow={flow if flow is not None else 'n/a'} L/min, slope={row['slope_pct_per_min']:+.6f} %/min, "
                f"R^2={row['r2']:.3f}, eff={eff_str}, n={row['n']}"
                + (f", label={label}" if label else "")
            )

        # Best (highest O2 decrease per L) among segments with a known flow.
        eff_rows = [r for r in slope_rows if r.get("eff_pct_per_L") is not None]
        if eff_rows:
            best = max(eff_rows, key=lambda r: float(r["eff_pct_per_L"]))
            print(
                "\nBest efficiency (highest O2 decrease per L of He): "
                f"{best['start'].strftime('%H:%M')}-{best['end'].strftime('%H:%M')} "
                f"@ {best['flow_lpm']} L/min, eff={best['eff_pct_per_L']:.6f} %/L"
            )

    if not args.no_show:
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
