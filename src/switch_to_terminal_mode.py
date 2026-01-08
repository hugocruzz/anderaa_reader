"""
Switch Aanderaa Sensors from AADI Real-Time Mode to Smart Sensor Terminal Mode
"""
import serial
import time

def try_xml_commands(port_name):
    """Test if sensor is in AADI Real-Time mode by trying XML commands"""
    print(f"\n{'='*70}")
    print(f"Testing {port_name} for AADI Real-Time Mode (XML)")
    print('='*70)
    
    try:
        ser = serial.Serial(port_name, 9600, timeout=3)
        print(f"✓ Port opened\n")
        
        # Wake up
        ser.write(b'\r\n')
        time.sleep(0.5)
        ser.reset_input_buffer()
        
        # Try XML command to get product info
        print("[Test 1] Sending XML command: <Get><ProductName/></Get>")
        ser.write(b'<Get><ProductName/></Get>\r\n')
        time.sleep(1.5)
        
        response = ""
        attempts = 0
        while attempts < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                response += chunk
                time.sleep(0.2)
            else:
                if response:
                    break
                time.sleep(0.2)
            attempts += 1
        
        print(f"Response: {response[:200]}")
        
        if '<Result>' in response or '<ProductName>' in response:
            print("\n✓ CONFIRMED: Sensor is in AADI Real-Time mode (XML)")
            print("  This explains the 'Syntax error' with ASCII commands!")
            return True, response
        else:
            print("\n? Not sure - no XML response received")
            return False, response
        
        ser.close()
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False, ""


def switch_mode_instructions(port_name):
    """Show how to switch from Real-Time to Terminal mode"""
    print(f"\n{'='*70}")
    print(f"HOW TO SWITCH {port_name} TO SMART SENSOR TERMINAL MODE")
    print('='*70)
    
    print("""
Your sensors are in AADI Real-Time mode (XML protocol).
Our Python scripts expect Smart Sensor Terminal mode (ASCII commands).

═══════════════════════════════════════════════════════════════
OPTION 1: Use XML Commands to Switch Mode (Try This First!)
═══════════════════════════════════════════════════════════════

I'll try to switch the sensor automatically...
""")


def try_auto_switch(port_name):
    """Attempt to switch sensor to Terminal mode using XML commands"""
    print(f"\n[ATTEMPTING AUTO-SWITCH ON {port_name}]")
    
    try:
        ser = serial.Serial(port_name, 9600, timeout=5)
        
        # Wake up
        ser.write(b'\r\n')
        time.sleep(0.5)
        ser.reset_input_buffer()
        
        # Step 1: Get current mode
        print("\n1. Checking current mode...")
        ser.write(b'<Get><Mode/></Get>\r\n')
        time.sleep(1.0)
        
        mode_response = ""
        if ser.in_waiting > 0:
            mode_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   Current mode response: {mode_response[:150]}")
        
        # Step 2: Set mode to Terminal
        print("\n2. Setting mode to 'Smart Sensor Terminal'...")
        ser.write(b'<Set><Mode>Smart Sensor Terminal</Mode></Set>\r\n')
        time.sleep(1.5)
        
        set_response = ""
        if ser.in_waiting > 0:
            set_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   Response: {set_response[:150]}")
        
        if 'Error' in set_response or 'error' in set_response:
            print("   ✗ Error setting mode")
            ser.close()
            return False
        
        # Step 3: Save settings
        print("\n3. Saving settings...")
        ser.write(b'<Command>Save</Command>\r\n')
        time.sleep(1.0)
        
        save_response = ""
        if ser.in_waiting > 0:
            save_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   Response: {save_response[:150]}")
        
        # Step 4: Reset sensor
        print("\n4. Resetting sensor (will reboot)...")
        ser.write(b'<Command>Reset</Command>\r\n')
        time.sleep(0.5)
        ser.close()
        
        print("\n   ⏳ Waiting 10 seconds for sensor to reboot...")
        time.sleep(10)
        
        # Step 5: Test if it worked
        print("\n5. Testing if sensor is now in Terminal mode...")
        ser = serial.Serial(port_name, 9600, timeout=3)
        
        # Wake up
        for _ in range(3):
            ser.write(b'\r\n')
            time.sleep(0.2)
        
        time.sleep(1.0)
        ser.reset_input_buffer()
        
        # Try ASCII command
        ser.write(b'$GET ProductName\r\n')
        time.sleep(1.5)
        
        test_response = ""
        if ser.in_waiting > 0:
            test_response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
            print(f"   Response: {test_response[:200]}")
        
        ser.close()
        
        if 'Syntax error' not in test_response and '=' in test_response:
            print("\n   ✓ SUCCESS! Sensor is now in Terminal mode!")
            return True
        else:
            print("\n   ✗ Still getting errors - manual switch needed")
            return False
        
    except Exception as e:
        print(f"\n   ✗ Error during auto-switch: {e}")
        return False


