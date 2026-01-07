# Aanderaa Sensor Connection Guide
## Based on Official Documentation

## Communication Protocol Details

### Default Settings (All Sensors)
From the manuals, factory default settings are:

| Parameter | Value |
|-----------|-------|
| Baudrate | 9600 |
| Data bits | 8 |
| Stop bits | 1 |
| Parity | None |
| Flow control | Xon/Xoff or None |

### Available Baudrates by Sensor

| Sensor | Available Baudrates |
|--------|-------------------|
| 4117B Pressure | 4800, 9600, 57600, 115200 |
| 4330 Oxygen | 300, 1200, 2400, 4800, 9600, 57600, 115200 |
| 5819 Conductivity | 4800, 9600, 57600, 115200 |

**Note:** Baudrates lower than 9600 may limit sampling frequency.

## Sensor Modes (Critical!)

Aanderaa sensors can operate in different modes:

### 1. **Smart Sensor Terminal Mode** (for standalone RS-232)
- ✅ Use this mode for direct PC connection
- ✅ ASCII command protocol ($GET, $SET, DO, HELP)
- ✅ Works with our Python scripts

### 2. **AiCaP Mode** (for SeaGuard/SmartGuard)
- ❌ NOT for standalone use
- ❌ Will NOT respond to RS-232 commands
- Uses CANbus protocol for logger connection

### 3. **AADI Real-Time Mode** (XML-based)
- XML-based communication
- More structured than Terminal mode

## Communication Sleep Mode

**IMPORTANT:** Sensors enter sleep mode after inactivity!

### Wake-up Protocol (from documentation):

1. **Send carriage returns:**
   ```
   \r\n (multiple times, 3-5 recommended)
   ```

2. **Send '%' character:**
   ```
   % (single character, wakes from communication sleep)
   ```

3. **Wait for '!' indicator:**
   ```
   ! (means sensor is ready for communication)
   ```

### Communication Timeout Settings

Default timeout periods (configurable):
- Always On (no sleep)
- 10 seconds
- 20 seconds
- 30 seconds
- 1 minute
- 2 minutes
- 5 minutes
- 10 minutes

## Cable Requirements

### Proper Aanderaa Cables:

1. **Cable 3855** - Laboratory setup (RS-232)
   - Sensor to PC
   - Short cable for bench testing

2. **Cable 4865** - Field use (RS-232)
   - Sensor to PC
   - Ruggedized for field deployment

3. **Cable 4762** - Sensor to free end (RS-232)
   - Custom termination

4. **Cable 4793** - Remote sensor (for SeaGuard)
   - AiCaP connection

**⚠️ DO NOT use generic serial cables!** Pin configurations are specific.

## Pin Configurations

### Pressure Sensor 4117B (RS-232 version)
```
Pin 1: CAN_H (not used in RS-232)
Pin 2: NCG (Node Communication Ground)
Pin 3: NCR (Node Communication Request)
Pin 4: Gnd (Ground)
Pin 5: +V (6-14V DC positive supply)
Pin 6: NCE (Node Communication Enable)
Pin 7: BOOT_EN (do not connect)
Pin 8: CAN_L (not used in RS-232)
Pin 9: RS-232 RXD (Receive)
Pin 10: RS-232 TXD (Transmit)
```

### Oxygen Optode 4330 & Conductivity 5819
Similar pinout, RS-232 on pins 9-10.

## Troubleshooting Connection Issues

### Issue: "Stuck at Connecting to Sensors"

**Most Common Causes:**

#### 1. Sensor in Wrong Mode ⚙️
**Check:** Sensor is in **AiCaP mode** instead of **Terminal mode**

**Symptoms:**
- Port opens successfully
- No response to any commands
- No error messages

**Fix:**
1. Use Aanderaa Real-Time Collector software
2. Connect to sensor
3. Go to System Configuration
4. Change Mode property to "Terminal"
5. Save and Reset sensor
6. Reconnect

**Command line fix (if accessible):**
```
$SET Mode=Terminal
SAVE
RESET
```

#### 2. Communication Sleep Active 💤
**Check:** Sensor entered sleep mode

**Fix:** Use proper wake-up sequence (now in updated scripts):
```python
# Send multiple carriage returns
for i in range(5):
    ser.write(b'\r\n')
    time.sleep(0.15)

# Send '%' character
ser.write(b'%')
time.sleep(0.3)

# Wait for '!' ready indicator
time.sleep(0.7)
```

#### 3. Wrong Baudrate 📡
**Check:** Sensor configured for different baudrate

**Common scenarios:**
- Sensor was reconfigured to 57600 or 115200
- Previous user changed baudrate

**Fix:** Run `python quick_baudrate_test.py` to detect

#### 4. Wrong COM Port 🔌
**Check:** Device Manager shows different port

**Fix:**
1. Open Device Manager
2. Expand "Ports (COM & LPT)"
3. Note actual COM numbers
4. Update sensor_config.json

#### 5. Flow Control Mismatch 🔄
**Check:** Terminal software flow control doesn't match sensor

**Default:** Xon/Xoff or None
**Fix:** Our scripts use None (should work)

