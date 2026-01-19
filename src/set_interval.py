"""
Simple script to set the Interval property on Aanderaa sensors.

This configures sensors to sample at a specific interval (in seconds) and
disables polled mode so they stream data automatically.

Usage:
    python set_interval.py --interval 5
    python set_interval.py --interval 2 --ports COM12 COM13
    python set_interval.py --interval 10 --from-config

Default behavior reads ports from sensor_config.json
"""

from __future__ import annotations

import argparse
import json
import re
import serial
import time
from pathlib import Path
from typing import List, Optional, Literal, Tuple


def load_ports_from_config(config_path: Path) -> List[str]:
    """Load COM ports from sensor_config.json"""
    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        
        ports = []
        for sensor in config.get("sensors", []):
            port = sensor.get("com_port", "")
            if port:
                ports.append(str(port).upper())
        
        return ports
    except Exception as e:
        print(f"Error loading config: {e}")
        return []


def send_command(ser: serial.Serial, command: str, wait_s: float = 1.0) -> str:
    """Send a command and return the response (best-effort)."""
    ser.reset_input_buffer()
    ser.write((command + "\r\n").encode("ascii", errors="ignore"))
    time.sleep(wait_s)

    # Drain for a little while to catch multi-line responses.
    end = time.time() + max(0.2, wait_s)
    chunks: List[str] = []
    while time.time() < end:
        waiting = 0
        try:
            waiting = ser.in_waiting
        except Exception:
            waiting = 0
        if waiting:
            chunks.append(ser.read(waiting).decode("ascii", errors="ignore"))
            end = time.time() + 0.3
        else:
            time.sleep(0.05)

    return "".join(chunks)


def _is_error_response(text: str) -> bool:
    t = (text or "").upper()
    return any(k in t for k in ["SYNTAX ERROR", "ARGUMENT ERROR", "*\tERROR", "*   ERROR", "ERROR"])


def _looks_like_fw2(text: str) -> bool:
    # FW2-ish responses in this repo are parsed as: "RESULT GET Property=Value"
    t = (text or "").upper()
    return "RESULT" in t and "=" in t


def _looks_like_fw3(text: str) -> bool:
    # FW3 Smart Sensor Terminal often returns tab-delimited lines starting with property name.
    return ("\t" in (text or "")) and ("PRODUCT" in (text or "").upper())


def _extract_last_float(text: str) -> Optional[float]:
    """Extract the last float-looking number from a response."""
    if not text:
        return None
    matches = re.findall(r"[-+]?(?:\d+\.?\d*|\d*\.?\d+)(?:[Ee][-+]?\d+)?", text)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except Exception:
        return None


Protocol = Literal["fw2", "fw3"]


def detect_protocol(ser: serial.Serial) -> Tuple[Optional[Protocol], str]:
    """Try to detect which command dialect the sensor speaks."""
    probes = [
        ("fw2", "$GET ProductName"),
        ("fw3", "Get ProductName"),
        ("fw3", "Help"),
        ("fw3", "HELP"),
    ]
    last = ""
    for proto, cmd in probes:
        resp = send_command(ser, cmd, wait_s=1.2)
        last = resp
        if resp and not _is_error_response(resp):
            if proto == "fw2" and _looks_like_fw2(resp):
                return "fw2", resp
            if proto == "fw3":
                return "fw3", resp
    return None, last


def _wake_sensor(ser: serial.Serial) -> None:
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.1)
    for _ in range(5):
        ser.write(b"\r\n")
        time.sleep(0.1)
    # Many setups use '%' as wake; harmless if not needed.
    ser.write(b"%")
    time.sleep(0.4)
    ser.reset_input_buffer()
    time.sleep(0.2)


def _stop_streaming(ser: serial.Serial, protocol: Protocol) -> None:
    # Best effort: try Stop command in both dialects.
    if protocol == "fw2":
        ser.write(b"$STOP\r\n")
        time.sleep(0.2)
        ser.write(b"STOP\r\n")
    else:
        ser.write(b"Stop\r\n")
    time.sleep(0.4)
    ser.reset_input_buffer()


def _get_property(ser: serial.Serial, protocol: Protocol, prop: str) -> str:
    cmd = f"$GET {prop}" if protocol == "fw2" else f"Get {prop}"
    return send_command(ser, cmd, wait_s=1.2)


