"""
Aanderaa Sensor Reader - Custom Tab-Delimited Protocol
Works with sensors in NI-VISA mode
"""
import serial
import time
import json
from datetime import datetime
from pathlib import Path
import re
from typing import Optional, List, Dict
import threading
import queue
from dataclasses import dataclass

from config_manager import resolve_config_path


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _strip_control_chars(s: str) -> str:
    # Keep tab/newline/carriage return; drop other ASCII control chars.
    return _CONTROL_CHARS_RE.sub("", s)


def _infer_sensor_type(product: str) -> str:
    p = (product or "").upper()
    if p.startswith("4117") or p.startswith("5217") or p.startswith("5218"):
        return "pressure"
    if p.startswith("4330") or p.startswith("4835") or p.startswith("4831"):
        return "oxygen"
    if p.startswith("5819") or p.startswith("5990"):
        return "conductivity"
    return "unknown"

class AanderaaSensorCustom:
    """Handler for Aanderaa sensors using custom tab-delimited protocol"""
    
    def __init__(self, com_port, name="Unknown", sensor_type=""):
        self.com_port = com_port
        self.name = name
        self.sensor_type = sensor_type
        self.serial_port = None
        self.is_connected = False
        self.product_number = None
        self.serial_number = None
        self.protocol_mode = "unknown"  # 'tab', 'terminal', 'unknown'
        self.last_measurement: Dict[str, str] = {}
        self.last_measurement_time: Optional[datetime] = None

    def parse_tab_frame(self, data_frame: List[str]) -> Dict[str, str]:
        """Convert a tab-delimited frame fields list into a measurement dict."""
        if len(data_frame) < 2:
            return {}

        product = data_frame[0]
        serial_no = data_frame[1]
        values = data_frame[2:]

        inferred = _infer_sensor_type(product)
        if inferred != "unknown" and self.sensor_type != inferred:
            self.sensor_type = inferred

        self.product_number = product
        self.serial_number = serial_no
        self.name = f"Sensor {product} SN {serial_no}"
        self.protocol_mode = "tab"

        measurements: Dict[str, str] = {
            "ProductNumber": product,
            "SerialNumber": serial_no,
        }

        # Always keep the raw value columns so you can see extra parameters
        # even if the labeling below isn't perfect for a given firmware/config.
        for i, v in enumerate(values, start=1):
            measurements[f"Value{i}"] = v

        if self.sensor_type == "oxygen" and len(values) >= 3:
            measurements["O2Concentration"] = measurements["Value1"]
            measurements["O2Saturation"] = measurements["Value2"]
            measurements["Temperature"] = measurements["Value3"]
        elif self.sensor_type == "conductivity":
            # Common output pattern: Conductivity, Salinity, Temperature
            if len(values) >= 2:
                measurements["Conductivity"] = measurements["Value1"]
                measurements["Temperature"] = measurements["Value2"]
            if len(values) >= 3:
                measurements["Salinity"] = measurements["Value2"]
                measurements["Temperature"] = measurements["Value3"]
        elif self.sensor_type == "pressure" and len(values) >= 2:
            measurements["Pressure"] = measurements["Value1"]
            measurements["Temperature"] = measurements["Value2"]

        self.last_measurement = measurements
        self.last_measurement_time = datetime.now()
        return measurements

    def _read_for(self, duration_s: float) -> str:
        """Read whatever the sensor emits for a short duration."""
        if not self.serial_port:
            return ""

        end_time = time.time() + duration_s
        chunks: List[str] = []
        while time.time() < end_time:
            waiting = self.serial_port.in_waiting
            if waiting > 0:
                chunks.append(self.serial_port.read(waiting).decode("ascii", errors="ignore"))
                # small sleep to allow framing
                time.sleep(0.05)
            else:
                time.sleep(0.05)
        return "".join(chunks)

    def _extract_tab_frames(self, raw: str) -> List[List[str]]:
        """Return list of tab-delimited frames (fields list)."""
        if not raw:
            return []
        text = _strip_control_chars(raw).replace("!", "")
        frames: List[List[str]] = []
        for line in text.replace("\r", "\n").split("\n"):
            if "\t" not in line:
                continue
            fields = [f.strip() for f in line.split("\t") if f.strip() != ""]
            if not fields:
                continue
            frames.append(fields)
        return frames

    def _pick_best_data_frame(self, frames: List[List[str]]) -> Optional[List[str]]:
        """Prefer non-error frames that look like '<product> <serial> <values...>'."""
        best = None
        for fields in frames:
            if len(fields) < 2:
                continue
            # Typical error: '*\tERROR\tSYNTAX ERROR'
            if fields[0] == "*" and len(fields) >= 2 and fields[1].upper() == "ERROR":
                continue

            product = fields[0]
            serial = fields[1]
            # Heuristic: product often starts with 4 digits
            if not re.match(r"^\d{4}.*", product):
                continue
            if not re.match(r"^\d+", serial):
                # Some devices might include non-numeric serial; still accept if we have values
                if len(fields) < 3:
                    continue
            best = fields
        return best
    
    def connect(self):
        """Connect to sensor"""
        try:
            print(f"  Attempting to open {self.com_port}...")
            self.serial_port = serial.Serial(
                port=self.com_port,
                baudrate=9600,
                bytesize=8,
                parity='N',
                stopbits=1,
                # Short timeout helps responsive shutdown in continuous mode.
                timeout=1.0,
                # Some Aanderaa/adapter setups actively use XON/XOFF (\x11/\x13).
                # Enabling it prevents these control bytes from clogging the stream.
                xonxoff=True,
                rtscts=False,
                dsrdtr=False
            )
            
            print(f"  Port {self.com_port} opened, clearing buffers...")
            # Clear buffers
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            time.sleep(0.3)
            
            # Send wake-up
            print(f"  Sending wake-up to {self.com_port}...")
            # Wake sequence: CR/LF + '%' (common for Aanderaa sleep wake).
            for _ in range(3):
                self.serial_port.write(b"\r\n")
                time.sleep(0.15)
            # ';' is used by SensorTerminalSession and is generally safe as a wake character.
            self.serial_port.write(b";")

            wake_resp = self._read_for(1.2)
            if wake_resp:
                print(f"  Wake response: {repr(wake_resp)}")

            # PROBE 1: passively listen for a tab-delimited data frame.
            probe = self._read_for(1.5)
            frames = self._extract_tab_frames(probe)
            data_frame = self._pick_best_data_frame(frames)

            # PROBE 2: if nothing yet, send a harmless newline (some setups only emit after a trigger)
            if not data_frame:
                self.serial_port.write(b"\r\n")
                probe2 = self._read_for(1.5)
                frames2 = self._extract_tab_frames(probe2)
                data_frame = self._pick_best_data_frame(frames2)

            # NOTE: Avoid sending Terminal-mode probes here.
            # Some sensors speak FW3 (Get/Set) and will respond to "$GET" with a SYNTAX ERROR that
            # leaves stray '*' bytes in the stream buffer and confuses the streaming parser.

            if data_frame:
                self.protocol_mode = "tab"
                self.product_number = data_frame[0]
                self.serial_number = data_frame[1]
                inferred = _infer_sensor_type(self.product_number)
                if inferred != "unknown" and self.sensor_type and self.sensor_type != "unknown" and self.sensor_type != inferred:
                    print(f"  ℹ Detected product {self.product_number}; overriding configured sensor_type '{self.sensor_type}' -> '{inferred}'")
                if inferred != "unknown":
                    self.sensor_type = inferred
                self.name = f"Sensor {self.product_number} SN {self.serial_number}"
                self.is_connected = True
                print(f"✓ Connected to {self.name} on {self.com_port} ({self.protocol_mode} mode)")
                return True

            # If we got *any* response at all (wake / error), keep it as a soft-connect
            # but mark as unknown; measurements may still start streaming.
            if wake_resp:
                self.protocol_mode = "unknown"
                self.is_connected = True
                print(f"✓ Port responsive on {self.com_port}, awaiting first data frame...")
                return True

            print(f"✗ No usable response/data from {self.com_port}")
            self.serial_port.close()
            return False
            
        except Exception as e:
            print(f"✗ Error connecting to {self.com_port}: {e}")
            return False
    
    def get_measurement(self):
        """Get measurement from sensor"""
        if not self.is_connected or not self.serial_port:
            return {}
        
        try:
            # Important: do NOT clear the input buffer here.
            # In tab-delimited/streaming modes, clearing discards real measurements.

            # Many devices emit a frame on their own interval (e.g., ~15–30s).
            # Use a slightly wider window so we don't miss samples.
            response = self._read_for(2.2)

            # If nothing arrived, try to gently trigger output.
            if not response:
                self.serial_port.write(b"\r\n")
                response = self._read_for(2.2)
            
            # Debug output
            if response:
                print(f"  [DEBUG] Raw response: {repr(response)}")

            frames = self._extract_tab_frames(response)
            data_frame = self._pick_best_data_frame(frames)
            if not data_frame:
                return {}

            return self.parse_tab_frame(data_frame)
            
        except Exception as e:
            print(f"✗ Error reading from {self.name}: {e}")
            return {}
    
    def disconnect(self):
        """Close connection"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.is_connected = False


@dataclass
class SensorEvent:
    timestamp: datetime
    com_port: str
    name: str
    measurements: Dict[str, str]
    raw_line: str


def _reader_loop(sensor: AanderaaSensorCustom, out_queue: "queue.Queue[SensorEvent]", stop_event: threading.Event) -> None:
    if not sensor.serial_port:
        return

    buffer = ""
    last_frame = time.time()
    last_debug = time.time()
    last_nudge = time.time()
    last_do = time.time()

    while not stop_event.is_set():
        try:
            # Read whatever is available; if nothing is buffered, read a small chunk.
            # Using a larger read helps capture complete frames that arrive in bursts.
            chunk = sensor.serial_port.read(sensor.serial_port.in_waiting or 256)
            if chunk:
                buffer += chunk.decode("ascii", errors="ignore")

            # Drop pure noise/echo characters quickly.
            if buffer and all(c in "%;!*\r\n\t \x11\x13" for c in buffer):
                # Keep tabs/newlines if present (they might precede a real frame).
                if "\t" not in buffer:
                    buffer = ""

            now = time.time()

            # If no frames arrive, periodically send a harmless newline.
            # This does not change configuration; it just prompts some devices.
            if now - last_frame > 8.0 and now - last_nudge > 8.0:
                try:
                    sensor.serial_port.write(b"\r\n")
                except Exception:
                    pass
                last_nudge = now

            # If still nothing for a long time, try a one-shot measurement trigger.
            if now - last_frame > 25.0 and now - last_do > 25.0:
                try:
                    sensor.serial_port.write(b"Do\r\n")
                    sensor.serial_port.write(b"DO\r\n")
                except Exception:
                    pass
                last_do = now

            # Some setups may deliver frames without newline terminators.
            if "\n" not in buffer and "\r" not in buffer:
                if buffer and (time.time() - last_debug) > 10.0:
                    tail = buffer[-120:].replace("\x11", "").replace("\x13", "")
                    print(f"  [DEBUG {sensor.com_port}] waiting for frame, buffer tail: {repr(tail)}")
                    last_debug = time.time()
                if "\t" in buffer and len(buffer) > 20:
                    frames = sensor._extract_tab_frames(buffer)
                    data_frame = sensor._pick_best_data_frame(frames)
                    if data_frame:
                        measurements = sensor.parse_tab_frame(data_frame)
                        if measurements:
                            ts = sensor.last_measurement_time or datetime.now()
                            out_queue.put(
                                SensorEvent(
                                    timestamp=ts,
                                    com_port=sensor.com_port,
                                    name=sensor.name,
                                    measurements=measurements,
                                    raw_line=buffer,
                                )
                            )
                            last_frame = time.time()
                            buffer = ""
                continue

            lines = buffer.replace("\r", "\n").split("\n")
            buffer = lines[-1]

            for line in lines[:-1]:
                if not line.strip():
                    continue
                frames = sensor._extract_tab_frames(line)
                data_frame = sensor._pick_best_data_frame(frames)
                if not data_frame:
                    continue

                measurements = sensor.parse_tab_frame(data_frame)
                if not measurements:
                    continue

                last_frame = time.time()

                ts = sensor.last_measurement_time or datetime.now()
                out_queue.put(
                    SensorEvent(
                        timestamp=ts,
                        com_port=sensor.com_port,
                        name=sensor.name,
                        measurements=measurements,
                        raw_line=line,
                    )
                )
        except Exception:
            time.sleep(0.05)


def load_config(config_path="sensor_config.json"):
    """Load sensor configuration"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get('sensors', [])
    except FileNotFoundError:
        print(f"✗ Config file not found: {config_path}")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ Error parsing config file: {e}")
        return []


