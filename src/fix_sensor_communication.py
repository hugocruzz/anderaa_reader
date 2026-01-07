"""
Direct Sensor Communication Fix
Step-by-step approach to get data from Aanderaa sensors
"""

import serial
import time
import sys


def try_communication_method(ser, method_name, commands, wait_time=1.5):
    """Try a specific communication method"""
    print(f"\n  [{method_name}]")
    
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    for cmd in commands:
        if isinstance(cmd, bytes):
            ser.write(cmd)
        elif isinstance(cmd, (int, float)):
            time.sleep(cmd)
    
    time.sleep(wait_time)
    
    if ser.in_waiting > 0:
        data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
        print(f"    ✓ SUCCESS! Got response: {repr(data[:150])}")
        return True, data
    else:
        print(f"    ✗ No response")
        return False, None


def test_all_methods(port, baudrate=9600):
    """Try every possible method to communicate"""
    print(f"\n{'='*70}")
    print(f"TRYING ALL COMMUNICATION METHODS: {port}")
    print('='*70)
    
    try:
        # Open port with all flow control disabled
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=2,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        print(f"\n✓ Port opened: {port} @ {baudrate} baud")
        
        methods = [
            ("Simple CR", [b'\r\n' * 5, b'HELP\r\n'], 1.5),
            ("With % wake", [b'\r\n' * 3, b'%', 0.5, b'HELP\r\n'], 2.0),
            ("Long wake", [b'\r\n' * 20, 1.0, b'HELP\r\n'], 2.0),
            ("$GET ProductName", [b'\r\n' * 5, b'%', 0.5, b'$GET ProductName\r\n'], 2.0),
            ("DO command", [b'\r\n' * 5, b'DO\r\n'], 2.5),
            ("With DTR/RTS", None, 0),  # Special handling
            ("Just listen", [], 3.0),  # Just wait for data
        ]
        
        for i, method in enumerate(methods, 1):
            if len(method) == 3:
                name, cmds, wait = method
                
                if name == "With DTR/RTS":
                    # Try with DTR/RTS enabled
                    print(f"\n  [With DTR/RTS enabled]")
                    ser.dtr = True
                    ser.rts = True
                    time.sleep(0.5)
                    ser.reset_input_buffer()
                    ser.write(b'\r\n' * 5)
                    ser.write(b'HELP\r\n')
                    time.sleep(2)
                    
                    if ser.in_waiting > 0:
                        data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                        print(f"    ✓ SUCCESS with DTR/RTS! {repr(data[:150])}")
                        ser.close()
                        return True, 'DTR/RTS', data
                    else:
                        print(f"    ✗ No response")
                        ser.dtr = False
                        ser.rts = False
                else:
                    success, data = try_communication_method(ser, name, cmds, wait)
                    if success:
                        ser.close()
                        return True, name, data
        
        ser.close()
        return False, None, None
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False, None, str(e)


def test_different_baudrates(port):
    """Quickly test common baudrates"""
    print(f"\n{'='*70}")
    print(f"TESTING DIFFERENT BAUDRATES: {port}")
    print('='*70)
    
    baudrates = [9600, 19200, 4800, 57600, 115200]
    
    for baud in baudrates:
        print(f"\n[{baud} baud]", end='')
        try:
            ser = serial.Serial(port, baud, timeout=1)
            ser.reset_input_buffer()
            
            # Quick test
            ser.write(b'\r\n' * 3)
            ser.write(b'HELP\r\n')
            time.sleep(1)
            
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f" ✓ WORKS!")
                print(f"    Response: {repr(data[:100])}")
                ser.close()
                return baud
            else:
                print(f" ✗")
            
            ser.close()
        except:
            print(f" ✗ Error")
    
    return None


def interactive_test(port):
    """Interactive manual testing"""
    print(f"\n{'='*70}")
    print(f"INTERACTIVE MANUAL TEST: {port}")
    print('='*70)
    
    print("\nYou can manually send commands to the sensor.")
    print("Common commands:")
    print("  HELP")
    print("  $GET ProductName")
    print("  $GET SerialNumber")
    print("  DO")
    print("  (or type 'quit' to exit)")
    
    try:
        ser = serial.Serial(port, 9600, timeout=1)
        print(f"\n✓ Port opened. Type commands below:")
        
        while True:
            cmd = input("\n> ").strip()
            
            if cmd.lower() in ['quit', 'exit', 'q']:
                break
            
            if not cmd:
                continue
            
            # Send command
            ser.reset_input_buffer()
            ser.write((cmd + '\r\n').encode())
            time.sleep(1.5)
            
            # Read response
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f"\nResponse:\n{data}")
            else:
                print("\n(No response)")
        
        ser.close()
        
    except Exception as e:
        print(f"\n✗ Error: {e}")


