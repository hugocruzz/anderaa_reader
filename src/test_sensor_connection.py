"""
Comprehensive Aanderaa Sensor Connection Test
Tests connectivity and identifies sensor types
"""

import serial
import serial.tools.list_ports
import time
import sys
import re


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _strip_control_chars(s: str) -> str:
    # Keep tab/newline/carriage return; drop other ASCII control chars.
    return _CONTROL_CHARS_RE.sub("", s)


def _extract_tab_frames(raw: str):
    if not raw:
        return []
    text = _strip_control_chars(raw).replace("!", "")
    frames = []
    for line in text.replace("\r", "\n").split("\n"):
        if "\t" not in line:
            continue
        fields = [f.strip() for f in line.split("\t") if f.strip()]
        if fields:
            frames.append(fields)
    return frames


def _pick_best_data_frame(frames):
    best = None
    for fields in frames:
        if len(fields) < 2:
            continue
        # Typical error: '*\tERROR\tSYNTAX ERROR'
        if fields[0] == "*" and fields[1].upper() == "ERROR":
            continue
        product = fields[0]
        serial_no = fields[1]
        if not re.match(r"^\d{4}.*", product):
            continue
        if not re.match(r"^\d+", serial_no) and len(fields) < 3:
            continue
        best = fields
    return best


def _infer_sensor_type(product: str) -> str:
    p = (product or "").upper()
    if p.startswith("4117") or p.startswith("5217") or p.startswith("5218"):
        return "pressure"
    if p.startswith("4330") or p.startswith("4835") or p.startswith("4831"):
        return "oxygen"
    if p.startswith("5819") or p.startswith("5990"):
        return "conductivity"
    return "unknown"


def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*70)
    print(text)
    print("="*70)


def list_ports():
    """List all available COM ports"""
    print_header("Step 1: Scanning for COM Ports")
    
    ports = list(serial.tools.list_ports.comports())
    
    if not ports:
        print("\n✗ NO COM PORTS FOUND!")
        print("\nPossible issues:")
        print("  • Sensors not connected via USB")
        print("  • USB-to-Serial adapter drivers not installed")
        print("  • Cable issues")
        return []
    
    print(f"\n✓ Found {len(ports)} COM port(s):\n")
    for i, port in enumerate(ports, 1):
        print(f"{i}. {port.device}")
        print(f"   Description: {port.description}")
        if port.manufacturer:
            print(f"   Manufacturer: {port.manufacturer}")
        print()
    
    return [p.device for p in ports]


