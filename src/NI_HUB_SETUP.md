# National Instruments USB Hub Setup Guide

## Your Hardware Setup

You have:
- **National Instruments USB Hub** (4 ports)
- **3 Aanderaa sensors** (Pressure, Oxygen, Conductivity)
- **USB connection** to PC

## Critical Understanding: USB Hub is for COMMUNICATION ONLY!

⚠️ **IMPORTANT:** The NI USB hub provides RS-232 communication, **NOT power!**

### Correct Setup:

```
Power Supply (12V DC) ──┐
                        ├──> Sensor 1 (Pressure)
                        │      │
                        │      └──> RS-232 ──> NI Hub Port 1
                        │
                        ├──> Sensor 2 (Oxygen)
                        │      │
                        │      └──> RS-232 ──> NI Hub Port 2
                        │
                        └──> Sensor 3 (Conductivity)
                               │
                               └──> RS-232 ──> NI Hub Port 3

NI Hub ──USB──> PC
```

## Why Nothing Works - Common Issues

### Issue 1: No External Power ⚡
**Problem:** Sensors need 6-14V DC, USB only provides 5V

**Symptoms:**
- Ports open successfully
- No response from sensors
- No error messages

**Fix:**
- Connect EACH sensor to external 12V DC power supply
- Verify power supply is ON
- Check voltage with multimeter (should be 6-14V)

### Issue 2: NI Drivers Not Installed 💿
**Problem:** Windows doesn't recognize NI hardware

**Symptoms:**
- No COM ports appear
- Device Manager shows unknown device
- Yellow warning in Device Manager

**Fix:**
1. Download **NI-VISA** from ni.com/downloads
2. Or download **NI Serial** drivers
3. Install and **restart computer**
4. Check Device Manager → Ports (COM & LPT)

### Issue 3: Wrong Port Enumeration 🔢
**Problem:** NI hub creates 4 COM ports, but they might not be sequential

**Symptoms:**
- Only some ports work
- COM3, COM5, COM7, COM9 (skipped numbers)

**Fix:**
- Use our diagnostic tool (see below)
- Don't assume COM3, COM4, COM5, COM6

### Issue 4: Sensors in AiCaP Mode ⚙️
**Problem:** Sensors configured for SeaGuard, not standalone

**Symptoms:**
- Port opens successfully
- No response to any command
- Works with AADI Real-Time Collector

**Fix:**
- Use Aanderaa Real-Time Collector
- Change Mode to "Terminal"
- Save and Reset each sensor

## Step-by-Step Setup Procedure

### Step 1: Install NI Drivers

1. **Download NI-VISA:**
   - Go to ni.com/downloads
   - Search for "NI-VISA"
   - Download latest version
   - Install

2. **Restart computer** (required!)

3. **Verify in Device Manager:**
   - Open Device Manager
   - Expand "Ports (COM & LPT)"
   - Should see "NI USB Serial Port (COMx)" entries
   - Note the COM numbers

### Step 2: Connect Hardware

**For EACH sensor:**

1. **Connect power:**
   - Sensor power input: 6-14V DC (typically 12V)
   - Use appropriate power connector
   - Turn ON power supply
   - Verify sensor LED (if present)

2. **Connect RS-232:**
   - Use Aanderaa cable (3855, 4865, or 4762)
   - Sensor connector to sensor
   - DB-9 connector to NI hub port

3. **Connect NI hub:**
   - USB cable from hub to PC
   - Verify Windows recognizes device

### Step 3: Run Our Diagnostic

```bash
python test_ni_hub.py
```

This specialized tool will:
- ✅ Detect NI USB hub
- ✅ Find all NI COM ports
- ✅ Test each port for sensors
- ✅ Identify which ports have responding sensors
- ✅ Show power warnings
- ✅ Generate configuration

### Step 4: Check Results

**If NO sensors detected:**
1. **Power issue** - Most likely!
   - Each sensor needs external power
   - USB is NOT enough
   - Check with multimeter

2. **Mode issue:**
   - Sensors in AiCaP mode
   - Need to change to Terminal mode
   - Use AADI Real-Time Collector

3. **Driver issue:**
   - NI drivers not working
   - Reinstall NI-VISA
   - Check Device Manager

**If SOME sensors detected:**
- Working ports: Sensors powered and configured correctly
- Non-working ports: Check power and mode

### Step 5: Update Configuration

Copy the COM ports that worked into `sensor_config.json`:

