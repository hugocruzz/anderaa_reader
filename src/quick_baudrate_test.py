"""
Simple Baudrate Detection Script
Quickly tests common baudrates on a specific COM port
"""

import serial
import time

def test_baudrate(port, baudrate):
    """Test a specific baudrate"""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.5,
            write_timeout=0.5
        )
        
        # Clear buffers
        time.sleep(0.1)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Send wake-up (per Aanderaa documentation)
        for _ in range(5):
            ser.write(b'\r\n')
            time.sleep(0.15)
        
        # Send '%' character for communication sleep wake-up
        ser.write(b'%')
        time.sleep(0.3)
        
        # Wait for '!' ready indicator
        time.sleep(0.5)
        
        # Try HELP command
        ser.reset_input_buffer()
        ser.write(b'HELP\r\n')
        time.sleep(0.5)
        
        response = ""
        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
        
        ser.close()
        
        return len(response) > 0, response
        
    except Exception as e:
        return False, str(e)


def main():
    print("="*60)
    print("Aanderaa Sensor Baudrate Detection")
    print("="*60)
    
    # Get COM port from user
    port = input("\nEnter COM port (e.g., COM3): ").strip().upper()
    if not port.startswith('COM'):
        port = 'COM' + port
    
    print(f"\nTesting {port} with common baudrates...")
    print("-"*60)
    
    # Common baudrates for Aanderaa sensors (from manuals)
    baudrates = [9600, 19200, 57600, 115200, 4800, 38400]
    
    found = []
    
    for baudrate in baudrates:
        print(f"\nTesting {baudrate} baud...", end=" ")
        success, response = test_baudrate(port, baudrate)
        
        if success:
            print(f"✓ RESPONSE RECEIVED!")
            print(f"   First 100 chars: {repr(response[:100])}")
            found.append(baudrate)
        else:
            print("✗ No response")
    
    print("\n" + "="*60)
    print("Results:")
    print("="*60)
    
    if found:
        print(f"\n✓ Working baudrate(s): {', '.join(map(str, found))}")
        print(f"\n→ Use baudrate {found[0]} in your sensor_config.json")
    else:
        print("\n✗ No working baudrate found!")
        print("\nTroubleshooting:")
        print("  1. Check sensor is powered (6-14V DC)")
        print("  2. Verify cable connections")
        print("  3. Confirm correct COM port")
        print("  4. Check if sensor is in Smart Sensor Terminal mode")
        print("  5. Try different COM ports")


if __name__ == "__main__":
    main()