def _set_property(ser: serial.Serial, protocol: Protocol, prop: str, value: str, *, wait_s: float = 1.0) -> str:
    # FW2 in this repo commonly uses "$SET Name Value" (space separated)
    # FW3 uses "Set Name(Value)".
    if protocol == "fw2":
        cmd = f"$SET {prop} {value}"
        return send_command(ser, cmd, wait_s=wait_s)
    cmd = f"Set {prop}({value})"
    return send_command(ser, cmd, wait_s=wait_s)


def _try_set_passkey(ser: serial.Serial, protocol: Protocol) -> Tuple[bool, str]:
    """Best-effort: set access level. Returns (ok, last_response)."""
    if protocol == "fw2":
        candidates = [
            "$SET Passkey 1",
            "$SET Passkey 1000",
            "$SET Passkey(1)",
            "$SET Passkey(1000)",
            "Set Passkey(1)",
            "Set Passkey(1000)",
        ]
    else:
        # Manuals use "Set Passkey(1)" but some Help outputs show underscored aliases.
        candidates = [
            "Set Passkey(1)",
            "Set Passkey(1000)",
            "Set_Passkey(1)",
            "Set_Passkey(1000)",
            "Set Passkey 1",
            "Set Passkey 1000",
        ]

    last = ""
    for cmd in candidates:
        resp = send_command(ser, cmd, wait_s=1.2)
        last = resp
        # Success can be empty (some firmwares only respond with '#') so the only hard signal
        # we can rely on is that it is NOT an error.
        if resp and _is_error_response(resp):
            continue
        return True, resp
    return False, last


def _save_and_reset(ser: serial.Serial, protocol: Protocol, do_reset: bool) -> Tuple[str, str]:
    save_cmd = "$SAVE" if protocol == "fw2" else "Save"
    save_resp = send_command(ser, save_cmd, wait_s=6.0)
    reset_resp = ""
    if do_reset:
        reset_cmd = "$RESET" if protocol == "fw2" else "Reset"
        reset_resp = send_command(ser, reset_cmd, wait_s=1.0)
    return save_resp, reset_resp


def _set_mode_terminal(ser: serial.Serial, protocol: Protocol) -> bool:
    """Best-effort: set Mode to Smart Sensor Terminal."""
    candidates: List[str]
    if protocol == "fw2":
        candidates = [
            "$SET Mode Smart Sensor Terminal",
            "$SET Mode Smart Sensor Terminal FW2",
            '$SET Mode "Smart Sensor Terminal"',
            '$SET Mode "Smart Sensor Terminal FW2"',
        ]
    else:
        candidates = [
            "Set Mode(Smart Sensor Terminal)",
            "Set Mode(Smart Sensor Terminal FW2)",
        ]

    for cmd in candidates:
        resp = send_command(ser, cmd, wait_s=1.2)
        if resp and _is_error_response(resp):
            continue
        # Empty response is ambiguous; treat as success and let later Get Mode confirm.
        return True
    return False


