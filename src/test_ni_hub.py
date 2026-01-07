"""
National Instruments USB Hub Diagnostic
Specialized tool for NI USB-to-Serial hubs with multiple ports
"""

import serial
import serial.tools.list_ports
import time
import sys


def check_ni_hub():
    """Check for National Instruments USB hub"""
    print("\n" + "="*70)
    print("Checking for National Instruments USB Hub")
    print("="*70)
    
    ports = list(serial.tools.list_ports.comports())
    
    ni_ports = []
    other_ports = []
    
    for port in ports:
        info = {
            'device': port.device,
            'description': port.description,
            'manufacturer': port.manufacturer or 'Unknown',
            'vid': port.vid,
            'pid': port.pid,
            'serial_number': port.serial_number,
            'hwid': port.hwid
        }
        
        # Check if it's National Instruments
        if port.manufacturer and 'national' in port.manufacturer.lower():
            ni_ports.append(info)
        elif port.description and 'national' in port.description.lower():
            ni_ports.append(info)
        elif port.hwid and 'ni' in port.hwid.lower():
            ni_ports.append(info)
        else:
            other_ports.append(info)
    
    if ni_ports:
        print(f"\n✓ Found {len(ni_ports)} National Instruments port(s):\n")
        for i, port in enumerate(ni_ports, 1):
            print(f"{i}. {port['device']}")
            print(f"   Description: {port['description']}")
            print(f"   Manufacturer: {port['manufacturer']}")
            if port['vid'] and port['pid']:
                print(f"   VID:PID: {port['vid']:04X}:{port['pid']:04X}")
            if port['serial_number']:
                print(f"   Serial: {port['serial_number']}")
            print()
    else:
        print("\n✗ No National Instruments ports detected!")
        print("\nPossible issues:")
        print("  1. NI USB hub not plugged in")
        print("  2. NI drivers not installed")
        print("  3. USB hub not recognized by Windows")
        print("  4. Hub connected but ports not enumerated")
    
    if other_ports:
        print(f"\nFound {len(other_ports)} other serial port(s):")
        for port in other_ports:
            print(f"  - {port['device']}: {port['description']}")
    
    return ni_ports, other_ports


def check_usb_power():
    """Check USB power considerations"""
    print("\n" + "="*70)
    print("USB Hub Power Check")
    print("="*70)
    
    print("\n⚠️  IMPORTANT: USB Power Limitations")
    print("-" * 70)
    print("\nAanderaa sensors require 6-14V DC power supply.")
    print("USB provides only 5V and limited current (500mA per port max).")
    print("\nThe NI USB hub is for COMMUNICATION only, not power!")
    print("\nConnection setup should be:")
    print("  1. Sensor powered by external 12V DC supply")
    print("  2. Sensor RS-232 connected to NI USB hub for communication")
    print("  3. NI hub connected to PC via USB")
    print("\n✓ Verify each sensor has external power connected!")


def test_ni_port(port_info, verbose=True):
    """Test a specific NI USB hub port"""
    port_name = port_info['device']
    
    if verbose:
        print(f"\n{'─'*70}")
        print(f"Testing: {port_name}")
        print(f"Description: {port_info['description']}")
        print('─'*70)
    
    baudrate = 9600
    
    try:
        if verbose:
            print(f"\n1. Opening port...")
        
        # Try to open with shorter timeout first
        ser = serial.Serial(
            port=port_name,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1,
            write_timeout=1
        )
        
        if verbose:
            print("   ✓ Port opened successfully")
        
        # Check RTS/CTS/DTR/DSR status
        if verbose:
            print(f"\n2. Checking serial port signals:")
            print(f"   CTS (Clear To Send): {ser.cts}")
            print(f"   DSR (Data Set Ready): {ser.dsr}")
            print(f"   RI (Ring Indicator): {ser.ri}")
            print(f"   CD (Carrier Detect): {ser.cd}")
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.2)
        
        # Wake-up sequence
        if verbose:
            print(f"\n3. Sending wake-up sequence...")
        
        for i in range(5):
            ser.write(b'\r\n')
            time.sleep(0.15)
        
        ser.write(b'%')
        time.sleep(0.3)
        time.sleep(0.7)
        
        # Check for any response
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            if verbose:
                print(f"   ✓ Received wake-up response: {repr(response[:100])}")
        else:
            if verbose:
                print("   ℹ No immediate response (normal if sensor sleeping)")
        
        # Try to identify sensor
        if verbose:
            print(f"\n4. Attempting sensor identification...")
        
        ser.reset_input_buffer()
        ser.write(b'$GET ProductName\r\n')
        time.sleep(1.0)
        
        product_name = ""
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            if verbose:
                print(f"   ✓ Response received ({len(response)} bytes)")
                print(f"   Raw: {repr(response[:150])}")
            
            for line in response.split('\n'):
                if '=' in line:
                    product_name = line.split('=')[1].strip()
                    if verbose:
                        print(f"   ✓ Sensor: {product_name}")
                    break
        else:
            if verbose:
                print("   ✗ No response to ProductName query")
        
        ser.close()
        
        if product_name:
            return {
                'success': True,
                'port': port_name,
                'product': product_name,
                'port_info': port_info
            }
        else:
            return {
                'success': False,
                'port': port_name,
                'port_info': port_info,
                'reason': 'No sensor response'
            }
        
    except serial.SerialException as e:
        if verbose:
            print(f"\n✗ Serial Error: {e}")
        return {
            'success': False,
            'port': port_name,
            'error': str(e),
            'port_info': port_info
        }
    
    except Exception as e:
        if verbose:
            print(f"\n✗ Error: {e}")
        return {
            'success': False,
            'port': port_name,
            'error': str(e),
            'port_info': port_info
        }