def _suggest_name(product: str, serial_no: str) -> str:
    inferred = _infer_sensor_type(product)
    if inferred == "oxygen":
        return f"Oxygen Optode {product} SN {serial_no}"
    if inferred == "conductivity":
        return f"Conductivity Sensor {product} SN {serial_no}"
    if inferred == "pressure":
        return f"Pressure Sensor {product} SN {serial_no}"
    return f"Sensor {product} SN {serial_no}"


def print_suggested_config(sensors: List[AanderaaSensorCustom], config_path: Path) -> None:
    detected = [s for s in sensors if s.product_number and s.serial_number]
    if not detected:
        return

    print("\n" + "=" * 60)
    print("Suggested sensor_config.json (based on live detection)")
    print("=" * 60)

    payload = {
        "sensors": [
            {
                "name": _suggest_name(s.product_number, s.serial_number),
                "com_port": s.com_port,
                "baudrate": 9600,
                "sensor_type": _infer_sensor_type(s.product_number),
                "timeout": 5,
            }
            for s in detected
        ]
    }

    print(json.dumps(payload, indent=2))
    print(f"\nConfig file location: {config_path}")


def prime_identification(sensors: List[AanderaaSensorCustom], max_wait_s: float = 8.0) -> None:
    """Wait briefly for each sensor to emit at least one valid tab frame.

    Some devices only transmit on their own interval (e.g., 15–30s). This function
    opportunistically captures IDs without requiring a full extra polling cycle.
    """
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        remaining = [s for s in sensors if not (s.product_number and s.serial_number)]
        if not remaining:
            return

        for s in remaining:
            if not s.serial_port:
                continue
            # Read a short window and look for a valid data frame.
            raw = s._read_for(0.6)
            frames = s._extract_tab_frames(raw)
            data_frame = s._pick_best_data_frame(frames)
            if not data_frame:
                continue

            product = data_frame[0]
            serial_no = data_frame[1]
            s.product_number = product
            s.serial_number = serial_no
            inferred = _infer_sensor_type(product)
            if inferred != "unknown":
                s.sensor_type = inferred
            s.name = f"Sensor {product} SN {serial_no}"

        time.sleep(0.1)


