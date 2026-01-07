"""
Debug Tool for Aanderaa Sensor Communication Issues
Tests different communication approaches when ports open but no data received
"""

import serial
import time
import sys


def test_basic_serial(port, baudrate=9600):
    """Test basic serial communication with detailed output"""
    print(f"\n{'='*70}")
    print(f"DEBUGGING: {port} at {baudrate} baud")
    print('='*70)
    
    try:
        # Open port
        print("\n[Step 1] Opening port...")
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2,
            write_timeout=2,
            xonxoff=False,  # No software flow control
            rtscts=False,   # No hardware flow control
            dsrdtr=False    # No DSR/DTR flow control
        )
        print(f"   ✓ Port {port} opened successfully")
        print(f"   - Baudrate: {ser.baudrate}")
        print(f"   - Timeout: {ser.timeout}s")
        
        # Check control signals
        print(f"\n[Step 2] Checking control signals...")
        print(f"   - CTS (Clear to Send): {ser.cts}")
        print(f"   - DSR (Data Set Ready): {ser.dsr}")
        print(f"   - RI (Ring Indicator): {ser.ri}")
        print(f"   - CD (Carrier Detect): {ser.cd}")
        
        # Clear buffers
        print(f"\n[Step 3] Clearing buffers...")
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.2)
        print(f"   ✓ Buffers cleared")
        
        # Test 1: Simple wake-up with carriage returns
        print(f"\n[Test 1] Sending carriage returns only...")
        for i in range(10):
            ser.write(b'\r\n')
            time.sleep(0.1)
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f"   ✓ Got response after {i+1} CR: {repr(response)}")
                ser.reset_input_buffer()
                break
        else:
            print(f"   ✗ No response to carriage returns")
        
        time.sleep(0.5)
        
        # Test 2: Wake with '%' character
        print(f"\n[Test 2] Sending '%' character (wake from sleep)...")
        ser.reset_input_buffer()
        ser.write(b'%')
        time.sleep(1.0)
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   ✓ Response: {repr(response)}")
        else:
            print(f"   ✗ No response to '%'")
        
        # Test 3: Full wake-up sequence
        print(f"\n[Test 3] Full documented wake-up sequence...")
        ser.reset_input_buffer()
        for _ in range(5):
            ser.write(b'\r\n')
            time.sleep(0.15)
        ser.write(b'%')
        time.sleep(1.5)  # Longer wait
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   ✓ Response: {repr(response)}")
        else:
            print(f"   ℹ No immediate response (may be normal)")
        
        # Test 4: Try HELP command
        print(f"\n[Test 4] Sending HELP command...")
        ser.reset_input_buffer()
        ser.write(b'HELP\r\n')
        time.sleep(1.5)
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   ✓ HELP response ({len(response)} bytes):")
            print(f"   {repr(response[:200])}")
            return {'success': True, 'mode': 'Terminal', 'response': response}
        else:
            print(f"   ✗ No response to HELP")
        
        # Test 5: Try $GET command
        print(f"\n[Test 5] Sending $GET ProductName...")
        ser.reset_input_buffer()
        ser.write(b'$GET ProductName\r\n')
        time.sleep(1.5)
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   ✓ $GET response:")
            print(f"   {repr(response)}")
            return {'success': True, 'mode': 'Terminal', 'response': response}
        else:
            print(f"   ✗ No response to $GET")
        
        # Test 6: Try DO command
        print(f"\n[Test 6] Sending DO command (measurement)...")
        ser.reset_input_buffer()
        ser.write(b'DO\r\n')
        time.sleep(2.0)
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   ✓ DO response:")
            print(f"   {repr(response)}")
            return {'success': True, 'mode': 'Terminal', 'response': response}
        else:
            print(f"   ✗ No response to DO")
        
        # Test 7: Listen for any unsolicited data
        print(f"\n[Test 7] Listening for 5 seconds for any data...")
        ser.reset_input_buffer()
        start_time = time.time()
        received_any = False
        
        while time.time() - start_time < 5:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"   ✓ Received {len(data)} bytes: {repr(data)}")
                received_any = True
            time.sleep(0.1)
        
        if not received_any:
            print(f"   ✗ No data received in 5 seconds")
        
        # Test 8: Check if in AiCaP mode
        print(f"\n[Test 8] Checking for AiCaP mode indicators...")
        print(f"   (AiCaP sensors won't respond to RS-232 commands)")
        print(f"   Trying XML format request...")
        ser.reset_input_buffer()
        ser.write(b'<?xml version="1.0"?><sensor><get>ProductName</get></sensor>\r\n')
        time.sleep(1.5)
        
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   ✓ XML response: {repr(response)}")
            return {'success': True, 'mode': 'Real-Time', 'response': response}
        else:
            print(f"   ✗ No response to XML either")
        
        ser.close()
        
        print(f"\n{'─'*70}")
        print(f"RESULT: No communication established")
        print(f"{'─'*70}")
        
        return {'success': False, 'port': port, 'baudrate': baudrate}
        
    except serial.SerialException as e:
        print(f"\n✗ Serial Error: {e}")
        return {'success': False, 'error': str(e)}
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return {'success': False, 'error': str(e)}


