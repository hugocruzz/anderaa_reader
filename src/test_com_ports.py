"""
COM Port Diagnostic Tool
Tests which COM ports are available and attempts basic communication
"""

import serial
import serial.tools.list_ports
import time

def list_available_ports():
    """List all available COM ports"""
    print("\n" + "="*70)
    print("Available COM Ports:")
    print("="*70)
    
    ports = serial.tools.list_ports.comports()
    
    if not ports:
        print("No COM ports found!")
        return []
    
    available = []
    for i, port in enumerate(ports, 1):
        print(f"\n{i}. {port.device}")
        print(f"   Description: {port.description}")
        print(f"   Manufacturer: {port.manufacturer or 'N/A'}")
        print(f"   Hardware ID: {port.hwid}")
        available.append(port.device)
    
    return available


def test_port(port_name, baudrates=[9600, 19200, 4800, 115200]):
    """Test a specific COM port with different baudrates"""
    print(f"\n" + "="*70)
    print(f"Testing {port_name}")
    print("="*70)
    
    for baudrate in baudrates:
        print(f"\nTrying baudrate: {baudrate}")
        print("-" * 50)
        
        try:
            # Try to open the port
            ser = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            
            print(f"✓ Port opened successfully")
            
            # Clear buffers
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Try to wake up sensor (per Aanderaa documentation)
            print("  Sending wake-up signals (CR + '%' character)...")
            for i in range(5):
                ser.write(b'\r\n')
                time.sleep(0.15)
            
            # Send '%' to wake from communication sleep
            ser.write(b'%')
            time.sleep(0.3)
            
            # Wait for '!' ready indicator
            time.sleep(0.7)
            
            # Check if there's any response
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f"  ✓ Received data: {repr(response)}")
            else:
                print("  ✗ No response to wake-up signals")
            
            # Try HELP command (Aanderaa Smart Sensor Terminal)
            print("  Sending HELP command...")
            ser.reset_input_buffer()
            ser.write(b'HELP\r\n')
            time.sleep(1)
            
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f"  ✓ Response to HELP: {repr(response[:200])}")
                if len(response) > 200:
                    print("     ... (truncated)")
            else:
                print("  ✗ No response to HELP command")
            
            # Try $GET ProductName command
            print("  Sending $GET ProductName command...")
            ser.reset_input_buffer()
            ser.write(b'$GET ProductName\r\n')
            time.sleep(1)
            
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                print(f"  ✓ Response to $GET ProductName: {repr(response)}")
            else:
                print("  ✗ No response to $GET ProductName")
            
            ser.close()
            print(f"\n  → Baudrate {baudrate} might work for this sensor")
            
        except serial.SerialException as e:
            print(f"✗ Could not open port: {e}")
        except Exception as e:
            print(f"✗ Error: {e}")


def interactive_test():
    """Interactive mode to test specific ports"""
    ports = list_available_ports()
    
    if not ports:
        print("\nNo COM ports available. Check your connections.")
        return
    
    print("\n" + "="*70)
    print("Interactive Port Testing")
    print("="*70)
    print("\nEnter COM port numbers to test (comma-separated)")
    print("Examples: 'COM3' or 'COM3,COM4,COM5' or 'all' for all ports")
    print("Press Enter to skip")
    
    user_input = input("\nCOM ports to test: ").strip()
    
    if not user_input:
        print("No ports selected. Exiting.")
        return
    
    if user_input.lower() == 'all':
        test_ports = ports
    else:
        # Parse user input
        test_ports = []
        for item in user_input.split(','):
            item = item.strip().upper()
            if not item.startswith('COM'):
                item = 'COM' + item
            test_ports.append(item)
    
    for port in test_ports:
        if port in ports or user_input.lower() == 'all':
            test_port(port)
        else:
            print(f"\n✗ {port} not found in available ports")


def main():
    """Main function"""
    print("\n" + "="*70)
    print("Aanderaa Sensor COM Port Diagnostic Tool")
    print("="*70)
    
    # First, list all available ports
    ports = list_available_ports()
    
    if not ports:
        print("\n✗ No COM ports detected!")
        print("\nPossible reasons:")
        print("  1. Sensors not connected")
        print("  2. USB-to-Serial drivers not installed")
        print("  3. Sensors not powered")
        print("  4. Cable issues")
        return
    
    # Run interactive test
    interactive_test()
    
    print("\n" + "="*70)
    print("Diagnostic Complete")
    print("="*70)
    print("\nRecommendations:")
    print("  1. Use the COM port that responded to commands")
    print("  2. Use the baudrate that showed a response")
    print("  3. Update sensor_config.json with correct values")
    print("  4. If no responses, check:")
    print("     - Sensor power (6-14V DC)")
    print("     - Cable connections")
    print("     - Sensor mode (should be in Smart Sensor Terminal mode)")


if __name__ == "__main__":
    main()