def show_manual_instructions():
    """Show manual switching instructions"""
    print(f"""
═══════════════════════════════════════════════════════════════
OPTION 2: Manual Switch Using Aanderaa Real-Time Collector
═══════════════════════════════════════════════════════════════

If automatic switching didn't work, use the official software:

1. Download "Aanderaa Real-Time Collector" from:
   https://www.aanderaa.com/software
   (or contact aanderaa.support@xylem.com)

2. Install and launch the software

3. Add New Connection:
   • Click "Add Connection"
   • Select your COM port (COM3, COM4, or COM5)
   • Protocol: "AADI Real-Time"
   • Baudrate: 9600
   • Click "Connect"

4. Change Mode:
   • Go to "Device Configuration" tab
   • Find "System Configuration" → "Common Settings"
   • Find "Mode" property
   • Change from "AADI Real-Time" to "Smart Sensor Terminal"
   • Click "Write to Device"

5. Reset Sensor:
   • Go to "Device" menu
   • Click "Reset"
   • Wait 10 seconds for sensor to reboot

6. Repeat for all 3 sensors (COM3, COM4, COM5)

7. After all sensors are switched, run:
   python aanderaa_sensor_reader_config.py

═══════════════════════════════════════════════════════════════
""")


def main():
    print("\n" + "="*70)
    print("AANDERAA SENSOR MODE SWITCHER")
    print("="*70)
    print("\nYour sensors are responding but giving 'Syntax error'.")
    print("This means they're in AADI Real-Time mode (XML), not Terminal mode.")
    print("\nLet's fix this!\n")
    
    ports = ['COM3', 'COM4', 'COM5']
    
    # Test each port
    xml_confirmed = []
    for port in ports:
        is_xml, response = try_xml_commands(port)
        if is_xml:
            xml_confirmed.append(port)
        time.sleep(0.5)
    
    if not xml_confirmed:
        print("\n⚠️  Couldn't confirm XML mode, but let's try switching anyway...")
        xml_confirmed = ports
    
    # Try to switch each sensor automatically
    print("\n\n" + "="*70)
    print("ATTEMPTING AUTOMATIC MODE SWITCH")
    print("="*70)
    
    success_count = 0
    for port in xml_confirmed:
        switch_mode_instructions(port)
        if try_auto_switch(port):
            success_count += 1
        time.sleep(1)
    
    # Summary
    print("\n\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    if success_count == len(xml_confirmed):
        print(f"\n✓ All {success_count} sensor(s) successfully switched!")
        print("\nYou can now run:")
        print("  python aanderaa_sensor_reader_config.py")
    elif success_count > 0:
        print(f"\n⚠️  {success_count} of {len(xml_confirmed)} sensor(s) switched successfully")
        print("The remaining sensors need manual switching.")
        show_manual_instructions()
    else:
        print(f"\n✗ Automatic switching failed for all sensors")
        print("You need to use the manual method:")
        show_manual_instructions()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