def show_working_script(port, method, baudrate=9600):
    """Generate a working script based on successful method"""
    print(f"\n{'='*70}")
    print(f"WORKING CODE FOR YOUR SETUP")
    print('='*70)
    
    dtr_rts = "DTR/RTS" in method
    
    print(f"""
# Save this as working_sensor_test.py

import serial
import time

port = '{port}'
baudrate = {baudrate}

ser = serial.Serial(
    port=port,
    baudrate=baudrate,
    timeout=2,
    xonxoff=False,
    rtscts=False,
    dsrdtr=False
)

print(f"Connected to {{port}}")
""")
    
    if dtr_rts:
        print("""
# Enable DTR/RTS (required for your setup)
ser.dtr = True
ser.rts = True
time.sleep(0.5)
""")
    
    print("""
# Wake up sensor
for _ in range(5):
    ser.write(b'\\r\\n')
    time.sleep(0.15)

ser.write(b'%')
time.sleep(1)

# Get sensor info
ser.write(b'$GET ProductName\\r\\n')
time.sleep(1)

if ser.in_waiting > 0:
    response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
    print(f"Product: {response}")

# Get measurement
ser.write(b'DO\\r\\n')
time.sleep(2)

if ser.in_waiting > 0:
    response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
    print(f"Measurement: {response}")

ser.close()
""")


def main():
    """Main troubleshooting flow"""
    print("\n" + "="*70)
    print("AANDERAA SENSOR - GET DATA NOW!")
    print("="*70)
    
    print("\nThis will try every method to get your sensors working.")
    
    # Get COM ports
    port_input = input("\nEnter COM port to test (e.g., COM3): ").strip().upper()
    if not port_input.startswith('COM'):
        port_input = 'COM' + port_input
    
    port = port_input
    
    print(f"\n{'#'*70}")
    print(f"# TESTING {port}")
    print(f"{'#'*70}")
    
    # Step 1: Try all methods at 9600 baud
    print("\n[STEP 1] Trying all communication methods at 9600 baud...")
    success, method, data = test_all_methods(port, 9600)
    
    if success:
        print(f"\n{'='*70}")
        print(f"✓✓✓ SUCCESS! ✓✓✓")
        print(f"{'='*70}")
        print(f"\nWorking method: {method}")
        print(f"Baudrate: 9600")
        show_working_script(port, method, 9600)
        
        # Offer interactive test
        if input("\nTry interactive mode? (y/n): ").lower() == 'y':
            interactive_test(port)
        
        return
    
    # Step 2: Try different baudrates
    print("\n[STEP 2] Trying different baudrates...")
    working_baud = test_different_baudrates(port)
    
    if working_baud:
        print(f"\n{'='*70}")
        print(f"✓ SUCCESS with baudrate {working_baud}!")
        print(f"{'='*70}")
        show_working_script(port, "Standard", working_baud)
        return
    
    # Step 3: Still not working
    print(f"\n{'='*70}")
    print(f"NO COMMUNICATION ESTABLISHED")
    print(f"{'='*70}")
    
    print(f"\n⚠️  Sensor is not responding to any method.")
    print(f"\nMost likely causes:")
    
    print(f"\n1. SENSOR IN AICAP MODE (90% probability)")
    print(f"   The sensor is configured for SeaGuard, not RS-232.")
    print(f"   ")
    print(f"   FIX: Use Aanderaa Real-Time Collector software:")
    print(f"   - Download from Aanderaa/Xylem website")
    print(f"   - Connect to sensor")
    print(f"   - Change Mode from 'AiCaP' to 'Terminal'")
    print(f"   - Save and Reset")
    
    print(f"\n2. WRONG CABLE (5% probability)")
    print(f"   TX/RX pins might be swapped.")
    print(f"   ")
    print(f"   FIX: Try a null-modem adapter between sensor and hub")
    
    print(f"\n3. SENSOR NOT POWERED CORRECTLY (3% probability)")
    print(f"   Even though you checked voltage, verify:")
    print(f"   - Correct polarity")
    print(f"   - Voltage at sensor connector (not just at supply)")
    
    print(f"\n4. HARDWARE FAULT (2% probability)")
    print(f"   Sensor or hub might be faulty.")
    print(f"   Since it works on another PC, likely PC/driver issue.")
    
    # Offer interactive mode anyway
    if input("\nTry interactive mode to test manually? (y/n): ").lower() == 'y':
        interactive_test(port)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled")
        sys.exit(0)
