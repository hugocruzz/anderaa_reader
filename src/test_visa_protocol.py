"""
Test Aanderaa sensors with SCPI/VISA commands
Based on NI-VISA configuration
"""
import serial
import time

def test_scpi_commands(port_name):
    """Test sensor with SCPI standard commands"""
    print(f"\n{'='*70}")
    print(f"Testing {port_name} with SCPI Commands")
    print('='*70)
    
    try:
        # Exact settings from user's VISA configuration
        ser = serial.Serial(
            port=port_name,
            baudrate=9600,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=3,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        print(f"✓ Port opened with VISA settings")
        print(f"  Baudrate: 9600, Data bits: 8, Parity: None")
        print(f"  Stop bits: 1, Flow control: None\n")
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)
        
        # Test 1: *IDN? command (SCPI standard identification)
        print("[Test 1] Sending: *IDN?")
        ser.write(b'*IDN?\r\n')
        time.sleep(1.0)
        
        response1 = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response1 += chunk
                time.sleep(0.2)
            else:
                if response1:
                    break
                time.sleep(0.2)
            attempts += 1
        
        print(f"Response ({len(response1)} bytes): {repr(response1)}")
        
        if response1:
            print(f"✓ Sensor responded to *IDN?")
            print(f"\nParsed response:")
            for line in response1.split('\n'):
                if line.strip():
                    print(f"  {line.strip()}")
        else:
            print("✗ No response to *IDN?")
        
        # Test 2: Try to get product info with different formats
        print(f"\n[Test 2] Trying Aanderaa ASCII command: $GET ProductName")
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b'$GET ProductName\r\n')
        time.sleep(1.0)
        
        response2 = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response2 += chunk
                time.sleep(0.2)
            else:
                if response2:
                    break
                time.sleep(0.2)
            attempts += 1
        
        print(f"Response: {repr(response2[:200])}")
        
        # Test 3: Try Aanderaa XML command
        print(f"\n[Test 3] Trying Aanderaa XML command: <Get><ProductName/></Get>")
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b'<Get><ProductName/></Get>\r\n')
        time.sleep(1.0)
        
        response3 = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response3 += chunk
                time.sleep(0.2)
            else:
                if response3:
                    break
                time.sleep(0.2)
            attempts += 1
        
        print(f"Response: {repr(response3[:200])}")
        
        # Test 4: Try simple query format
        print(f"\n[Test 4] Trying simple query: ProductName?")
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b'ProductName?\r\n')
        time.sleep(1.0)
        
        response4 = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response4 += chunk
                time.sleep(0.2)
            else:
                if response4:
                    break
                time.sleep(0.2)
            attempts += 1
        
        print(f"Response: {repr(response4[:200])}")
        
        # Test 5: Other SCPI commands
        print(f"\n[Test 5] Trying: *RST (Reset)")
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b'*RST\r\n')
        time.sleep(1.0)
        
        response5 = ""
        if ser.in_waiting > 0:
            response5 = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
        print(f"Response: {repr(response5[:200])}")
        
        ser.close()
        
        # Analysis
        print(f"\n{'-'*70}")
        print("ANALYSIS:")
        print('-'*70)
        
        if response1:
            print("✓ Sensor responds to SCPI *IDN? command")
            print("  → Sensor is using SCPI/VISA protocol")
        
        if 'Syntax error' in response2:
            print("✗ Aanderaa ASCII commands not working (Syntax error)")
        elif response2 and '=' in response2:
            print("✓ Aanderaa ASCII commands working")
        
        if response3 and '<Result>' in response3:
            print("✓ Aanderaa XML commands working")
        elif 'Syntax error' in response3:
            print("✗ Aanderaa XML commands not working")
        
        return {
            'port': port_name,
            'idn_response': response1,
            'ascii_response': response2,
            'xml_response': response3,
            'simple_response': response4
        }
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return {'port': port_name, 'error': str(e)}


def main():
    print("\n" + "="*70)
    print("AANDERAA SENSOR SCPI/VISA PROTOCOL TEST")
    print("="*70)
    print("\nTesting with NI-VISA compatible commands")
    print("Settings: 9600 baud, 8 data bits, no parity, 1 stop bit\n")
    
    ports = ['COM3', 'COM4', 'COM5']
    
    results = []
    for port in ports:
        result = test_scpi_commands(port)
        results.append(result)
        time.sleep(1)
    
    # Summary
    print("\n\n" + "="*70)
    print("SUMMARY")
    print("="*70 + "\n")
    
    for r in results:
        if 'error' not in r:
            print(f"\n{r['port']}:")
            if r.get('idn_response'):
                print(f"  *IDN? → {r['idn_response'][:100]}")
            else:
                print(f"  *IDN? → No response")
    
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("""
Based on the responses, we'll create a script that uses the
correct protocol for your sensors.

If *IDN? works, the sensors might be using a different command
set than standard Aanderaa ASCII or XML commands.
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
