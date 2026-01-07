"""
PC/Hub Compatibility Diagnostic
Tests PC-specific issues when sensors work elsewhere but not on this PC
"""

import serial
import serial.tools.list_ports
import sys
import platform
import subprocess


def get_system_info():
    """Get detailed system information"""
    print("\n" + "="*70)
    print("SYSTEM INFORMATION")
    print("="*70)
    
    print(f"\nOS: {platform.system()} {platform.release()}")
    print(f"Version: {platform.version()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Python: {platform.python_version()}")
    print(f"PySerial: {serial.__version__}")


def check_com_port_settings(port):
    """Check Windows COM port settings"""
    print(f"\n{'='*70}")
    print(f"CHECKING WINDOWS SETTINGS FOR {port}")
    print('='*70)
    
    try:
        # Try to get mode settings using Windows mode command
        result = subprocess.run(
            ['mode', port],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print(f"\n✓ Windows COM port settings:")
            print(result.stdout)
        else:
            print(f"\n⚠ Could not read COM port settings")
            
    except Exception as e:
        print(f"\n⚠ Error reading settings: {e}")


def check_usb_power_management(port_info):
    """Check if USB power management might be interfering"""
    print(f"\n{'='*70}")
    print(f"USB POWER MANAGEMENT CHECK")
    print('='*70)
    
    print(f"\n⚠️  USB Selective Suspend can cause communication failures!")
    print(f"\nTo check/disable:")
    print(f"  1. Open Device Manager")
    print(f"  2. Find 'Universal Serial Bus controllers'")
    print(f"  3. Right-click each USB Root Hub")
    print(f"  4. Properties → Power Management")
    print(f"  5. UNCHECK 'Allow computer to turn off this device'")
    print(f"\nAlso check:")
    print(f"  - Control Panel → Power Options → Change plan settings")
    print(f"  - Change advanced power settings → USB settings")
    print(f"  - Set 'USB selective suspend' to DISABLED")


def test_raw_serial_io(port, baudrate=9600):
    """Test raw serial I/O without any protocol"""
    print(f"\n{'='*70}")
    print(f"RAW SERIAL I/O TEST: {port}")
    print('='*70)
    
    try:
        print(f"\n[Opening port with minimal settings...]")
        
        # Open with very basic settings
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.bytesize = serial.EIGHTBITS
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        ser.timeout = 1
        ser.write_timeout = 1
        
        # Critical: Disable all flow control
        ser.xonxoff = False
        ser.rtscts = False
        ser.dsrdtr = False
        
        # Try to open
        ser.open()
        print(f"   ✓ Port opened")
        
        # Check if port is actually writable
        print(f"\n[Testing if data can be written...]")
        try:
            bytes_written = ser.write(b'\r\n')
            ser.flush()  # Force write
            print(f"   ✓ Wrote {bytes_written} bytes")
        except Exception as e:
            print(f"   ✗ Write failed: {e}")
            ser.close()
            return False
        
        # Check if port can be read
        print(f"\n[Testing if data can be read...]")
        try:
            ser.timeout = 0.5
            data = ser.read(100)
            print(f"   ✓ Read operation works (got {len(data)} bytes)")
        except Exception as e:
            print(f"   ✗ Read failed: {e}")
            ser.close()
            return False
        
        # Test buffer sizes
        print(f"\n[Checking buffer settings...]")
        print(f"   Input buffer size: {ser.in_waiting} bytes waiting")
        print(f"   Output buffer: {ser.out_waiting} bytes waiting")
        
        # Try aggressive write/read test
        print(f"\n[Aggressive communication test...]")
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        test_string = b'HELLO\r\n' * 10
        print(f"   Writing {len(test_string)} bytes...")
        
        try:
            ser.write(test_string)
            ser.flush()
            print(f"   ✓ Write successful")
            
            # Wait a bit
            import time
            time.sleep(0.5)
            
            # Try to read
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"   ✓ Got echo back: {len(data)} bytes")
            else:
                print(f"   ℹ No echo (expected if nothing connected)")
                
        except Exception as e:
            print(f"   ✗ Write/flush failed: {e}")
            ser.close()
            return False
        
        ser.close()
        print(f"\n✓ Port {port} is functioning at low level")
        return True
        
    except serial.SerialException as e:
        print(f"\n✗ Serial Error: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def test_with_increased_timeouts(port, baudrate=9600):
    """Test with very long timeouts to rule out timing issues"""
    print(f"\n{'='*70}")
    print(f"EXTENDED TIMEOUT TEST: {port}")
    print('='*70)
    
    try:
        print(f"\n[Testing with extended timeouts (5 seconds)...]")
        
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=5,  # Very long timeout
            write_timeout=5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        import time
        
        print(f"   ✓ Port opened with 5s timeout")
        
        # Long wake-up sequence
        print(f"\n[Sending extended wake-up (20 seconds total)...]")
        for i in range(40):
            ser.write(b'\r\n')
            time.sleep(0.5)  # Half second between each
            
            if i % 5 == 0:
                print(f"   ... {i} attempts", end='\r')
            
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"\n   ✓ Got response after {i+1} attempts!")
                print(f"   Data: {repr(data)}")
                ser.close()
                return True
        
        print(f"\n   ✗ No response after 40 attempts")
        
        # Try HELP with very long wait
        print(f"\n[Sending HELP with 10 second wait...]")
        ser.reset_input_buffer()
        ser.write(b'HELP\r\n')
        ser.flush()
        time.sleep(10)  # Wait 10 full seconds
        
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            print(f"   ✓ Got response: {repr(data)}")
            ser.close()
            return True
        else:
            print(f"   ✗ No response even with 10s wait")
        
        ser.close()
        return False
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def compare_port_details():
    """Get detailed info about all ports for comparison"""
    print(f"\n{'='*70}")
    print(f"DETAILED PORT COMPARISON")
    print('='*70)
    
    ports = list(serial.tools.list_ports.comports())
    
    for port in ports:
        print(f"\n{port.device}:")
        print(f"  Description: {port.description}")
        print(f"  HWID: {port.hwid}")
        print(f"  VID:PID: {port.vid}:{port.pid}")
        print(f"  Serial Number: {port.serial_number}")
        print(f"  Location: {port.location}")
        print(f"  Manufacturer: {port.manufacturer}")
        print(f"  Product: {port.product}")
        print(f"  Interface: {port.interface}")


