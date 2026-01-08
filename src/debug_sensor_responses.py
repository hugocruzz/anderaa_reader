"""
Debug tool to see RAW sensor responses
This will show exactly what each sensor is saying
"""
import serial
import time

def debug_sensor(port_name):
    """Show raw responses from sensor"""
    print(f"\n{'='*70}")
    print(f"DEBUGGING {port_name}")
    print('='*70)
    
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=9600,
            timeout=5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        print(f"✓ Port opened\n")
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)
        
        # Wake up sensor
        print("[1] Waking up sensor...")
        for _ in range(5):
            ser.write(b'\r\n')
            time.sleep(0.2)
        
        ser.write(b'%')
        time.sleep(0.5)
        
        # Clear wake-up response
        ser.reset_input_buffer()
        time.sleep(1.0)
        
        # Test 1: Get Product Name
        print("\n[2] Sending: $GET ProductName")
        ser.reset_input_buffer()
        ser.write(b'$GET ProductName\r\n')
        time.sleep(1.5)  # Longer wait
        
        response1 = ""
        attempts = 0
        while attempts < 8:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response1 += chunk
                time.sleep(0.3)
            else:
                if response1:
                    break
                time.sleep(0.3)
            attempts += 1
        
        print(f"RAW RESPONSE (length={len(response1)} bytes):")
        print(f"'{response1}'")
        print(f"\nResponse lines:")
        for i, line in enumerate(response1.split('\n'), 1):
            print(f"  Line {i}: '{line.strip()}'")
        
        # Test 2: Get Serial Number
        print(f"\n[3] Sending: $GET SerialNumber")
        ser.reset_input_buffer()
        time.sleep(0.5)
        ser.write(b'$GET SerialNumber\r\n')
        time.sleep(1.5)
        
        response2 = ""
        attempts = 0
        while attempts < 8:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response2 += chunk
                time.sleep(0.3)
            else:
                if response2:
                    break
                time.sleep(0.3)
            attempts += 1
        
        print(f"RAW RESPONSE (length={len(response2)} bytes):")
        print(f"'{response2}'")
        print(f"\nResponse lines:")
        for i, line in enumerate(response2.split('\n'), 1):
            print(f"  Line {i}: '{line.strip()}'")
        
        # Test 3: Try HELP command
        print(f"\n[4] Sending: HELP")
        ser.reset_input_buffer()
        time.sleep(0.5)
        ser.write(b'HELP\r\n')
        time.sleep(1.5)
        
        response3 = ""
        attempts = 0
        while attempts < 8:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response3 += chunk
                time.sleep(0.3)
            else:
                if response3:
                    break
                time.sleep(0.3)
            attempts += 1
        
        print(f"RAW RESPONSE (length={len(response3)} bytes):")
        print(f"'{response3[:500]}'")  # First 500 chars
        
        # Test 4: Try DO command
        print(f"\n[5] Sending: DO")
        ser.reset_input_buffer()
        time.sleep(0.5)
        ser.write(b'DO\r\n')
        time.sleep(2.0)  # DO takes longer
        
        response4 = ""
        attempts = 0
        while attempts < 10:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response4 += chunk
                time.sleep(0.3)
            else:
                if response4:
                    break
                time.sleep(0.3)
            attempts += 1
        
        print(f"RAW RESPONSE (length={len(response4)} bytes):")
        print(f"'{response4[:500]}'")  # First 500 chars
        
        ser.close()
        
        # Analysis
        print(f"\n{'-'*70}")
        print("ANALYSIS:")
        print('-'*70)
        
        if "Syntax error" in response1 or "Syntax error" in response2:
            print("✗ Getting 'Syntax error' - sensor doesn't understand command")
            print("  Possible causes:")
            print("  - Sensor in wrong mode (not Smart Sensor Terminal)")
            print("  - Need longer wake-up sequence")
            print("  - Command format issue")
        elif not response1 and not response2:
            print("✗ No response at all")
            print("  Possible causes:")
            print("  - Sensor not powered")
            print("  - Wrong baudrate")
            print("  - Sensor in AiCaP mode")
        elif response1 or response2:
            print("✓ Getting some response")
            if '=' not in response1 and '=' not in response2:
                print("  But no '=' found in responses")
                print("  Response format unexpected")
        
        return {
            'port': port_name,
            'product_response': response1,
            'serial_response': response2,
            'help_response': response3[:200],
            'do_response': response4[:200]
        }
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return {'port': port_name, 'error': str(e)}


def main():
    print("\n" + "="*70)
    print("RAW SENSOR RESPONSE DEBUG TOOL")
    print("="*70)
    print("\nThis will show the exact raw responses from each sensor")
    print("to help diagnose the parsing issue.\n")
    
    ports = ['COM3', 'COM4', 'COM5']
    
    results = []
    for port in ports:
        result = debug_sensor(port)
        results.append(result)
        time.sleep(1)
    
    # Summary
    print("\n\n" + "="*70)
    print("SUMMARY - Save this output and share if needed")
    print("="*70)
    
    for r in results:
        if 'error' not in r:
            print(f"\n{r['port']}:")
            print(f"  ProductName response: {repr(r['product_response'][:100])}")
            print(f"  SerialNumber response: {repr(r['serial_response'][:100])}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
