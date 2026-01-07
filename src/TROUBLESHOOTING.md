# Quick Start - Troubleshooting Connection Issues

## Your Issue: Script Stuck at "Connecting to Sensors"

This means the script cannot establish communication with the sensors.

## Quick Fix - Run Diagnostic

**FIRST, run this:**
```bash
python test_sensor_connection.py
```

This will:
✓ Find all COM ports automatically  
✓ Test each port for Aanderaa sensors  
✓ Identify which sensors are connected  
✓ Generate correct configuration for you  

## Common Causes & Solutions

### 1. Wrong COM Port ❌
**How to check:**
- Open Device Manager → Ports (COM & LPT)
- Look for USB Serial Port or similar
- Note the COM numbers (COM3, COM4, etc.)

**Fix:** Update COM ports in `sensor_config.json`

### 2. Sensors Not Powered ⚡
**Check:**
- Power supply is ON
- Voltage is 6-14V DC
- Power cable is connected properly

**Fix:** Turn on power supply

### 3. Wrong Cable Type 🔌
**You need:**
- Proper Aanderaa RS-232 cable
- NOT just any serial cable
- Cables: 3855 (lab), 4865 (field), or 4762 (free end)

**Fix:** Use correct Aanderaa cable

### 4. Wrong Sensor Mode ⚙️
**Issue:**
- Sensor might be in "AiCaP" mode
- Needs to be in "Smart Sensor Terminal" mode

**Fix:**
- Use Aanderaa Real-Time Collector software
- Change Mode property to "Terminal"
- Save and reset sensor

### 5. Wrong Baudrate 📡
**Default is 9600**
- Pressure sensor: 4800, 9600, 57600, 115200
- Oxygen Optode: 9600, 19200, 57600, 115200
- Conductivity: 9600, 19200, 57600, 115200

**Fix:** Run `python quick_baudrate_test.py` to auto-detect

## Step-by-Step Troubleshooting

### Step 1: Check Physical Connections
```
1. Is power supply ON? → Check voltage (6-14V DC)
2. Are cables properly connected? → Check both ends
3. Is USB-to-Serial adapter plugged in? → Should see light
```

### Step 2: Find COM Ports
```bash
# Windows Command Prompt or PowerShell:
mode

# Or in Python:
python -c "import serial.tools.list_ports; [print(p.device, '-', p.description) for p in serial.tools.list_ports.comports()]"
```

### Step 3: Run Diagnostic
```bash
python test_sensor_connection.py
```
This will test everything automatically.

### Step 4: Update Configuration
Edit `sensor_config.json` with correct COM ports from Step 3.

### Step 5: Try Again
```bash
python aanderaa_sensor_reader_config.py
```

## Expected Sensor Settings

According to the manuals:

| Sensor | Default Baudrate | Available Baudrates |
|--------|-----------------|-------------------|
| 4117B Pressure | 9600 | 4800, 9600, 57600, 115200 |
| 4330 Oxygen | 9600 | 9600, 19200, 57600, 115200 |
| 5819 Conductivity | 9600 | 4800, 9600, 57600, 115200 |

**Communication Settings:**
- Data bits: 8
- Stop bits: 1
- Parity: None
- Flow control: Xon/Xoff or None

## Still Not Working?

### Test Individual Port Manually

```python
import serial
import time

# Replace COM3 with your port
ser = serial.Serial('COM3', 9600, timeout=2)

# Wake up
for i in range(5):
    ser.write(b'\r\n')
    time.sleep(0.2)

# Test command
ser.write(b'$GET ProductName\r\n')
time.sleep(1)

# Read response
if ser.in_waiting > 0:
    print("SUCCESS:", ser.read(ser.in_waiting).decode('ascii', errors='ignore'))
else:
    print("NO RESPONSE - Check power, cable, or sensor mode")

ser.close()
```

## Get Help

If still stuck:
1. Check which LED lights are ON (power, communication)
2. Try a different USB port
3. Reinstall USB-to-Serial drivers
4. Test with Aanderaa Real-Time Collector software first
5. Verify sensor is not in sleep mode or AiCaP mode

## Quick Reference

**Files:**
- `test_sensor_connection.py` - Main diagnostic tool (RUN THIS FIRST)
- `quick_baudrate_test.py` - Test baudrates on one port
- `test_com_ports.py` - Detailed port testing
- `sensor_config.json` - Configuration file (update COM ports here)
- `aanderaa_sensor_reader_config.py` - Main script

**Typical sensor_config.json:**
```json
{
  "sensors": [
    {
      "name": "Pressure Sensor 4117B SN 2378",
      "com_port": "COM3",
      "baudrate": 9600,
      "sensor_type": "pressure",
      "timeout": 2
    }
  ]
}
```