def main():
    """Main function"""
    print("\n" + "="*60)
    print("Aanderaa Sensor Reader - Custom Protocol")
    print("="*60 + "\n")
    
    # Load configuration
    script_dir = Path(__file__).parent
    repo_config_path = script_dir / "sensor_config.json"
    config_path = resolve_config_path(repo_config_path)
    print(f"Using config: {config_path}")
    
    sensor_configs = load_config(str(config_path))
    
    if not sensor_configs:
        print("No sensors configured. Using defaults: COM12, COM13, COM14")
        sensor_configs = [
            {"name": "Sensor 1", "com_port": "COM12", "sensor_type": "unknown"},
            {"name": "Sensor 2", "com_port": "COM13", "sensor_type": "unknown"},
            {"name": "Sensor 3", "com_port": "COM14", "sensor_type": "unknown"}
        ]
    
    # Create sensor objects
    sensors = []
    for config in sensor_configs:
        sensor = AanderaaSensorCustom(
            com_port=config['com_port'],
            name=config.get('name', 'Unknown'),
            sensor_type=config.get('sensor_type', '')
        )
        sensors.append(sensor)
    
    # Connect to sensors
    print("Connecting to sensors...")
    print("-"*60 + "\n")
    
    connected_sensors = []
    for sensor in sensors:
        if sensor.connect():
            connected_sensors.append(sensor)
        time.sleep(0.3)
    
    if not connected_sensors:
        print("\n✗ No sensors connected!")
        return
    
    print(f"\n✓ Connected to {len(connected_sensors)} sensor(s)")

    # Show a config that matches the detected mapping
    prime_identification(connected_sensors, max_wait_s=8.0)
    print_suggested_config(connected_sensors, config_path)
    
    # Read measurements continuously
    print("\n" + "="*60)
    print("Reading Measurements (Press Ctrl+C to stop)")
    print("="*60 + "\n")

    stop_event = threading.Event()
    event_queue: "queue.Queue[SensorEvent]" = queue.Queue()

    threads: List[threading.Thread] = []
    for s in connected_sensors:
        t = threading.Thread(target=_reader_loop, args=(s, event_queue, stop_event), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            ev = event_queue.get()
            print(f"\n[{ev.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {ev.name} ({ev.com_port})")
            for key, value in ev.measurements.items():
                print(f"  {key}: {value}")

    except KeyboardInterrupt:
        print("\n\n✓ Stopping measurements...")
    
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=1.0)
        # Disconnect all sensors
        for sensor in connected_sensors:
            sensor.disconnect()
        print("✓ All sensors disconnected")


if __name__ == "__main__":
    main()