def configure_sensor_interval(
    port: str,
    interval_s: float,
    *,
    do_reset: bool = True,
    force_terminal_mode: bool = False,
) -> bool:
    """Configure a single sensor's interval"""
    print(f"\n{'='*60}")
    print(f"Configuring {port}")
    print('='*60)
    
    try:
        # Open serial connection
        print(f"Opening {port}...")
        ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=2.0,
            # Most of the working debug tools in this repo use xonxoff=False.
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        
        print("✓ Port opened")
        
        _wake_sensor(ser)

        protocol, probe_resp = detect_protocol(ser)
        if not protocol:
            print("✗ Could not determine command protocol")
            print(f"  Last response: {probe_resp[:120] if probe_resp else 'empty'}")
            print("  Next step: run debug tool: python src/debug_sensor_responses.py")
            ser.close()
            return False

        print(f"✓ Detected protocol: {protocol}")

        # If the sensor is streaming, Stop often helps.
        print("Stopping any active streaming...")
        _stop_streaming(ser, protocol)
        _wake_sensor(ser)

        # Some properties are writable only after Passkey(1), but Interval is often NOT protected.
        # So we try Passkey, but we don't fail hard if the device rejects it.
        print("Setting Passkey (try 1 / 1000)...")
        passkey_ok, passkey_resp = _try_set_passkey(ser, protocol)
        if passkey_resp:
            if passkey_ok:
                print("✓ Passkey accepted")
            else:
                print("⚠ Passkey rejected")
                print(f"  Response: {passkey_resp.strip()[:200]}")
        else:
            if passkey_ok:
                print("✓ Passkey sent (no response)")
            else:
                print("⚠ Passkey failed (no response)")

        # Print current Mode/Interval for diagnostics.
        mode_before = _get_property(ser, protocol, "Mode")
        if mode_before and _is_error_response(mode_before):
            # Some sensors/firmware variants expose the same concept under different property names
            # or only in some modes.
            for alt in ["Output", "Interface", "Protocol"]:
                alt_resp = _get_property(ser, protocol, alt)
                if alt_resp and not _is_error_response(alt_resp):
                    mode_before = alt_resp
                    break

        interval_before = _get_property(ser, protocol, "Interval")
        if mode_before:
            print(f"Current Mode response: {mode_before.strip()[:120]}")
        if interval_before:
            print(f"Current Interval response: {interval_before.strip()[:120]}")

        if force_terminal_mode:
            print("Forcing Mode=Smart Sensor Terminal...")
            ok = _set_mode_terminal(ser, protocol)
            if not ok:
                print("⚠ Could not set Mode to Smart Sensor Terminal")
                print("  Continuing anyway (Mode change is optional for changing Interval).")
                # Do not fail hard here; many setups simply don't expose Mode over this interface.
            else:
                save_resp, _ = _save_and_reset(ser, protocol, do_reset=True)
                if save_resp and _is_error_response(save_resp):
                    print("⚠ Save failed while changing Mode")
                    print(f"  Response: {save_resp.strip()[:200]}")
                time.sleep(1.0)
                _wake_sensor(ser)
                mode_after = _get_property(ser, protocol, "Mode")
                if mode_after:
                    print(f"Mode after: {mode_after.strip()[:120]}")

        print(f"Setting Interval={interval_s}...")
        set_interval_resp = _set_property(ser, protocol, "Interval", str(interval_s), wait_s=1.2)
        if set_interval_resp and _is_error_response(set_interval_resp):
            print("✗ Interval rejected")
            print(f"  Response: {set_interval_resp.strip()[:200]}")
            ser.close()
            return False

        print("Disabling polled mode (Enable Polled Mode=no)...")
        polled_resp = _set_property(ser, protocol, "Enable Polled Mode", "no", wait_s=1.2)
        if polled_resp and _is_error_response(polled_resp):
            print("⚠ Warning: could not change polled mode")
            print(f"  Response: {polled_resp.strip()[:200]}")

        print("Saving to flash...")
        save_resp, reset_resp = _save_and_reset(ser, protocol, do_reset)
        if save_resp and _is_error_response(save_resp):
            print("✗ Save failed")
            print(f"  Response: {save_resp.strip()[:200]}")
            ser.close()
            return False

        # Re-read interval to confirm (best-effort but we try to be robust):
        # After Reset, the device may reboot and/or start streaming again.
        ser.close()
        time.sleep(0.5)

        interval_after_txt = ""
        interval_after_val: Optional[float] = None
        try:
            if do_reset:
                time.sleep(3.0)

            verify_ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=2.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            _wake_sensor(verify_ser)
            verify_protocol, _ = detect_protocol(verify_ser)
            if verify_protocol:
                protocol = verify_protocol
            _stop_streaming(verify_ser, protocol)
            _wake_sensor(verify_ser)

            interval_after_txt = _get_property(verify_ser, protocol, "Interval")
            if interval_after_txt:
                print(f"Interval after: {interval_after_txt.strip()[:120]}")
                if not _is_error_response(interval_after_txt):
                    interval_after_val = _extract_last_float(interval_after_txt)
            verify_ser.close()
        except Exception as e:
            print(f"⚠ Warning: could not verify Interval after save/reset: {e}")

        if interval_after_txt and _is_error_response(interval_after_txt):
            print("⚠ Warning: sensor responded with SYNTAX ERROR when verifying Interval")
            print("  The interval may still have been applied; confirm by observing data rate.")
        elif interval_after_val is not None:
            if abs(interval_after_val - float(interval_s)) > 1e-6:
                print(f"✗ Interval verify mismatch: expected {interval_s}, got {interval_after_val}")
                print("  Configuration may not have applied. Try again with --force-terminal-mode or --no-reset.")
                return False
        
        print(f"\n{'='*60}")
        print(f"✓ SUCCESS: {port} configured to {interval_s}s interval")
        print('='*60)
        
        return True
        
    except serial.SerialException as e:
        print(f"✗ Serial port error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set sampling interval on Aanderaa sensors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python set_interval.py --interval 5
  python set_interval.py --interval 2 --ports COM12 COM13 COM14
  python set_interval.py --interval 10 --no-reset

Notes:
    - RS-232 vs RS-422 is hardware (cable/sensor variant); you can't change that in software.
    - The 'Mode' property selects AiCaP vs Smart Sensor Terminal vs AADI Real-Time etc.
  - Requires bidirectional cable connection
  - Default reads ports from sensor_config.json
        """
    )
    
    parser.add_argument(
        "--interval",
        type=float,
        required=True,
        help="Sampling interval in seconds (e.g., 5, 2, 10)"
    )
    
    parser.add_argument(
        "--ports",
        nargs="*",
        default=None,
        help="COM ports to configure (e.g., COM12 COM13)"
    )
    
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Read ports from sensor_config.json (default if no ports specified)"
    )
    
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Don't reset sensor after saving (not recommended)"
    )

    parser.add_argument(
        "--force-terminal-mode",
        action="store_true",
        help="Attempt to set Mode=Smart Sensor Terminal before changing Interval (use if device is in AiCaP/AADI modes)",
    )
    
    args = parser.parse_args(argv)
    
    # Determine which ports to configure
    ports: List[str] = []
    
    if args.ports:
        # Use explicitly specified ports
        for p in args.ports:
            port = str(p).upper()
            if not port.startswith("COM"):
                port = "COM" + port
            ports.append(port)
    else:
        # Default: read from config file
        script_dir = Path(__file__).parent
        config_path = script_dir / "sensor_config.json"
        
        if not config_path.exists():
            print(f"Error: {config_path} not found")
            print("Please specify ports with --ports or create sensor_config.json")
            return 1
        
        ports = load_ports_from_config(config_path)
    
    if not ports:
        print("Error: No COM ports specified")
        print("Use --ports COM12 COM13 or ensure sensor_config.json exists")
        return 1
    
    interval_s = args.interval
    do_reset = not args.no_reset
    force_terminal_mode = bool(args.force_terminal_mode)
    
    if interval_s <= 0:
        print(f"Error: Interval must be positive (got {interval_s})")
        return 1
    
    # Print summary
    print("\n" + "="*60)
    print("Aanderaa Sensor Interval Configuration")
    print("="*60)
    print(f"Interval: {interval_s} seconds")
    print(f"Ports: {', '.join(ports)}")
    print(f"Reset after save: {'Yes' if do_reset else 'No'}")
    print(f"Force terminal mode: {'Yes' if force_terminal_mode else 'No'}")
    print("="*60)
    
    # Configure each sensor
    success_count = 0
    for port in ports:
        if configure_sensor_interval(port, interval_s, do_reset=do_reset, force_terminal_mode=force_terminal_mode):
            success_count += 1
        time.sleep(1.0)  # Brief pause between sensors
    
    # Summary
    print("\n" + "="*60)
    print("CONFIGURATION SUMMARY")
    print("="*60)
    print(f"Configured: {success_count}/{len(ports)} sensors")
    
    if success_count == len(ports):
        print("✓ All sensors configured successfully!")
        print(f"\nSensors will now sample every {interval_s} seconds")
        print("You can now run aanderaa_reader_gui.py to collect data")
    else:
        print(f"⚠ {len(ports) - success_count} sensor(s) failed")
        print("\nTroubleshooting:")
        print("  1. Check sensor power supply (6-14V DC)")
        print("  2. Verify correct COM ports in Device Manager")
        print("  3. Ensure sensors are in RS-232 mode (not AiCaP)")
        print("  4. Try power cycling sensors that failed")
        print("  5. Check cable connections")
    
    print("="*60 + "\n")
    
    return 0 if success_count == len(ports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