```json
{
  "sensors": [
    {
      "name": "Pressure Sensor 4117B SN 2378",
      "com_port": "COM3",  // Use actual COM from diagnostic
      "baudrate": 9600,
      "sensor_type": "pressure",
      "timeout": 2
    },
    {
      "name": "Oxygen Optode 4330IW SN 4445",
      "com_port": "COM5",  // Use actual COM from diagnostic
      "baudrate": 9600,
      "sensor_type": "oxygen",
      "timeout": 2
    },
    {
      "name": "Conductivity Sensor 5819C IW SN 385",
      "com_port": "COM7",  // Use actual COM from diagnostic
      "baudrate": 9600,
      "sensor_type": "conductivity",
      "timeout": 2
    }
  ]
}
```

## NI Hub Specific Issues

### Issue: "Access Denied" Errors

**Cause:** NI hub driver conflicts

**Fix:**
```bash
# Run Command Prompt as Administrator
# Then run Python script
```

### Issue: Intermittent Connections

**Cause:** USB power management

**Fix:**
1. Device Manager → Ports
2. Right-click each NI USB Serial Port
3. Properties → Power Management
4. **Uncheck** "Allow computer to turn off this device"

### Issue: Hub Not Recognized

**Cause:** Driver not loaded or USB issue

**Fix:**
1. Unplug hub, wait 10 seconds
2. Plug into different USB port (preferably USB 3.0)
3. Check Device Manager for errors
4. Reinstall NI-VISA

## Testing Individual Ports

If you want to test a specific NI hub port:

```python
import serial
import time

# Replace with your actual COM port
port = "COM5"

try:
    ser = serial.Serial(port, 9600, timeout=2)
    print(f"✓ {port} opened successfully")
    
    # Wake up
    for _ in range(5):
        ser.write(b'\r\n')
        time.sleep(0.15)
    ser.write(b'%')
    time.sleep(1)
    
    # Test command
    ser.write(b'$GET ProductName\r\n')
    time.sleep(1)
    
    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
        print(f"✓ Response: {response}")
    else:
        print("✗ No response - Check power and sensor mode!")
    
    ser.close()
    
except Exception as e:
    print(f"✗ Error: {e}")
```

## Wiring Diagram

```
┌─────────────────────────────────────────────────┐
│ Sensor 1 (Pressure 4117B)                       │
│                                                  │
│  Power In ←── 12V DC Power Supply               │
│  RS-232 Out ──→ NI Hub Port 1 (COM3)           │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ Sensor 2 (Oxygen 4330IW)                        │
│                                                  │
│  Power In ←── 12V DC Power Supply               │
│  RS-232 Out ──→ NI Hub Port 2 (COM5)           │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ Sensor 3 (Conductivity 5819C)                   │
│                                                  │
│  Power In ←── 12V DC Power Supply               │
│  RS-232 Out ──→ NI Hub Port 3 (COM7)           │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ NI USB Hub (4-port)                             │
│                                                  │
│  Port 1 ───┐                                    │
│  Port 2 ───┼─── Individual RS-232 connections  │
│  Port 3 ───┤                                    │
│  Port 4 ───┘    (Communication only, NO power) │
│                                                  │
│  USB ────────→ PC                               │
└─────────────────────────────────────────────────┘
```

## Quick Checklist

Before running any scripts:

- [ ] NI-VISA drivers installed
- [ ] Computer restarted after driver install
- [ ] Device Manager shows NI USB Serial Ports
- [ ] Each sensor connected to 12V DC power supply
- [ ] Power supply is ON
- [ ] RS-232 cables from sensors to NI hub
- [ ] NI hub USB cable to PC
- [ ] Noted actual COM port numbers from Device Manager

## Running the Diagnostic

```bash
# Install Python dependencies
pip install pyserial

# Run NI hub specific diagnostic
python test_ni_hub.py

# Follow the prompts
# Note which COM ports have sensors
# Update sensor_config.json with working ports
```

## Still Not Working?

### Check 1: Device Manager
```
Open Device Manager
└─ Ports (COM & LPT)
   ├─ NI USB Serial Port (COM3)
   ├─ NI USB Serial Port (COM5)
   ├─ NI USB Serial Port (COM7)
   └─ NI USB Serial Port (COM9)
```
- No yellow warnings?
- COM ports listed?
- If not, reinstall NI-VISA

### Check 2: Sensor Power
```
Use multimeter to check:
- Voltage at sensor power input: 6-14V DC
- If 0V: power supply off or disconnected
- If wrong polarity: check cable pinout
```

### Check 3: Sensor Mode
```
Use AADI Real-Time Collector:
1. Connect to sensor
2. System Configuration → Mode
3. Should be "Terminal" not "AiCaP"
4. If AiCaP, change to Terminal, Save, Reset
```

### Check 4: Cable Continuity
```
Use multimeter to check:
- Continuity on TX, RX, GND pins
- No shorts between pins
- Proper DB-9 wiring
```

## Contact Info

**National Instruments Support:**
- ni.com/support
- For driver and hardware issues

**Aanderaa Support:**
- aanderaa.support@xylem.com
- For sensor configuration issues
