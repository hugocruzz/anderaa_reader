"""
Identify which Aanderaa sensor is on which COM port
This will tell you the actual sensor type connected to each port
"""
import serial
import time

def identify_sensor(port_name):
    """Connect to a port and identify what sensor is there"""
    print(f"\n{'='*60}")
    print(f"Testing {port_name}")
    print('='*60)
    
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=9600,
            timeout=5,  # Longer timeout
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        
        print(f"✓ Port opened")
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)
        
        # Wake up sensor
        print("Waking up sensor...")
        for _ in range(5):
            ser.write(b'\r\n')
            time.sleep(0.2)
        
        ser.write(b'%')
        time.sleep(0.5)
        
        # Clear wake-up response
        ser.reset_input_buffer()
        time.sleep(1.0)
        
        # Get Product Name
        print("Requesting ProductName...")
        ser.reset_input_buffer()
        ser.write(b'$GET ProductName\r\n')
        time.sleep(1.0)
        
        product_response = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                product_response += chunk
                time.sleep(0.2)
            else:
                if product_response:
                    break
                time.sleep(0.2)
            attempts += 1
        
        # Get Serial Number
        print("Requesting SerialNumber...")
        ser.reset_input_buffer()
        time.sleep(0.3)
        ser.write(b'$GET SerialNumber\r\n')
        time.sleep(1.0)
        
        serial_response = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                serial_response += chunk
                time.sleep(0.2)
            else:
                if serial_response:
                    break
                time.sleep(0.2)
            attempts += 1
        
        ser.close()
        
        # Parse responses
        product_name = "UNKNOWN"
        serial_number = "UNKNOWN"
        sensor_type = "UNKNOWN"
        
        if product_response:
            for line in product_response.split('\n'):
                if '=' in line:
                    product_name = line.split('=')[1].strip()
                    break
        
        if serial_response:
            for line in serial_response.split('\n'):
                if '=' in line:
                    serial_number = line.split('=')[1].strip()
                    break
        
        # Identify sensor type
        if '4117' in product_name:
            sensor_type = "pressure"
            full_name = f"Pressure Sensor {product_name} SN {serial_number}"
        elif '4330' in product_name:
            sensor_type = "oxygen"
            full_name = f"Oxygen Optode {product_name} SN {serial_number}"
        elif '5819' in product_name or '5990' in product_name:
            sensor_type = "conductivity"
            full_name = f"Conductivity Sensor {product_name} SN {serial_number}"
        else:
            full_name = f"{product_name} SN {serial_number}"
        
        print(f"\n✓ IDENTIFIED:")
        print(f"  Product: {product_name}")
        print(f"  Serial#: {serial_number}")
        print(f"  Type: {sensor_type}")
        
        return {
            'port': port_name,
            'success': True,
            'product_name': product_name,
            'serial_number': serial_number,
            'sensor_type': sensor_type,
            'full_name': full_name
        }
        
    except serial.SerialException as e:
        print(f"✗ Port error: {e}")
        return {'port': port_name, 'success': False, 'error': str(e)}
    except Exception as e:
        print(f"✗ Error: {e}")
        return {'port': port_name, 'success': False, 'error': str(e)}


def main():
    print("\n" + "="*60)
    print("AANDERAA SENSOR IDENTIFICATION TOOL")
    print("="*60)
    print("\nThis will identify which sensor is on which COM port")
    print("and show you the correct configuration.\n")
    
    # Test your three ports
    ports = ['COM3', 'COM4', 'COM5']
    
    results = []
    for port in ports:
        result = identify_sensor(port)
        results.append(result)
        time.sleep(0.5)
    
    # Summary
    print("\n\n" + "="*60)
    print("IDENTIFICATION SUMMARY")
    print("="*60 + "\n")
    
    detected = [r for r in results if r.get('success')]
    
    if detected:
        print(f"✓ Found {len(detected)} sensor(s):\n")
        for r in detected:
            print(f"{r['port']}: {r['full_name']}")
            print(f"         Type = '{r['sensor_type']}'")
            print()
    else:
        print("✗ No sensors detected!")
        print("\nPossible issues:")
        print("  - Sensors not powered")
        print("  - Wrong COM ports")
        print("  - Sensors in AiCaP mode")
        return
    
    # Generate correct config
    print("\n" + "="*60)
    print("CORRECT sensor_config.json")
    print("="*60 + "\n")
    
    print("{")
    print('  "sensors": [')
    
    for i, sensor in enumerate(detected):
        comma = "," if i < len(detected) - 1 else ""
        print('    {')
        print(f'      "name": "{sensor["full_name"]}",')
        print(f'      "com_port": "{sensor["port"]}",')
        print(f'      "baudrate": 9600,')
        print(f'      "sensor_type": "{sensor["sensor_type"]}",')
        print(f'      "timeout": 5')
        print(f'    }}{comma}')
    
    print('  ]')
    print('}')
    
    print("\n" + "="*60)
    print("ACTION REQUIRED:")
    print("="*60)
    print("\nCompare the configuration above with your current")
    print("sensor_config.json file. Update if different!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
