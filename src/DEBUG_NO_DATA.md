# Debugging "No Data Received" Issue

## Your Situation
- ✅ Sensors have proper voltage/power
- ✅ COM ports detected: COM3, COM4, COM5
- ✅ Ports open successfully
- ❌ **No data received from any of the 3 sensors**

## Most Likely Causes

### 1. **Sensors in AiCaP Mode** (80% probability) ⚙️

**Problem:** Sensors configured for SeaGuard logger, not standalone RS-232

**Why this happens:**
- Aanderaa sensors can operate in different modes
- AiCaP = for use with SeaGuard/SmartGuard loggers
- Terminal = for standalone RS-232 communication
- **Sensors in AiCaP mode will NOT respond to RS-232 commands!**

**How to check:**
```bash
python debug_communication.py
# Enter: COM3,COM4,COM5
```

This will test:
- Different wake-up sequences
- Multiple command formats
- Different baudrates
- Listen for any data

**If all tests fail:** Sensors are likely in AiCaP mode

**How to fix:**
1. Download Aanderaa Real-Time Collector (from Aanderaa/Xylem)
2. Connect to each sensor one at a time
3. Go to: System Configuration → Common Settings
4. Find "Mode" property
5. Change from "AiCaP" to "Terminal"
6. Click "Write to device"
7. Important: Send RESET command (Device menu)
8. Wait 10 seconds for sensor to reboot
9. Repeat for all 3 sensors

### 2. **TX/RX Wires Crossed** (15% probability) 🔌

**Problem:** Cable has TX and RX swapped

**How to check:**
- Are you using proper Aanderaa cables (3855, 4865)?
- Or generic DB-9 serial cables?

**Generic cables may need null-modem adapter!**

**Pinout for Aanderaa sensors:**
```
DB-9 Female (at PC/hub):
Pin 2: RX (receive from sensor)
Pin 3: TX (transmit to sensor)  
Pin 5: GND

Sensor should transmit on pin 3 of its connector
```

**Quick test:**
- Try a null-modem adapter between sensor and hub
- Or swap pins 2 and 3 in cable

### 3. **Flow Control Mismatch** (3% probability) 🔄

**Problem:** Sensor expects flow control signals

**Quick fix - try with DTR/RTS asserted:**

```python
import serial
ser = serial.Serial('COM3', 9600, timeout=2)
ser.dtr = True  # Assert DTR
ser.rts = True  # Assert RTS
time.sleep(0.5)
ser.write(b'HELP\r\n')
time.sleep(1)
print(ser.read(ser.in_waiting))
```

### 4. **Wrong Baudrate** (2% probability) 📡

**Problem:** Someone changed baudrate from default 9600

**Less likely** because you'd expect at least 1 of 3 sensors to work

**Test:** Run `debug_communication.py` - it auto-tests multiple baudrates

## Step-by-Step Debugging

### Step 1: Run Comprehensive Diagnostic

```bash
python debug_communication.py
```

Enter: `COM3,COM4,COM5`

This will:
- Test 8 different communication methods per port
- Try different baudrates
- Listen for any transmissions
- Show detailed results

**Expected outcomes:**

**If NO response to any test:**
→ Sensors in AiCaP mode (most likely)

**If response to some tests:**
→ Timing or protocol issue (we can fix)

**If data received but garbled:**
→ Wrong baudrate

### Step 2: Check with Real-Time Collector

If you have Aanderaa Real-Time Collector:

1. Launch the software
2. Add new connection (your COM port)
3. Baudrate: 9600
4. Protocol: Real-Time
5. Click Connect

**If it connects:**
- Check Device Configuration
- Look at Mode setting
- Should be "Terminal" not "AiCaP"

**If it doesn't connect:**
- Try "AiCaP" protocol setting
- If THAT works, sensors are in AiCaP mode!

### Step 3: Manual Cable Check

**Test cable continuity:**

1. Disconnect sensor
2. Use multimeter to check:
   - Pin 2 to Pin 2 (continuity)
   - Pin 3 to Pin 3 (continuity)
   - Pin 5 to Pin 5 (continuity)
   - No shorts between pins

**Or test with loopback:**

1. At sensor end: Connect TX to RX (pins 2 to 3)
2. At PC: Send data, should receive it back
3. If loopback works, cable is good

## Quick Test Script

Save this as `quick_test.py`:

```python
import serial
import time

port = 'COM3'  # Change as needed

print(f"Testing {port}...")

try:
    ser = serial.Serial(port, 9600, timeout=2)
    print("✓ Port opened")
    
    # Test 1: Maximum wake-up
    print("\nWaking up sensor (aggressive)...")
    for i in range(20):
        ser.write(b'\r')
        time.sleep(0.05)
    time.sleep(1)
    
    # Test 2: HELP command
    print("Sending HELP...")
    ser.write(b'HELP\r\n')
    time.sleep(2)
    
    if ser.in_waiting > 0:
        data = ser.read(ser.in_waiting)
        print(f"✓ RECEIVED {len(data)} bytes!")
        print(f"Data: {data}")
        print("\n→ Sensor is responding!")
    else:
        print("✗ No data received")
        print("\nTrying with DTR/RTS asserted...")
        ser.dtr = True
        ser.rts = True
        time.sleep(0.5)
        ser.write(b'HELP\r\n')
        time.sleep(2)
        
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            print(f"✓ RECEIVED with DTR/RTS: {data}")
        else:
            print("✗ Still no data")
            print("\n→ Likely in AiCaP mode or cable issue")
    
    ser.close()
    
except Exception as e:
    print(f"✗ Error: {e}")
```

## What Each Test Means

### If debug tool shows:

**"No response to carriage returns"**
- Normal, continue testing

**"No response to '%'"**
- Normal if not in sleep mode

**"No response to HELP"**
- ⚠️ Problem - sensor not in Terminal mode or cable issue

**"No response to $GET"**
- ⚠️ Problem - sensor not responding to commands

**"No data in 5 seconds"**
- ⚠️ Problem - sensor not transmitting anything

**"No response to XML either"**
- 🔴 Likely in AiCaP mode (CANbus only)

## Expected Behavior (Normal Sensor)

**When working correctly:**
```
[Test 4] Sending HELP command...
   ✓ HELP response (1234 bytes):
   'HELP\r\nAvailable commands:\r\n$GET\r\n$SET\r\nDO\r\n...'
```

## Next Actions Based on Results

### All ports: "No response to any test"
→ **Use Real-Time Collector to change mode to Terminal**

### Some ports work, some don't
→ **Different sensors in different modes**
→ **Check each sensor individually**

### Garbled data or wrong characters
→ **Wrong baudrate**
→ **Try 19200, 57600, or 115200**

### Port opens but immediate error
→ **Driver issue**
→ **Try different USB port**

### Data received but not command responses
→ **Sensor transmitting but not receiving**
→ **Check TX/RX wiring**

## Important Notes

1. **Aanderaa sensors have 3 modes:**
   - Terminal (for RS-232 standalone) ← YOU NEED THIS
   - AiCaP (for SeaGuard logger)
   - Real-Time (XML protocol)

2. **Mode can ONLY be changed with:**
   - Aanderaa Real-Time Collector, OR
   - Terminal command: `$SET Mode=Terminal` (but need to be connected first!)

3. **After changing mode:**
   - MUST send RESET command
   - Wait 10 seconds for reboot
   - Then reconnect

4. **If nothing works:**
   - Contact Aanderaa support: aanderaa.support@xylem.com
   - They can verify sensor mode remotely
   - Provide serial numbers: 2378, 4445, 385