def test_single_port(port_name, verbose=True):
    """Test a single COM port with Aanderaa sensor"""
    
    if verbose:
        print(f"\n{'─'*70}")
        print(f"Testing: {port_name}")
        print('─'*70)
    
    # Default baudrate for Aanderaa sensors
    baudrate = 9600
    
    try:
        if verbose:
            print(f"\n1. Opening port {port_name} at {baudrate} baud...")
        
        ser = serial.Serial(
            port=port_name,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            write_timeout=2
        )

        # Enable XON/XOFF (sensor sometimes emits \x11/\x13)
        ser.xonxoff = True
        
        if verbose:
            print("   ✓ Port opened successfully")
        
        # Step 1: Wake up sensor (per Aanderaa documentation)
        if verbose:
            print("\n2. Waking up sensor...")
            print("   (Using documented wake-up protocol: carriage returns + '%' character)")
        
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Method 1: Carriage returns (traditional)
        for i in range(5):
            ser.write(b'\r\n')
            time.sleep(0.15)
        
        # Method 2: '%' character (per documentation for communication sleep)
        ser.write(b'%')
        time.sleep(0.3)
        
        # Wait for communication ready indicator '!'
        time.sleep(0.7)
        
        # Check for any wake-up response
        if ser.in_waiting > 0:
            wake_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            if verbose:
                print(f"   ✓ Received wake-up response: {repr(wake_response[:50])}")
        else:
            if verbose:
                print("   ℹ No immediate wake-up response (normal)")
        
        # Step 2: Prefer tab-delimited streaming mode (what your NI setup is using)
        if verbose:
            print("\n3. Listening for tab-delimited frame (streaming mode)...")

        product_name = ""
        serial_number = ""
        mode = "unknown"

        # Passively listen
        time.sleep(1.2)
        raw = ""
        if ser.in_waiting > 0:
            raw = ser.read(ser.in_waiting).decode("ascii", errors="ignore")

        frames = _extract_tab_frames(raw)
        data_frame = _pick_best_data_frame(frames)

        # If nothing yet, nudge once
        if not data_frame:
            ser.write(b"\r\n")
            time.sleep(1.2)
            raw2 = ""
            if ser.in_waiting > 0:
                raw2 = ser.read(ser.in_waiting).decode("ascii", errors="ignore")
            frames2 = _extract_tab_frames(raw2)
            data_frame = _pick_best_data_frame(frames2)
            raw = raw + raw2

        if data_frame:
            mode = "tab"
            product_name = data_frame[0]
            serial_number = data_frame[1]
            if verbose:
                print(f"   ✓ Frame: {product_name} {serial_number} ...")
        else:
            if verbose and raw:
                print(f"   ℹ Raw: {repr(raw[:200])}")
        
        # Step 3 (fallback): try Terminal-mode queries
        help_response = ""
        sensor_mode = ""

        if not product_name:
            if verbose:
                print("\n4. Fallback: trying Terminal-mode commands ($GET / HELP)...")

            ser.reset_input_buffer()
            ser.write(b'$GET ProductName\r\n')
            time.sleep(0.8)
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                if verbose:
                    print(f"   ProductName response: {repr(response)}")
                for line in response.split('\n'):
                    if '=' in line:
                        product_name = line.split('=')[1].strip()
                        break

            ser.reset_input_buffer()
            ser.write(b'$GET SerialNumber\r\n')
            time.sleep(0.8)
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                if verbose:
                    print(f"   SerialNumber response: {repr(response)}")
                for line in response.split('\n'):
                    if '=' in line:
                        serial_number = line.split('=')[1].strip()
                        break

            ser.reset_input_buffer()
            ser.write(b'HELP\r\n')
            time.sleep(0.8)
            if ser.in_waiting > 0:
                help_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                if verbose:
                    print(f"   HELP response ({len(help_response)} chars)")

            ser.reset_input_buffer()
            ser.write(b'$GET Mode\r\n')
            time.sleep(0.8)
            if ser.in_waiting > 0:
                mode_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                for line in mode_response.split('\n'):
                    if '=' in line:
                        sensor_mode = line.split('=')[1].strip()
                        break

            mode = "terminal" if (product_name or help_response) else mode
        
        # Report mode hints
        if verbose and mode == "terminal" and sensor_mode:
            if 'AICAP' in sensor_mode.upper():
                print(f"   ⚠ WARNING: Sensor is in AiCaP mode (not standalone RS-232)")
        
        ser.close()
        
        # Determine sensor type
        sensor_type = _infer_sensor_type(product_name) if product_name else "unknown"
        
        # Summary
        if verbose:
            print("\n" + "─"*70)
            print("RESULT:")
            print("─"*70)
        
        success = bool(product_name or help_response)
        
        if success:
            if verbose:
                print(f"✓ SENSOR DETECTED!")
                if product_name:
                    print(f"  Product: {product_name}")
                if serial_number:
                    print(f"  Serial Number: {serial_number}")
                if sensor_type != "Unknown":
                    print(f"  Type: {sensor_type}")
                print(f"  Port: {port_name}")
                print(f"  Baudrate: {baudrate}")
            
            return {
                'success': True,
                'port': port_name,
                'baudrate': baudrate,
                'product_name': product_name,
                'serial_number': serial_number,
                'sensor_type': sensor_type,
                'mode': mode
            }
        else:
            if verbose:
                print("✗ No response from sensor")
                print("\nTroubleshooting:")
                print("  • Check sensor power (6-14V DC)")
                print("  • Verify cable connections")
                print("  • Ensure sensor is in Smart Sensor Terminal mode")
            
            return {
                'success': False,
                'port': port_name,
                'baudrate': baudrate
            }
        
    except serial.SerialException as e:
        if verbose:
            print(f"\n✗ Serial port error: {e}")
        return {'success': False, 'port': port_name, 'error': str(e)}
    
    except Exception as e:
        if verbose:
            print(f"\n✗ Unexpected error: {e}")
        return {'success': False, 'port': port_name, 'error': str(e)}