## How to Change Sensor Mode

### Using Aanderaa Real-Time Collector:

1. **Connect sensor** via RS-232 cable
2. **Launch** AADI Real-Time Collector
3. **Add connection:**
   - Select COM port
   - Baudrate: 9600
   - Click Connect
4. **Go to Device Configuration** tab
5. **System Configuration** → **Common Settings**
6. **Find "Mode" property**
7. **Change to:** "Terminal"
8. **Click "Write to device"**
9. **Important:** Send RESET command (Device menu)
10. **Reconnect** after reset

### Using Terminal Software:

```
# Wake up sensor
<CR><CR><CR>%

# Check current mode
$GET Mode

# Change to Terminal mode
$SET Mode=Terminal

# Save changes
SAVE

# Reset sensor (required!)
RESET

# Wait 5-10 seconds for reboot
# Reconnect
```

## Command Reference

### Essential Commands:

```bash
# Get property value
$GET PropertyName

# Set property value
$SET PropertyName=Value

# Perform measurement
DO

# List available commands
HELP

# Save changes to persistent memory
SAVE

# Reset sensor (reboot)
RESET

# Get all measurements
GETALL
```

### Common Properties:

```bash
$GET ProductName      # e.g., "4117B", "4330IW", "5819C"
$GET SerialNumber     # Sensor serial number
$GET SWVersion        # Firmware version
$GET Mode             # Current mode (AiCaP/Terminal/Real-Time)
$GET Baudrate         # Current baudrate
$GET Pressure         # Current pressure reading
$GET Temperature      # Current temperature
$GET O2Concentration  # Oxygen concentration (4330 only)
$GET Conductivity     # Conductivity (5819 only)
```

## Testing Procedure

### Step 1: Physical Check
- ✅ Power supply ON (6-14V DC)
- ✅ Correct cable type (Aanderaa 3855 or 4865)
- ✅ Cable fully inserted
- ✅ No visible damage

### Step 2: Run Diagnostic
```bash
python test_sensor_connection.py
```

This will:
1. Find all COM ports
2. Test each port
3. Detect sensor mode
4. Identify sensor type
5. Generate configuration

### Step 3: Check Mode
If diagnostic shows **"Mode: AiCaP"**:
1. This is the problem!
2. Use AADI Real-Time Collector to change to Terminal
3. OR connect to SeaGuard/SmartGuard (AiCaP is correct for that)

### Step 4: Update Configuration
Copy the generated sensor_config.json

### Step 5: Test Communication
```bash
python aanderaa_sensor_reader_config.py
```

## Power Requirements

All sensors require **6-14V DC**:
- Typical: 12V DC
- Current: Varies by sensor and operation
  - Pressure 4117B: ~8-15 mA @ 12V
  - Oxygen 4330: ~20-30 mA @ 12V  
  - Conductivity 5819: ~15-25 mA @ 12V

**⚠️ Without proper power, sensors will not respond!**

## RS-422 vs RS-232

### RS-232 Versions (4117, 4330, 5819):
- ✅ Can work with SeaGuard (AiCaP mode)
- ✅ Can work standalone (Terminal mode)
- Maximum cable length: ~30 meters @ 9600 baud

### RS-422 Versions (4117R, 4330R, 5819R):
- ❌ Cannot work with SeaGuard
- ✅ Standalone only
- Maximum cable length: ~1200 meters @ 9600 baud

**Note:** You cannot convert between RS-232 and RS-422 versions!

## Common Error Messages

### "PermissionError: Access is denied"
- COM port already in use
- Close other programs (TeraTerm, PuTTY, etc.)
- Disconnect/reconnect USB adapter

### "Could not open port COM3: FileNotFoundError"
- Wrong COM port number
- USB adapter not plugged in
- Driver not installed

### "No response from sensor"
- Sensor not powered
- Sensor in AiCaP mode
- Wrong baudrate
- Cable issue

## Quick Reference Card

```
┌─────────────────────────────────────────────┐
│  AANDERAA SENSOR QUICK CONNECT              │
├─────────────────────────────────────────────┤
│  1. Power: 6-14V DC                         │
│  2. Cable: Aanderaa 3855 or 4865           │
│  3. COM port: Check Device Manager          │
│  4. Baudrate: 9600 (default)               │
│  5. Mode: Must be "Terminal" not "AiCaP"   │
│  6. Wake-up: Send \r\n then %              │
│  7. Test: $GET ProductName                  │
│  8. Measure: DO                             │
└─────────────────────────────────────────────┘
```

## Getting Help

If still having issues:

1. **Run full diagnostic:**
   ```bash
   python test_sensor_connection.py
   ```

2. **Check sensor with Real-Time Collector:**
   - Aanderaa's official software
   - Can always communicate (even in AiCaP mode)
   - Can change mode back to Terminal

3. **Verify hardware:**
   - Use multimeter to check power voltage
   - Check for continuity in cable
   - Try different USB port

4. **Contact Aanderaa support:**
   - aanderaa.support@xylem.com
   - Have sensor S/N ready
   - Mention mode configuration issue
