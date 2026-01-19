"""Configure Aanderaa sensors for automatic streaming.

This script talks to the sensor's Smart Sensor Terminal command interface to:
- Disable polled mode (Enable Polled Mode = no)
- Set Interval (seconds)
- Save to flash (Save)
- Optionally reset (Reset) to apply

It is intended as a one-time configuration utility. It does not modify your
Python reader configuration; it changes settings on the sensor.

Usage examples:
  python configure_streaming_mode.py --ports COM12 COM13 COM14 --interval 5
  python configure_streaming_mode.py --from-config --interval 2

Notes:
- Commands require a bidirectional RS-232/RS-422 connection (some cables are RX-only).
- Save can take several seconds; do not power off during save.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import serial

from config_manager import load_sensors


@dataclass
class CommandResult:
    command: str
    response: str
    saw_ack: bool


def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_available(ser: serial.Serial) -> str:
    try:
        waiting = ser.in_waiting
    except Exception:
        waiting = 0
    if not waiting:
        return ""
    return ser.read(waiting).decode("ascii", errors="ignore")


def _drain_for(ser: serial.Serial, duration_s: float) -> str:
    end = time.time() + duration_s
    chunks: List[str] = []
    while time.time() < end:
        chunk = _read_available(ser)
        if chunk:
            chunks.append(chunk)
            time.sleep(0.05)
        else:
            time.sleep(0.05)
    return "".join(chunks)


def _send_line(ser: serial.Serial, line: str) -> None:
    # Manuals show <CRLF> / Enter (↵). Use CRLF for compatibility.
    ser.write((line + "\r\n").encode("ascii", errors="ignore"))


class SensorTerminalSession:
    def __init__(self, port: str, *, baudrate: int = 9600, timeout_s: float = 1.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout_s = timeout_s
        self.ser: Optional[serial.Serial] = None

    def __enter__(self) -> "SensorTerminalSession":
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout_s,
            xonxoff=True,
            rtscts=False,
            dsrdtr=False,
        )
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        time.sleep(0.2)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        finally:
            self.ser = None

    def wake(self) -> str:
        if not self.ser:
            raise RuntimeError("Serial not open")

        # Wake by sending Enter a few times.
        for _ in range(3):
            self.ser.write(b"\r\n")
            time.sleep(0.15)

        # Some manuals mention that any character can wake from sleep.
        self.ser.write(b";")
        time.sleep(0.2)
        return _drain_for(self.ser, 1.0)

    def run_command(
        self,
        command: str,
        *,
        wait_for_ack: bool = False,
        timeout_s: float = 3.0,
    ) -> CommandResult:
        if not self.ser:
            raise RuntimeError("Serial not open")

        self.ser.reset_input_buffer()
        _send_line(self.ser, command)

        start = time.time()
        chunks: List[str] = []
        saw_ack = False
        while time.time() - start < timeout_s:
            chunk = _read_available(self.ser)
            if chunk:
                chunks.append(chunk)
                if "#" in chunk:
                    saw_ack = True
                    if wait_for_ack:
                        break
            else:
                time.sleep(0.05)

        # If we were expecting an ack, do a last small drain.
        if wait_for_ack and not saw_ack:
            chunks.append(_drain_for(self.ser, 0.4))
            if "#" in "".join(chunks):
                saw_ack = True

        return CommandResult(command=command, response="".join(chunks), saw_ack=saw_ack)


def _is_error_response(text: str) -> bool:
    t = (text or "").upper()
    return any(k in t for k in ["SYNTAX ERROR", "ARGUMENT ERROR", "*\tERROR", "ERROR"]) and len(t.strip()) > 0


def _one_line(text: str, limit: int = 300) -> str:
    s = (text or "").replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())
    if len(s) > limit:
        return s[:limit] + "..."
    return s


def _ports_from_config() -> List[str]:
    script_dir = Path(__file__).parent
    cfg = script_dir / "sensor_config.json"
    sensors = load_sensors(cfg)
    ports: List[str] = []
    for s in sensors:
        p = (s.get("com_port") or "").strip()
        if p and p not in ports:
            ports.append(p)
    return ports


def configure_port(
    port: str,
    *,
    interval_s: float,
    do_reset: bool,
) -> None:
    print(f"\n=== {port} ===")

    with SensorTerminalSession(port) as session:
        wake = session.wake()
        if wake:
            print(f"Wake: {_one_line(wake)}")

        # Stop streaming (if active) to make sure config commands are accepted.
        # Manuals say: wait for ack # and repeat if necessary.
        for attempt in range(1, 4):
            r = session.run_command("Stop", wait_for_ack=True, timeout_s=2.5)
            if r.saw_ack:
                break
            if attempt == 3:
                if _is_error_response(r.response):
                    print("Warning: 'Stop' returned an error. The sensor may not be in Smart Sensor Terminal mode.")
                else:
                    print("Warning: no ack for Stop (#). Continuing anyway.")

        # Some properties require passkey(1) for changes.
        session.run_command("Set Passkey(1)", wait_for_ack=False, timeout_s=1.5)

        # Best-effort: show current Mode/Interval if supported.
        r_mode = session.run_command("Get Mode", wait_for_ack=False, timeout_s=2.0)
        if r_mode.response.strip():
            print("Mode:", _one_line(r_mode.response, 240))
        elif _is_error_response(r_mode.response):
            print("Mode: ERROR (device did not accept 'Get Mode')")

        r_int = session.run_command("Get Interval", wait_for_ack=False, timeout_s=2.0)
        if r_int.response.strip():
            print("Interval (before):", _one_line(r_int.response, 240))
        elif _is_error_response(r_int.response):
            print("Interval (before): ERROR (device did not accept 'Get Interval')")

        # Ensure automatic streaming (polled mode off) and set Interval.
        r_polled = session.run_command("Set Enable Polled Mode(no)", wait_for_ack=True, timeout_s=3.0)
        if not r_polled.saw_ack:
            if _is_error_response(r_polled.response):
                print("Warning: 'Set Enable Polled Mode(no)' returned an error. Wrong mode or RX-only link likely.")
            else:
                print("Warning: no ack for 'Set Enable Polled Mode(no)' (#).")

        r_set = session.run_command(f"Set Interval({interval_s})", wait_for_ack=True, timeout_s=3.0)
        if not r_set.saw_ack:
            if _is_error_response(r_set.response):
                print("Warning: 'Set Interval(...)' returned an error. Wrong mode or RX-only link likely.")
            else:
                print("Warning: no ack for 'Set Interval(...)' (#).")

        r_save = session.run_command("Save", wait_for_ack=True, timeout_s=25.0)
        if not r_save.saw_ack:
            if _is_error_response(r_save.response):
                print("Warning: 'Save' returned an error. Wrong mode or RX-only link likely.")
            else:
                print("Warning: no ack for Save (#).")

        # Many manuals recommend Reset after Save.
        if do_reset:
            session.run_command("Reset", wait_for_ack=False, timeout_s=2.0)
            time.sleep(1.0)

        # Read back interval quickly (may or may not respond post-reset)
        r_int2 = session.run_command("Get Interval", wait_for_ack=False, timeout_s=2.0)
        if r_int2.response.strip():
            print("Interval (after):", _one_line(r_int2.response, 240))
        elif _is_error_response(r_int2.response):
            print("Interval (after): ERROR (device did not accept 'Get Interval')")

        if (not r_save.saw_ack) or _is_error_response(r_set.response) or _is_error_response(r_save.response):
            print("\nLikely causes:")
            print("- Sensor is not in Smart Sensor Terminal mode (e.g. AiCaP or AADI Real-Time)")
            print("- Cable/adapter is RX-only (you can read data but cannot send config commands)")
            print("- Another application is connected to the port")

    print(f"Done: set Interval={interval_s}, polled=no{', reset=yes' if do_reset else ', reset=no'}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Configure sensors for automatic streaming (Interval + polled mode off).")
    parser.add_argument("--ports", nargs="*", default=[], help="COM ports to configure (e.g., COM12 COM13)")
    parser.add_argument("--from-config", action="store_true", help="Use COM ports from sensor_config.json (resolved via config_manager)")
    parser.add_argument("--interval", type=float, default=5.0, help="New Interval in seconds (default: 5)")
    parser.add_argument("--no-reset", action="store_true", help="Do not send Reset after Save")

    args = parser.parse_args(argv)

    ports: List[str] = []
    for p in args.ports:
        p = (p or "").strip()
        if p and p not in ports:
            ports.append(p)

    if args.from_config:
        for p in _ports_from_config():
            if p not in ports:
                ports.append(p)

    if not ports:
        parser.error("No ports specified. Use --ports or --from-config.")

    interval_s = float(args.interval)
    if interval_s <= 0:
        parser.error("--interval must be > 0")

    do_reset = not args.no_reset

    print("Configuring automatic streaming:")
    print(f"- Ports: {', '.join(ports)}")
    print(f"- Interval: {interval_s} s")
    print(f"- Reset after save: {'yes' if do_reset else 'no'}")

    for port in ports:
        try:
            configure_port(port, interval_s=interval_s, do_reset=do_reset)
        except serial.SerialException as e:
            print(f"ERROR: {port}: serial error: {e}")
        except Exception as e:
            print(f"ERROR: {port}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