def test_all_ports(ports):
    """Test all available ports"""
    print_header("Step 2: Testing Each Port for Aanderaa Sensors")
    
    results = []
    
    for port in ports:
        result = test_single_port(port, verbose=True)
        results.append(result)
        time.sleep(0.5)
    
    return results


def generate_config(results):
    """Generate configuration based on test results"""
    print_header("Step 3: Configuration Summary")
    
    detected = [r for r in results if r.get('success')]
    
    if not detected:
        print("\n✗ No sensors detected!")
        print("\nPlease check:")
        print("  1. Sensor power supply (6-14V DC)")
        print("  2. Cable connections (use proper RS-232 cables)")
        print("  3. USB-to-Serial adapter drivers")
        print("  4. Sensor mode (should be Smart Sensor Terminal, not AiCaP)")
        return
    
    print(f"\n✓ Detected {len(detected)} sensor(s):\n")
    
    for i, sensor in enumerate(detected, 1):
        print(f"{i}. {sensor.get('sensor_type', 'Unknown')} on {sensor['port']}")
        if sensor.get('product_name'):
            print(f"   Product: {sensor['product_name']}")
        if sensor.get('serial_number'):
            print(f"   S/N: {sensor['serial_number']}")
        print(f"   Baudrate: {sensor['baudrate']}")
        if sensor.get('mode'):
            mode = sensor['mode']
            if 'AiCaP' in mode or 'AICAP' in mode.upper():
                print(f"   ⚠ Mode: {mode} (NEEDS TO BE CHANGED TO TERMINAL!)")
            else:
                print(f"   Mode: {mode}")
        print()
    
    # Generate JSON config
    print("\n" + "─"*70)
    print("Suggested sensor_config.json:")
    print("─"*70)
    print("\n{")
    print('  "sensors": [')
    
    for i, sensor in enumerate(detected):
        name = sensor.get('product_name', 'Aanderaa Sensor')
        if sensor.get('serial_number'):
            name += f" SN {sensor['serial_number']}"
        
        sensor_type = "unknown"
        if '4117' in sensor.get('product_name', '').upper():
            sensor_type = "pressure"
        elif '4330' in sensor.get('product_name', '').upper():
            sensor_type = "oxygen"
        elif '5819' in sensor.get('product_name', '').upper() or '5990' in sensor.get('product_name', '').upper():
            sensor_type = "conductivity"
        
        print('    {')
        print(f'      "name": "{name}",')
        print(f'      "com_port": "{sensor["port"]}",')
        print(f'      "baudrate": {sensor["baudrate"]},')
        print(f'      "sensor_type": "{sensor_type}",')
        print('      "timeout": 2')
        print('    }' + (',' if i < len(detected) - 1 else ''))
    
    print('  ]')
    print('}')


def main():
    """Main test function"""
    print("\n" + "="*70)
    print("AANDERAA SENSOR CONNECTION DIAGNOSTIC")
    print("="*70)
    print("\nThis tool will:")
    print("  1. Scan for available COM ports")
    print("  2. Test each port for Aanderaa sensors")
    print("  3. Generate configuration for detected sensors")
    print("\nMake sure sensors are:")
    print("  ✓ Powered (6-14V DC)")
    print("  ✓ Connected via RS-232 cable")
    print("  ✓ In Smart Sensor Terminal mode")
    
    input("\nPress Enter to start...")
    
    # Step 1: List ports
    ports = list_ports()
    
    if not ports:
        print("\n✗ No COM ports available. Cannot proceed.")
        sys.exit(1)
    
    # Step 2: Test all ports
    results = test_all_ports(ports)
    
    # Step 3: Generate config
    generate_config(results)
    
    print("\n" + "="*70)
    print("Diagnostic Complete!")
    print("="*70)
    print("\nNext steps:")
    print("  1. Copy the suggested sensor_config.json above")
    print("  2. Save it to your src/ directory")
    print("  3. Run: python aanderaa_sensor_reader_config.py")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Test cancelled by user")
        sys.exit(0)