def test_with_dtr_rts_combinations(port, baudrate=9600):
    """Test different DTR/RTS combinations"""
    print(f"\n{'='*70}")
    print(f"DTR/RTS SIGNAL COMBINATION TEST: {port}")
    print('='*70)
    
    import time
    
    combinations = [
        ("Both OFF", False, False),
        ("Both ON", True, True),
        ("DTR ON, RTS OFF", True, False),
        ("DTR OFF, RTS ON", False, True),
    ]
    
    for name, dtr, rts in combinations:
        print(f"\n[Testing: {name}]")
        
        try:
            ser = serial.Serial(port, baudrate, timeout=2)
            
            # Set signals
            ser.dtr = dtr
            ser.rts = rts
            time.sleep(0.5)
            
            print(f"   DTR={dtr}, RTS={rts}")
            
            # Try communication
            ser.reset_input_buffer()
            for _ in range(5):
                ser.write(b'\r\n')
                time.sleep(0.1)
            
            ser.write(b'HELP\r\n')
            time.sleep(1.5)
            
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"   ✓ RESPONSE! This combination works!")
                print(f"   Data: {repr(data[:100])}")
                ser.close()
                return (dtr, rts)
            else:
                print(f"   ✗ No response")
            
            ser.close()
            
        except Exception as e:
            print(f"   ✗ Error: {e}")
    
    return None