def test_all_ni_ports(ni_ports):
    """Test all NI ports sequentially"""
    print("\n" + "="*70)
    print("Testing All NI Hub Ports")
    print("="*70)
    
    results = []
    for port_info in ni_ports:
        result = test_ni_port(port_info, verbose=True)
        results.append(result)
        time.sleep(0.5)
    
    return results


def generate_summary(results):
    """Generate summary and recommendations"""
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    print(f"\nPorts tested: {len(results)}")
    print(f"Sensors detected: {len(successful)}")
    print(f"No response: {len(failed)}")
    
    if successful:
        print("\n✓ DETECTED SENSORS:")
        print("-" * 70)
        for r in successful:
            print(f"\n{r['port']}: {r.get('product', 'Unknown')}")
            print(f"  Manufacturer: {r['port_info']['manufacturer']}")
            print(f"  Use this port in sensor_config.json")
    
    if failed:
        print("\n✗ PORTS WITH NO SENSOR RESPONSE:")
        print("-" * 70)
        for r in failed:
            print(f"\n{r['port']}:")
            if 'error' in r:
                print(f"  Error: {r['error']}")
            elif 'reason' in r:
                print(f"  Reason: {r['reason']}")
            print(f"  Possible causes:")
            print(f"    - No sensor connected to this port")
            print(f"    - Sensor not powered (needs 6-14V DC externally)")
            print(f"    - Sensor in AiCaP mode (needs Terminal mode)")
            print(f"    - Wrong cable or bad connection")
    
    print("\n" + "="*70)
    print("Recommendations")
    print("="*70)
    
    if not successful:
        print("\n⚠️  NO SENSORS DETECTED - Check these:")
        print("\n1. POWER:")
        print("   ✓ Each sensor must have external 6-14V DC power")
        print("   ✓ USB hub provides communication ONLY, not power")
        print("   ✓ Verify power supply is ON and connected")
        
        print("\n2. CONNECTIONS:")
        print("   ✓ Sensor powered separately (6-14V DC)")
        print("   ✓ Sensor RS-232 cable to NI USB hub port")
        print("   ✓ NI hub USB cable to computer")
        print("   ✓ All cables fully inserted")
        
        print("\n3. SENSOR MODE:")
        print("   ✓ Sensors must be in 'Terminal' mode")
        print("   ✓ Use Aanderaa Real-Time Collector to check/change mode")
        print("   ✓ If in 'AiCaP' mode, sensors won't respond to RS-232")
        
        print("\n4. NI DRIVERS:")
        print("   ✓ Install NI-VISA or NI serial drivers")
        print("   ✓ Download from ni.com/downloads")
        print("   ✓ Restart computer after installation")
        
    elif len(successful) < len(results):
        print(f"\n✓ Found {len(successful)} sensor(s), but {len(failed)} port(s) have no response")
        print("\nFor ports with no response:")
        print("  - Either no sensor connected, or")
        print("  - Sensor not powered, or")
        print("  - Sensor needs mode change to Terminal")
    else:
        print("\n✓ All ports have responding sensors!")
        print("\nNext step:")
        print("  - Use the COM ports listed above in your sensor_config.json")
        print("  - Run: python aanderaa_sensor_reader_config.py")


def main():
    """Main diagnostic routine"""
    print("\n" + "="*70)
    print("NATIONAL INSTRUMENTS USB HUB DIAGNOSTIC")
    print("="*70)
    print("\nThis tool diagnoses NI USB hub connectivity for Aanderaa sensors")
    
    input("\nPress Enter to start diagnostic...")
    
    # Step 1: Find NI hub
    ni_ports, other_ports = check_ni_hub()
    
    if not ni_ports:
        print("\n" + "="*70)
        print("NEXT STEPS")
        print("="*70)
        print("\n1. Check USB connection:")
        print("   - Unplug and replug NI USB hub")
        print("   - Try different USB port on computer")
        print("   - Check if Windows recognizes device")
        
        print("\n2. Install/update NI drivers:")
        print("   - Download NI-VISA from ni.com")
        print("   - Or NI serial drivers")
        print("   - Restart computer after installation")
        
        print("\n3. Verify in Device Manager:")
        print("   - Open Device Manager")
        print("   - Look for 'Ports (COM & LPT)'")
        print("   - Should see NI USB Serial Port entries")
        print("   - If yellow warning, update driver")
        
        sys.exit(1)
    
    # Step 2: Check power
    check_usb_power()
    
    # Step 3: Test all ports
    print("\n⚠️  Make sure all sensors are POWERED EXTERNALLY (6-14V DC)!")
    input("\nPress Enter to test all NI hub ports...")
    
    results = test_all_ni_ports(ni_ports)
    
    # Step 4: Summary
    generate_summary(results)
    
    print("\n" + "="*70)
    print("Diagnostic Complete")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Diagnostic cancelled by user")
        sys.exit(0)