def test_different_baudrates(port):
    """Test multiple baudrates"""
    print(f"\n{'='*70}")
    print(f"TESTING DIFFERENT BAUDRATES on {port}")
    print('='*70)
    
    baudrates = [9600, 19200, 4800, 57600, 115200]
    
    for baud in baudrates:
        print(f"\n[Testing {baud} baud]")
        try:
            ser = serial.Serial(port, baud, timeout=1)
            
            # Quick test
            ser.reset_input_buffer()
            for _ in range(3):
                ser.write(b'\r\n')
                time.sleep(0.1)
            ser.write(b'HELP\r\n')
            time.sleep(1)
            
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f"   ✓ RESPONSE at {baud} baud!")
                print(f"   {repr(response[:100])}")
                ser.close()
                return baud
            else:
                print(f"   ✗ No response at {baud} baud")
            
            ser.close()
            
        except Exception as e:
            print(f"   ✗ Error at {baud}: {e}")
    
    print(f"\n   ℹ No baudrate worked - likely not a baudrate issue")
    return None


def test_continuous_read(port, baudrate=9600, duration=10):
    """Read continuously to see if sensor is sending data"""
    print(f"\n{'='*70}")
    print(f"CONTINUOUS READ TEST on {port}")
    print(f"Reading for {duration} seconds to detect any data...")
    print('='*70)
    
    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
        
        print(f"\n[Listening] Press Ctrl+C to stop early...")
        start = time.time()
        total_bytes = 0
        
        while time.time() - start < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)
                print(f"\n[{time.time()-start:.1f}s] Received {len(data)} bytes:")
                print(f"   Hex: {data.hex()}")
                print(f"   ASCII: {repr(data.decode('ascii', errors='ignore'))}")
        
        ser.close()
        
        print(f"\n{'─'*70}")
        print(f"Total bytes received: {total_bytes}")
        if total_bytes == 0:
            print(f"✗ No data detected - sensor not transmitting")
        print(f"{'─'*70}")
        
    except KeyboardInterrupt:
        print(f"\n\n[Stopped by user]")
        ser.close()
    except Exception as e:
        print(f"\n✗ Error: {e}")


def diagnose_port(port):
    """Complete diagnostic for a single port"""
    print(f"\n\n")
    print(f"{'#'*70}")
    print(f"# COMPREHENSIVE DIAGNOSTIC: {port}")
    print(f"{'#'*70}")
    
    # Test 1: Basic communication
    result = test_basic_serial(port)
    
    if result.get('success'):
        print(f"\n✓✓✓ SUCCESS! Sensor responding on {port}")
        return result
    
    # Test 2: Try different baudrates
    print(f"\n[Trying different baudrates...]")
    working_baud = test_different_baudrates(port)
    
    if working_baud:
        print(f"\n✓ Found working baudrate: {working_baud}")
        return {'success': True, 'baudrate': working_baud}
    
    # Test 3: Continuous read
    print(f"\n[Checking if sensor is transmitting anything...]")
    test_continuous_read(port, duration=5)
    
    return result


def main():
    """Main diagnostic"""
    print("\n" + "="*70)
    print("AANDERAA SENSOR COMMUNICATION DEBUG TOOL")
    print("="*70)
    print("\nThis tool performs detailed communication tests")
    print("to identify why sensors aren't responding.")
    
    # Get ports from user
    print("\n" + "─"*70)
    port_input = input("Enter COM ports to test (e.g., COM3,COM4,COM5): ").strip()
    
    if not port_input:
        print("No ports specified. Exiting.")
        sys.exit(1)
    
    ports = [p.strip().upper() for p in port_input.split(',')]
    
    # Make sure they start with COM
    ports = [p if p.startswith('COM') else 'COM' + p for p in ports]
    
    print(f"\nWill test: {', '.join(ports)}")
    input("\nPress Enter to start detailed diagnostics...")
    
    results = {}
    
    for port in ports:
        result = diagnose_port(port)
        results[port] = result
        time.sleep(1)
    
    # Summary
    print(f"\n\n")
    print(f"{'='*70}")
    print(f"DIAGNOSTIC SUMMARY")
    print(f"{'='*70}")
    
    working = [p for p, r in results.items() if r.get('success')]
    not_working = [p for p, r in results.items() if not r.get('success')]
    
    if working:
        print(f"\n✓ Ports with communication: {', '.join(working)}")
    
    if not_working:
        print(f"\n✗ Ports with NO communication: {', '.join(not_working)}")
        print(f"\nPossible causes for ports with no response:")
        print(f"  1. Sensor in AiCaP mode (not Terminal mode)")
        print(f"  2. Sensor requires different protocol")
        print(f"  3. Cable wiring issue (TX/RX not connected)")
        print(f"  4. Sensor firmware not responding")
        print(f"  5. Need to use Aanderaa Real-Time Collector first")
    
    print(f"\n{'='*70}")
    print(f"RECOMMENDATIONS")
    print(f"{'='*70}")
    
    if not working and not_working:
        print(f"\n⚠️  NO SENSORS RESPONDING via RS-232 commands")
        print(f"\nMost likely cause: Sensors in wrong mode")
        print(f"\nNext steps:")
        print(f"  1. Download Aanderaa Real-Time Collector software")
        print(f"  2. Connect to each sensor")
        print(f"  3. Check System Configuration → Mode")
        print(f"  4. If Mode = 'AiCaP', change to 'Terminal'")
        print(f"  5. Save and Reset each sensor")
        print(f"  6. Re-run this diagnostic")
        
        print(f"\nAlternatively:")
        print(f"  - Cable TX/RX pins might be swapped")
        print(f"  - Try null-modem adapter if using generic cable")
        print(f"  - Verify cable pinout matches Aanderaa spec")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Diagnostic cancelled")
        sys.exit(0)