def main():
    """Main diagnostic"""
    print("\n" + "="*70)
    print("PC/HUB COMPATIBILITY DIAGNOSTIC")
    print("="*70)
    print("\nDiagnoses PC-specific issues when sensors work on other PC")
    print("but not on this PC with the same NI hub.")
    
    # System info
    get_system_info()
    
    # Get port info
    compare_port_details()
    
    # USB power warning
    check_usb_power_management(None)
    
    # Get ports to test
    print("\n" + "─"*70)
    port_input = input("\nEnter COM ports to test (e.g., COM3,COM4,COM5): ").strip()
    
    if not port_input:
        print("No ports specified.")
        sys.exit(1)
    
    ports = [p.strip().upper() for p in port_input.split(',')]
    ports = [p if p.startswith('COM') else 'COM' + p for p in ports]
    
    print(f"\nTesting: {', '.join(ports)}")
    input("\nPress Enter to start tests...")
    
    results = {}
    
    for port in ports:
        print(f"\n\n{'#'*70}")
        print(f"# TESTING {port}")
        print(f"{'#'*70}")
        
        # Check Windows settings
        check_com_port_settings(port)
        
        # Test 1: Raw I/O
        raw_ok = test_raw_serial_io(port)
        
        # Test 2: Extended timeouts
        timeout_ok = test_with_increased_timeouts(port)
        
        # Test 3: DTR/RTS combinations
        working_signals = test_with_dtr_rts_combinations(port)
        
        results[port] = {
            'raw_io': raw_ok,
            'timeout_test': timeout_ok,
            'working_signals': working_signals
        }
    
    # Summary
    print(f"\n\n{'='*70}")
    print(f"DIAGNOSTIC SUMMARY")
    print(f"{'='*70}")
    
    for port, result in results.items():
        print(f"\n{port}:")
        print(f"  Raw I/O: {'✓' if result['raw_io'] else '✗'}")
        print(f"  Extended timeout: {'✓' if result['timeout_test'] else '✗'}")
        if result['working_signals']:
            dtr, rts = result['working_signals']
            print(f"  Working signals: DTR={dtr}, RTS={rts}")
        else:
            print(f"  Working signals: None found")
    
    print(f"\n{'='*70}")
    print(f"RECOMMENDATIONS")
    print(f"{'='*70}")
    
    # Analyze results
    all_raw_ok = all(r['raw_io'] for r in results.values())
    none_responding = not any(r['timeout_test'] or r['working_signals'] for r in results.values())
    
    if all_raw_ok and none_responding:
        print(f"\n⚠️  DIAGNOSIS: Port I/O works but sensors don't respond")
        print(f"\nThis indicates a PC-specific configuration issue:")
        print(f"\n1. USB POWER MANAGEMENT (Most likely)")
        print(f"   - Disable USB selective suspend")
        print(f"   - Set USB Root Hub to not turn off")
        print(f"   - Check instructions above")
        
        print(f"\n2. NI DRIVER VERSION")
        print(f"   - Update NI-VISA to latest version")
        print(f"   - Or try older version that worked on other PC")
        print(f"   - Check NI driver version on working PC")
        
        print(f"\n3. WINDOWS COM PORT BUFFER SETTINGS")
        print(f"   - Device Manager → Ports → {ports[0]}")
        print(f"   - Port Settings → Advanced")
        print(f"   - Try increasing Receive/Transmit buffers")
        print(f"   - Change latency timer to 1ms")
        
        print(f"\n4. USB HUB PORT")
        print(f"   - Try different USB port on PC")
        print(f"   - Prefer USB 3.0 ports")
        print(f"   - Avoid USB hubs (connect directly)")
        
        print(f"\n5. ANTIVIRUS/SECURITY SOFTWARE")
        print(f"   - Some security software blocks COM ports")
        print(f"   - Temporarily disable and test")
    
    elif not all_raw_ok:
        print(f"\n⚠️  DIAGNOSIS: Low-level port I/O failing")
        print(f"\nThis indicates a driver or hardware issue:")
        print(f"\n1. REINSTALL NI DRIVERS")
        print(f"   - Uninstall current NI drivers")
        print(f"   - Restart")
        print(f"   - Install fresh from ni.com")
        print(f"   - Restart again")
        
        print(f"\n2. CHECK DEVICE MANAGER")
        print(f"   - Look for yellow warnings")
        print(f"   - Update/reinstall drivers")
        
        print(f"\n3. TRY DIFFERENT USB PORT")
        print(f"   - Move NI hub to different USB port")
    
    else:
        print(f"\n✓ Some communication working!")
        print(f"\nCheck results above for working signal combinations")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDiagnostic cancelled")
        sys.exit(0)
