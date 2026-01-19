from __future__ import annotations

import queue
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports

import numpy as np

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from aanderaa_sensor_reader_custom import AanderaaSensorCustom, SensorEvent, _reader_loop
from config_manager import load_sensors, save_sensors_to_user_config, load_state, save_state
from configure_streaming_mode import SensorTerminalSession
from set_interval import configure_sensor_interval


_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _o2_umol_l_to_mg_l(o2_umol_l: float) -> float:
    """Convert dissolved O2 from µmol/L to mg/L.

    Uses molar mass of O2 = 31.998 g/mol.
    """
    return float(o2_umol_l) * 0.031998


def _conductivity_ms_cm_to_uS_cm(conductivity_ms_cm: float) -> float:
    """Convert conductivity from mS/cm to µS/cm."""
    return float(conductivity_ms_cm) * 1000.0


def _o2_sol_umol_per_l_weiss1970(temp_c: float, sal_psu: float) -> float:
    """O2 solubility in seawater at 1 atm (air-saturated), Weiss (1970).

    Returns oxygen solubility in µmol/L.
    """
    # Weiss 1970 uses T in Kelvin and returns concentration in ml/L.
    T = float(temp_c) + 273.15
    S = float(sal_psu)

    # Coefficients for O2
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
        + A3 * (float(np.log(Ts)))
        + A4 * Ts
        + S * (B1 + B2 * Ts + B3 * (Ts**2))
    )

    c_ml_per_l = float(np.exp(lnC))
    # 1 ml O2 (STP) = 44.6596 µmol
    return c_ml_per_l * 44.6596


def _pressure_to_dbar(pressure_kpa: float) -> float:
    """Convert absolute pressure from kPa to dbar.

    The 4117/4117R family reports pressure in kPa (see TD302 Table 2-1).
    1 dbar = 10 kPa.
    """
    return float(pressure_kpa) / 10.0


def _scale_o2_solubility_for_pressure(o2sol_umol_l_at_1atm: float, baro_kpa: Optional[float]) -> float:
    """Scale air-saturation O2 solubility for non-standard barometric pressure.

    The Weiss (1970) computation here returns an air-saturated reference at ~1 atm.
    As a practical approximation, scale linearly by total pressure ratio.
    """
    if baro_kpa is None or not np.isfinite(baro_kpa) or baro_kpa <= 0:
        return float(o2sol_umol_l_at_1atm)
    return float(o2sol_umol_l_at_1atm) * (float(baro_kpa) / 101.325)


def _pss78_salinity_from_conductivity_ms_cm(
    conductivity_ms_cm: float,
    temp_c: float,
    pressure_dbar: float = 0.0,
) -> Optional[float]:
    """Practical Salinity (PSS-78) from conductivity (mS/cm), temperature (°C), pressure (dbar).

    For typical tank/surface work, pressure effects are small; this uses the
    standard PSS-78 polynomial with an optional (best-effort) pressure correction.
    """
    C = float(conductivity_ms_cm)
    if not np.isfinite(C) or C <= 0:
        return None

    T = float(temp_c)
    P = float(pressure_dbar)

    # Conductivity ratio relative to C(35, 15, 0)
    C35150 = 42.914
    R = C / C35150
    if not np.isfinite(R) or R <= 0:
        return None

    # Temperature function for Rt at S=35, P=0 (UNESCO 1983 / PSS-78)
    rt35 = 0.6766097 + 0.0200564 * T + 0.0001104259 * T**2 + (-6.9698e-7) * T**3 + 1.0031e-9 * T**4

    # Pressure correction factor Rp (best-effort; negligible at low P).
    # This form is widely used in seawater toolboxes.
    if P != 0.0 and np.isfinite(P):
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
    if not np.isfinite(Rt) or Rt <= 0:
        return None

    sqrtRt = float(np.sqrt(Rt))

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

    # Base salinity at T=15
    S = a0 + (a1 * sqrtRt) + (a2 * Rt) + (a3 * Rt * sqrtRt) + (a4 * Rt**2) + (a5 * Rt**2 * sqrtRt)

    # Temperature correction
    dT = (T - 15.0) / (1.0 + 0.0162 * (T - 15.0))
    S += dT * (b0 + (b1 * sqrtRt) + (b2 * Rt) + (b3 * Rt * sqrtRt) + (b4 * Rt**2) + (b5 * Rt**2 * sqrtRt))

    if not np.isfinite(S):
        return None
    # Practical salinity is typically reported between 0 and ~42.
    return float(S)


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    m = _FLOAT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _format_plain_number(value: float, max_decimals: int = 6) -> str:
    """Format a float without scientific notation.

    Uses fixed-point formatting and trims trailing zeros.
    """
    text = f"{float(value):.{int(max_decimals)}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    # Avoid '-0'
    return "0" if text in {"-0", "-0.0"} else text


def _primary_key_for(sensor_type: str) -> str:
    st = (sensor_type or "").lower()
    if st == "oxygen":
        return "O2Concentration"
    if st == "conductivity":
        return "Conductivity"
    if st == "pressure":
        return "Pressure"
    return "Value1"


def _infer_sensor_type_from_product(product: str) -> str:
    p = (product or "").upper()
    if p.startswith("4117") or p.startswith("5217") or p.startswith("5218"):
        return "pressure"
    if p.startswith("4330") or p.startswith("4835") or p.startswith("4831"):
        return "oxygen"
    if p.startswith("5819") or p.startswith("5990"):
        return "conductivity"
    return "unknown"


@dataclass
class Series:
    t: List[datetime]
    y: List[float]


class AanderaaGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Aanderaa Reader")
        self.geometry("1100x720")

        self._stop_event = threading.Event()
        self._event_queue: "queue.Queue[SensorEvent]" = queue.Queue()
        self._threads: List[threading.Thread] = []
        self._sensors: List[AanderaaSensorCustom] = []

        # Store multiple series per sensor (COM port + key) so plots can switch
        # between raw and derived variables without losing history.
        self._series: Dict[Tuple[str, str], Series] = {}
        self._max_points = 600
        self._interval_var = tk.DoubleVar(value=5.0)
        self._auto_apply_interval_var = tk.BooleanVar(value=False)
        self._oxygen_plot_var = tk.StringVar(value="O2 (derived mg/L)")
        self._time_window_var = tk.StringVar(value="Last 10 min")
        self._use_baro_var = tk.BooleanVar(value=False)
        # User entry in hPa (common weather units). Empty/disabled means "assume 1 atm".
        self._baro_hpa_var = tk.StringVar(value="")
        self._plot_dirty = False
        self._stream_started_at: Optional[float] = None
        self._last_event_at: Optional[float] = None

        # Keep latest cross-sensor context for derived values.
        self._latest_salinity_psu: Optional[float] = None
        self._latest_salinity_at: Optional[datetime] = None
        self._latest_pressure: Optional[float] = None
        self._latest_pressure_at: Optional[datetime] = None
        self._latest_pressure_kpa_by_port: Dict[str, float] = {}
        self._pressure_sensor_id_by_port: Dict[str, str] = {}

        # Persisted: baseline absolute pressure (kPa) measured with sensor in air.
        # Keyed by sensor id (e.g. '4117B_SN_2378').
        state = load_state()
        baselines = state.get("pressure_air_kpa_by_sensor", {}) if isinstance(state, dict) else {}
        self._pressure_air_kpa_by_sensor: Dict[str, float] = {}
        if isinstance(baselines, dict):
            for k, v in baselines.items():
                try:
                    fv = float(v)
                except Exception:
                    continue
                if np.isfinite(fv) and fv > 0:
                    self._pressure_air_kpa_by_sensor[str(k)] = fv

        self._is_recording = False
        self._record_fp: Optional[object] = None
        self._record_path: Optional[Path] = None
        self._record_lines = 0

        self._build_ui()
        self._load_config_to_table()
        self.after(300, self._drain_events)
        self.after(500, self._plot_tick)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=10)
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(2, weight=1)

        ttk.Label(top, text="Sensors").grid(row=0, column=0, sticky="w")

        btns = ttk.Frame(top)
        btns.grid(row=0, column=1, sticky="w", padx=(10, 0))

        ttk.Button(btns, text="Scan + Identify", command=self._scan_and_identify).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="Connect", command=self._connect_sensors).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(btns, text="Start Streaming", command=self._start_streaming).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(btns, text="Stop", command=self._stop_streaming).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(btns, text="Disconnect", command=self._disconnect_sensors).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(btns, text="Save Config", command=self._save_config).grid(row=0, column=5)

        self._record_btn = ttk.Button(btns, text="Start Recording", command=self._toggle_recording)
        self._record_btn.grid(row=0, column=6, padx=(10, 0))

        # Interval configuration controls
        interval_frame = ttk.LabelFrame(top, text="Sampling Interval", padding=5)
        interval_frame.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Label(interval_frame, text="Interval (seconds):").grid(row=0, column=0, padx=(0, 5))
        interval_spin = ttk.Spinbox(
            interval_frame,
            from_=1,
            to=300,
            increment=1,
            textvariable=self._interval_var,
            width=10
        )
        interval_spin.grid(row=0, column=1, padx=(0, 10))
        ttk.Button(
            interval_frame,
            text="Apply to All Sensors",
            command=self._configure_interval
        ).grid(row=0, column=2, padx=(0, 5))

        ttk.Checkbutton(
            interval_frame,
            text="Auto-apply on Connect",
            variable=self._auto_apply_interval_var,
        ).grid(row=0, column=3, padx=(10, 0))

        ttk.Label(
            interval_frame,
            text="(Changes sensor sampling rate. Requires bidirectional cable.)",
            font=("TkDefaultFont", 8)
        ).grid(row=0, column=4, padx=(10, 0))

        # Barometric pressure (optional) for oxygen calculations.
        baro_frame = ttk.LabelFrame(top, text="Oxygen calculation", padding=5)
        baro_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Checkbutton(
            baro_frame,
            text="Use barometric pressure",
            variable=self._use_baro_var,
            command=self._mark_plot_dirty,
        ).grid(row=0, column=0, padx=(0, 10))

        ttk.Label(baro_frame, text="Baro (hPa):").grid(row=0, column=1, padx=(0, 5))
        baro_entry = ttk.Entry(baro_frame, textvariable=self._baro_hpa_var, width=10)
        baro_entry.grid(row=0, column=2, padx=(0, 10))
        baro_entry.bind("<KeyRelease>", lambda _e: self._mark_plot_dirty())

        ttk.Label(
            baro_frame,
            text="(Optional. If enabled, scales O₂ solubility by P/1013.25.)",
            font=("TkDefaultFont", 8),
        ).grid(row=0, column=3, padx=(0, 5))

        # Pressure baseline (optional) for gauge/sea-pressure display.
        pressure_frame = ttk.LabelFrame(top, text="Pressure", padding=5)
        pressure_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

        ttk.Button(
            pressure_frame,
            text="Tutorial + Set Air Baseline",
            command=self._tutorial_and_set_pressure_baseline,
        ).grid(row=0, column=0, padx=(0, 10))

        ttk.Button(
            pressure_frame,
            text="Clear Baseline",
            command=self._clear_pressure_baseline,
        ).grid(row=0, column=1, padx=(0, 10))

        ttk.Label(
            pressure_frame,
            text="(Stores atmospheric pressure so you can view water pressure relative to air.)",
            font=("TkDefaultFont", 8),
        ).grid(row=0, column=2, padx=(0, 5))

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(top, textvariable=self._status_var).grid(row=0, column=2, sticky="e")

        main = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left = ttk.Frame(main)
        right = ttk.Frame(main)
        main.add(left, weight=1)
        main.add(right, weight=4)  # Give plots 4x more space

        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        cols = ("name", "com_port", "sensor_type", "product", "serial")
        self._tree = ttk.Treeview(left, columns=cols, show="headings", height=6)
        self._tree.grid(row=0, column=0, sticky="nsew")

        headings = {
            "name": "Name",
            "com_port": "COM",
            "sensor_type": "Type",
            "product": "Product",
            "serial": "Serial",
        }
        widths = {
            "name": 260,
            "com_port": 80,
            "sensor_type": 110,
            "product": 90,
            "serial": 90,
        }
        for c in cols:
            self._tree.heading(c, text=headings[c])
            self._tree.column(c, width=widths[c], anchor="w")

        edit = ttk.LabelFrame(left, text="Edit selected", padding=10)
        edit.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        edit.columnconfigure(1, weight=1)

        ttk.Label(edit, text="COM port").grid(row=0, column=0, sticky="w")
        self._com_var = tk.StringVar()
        self._com_box = ttk.Combobox(edit, textvariable=self._com_var, values=[], state="readonly")
        self._com_box.grid(row=0, column=1, sticky="ew")

        ttk.Label(edit, text="Type").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._type_var = tk.StringVar()
        self._type_box = ttk.Combobox(edit, textvariable=self._type_var, values=["oxygen", "conductivity", "pressure", "unknown"], state="readonly")
        self._type_box.grid(row=1, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(edit, text="Name").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._name_var = tk.StringVar()
        ttk.Entry(edit, textvariable=self._name_var).grid(row=2, column=1, sticky="ew", pady=(8, 0))

        ttk.Button(edit, text="Apply", command=self._apply_edit).grid(row=3, column=1, sticky="e", pady=(10, 0))

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        latest = ttk.LabelFrame(right, text="Latest values", padding=8)
        latest.grid(row=0, column=0, sticky="ew")
        latest.columnconfigure(0, weight=1)

        self._latest_text = tk.Text(latest, height=4, wrap="none", font=("TkDefaultFont", 8))
        self._latest_text.grid(row=0, column=0, sticky="ew")
        self._latest_text.configure(state="disabled")

        plot = ttk.LabelFrame(right, text="Time series", padding=8)
        plot.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        plot.rowconfigure(0, weight=1)
        plot.columnconfigure(0, weight=1)

        self._fig = Figure(figsize=(7, 5), dpi=100)
        # Share a common time axis so all panels are visually synchronized.
        self._axes = []
        for i in range(4):
            if i == 0:
                ax = self._fig.add_subplot(4, 1, 1)
            else:
                ax = self._fig.add_subplot(4, 1, i + 1, sharex=self._axes[0])
            self._axes.append(ax)
        self._lines = []
        for ax in self._axes:
            ax.grid(True, alpha=0.3)
            (line,) = ax.plot([], [], linewidth=1.5)
            self._lines.append(line)

        self._fig.tight_layout()
        self._canvas = FigureCanvasTkAgg(self._fig, master=plot)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        
        # Plot controls
        plot_controls = ttk.Frame(plot)
        plot_controls.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        ttk.Label(plot_controls, text="Oxygen plot:").pack(side=tk.LEFT, padx=(5, 3))
        oxygen_box = ttk.Combobox(
            plot_controls,
            textvariable=self._oxygen_plot_var,
            values=[
                "O2 (derived mg/L)",
                "O2Concentration (raw mg/L)",
                "O2Saturation (%)",
            ],
            state="readonly",
            width=24,
        )
        oxygen_box.pack(side=tk.LEFT, padx=(0, 10))
        oxygen_box.bind("<<ComboboxSelected>>", lambda _e: self._mark_plot_dirty())

        ttk.Label(plot_controls, text="Time window:").pack(side=tk.LEFT, padx=(10, 3))
        time_box = ttk.Combobox(
            plot_controls,
            textvariable=self._time_window_var,
            values=[
                "Last 1 min",
                "Last 10 min",
                "Last 1 h",
            ],
            state="readonly",
            width=12,
        )
        time_box.pack(side=tk.LEFT, padx=(0, 10))
        time_box.bind("<<ComboboxSelected>>", lambda _e: self._mark_plot_dirty())

        ttk.Button(plot_controls, text="Reset Axes", command=self._reset_axes).pack(side=tk.LEFT, padx=5)
        ttk.Button(plot_controls, text="Clear Data", command=self._clear_data).pack(side=tk.LEFT, padx=5)

    def _barometric_pressure_kpa(self) -> Optional[float]:
        if not bool(self._use_baro_var.get()):
            return None
        hpa = _to_float(self._baro_hpa_var.get())
        if hpa is None or not np.isfinite(hpa) or hpa <= 0:
            return None
        return float(hpa) / 10.0

    def _pressure_sensor_id(self, com_port: str, measurements: Dict[str, str]) -> str:
        product = str(measurements.get("ProductNumber", "")).strip()
        serial_no = str(measurements.get("SerialNumber", "")).strip()
        if product and serial_no:
            return f"{product}_SN_{serial_no}"
        return str(com_port).upper()

    def _tutorial_and_set_pressure_baseline(self) -> None:
        tutorial = (
            "Pressure baseline (in air)\n\n"
            "The 4117 reports ABSOLUTE pressure (includes atmosphere).\n"
            "To see water pressure/depth, first store the air pressure baseline:\n\n"
            "1) Put the pressure sensor in AIR (dry, not submerged).\n"
            "2) Start streaming and wait ~10–20 seconds for stable readings.\n"
            "3) Click Yes to store the current pressure as the air baseline.\n\n"
            "Tip: If you store the baseline while submerged, depth/gauge values will be wrong."
        )
        messagebox.showinfo("Pressure baseline tutorial", tutorial)

        if not messagebox.askyesno("Set air baseline now?", "Sensor is in air and readings are stable?"):
            return

        # Find configured pressure sensors.
        pressure_ports: List[str] = []
        for item_id in self._tree.get_children():
            _name, com_port, sensor_type, *_ = self._tree.item(item_id).get("values", [])
            if not com_port:
                continue
            if str(sensor_type or "").lower() == "pressure":
                pressure_ports.append(str(com_port).upper())

        if not pressure_ports:
            messagebox.showwarning("No pressure sensor", "No sensor is configured as type 'pressure'.")
            return

        assignments: List[Tuple[str, float]] = []  # (sensor_id, baseline_kpa)
        preview_lines: List[str] = []
        for port in pressure_ports:
            baseline_kpa = None
            s = self._series.get((port, "Pressure_kPa"))
            if s and s.y:
                baseline_kpa = float(s.y[-1])
            if baseline_kpa is None:
                baseline_kpa = self._latest_pressure_kpa_by_port.get(port)
            if baseline_kpa is None or not np.isfinite(baseline_kpa):
                continue

            sensor_id = self._pressure_sensor_id_by_port.get(port, port)
            assignments.append((sensor_id, float(baseline_kpa)))
            preview_lines.append(f"{port}: {baseline_kpa:.3f} kPa")

        if not assignments:
            messagebox.showerror(
                "No data",
                "No recent pressure samples found yet. Start streaming and wait for pressure data, then try again.",
            )
            return

        msg = "Store these air baselines?\n\n" + "\n".join(preview_lines)
        if not messagebox.askyesno("Confirm baseline", msg):
            return

        for sensor_id, baseline_kpa in assignments:
            self._pressure_air_kpa_by_sensor[sensor_id] = baseline_kpa

        path = save_state({"pressure_air_kpa_by_sensor": self._pressure_air_kpa_by_sensor})
        self._set_status(f"Saved pressure baseline to {path.name}")
        self._mark_plot_dirty()

    def _clear_pressure_baseline(self) -> None:
        if not self._pressure_air_kpa_by_sensor:
            messagebox.showinfo("No baseline", "No stored pressure baseline to clear.")
            return
        if not messagebox.askyesno("Clear baseline", "Clear all stored pressure air baselines?"):
            return
        self._pressure_air_kpa_by_sensor.clear()
        path = save_state({"pressure_air_kpa_by_sensor": {}})
        self._set_status(f"Cleared pressure baseline ({path.name})")
        self._mark_plot_dirty()

    def _mark_plot_dirty(self) -> None:
        self._plot_dirty = True

    def _append_series(self, com_port: str, key: str, timestamp: datetime, value: float) -> None:
        series = self._series.setdefault((str(com_port).upper(), key), Series(t=[], y=[]))
        series.t.append(timestamp)
        series.y.append(float(value))
        if len(series.t) > self._max_points:
            series.t = series.t[-self._max_points :]
            series.y = series.y[-self._max_points :]

    def _oxygen_plot_key(self) -> Tuple[str, str, str]:
        """Return (series_key, title, ylabel) for oxygen plot."""
        sel = (self._oxygen_plot_var.get() or "").strip()
        if sel == "O2Saturation (%)":
            return ("O2Saturation", "O2 saturation", "%")
        if sel == "O2Concentration (raw mg/L)":
            return ("O2Concentration", "O2 concentration (raw)", "mg/L")
        return (
            "Derived_O2_umolL_from_sat",
            "O2 concentration (from sat; uses salinity if available)",
            "mg/L",
        )

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)
        self.update_idletasks()

    def _default_log_path(self) -> Path:
        # Workspace has a top-level Log/ folder; place files there.
        root = Path(__file__).resolve().parent.parent
        log_dir = root / "Log"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return log_dir / f"aanderaa_log_{stamp}.jsonl"

    def _toggle_recording(self) -> None:
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        try:
            path = self._default_log_path()
            # Line-buffered text write; flush periodically anyway.
            self._record_fp = path.open("a", encoding="utf-8", buffering=1)
            self._record_path = path
            self._record_lines = 0
            self._is_recording = True
            self._record_btn.configure(text="Stop Recording")
            print(f"Recording to: {path}")
            self._set_status(f"Recording: {path.name}")
        except Exception as e:
            self._record_fp = None
            self._record_path = None
            self._is_recording = False
            messagebox.showerror("Recording failed", f"Could not start recording:\n{e}")

    def _stop_recording(self) -> None:
        self._is_recording = False
        self._record_btn.configure(text="Start Recording")
        try:
            if self._record_fp:
                try:
                    self._record_fp.flush()
                except Exception:
                    pass
                try:
                    self._record_fp.close()
                except Exception:
                    pass
        finally:
            if self._record_path:
                print(f"Stopped recording: {self._record_path}")
            self._record_fp = None
            self._record_path = None
            self._record_lines = 0
            self._set_status("Ready")

    def _load_config_to_table(self) -> None:
        script_dir = Path(__file__).parent
        sensors = load_sensors(script_dir / "sensor_config.json")

        self._tree.delete(*self._tree.get_children())
        for s in sensors:
            self._tree.insert(
                "",
                "end",
                values=(
                    s.get("name", ""),
                    s.get("com_port", ""),
                    s.get("sensor_type", ""),
                    "",
                    "",
                ),
            )

        self._refresh_com_choices()

    def _refresh_com_choices(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self._com_box.configure(values=ports)

    def _scan_and_identify(self) -> None:
        self._refresh_com_choices()
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            messagebox.showwarning("No ports", "No COM ports found.")
            return

        msg = "Found COM ports:\n\n" + "\n".join(f"{p.device} - {p.description}" for p in ports)
        messagebox.showinfo("COM ports", msg)

        if self._threads:
            return

        if not messagebox.askyesno(
            "Identify sensors?",
            "Try to identify Aanderaa sensors on these ports now?\n\nThis can take ~10–30 seconds.",
        ):
            return

        self._set_status("Identifying sensors...")
        t = threading.Thread(target=self._identify_worker, daemon=True)
        t.start()

    def _identify_worker(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        detected: List[AanderaaSensorCustom] = []

        for port in ports:
            if len(detected) >= 3:
                break

            s = AanderaaSensorCustom(com_port=port, name="Unknown", sensor_type="unknown")
            try:
                ok = s.connect()
                if not ok:
                    continue

                # Give it a bit of time to emit a valid frame
                for _ in range(5):
                    if s.product_number and s.serial_number:
                        break
                    _ = s.get_measurement()
                    time.sleep(0.3)

                if s.product_number and s.serial_number:
                    detected.append(s)
            except Exception:
                pass
            finally:
                try:
                    s.disconnect()
                except Exception:
                    pass

        self.after(0, lambda: self._apply_detected(detected))

    def _apply_detected(self, detected: List[AanderaaSensorCustom]) -> None:
        if not detected:
            self._set_status("No sensors identified")
            messagebox.showwarning("No sensors", "No Aanderaa sensors were identified on the scanned ports.")
            return

        self._tree.delete(*self._tree.get_children())
        for s in detected:
            product = s.product_number or ""
            serial_no = s.serial_number or ""
            sensor_type = s.sensor_type or _infer_sensor_type_from_product(product)
            name = s.name or "Unknown"
            self._tree.insert("", "end", values=(name, s.com_port, sensor_type, product, serial_no))

        self._refresh_com_choices()
        self._set_status(f"Identified {len(detected)} sensor(s)")

    def _on_select(self, _evt: object) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        item = self._tree.item(sel[0])
        name, com_port, sensor_type, _, _ = item.get("values", ["", "", "", "", ""])
        self._name_var.set(name)
        self._com_var.set(com_port)
        self._type_var.set(sensor_type or "unknown")

    def _apply_edit(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        item_id = sel[0]
        vals = list(self._tree.item(item_id).get("values", []))
        if len(vals) < 5:
            vals = (vals + [""] * 5)[:5]
        vals[0] = self._name_var.get().strip()
        vals[1] = self._com_var.get().strip().upper()
        vals[2] = (self._type_var.get().strip() or "unknown").lower()
        self._tree.item(item_id, values=tuple(vals))

    def _save_config(self) -> None:
        sensors: List[Dict[str, object]] = []
        for item_id in self._tree.get_children():
            name, com_port, sensor_type, *_ = self._tree.item(item_id).get("values", [])
            if not com_port:
                continue
            sensors.append(
                {
                    "name": name or "Unknown",
                    "com_port": str(com_port).upper(),
                    "baudrate": 9600,
                    "sensor_type": (sensor_type or "unknown"),
                    "timeout": 5,
                }
            )

        if not sensors:
            messagebox.showwarning("Nothing to save", "No sensors with a COM port are configured.")
            return

        path = save_sensors_to_user_config(sensors)
        messagebox.showinfo("Saved", f"Saved config to:\n{path}")

    def _connect_sensors(self) -> None:
        """Connect to sensors without starting streaming."""
        if self._sensors:
            messagebox.showinfo("Already connected", "Sensors are already connected. Disconnect first to reconnect.")
            return

        sensors_cfg: List[Tuple[str, str, str]] = []
        for item_id in self._tree.get_children():
            name, com_port, sensor_type, *_ = self._tree.item(item_id).get("values", [])
            if not com_port:
                continue
            sensors_cfg.append((str(com_port).upper(), str(name), str(sensor_type)))

        if not sensors_cfg:
            messagebox.showwarning("No sensors", "Configure at least one sensor with a COM port.")
            return

        self._set_status("Connecting...")
        print("\n" + "="*60)
        print("Connecting to sensors...")
        print("="*60)

        interval_s = float(self._interval_var.get())
        auto_apply = bool(self._auto_apply_interval_var.get())

        # Do the potentially slow interval configuration in a background thread
        # to keep the GUI responsive and to avoid connecting while a sensor is rebooting.
        def worker() -> None:
            connected: List[AanderaaSensorCustom] = []

            for com_port, name, sensor_type in sensors_cfg:
                print(f"\nConnecting to {name} on {com_port}...")

                try:
                    # Only configure Interval/Save/Reset if the user explicitly enabled it.
                    # For pure streaming/reading, we should not touch Passkey or write settings.
                    if auto_apply and interval_s > 0:
                        ok = configure_sensor_interval(com_port, interval_s, do_reset=True, force_terminal_mode=False)
                        if not ok:
                            print(f"[{com_port}] Warning: interval configuration may not have applied")
                        # After Reset, give the sensor time to reboot.
                        time.sleep(6.0)
                except Exception as e:
                    print(f"[{com_port}] Warning: interval configuration error: {e}")

                sensor = AanderaaSensorCustom(com_port, name=name, sensor_type=sensor_type)
                # Retry connect a couple times (common right after Reset).
                for attempt in range(3):
                    sensor.connect()
                    if sensor.serial_port:
                        break
                    time.sleep(2.0)
                if sensor.serial_port:
                    connected.append(sensor)
                    print(f"✓ Connected to {name}")
                else:
                    print(f"✗ Failed to connect to {name}")

            def done() -> None:
                self._sensors = connected
                if not self._sensors:
                    messagebox.showerror("Connection failed", "Could not connect to any sensor.")
                    print("\n✗ Connection failed - no sensors connected")
                    self._set_status("Connection failed")
                    return

                print(f"\n✓ Connected to {len(self._sensors)} sensor(s)")
                self._set_status(f"Connected to {len(self._sensors)} sensor(s)")
                messagebox.showinfo("Connected", f"Connected to {len(self._sensors)} sensor(s).\n\nClick 'Start Streaming' to begin data collection.")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()
    
    def _start_streaming(self) -> None:
        """Start streaming from connected sensors."""
        if self._threads:
            messagebox.showinfo("Already streaming", "Streaming is already running.")
            return
        
        if not self._sensors:
            messagebox.showwarning("Not connected", "Connect to sensors first before starting streaming.")
            return
        
        print("\n" + "="*60)
        print("Starting streaming...")
        print("="*60)
        
        self._set_status("Starting streaming...")
        self._stop_event.clear()
        self._event_queue = queue.Queue()
        self._threads = []
        self._stream_started_at = time.time()
        self._last_event_at = None

        # Best-effort: prompt devices that require a runtime start command.
        for s in self._sensors:
            try:
                if s.serial_port:
                    s.serial_port.write(b"Start\r\n")
            except Exception:
                pass

        time.sleep(0.2)

        # Clear any residual bytes from connect/probes so parsing starts clean.
        for s in self._sensors:
            try:
                if s.serial_port:
                    s.serial_port.reset_input_buffer()
            except Exception:
                pass
        
        for sensor in self._sensors:
            thread = threading.Thread(
                target=_reader_loop,
                args=(sensor, self._event_queue, self._stop_event),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)
        
        print(f"\n✓ Streaming started from {len(self._sensors)} sensor(s)")
        self._set_status(f"Streaming from {len(self._sensors)} sensor(s)")
    
    def _stop_streaming(self) -> None:
        """Stop streaming but keep sensors connected."""
        if not self._threads:
            messagebox.showinfo("Not streaming", "Streaming is not running.")
            return

        print("\n" + "="*60)
        print("Stopping streaming...")
        print("="*60)
        
        self._set_status("Stopping...")
        self._stop_event.set()

        for t in self._threads:
            t.join(timeout=1.0)

        self._threads = []
        print("✓ Streaming stopped (sensors still connected)")
        self._set_status("Stopped (connected)")
        self._stream_started_at = None
        self._last_event_at = None
    
    def _disconnect_sensors(self) -> None:
        """Disconnect all sensors."""
        if self._threads:
            self._stop_streaming()
            time.sleep(0.5)

        if self._is_recording:
            self._stop_recording()
        
        if not self._sensors:
            messagebox.showinfo("Not connected", "No sensors are connected.")
            return
        
        print("\n" + "="*60)
        print("Disconnecting sensors...")
        print("="*60)
        
        for s in self._sensors:
            print(f"Disconnecting {s.name}...")
            s.disconnect()
        
        self._sensors = []
        print("✓ All sensors disconnected")
        self._set_status("Disconnected")
    
    def _stop_and_disconnect(self) -> None:
        """Stop streaming and disconnect (for internal use)."""
        self._set_status("Stopping...")
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=1.0)
        for s in self._sensors:
            try:
                s.disconnect()
            except Exception:
                pass
        self._threads = []
        self._sensors = []
        self._set_status("Stopped")

        if self._is_recording:
            self._stop_recording()

    def _force_command_mode(self, com_port: str) -> bool:
        """Try to force sensor out of streaming/AiCaP mode into command mode."""
        print(f"  Attempting to switch {com_port} to command mode...")
        
        # Strategy: Close any existing connection, wait, then try to break streaming on reconnect
        # This is necessary because sensors actively streaming won't respond to commands
        
        try:
            # First, ensure the port is completely closed
            print(f"  Closing any existing connections...")
            try:
                # Try to open and immediately close to force release
                test_ser = serial.Serial(com_port, 9600, timeout=0.5)
                test_ser.close()
                time.sleep(0.3)
            except:
                pass  # Port might already be closed
            
            # Now open with aggressive break strategy
            print(f"  Reopening port with break sequence...")
            ser = serial.Serial(
                port=com_port,
                baudrate=9600,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=1.0,
                xonxoff=True,
                rtscts=False,
                dsrdtr=False,
            )
            
            # Immediately send break sequences before sensor starts streaming again
            for _ in range(5):
                ser.write(b'\x03')  # Ctrl+C
                time.sleep(0.05)
            
            ser.reset_input_buffer()
            
            # Send ESC and break characters
            for _ in range(3):
                ser.write(b'\x1b')  # ESC
                ser.write(b'%')
                time.sleep(0.1)
            
            # Clear any streaming data
            ser.reset_input_buffer()
            time.sleep(0.5)
            
            # Try wake sequence
            for _ in range(3):
                ser.write(b'\r\n')
                time.sleep(0.1)
            
            ser.write(b'%')
            time.sleep(0.3)
            ser.reset_input_buffer()
            time.sleep(0.5)
            
            # Test if we can get a command response
            ser.write(b'$GET ProductName\r\n')
            time.sleep(1.0)
            
            response = ""
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            
            ser.close()
            
            # Check if we got a valid response
            if "RESULT" in response.upper() or "4117" in response or "4330" in response or "5819" in response:
                print(f"  ✓ {com_port} responded to commands")
                return True
            else:
                print(f"  ✗ {com_port} not responding to commands (got: {response[:50] if response else 'nothing'})")
                print(f"     Sensor may need power cycle to exit streaming mode")
                return False
                
        except Exception as e:
            print(f"  ✗ Error forcing command mode on {com_port}: {e}")
            return False
    
    def _configure_interval(self) -> None:
        """Configure sampling interval on all sensors."""
        interval_s = self._interval_var.get()
        if interval_s <= 0:
            messagebox.showerror("Invalid Interval", "Interval must be greater than 0 seconds.")
            return

        # Get COM ports from the table (not from active connections)
        com_ports: List[str] = []
        for item_id in self._tree.get_children():
            _, com_port, *_ = self._tree.item(item_id).get("values", [])
            if com_port:
                com_ports.append(str(com_port).upper())

        if not com_ports:
            messagebox.showwarning("No Sensors", "Add sensors to the table first (use Scan + Identify).")
            return

        was_streaming = bool(self._threads)
        if was_streaming:
            response = messagebox.askyesno(
                "Stop Streaming?",
                "Sensors are currently streaming. They must be stopped to configure interval.\n\n"
                "Stop streaming and configure interval now?\n"
                "(Streaming will restart automatically after configuration)",
            )
            if not response:
                return
            self._stop_and_disconnect()
            time.sleep(0.8)

        self._set_status(f"Configuring interval to {interval_s}s...")

        def worker() -> None:
            success = 0
            errors: List[str] = []
            for com_port in com_ports:
                try:
                    ok = configure_sensor_interval(com_port, float(interval_s), do_reset=True, force_terminal_mode=False)
                    if ok:
                        success += 1
                    else:
                        errors.append(f"{com_port}: failed")
                except Exception as e:
                    errors.append(f"{com_port}: {e}")
                time.sleep(0.5)

            def done() -> None:
                if success == len(com_ports):
                    messagebox.showinfo("Success", f"Configured all sensors to {interval_s}s interval.\n\nWait ~10s for reboot, then start streaming.")
                    self._set_status(f"Interval set to {interval_s}s")
                elif success > 0:
                    messagebox.showwarning("Partial Success", f"Configured {success}/{len(com_ports)} sensors.\n\n" + "\n".join(errors[:6]))
                    self._set_status("Interval partially configured")
                else:
                    messagebox.showerror("Failed", "Failed to configure interval.\n\n" + "\n".join(errors[:6]))
                    self._set_status("Interval configuration failed")

                if was_streaming and success > 0:
                    # Reconnect and restart streaming after reboot window.
                    self._set_status("Waiting for sensors to reboot...")
                    self.after(10000, lambda: (self._connect_sensors(), self.after(1500, self._start_streaming)))

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _connect_and_start(self) -> None:
        if self._threads:
            messagebox.showinfo("Already running", "Streaming is already running.")
            return

        sensors_cfg: List[Tuple[str, str, str]] = []
        for item_id in self._tree.get_children():
            name, com_port, sensor_type, *_ = self._tree.item(item_id).get("values", [])
            if not com_port:
                continue
            sensors_cfg.append((str(com_port).upper(), str(name), str(sensor_type)))

        if not sensors_cfg:
            messagebox.showwarning("No sensors", "Configure at least one sensor with a COM port.")
            return

        self._set_status("Connecting...")
        self._stop_event.clear()
        self._event_queue = queue.Queue()
        self._threads = []
        self._sensors = []

        connected = 0
        for com_port, name, sensor_type in sensors_cfg[:3]:
            safe_name = (name or "Unknown").strip() or "Unknown"
            safe_type = (sensor_type or "unknown").strip() or "unknown"
            s = AanderaaSensorCustom(com_port=com_port, name=safe_name, sensor_type=safe_type)
            ok = s.connect()
            if ok:
                connected += 1
            self._sensors.append(s)

        if connected == 0:
            self._set_status("No sensors connected")
            messagebox.showerror("Connect failed", "Could not connect to any configured sensors.")
            return

        # Start reader threads
        for s in self._sensors:
            if not s.is_connected or not s.serial_port:
                continue
            t = threading.Thread(target=_reader_loop, args=(s, self._event_queue, self._stop_event), daemon=True)
            t.start()
            self._threads.append(t)

        self._set_status(f"Streaming ({connected} connected)")

    def _drain_events(self) -> None:
        updated = False
        latest_lines: List[str] = []

        # Drain queue quickly
        drained = 0
        while True:
            try:
                ev = self._event_queue.get_nowait()
            except queue.Empty:
                break

            drained += 1
            updated = True
            self._last_event_at = time.time()

            # Normalize raw Value* fields to avoid scientific notation in the UI.
            # The original wire format is still preserved in ev.raw_line.
            for k in list(ev.measurements.keys()):
                if not re.match(r"^Value\d+$", str(k)):
                    continue
                f = _to_float(ev.measurements.get(k))
                if f is None:
                    continue
                ev.measurements[k] = _format_plain_number(f)

            # Update table row based on com_port
            self._update_row_for_event(ev)

            # Update cross-sensor context.
            st = self._sensor_type_for_port(ev.com_port)
            if st == "conductivity":
                cond = _to_float(ev.measurements.get("Conductivity"))
                t_c = _to_float(ev.measurements.get("Temperature"))
                # If the sensor already streams salinity, trust it.
                sal_stream = _to_float(ev.measurements.get("Salinity"))

                # Best-effort pressure in dbar.
                p_dbar = 0.0
                if self._latest_pressure is not None:
                    p_dbar = _pressure_to_dbar(self._latest_pressure)

                sal = sal_stream
                if sal is None and cond is not None and t_c is not None:
                    sal = _pss78_salinity_from_conductivity_ms_cm(cond, t_c, p_dbar)

                if sal is not None:
                    self._latest_salinity_psu = sal
                    self._latest_salinity_at = ev.timestamp
                    ev.measurements["Derived_Salinity_psu"] = f"{sal:.3f}"
                    if cond is not None:
                        ev.measurements["Conductivity"] = f"{cond:.3f} mS/cm"
                # Attach units for display consistency.
                if t_c is not None:
                    ev.measurements["Temperature"] = f"{t_c:.3f} °C"
                    self._append_series(ev.com_port, "Temperature_C", ev.timestamp, t_c)

                # Store plot series.
                if cond is not None:
                    self._append_series(ev.com_port, "Conductivity", ev.timestamp, cond)
            elif st == "pressure":
                p = _to_float(ev.measurements.get("Pressure"))
                if p is not None:
                    port = str(ev.com_port).upper()
                    sensor_id = self._pressure_sensor_id(port, ev.measurements)
                    self._pressure_sensor_id_by_port[port] = sensor_id
                    self._latest_pressure_kpa_by_port[port] = p

                    self._latest_pressure = p
                    self._latest_pressure_at = ev.timestamp

                    # 4117 reports absolute pressure in kPa (manual). Convert to dbar.
                    p_kpa = p
                    p_dbar = _pressure_to_dbar(p_kpa)
                    ev.measurements["Pressure"] = f"{p_kpa:.3f} kPa"
                    ev.measurements["Derived_Pressure_dbar"] = f"{p_dbar:.3f} dbar"
                    self._append_series(ev.com_port, "Pressure_kPa", ev.timestamp, p_kpa)
                    self._append_series(ev.com_port, "Derived_Pressure_dbar", ev.timestamp, p_dbar)

                    # If we have a stored air baseline, also provide gauge/sea pressure + depth.
                    base_kpa = self._pressure_air_kpa_by_sensor.get(sensor_id)
                    if base_kpa is not None and np.isfinite(base_kpa):
                        sea_dbar = _pressure_to_dbar(p_kpa - float(base_kpa))
                        ev.measurements["Derived_PressureAir_kPa"] = f"{float(base_kpa):.3f} kPa"
                        ev.measurements["Derived_SeaPressure_dbar"] = f"{sea_dbar:.3f} dbar"
                        ev.measurements["Derived_Depth_m"] = f"{sea_dbar:.3f} m"
                        self._append_series(ev.com_port, "Derived_SeaPressure_dbar", ev.timestamp, sea_dbar)
                        self._append_series(ev.com_port, "Derived_Depth_m", ev.timestamp, sea_dbar)
                t_c = _to_float(ev.measurements.get("Temperature"))
                if t_c is not None:
                    ev.measurements["Temperature"] = f"{t_c:.3f} °C"
                    self._append_series(ev.com_port, "Temperature_C", ev.timestamp, t_c)

            # Derived oxygen values (salinity compensation via Weiss 1970).
            if st == "oxygen":
                temp_c = _to_float(ev.measurements.get("Temperature"))
                sat_pct = _to_float(ev.measurements.get("O2Saturation"))
                # Prefer salinity from conductivity sensor if available.
                sal_psu = self._latest_salinity_psu

                # If salinity is missing (common when the conductivity probe is in air),
                # fall back to S=0 PSU so the derived oxygen plot still has values.
                if temp_c is not None:
                    sal_used = float(sal_psu) if sal_psu is not None else 0.0
                    assumed_salinity = sal_psu is None
                    try:
                        o2sol_1atm = _o2_sol_umol_per_l_weiss1970(temp_c, sal_used)
                        baro_kpa = self._barometric_pressure_kpa()
                        o2sol = _scale_o2_solubility_for_pressure(o2sol_1atm, baro_kpa)
                        ev.measurements["Derived_O2Sol_umolL"] = f"{o2sol:.2f}"
                        ev.measurements["Derived_Salinity_psu"] = f"{sal_used:.3f}"
                        if assumed_salinity:
                            ev.measurements["Derived_Salinity_assumed"] = "True"
                        if baro_kpa is not None:
                            ev.measurements["Derived_Baro_kPa"] = f"{baro_kpa:.2f}"
                        if sat_pct is not None:
                            o2_umol_l = (sat_pct / 100.0) * o2sol
                            ev.measurements["Derived_O2_umolL_from_sat"] = f"{o2_umol_l:.2f}"
                        # Also provide a saturation estimate from concentration (if present).
                        conc = _to_float(ev.measurements.get("O2Concentration"))
                        if conc is not None and o2sol > 0:
                            ev.measurements["Derived_O2Sat_pct_from_conc"] = f"{(100.0 * conc / o2sol):.2f}"
                    except Exception:
                        # Keep GUI resilient even if a single computation fails.
                        pass

                # Add units to the basic displayed keys.
                if temp_c is not None:
                    ev.measurements["Temperature"] = f"{temp_c:.3f} °C"
                    self._append_series(ev.com_port, "Temperature_C", ev.timestamp, temp_c)
                conc = _to_float(ev.measurements.get("O2Concentration"))
                if conc is not None:
                    ev.measurements["O2Concentration"] = f"{conc:.2f} µmol/L"
                if sat_pct is not None:
                    ev.measurements["O2Saturation"] = f"{sat_pct:.2f} %"

                # Store plot series (always store raw; derived may be missing).
                if conc is not None:
                    self._append_series(ev.com_port, "O2Concentration", ev.timestamp, conc)
                if sat_pct is not None:
                    self._append_series(ev.com_port, "O2Saturation", ev.timestamp, sat_pct)
                derived = _to_float(ev.measurements.get("Derived_O2_umolL_from_sat"))
                if derived is not None:
                    self._append_series(ev.com_port, "Derived_O2_umolL_from_sat", ev.timestamp, derived)

            # Recording (JSON lines)
            if self._is_recording and self._record_fp is not None:
                try:
                    payload = {
                        "timestamp": ev.timestamp.isoformat(),
                        "com_port": ev.com_port,
                        "name": ev.name,
                        "measurements": ev.measurements,
                        "raw_line": ev.raw_line,
                    }
                    self._record_fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    self._record_lines += 1
                    # Periodic flush for safety
                    if self._record_lines % 20 == 0:
                        self._record_fp.flush()
                except Exception as e:
                    print(f"Recording error: {e}")
                    self._stop_recording()

            # Note: per-sensor plot series are appended above.

            # Latest display
            latest_lines.append(f"[{ev.timestamp.strftime('%H:%M:%S')}] {ev.name} ({ev.com_port})")
            for k, val in ev.measurements.items():
                latest_lines.append(f"  {k}: {val}")

        if drained > 0:
            self._render_latest(latest_lines[-60:])

        if updated:
            self._plot_dirty = True

        self.after(300, self._drain_events)

    def _plot_tick(self) -> None:
        if self._plot_dirty:
            self._plot_dirty = False
            self._redraw_plots()

        # Streaming diagnostics: show time since last data.
        if self._threads and self._stream_started_at is not None:
            now = time.time()
            if self._last_event_at is None:
                age = now - self._stream_started_at
                if age > 3.0:
                    self._set_status(f"Streaming... (no data yet, {age:.0f}s)")
            else:
                age = now - self._last_event_at
                self._set_status(f"Streaming... (last data {age:.1f}s ago)")
        self.after(500, self._plot_tick)

    def _sensor_type_for_port(self, com_port: str) -> str:
        # Prefer live/detected sensor objects (works even if you didn't pre-assign types).
        for s in self._sensors:
            if str(s.com_port).upper() == str(com_port).upper() and s.sensor_type:
                return str(s.sensor_type)
        for item_id in self._tree.get_children():
            _, p, sensor_type, *_ = self._tree.item(item_id).get("values", [])
            if str(p).upper() == str(com_port).upper():
                return str(sensor_type or "unknown")
        return "unknown"

    def _update_row_for_event(self, ev: SensorEvent) -> None:
        # Find matching row by COM port
        for item_id in self._tree.get_children():
            vals = list(self._tree.item(item_id).get("values", []))
            if len(vals) < 5:
                vals = (vals + [""] * 5)[:5]
            if str(vals[1]).upper() != str(ev.com_port).upper():
                continue
            vals[0] = ev.name
            detected_type = _infer_sensor_type_from_product(str(ev.measurements.get("ProductNumber", "")))
            if detected_type != "unknown":
                vals[2] = detected_type
            vals[3] = ev.measurements.get("ProductNumber", vals[3])
            vals[4] = ev.measurements.get("SerialNumber", vals[4])
            self._tree.item(item_id, values=tuple(vals))
            return

    def _render_latest(self, lines: List[str]) -> None:
        self._latest_text.configure(state="normal")
        self._latest_text.delete("1.0", "end")
        self._latest_text.insert("end", "\n".join(lines))
        self._latest_text.configure(state="disabled")
    
    def _reset_axes(self) -> None:
        """Reset plot axes to auto-scale."""
        for ax in self._fig.axes:
            ax.relim()
            ax.autoscale_view()
        self._canvas.draw()
        print("Plot axes reset")
    
    def _clear_data(self) -> None:
        """Clear all plotted data."""
        self._series.clear()
        for idx, ax in enumerate(self._axes):
            ax.cla()
            ax.grid(True, alpha=0.3)
            # Recreate line artists after cla(); previous Line2D objects are removed.
            (line,) = ax.plot([], [], linewidth=1.5)
            self._lines[idx] = line
        self._canvas.draw_idle()
        print("Plot data cleared")
        self._set_status("Data cleared")

    def _redraw_plots(self) -> None:
        # Plot up to 3 configured sensors in the order shown.
        # Use existing Line2D objects (fast) instead of clearing/replotting each tick.
        rows = []
        for item_id in self._tree.get_children():
            name, com_port, sensor_type, *_ = self._tree.item(item_id).get("values", [])
            if not com_port:
                continue
            rows.append((str(name), str(com_port).upper(), str(sensor_type)))

        # Determine a shared time window across displayed panels.
        all_ts: List[datetime] = []
        for _, com_port, sensor_type in rows[:3]:
            st = (sensor_type or "").lower()
            if st == "oxygen":
                key, _, _ = self._oxygen_plot_key()
            elif st == "pressure":
                # Prefer gauge pressure if baseline exists; otherwise fall back to absolute.
                sid = self._pressure_sensor_id_by_port.get(str(com_port).upper(), str(com_port).upper())
                if sid in self._pressure_air_kpa_by_sensor:
                    key = "Derived_SeaPressure_dbar"
                else:
                    key = "Derived_Pressure_dbar"
            elif st == "conductivity":
                key = "Conductivity"
            else:
                key = _primary_key_for(sensor_type)
            s = self._series.get((str(com_port).upper(), key))
            if s and s.t:
                all_ts.extend(s.t)
        x_min = min(all_ts) if all_ts else None
        x_max = max(all_ts) if all_ts else None

        # Apply user-selected time window.
        if x_max is not None:
            sel = (self._time_window_var.get() or "").strip()
            base_min = x_min
            window_min: Optional[datetime] = None
            if sel == "Last 1 min":
                window_min = x_max - timedelta(minutes=1)
            elif sel == "Last 10 min":
                window_min = x_max - timedelta(minutes=10)
            elif sel == "Last 1 h":
                window_min = x_max - timedelta(hours=1)

            # Treat the selection as a *maximum* window. If we only have 10 seconds of
            # data, don't show 50 seconds of empty time before the first sample.
            if window_min is not None:
                if base_min is None:
                    x_min = window_min
                else:
                    x_min = max(base_min, window_min)

        for idx, ax in enumerate(self._axes):
            line = self._lines[idx]
            ax.grid(True, alpha=0.3)

            # Temperature panel (4th subplot)
            if idx == 3:
                ax.set_title("Temperature")
                ax.set_xlabel("Time")
                ax.set_ylabel("°C")
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

                # Prefer oxygen sensor temperature if present; else first available temperature series.
                preferred_ports: List[str] = []
                for name, com_port, sensor_type in rows[:3]:
                    if (sensor_type or "").lower() == "oxygen":
                        preferred_ports.append(str(com_port).upper())
                for _name, com_port, _sensor_type in rows[:3]:
                    preferred_ports.append(str(com_port).upper())

                temp_series = None
                for p in preferred_ports:
                    s = self._series.get((p, "Temperature_C"))
                    if s and s.t:
                        temp_series = s
                        break

                if not temp_series or not temp_series.t:
                    line.set_data([], [])
                    continue

                line.set_data(temp_series.t, temp_series.y)
                line.set_marker(".")
                line.set_markersize(4)
                ax.relim()
                ax.autoscale_view()
                if x_min is not None and x_max is not None:
                    ax.set_xlim(x_min, x_max)
                continue

            if idx >= len(rows):
                ax.set_title("(no sensor)")
                line.set_data([], [])
                continue

            name, com_port, sensor_type = rows[idx]
            primary = _primary_key_for(sensor_type)
            # Human-friendly labels with units and dropdown selection.
            st = (sensor_type or "").lower()
            plot_key = primary
            title = primary
            ylabel = primary
            if st == "oxygen":
                plot_key, title, ylabel = self._oxygen_plot_key()
            elif st == "conductivity":
                plot_key = "Conductivity"
                title = "Conductivity"
                ylabel = "µS/cm"
            elif st == "pressure":
                sid = self._pressure_sensor_id_by_port.get(str(com_port).upper(), str(com_port).upper())
                if sid in self._pressure_air_kpa_by_sensor:
                    plot_key = "Derived_SeaPressure_dbar"
                    title = "Pressure (relative to air)"
                    ylabel = "dbar"
                else:
                    plot_key = "Derived_Pressure_dbar"
                    title = "Pressure (absolute)"
                    ylabel = "dbar"

            ax.set_title(f"{name} - {title}")
            ax.set_xlabel("Time")
            ax.set_ylabel(ylabel)

            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))

            series = self._series.get((str(com_port).upper(), plot_key))
            if not series or not series.t:
                line.set_data([], [])
                continue

            xs = series.t
            ys = series.y

            # Unit conversions for plotting.
            if st == "oxygen" and plot_key != "O2Saturation":
                ys = [_o2_umol_l_to_mg_l(v) for v in ys]
            elif st == "conductivity":
                ys = [_conductivity_ms_cm_to_uS_cm(v) for v in ys]

            line.set_data(xs, ys)
            # Show markers so a single sample is visible.
            line.set_marker(".")
            line.set_markersize(4)
            ax.relim()
            ax.autoscale_view()

            if x_min is not None and x_max is not None:
                ax.set_xlim(x_min, x_max)

        self._fig.tight_layout()
        try:
            self._fig.autofmt_xdate(rotation=30, ha="right")
        except Exception:
            pass
        self._canvas.draw_idle()


def main() -> None:
    app = AanderaaGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
