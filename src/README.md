# Aanderaa Sensor Communication Scripts

Python scripts for communicating with Aanderaa sensors via RS-232/COM ports.

## Supported Sensors

- **Pressure Sensor 4117B** - Measures pressure, tide, and wave parameters
- **Oxygen Optode 4330** - Measures dissolved oxygen concentration and saturation
- **Conductivity Sensor 5819** - Measures conductivity, salinity, and temperature

## Installation

1. Install Python 3.7 or higher

2. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Method 1: Edit sensor_config.json

Edit the `sensor_config.json` file to specify your COM ports:

```json
{
  "sensors": [
    {
      "name": "Pressure Sensor 4117B SN 2378",
      "com_port": "COM3",
      "baudrate": 9600,
      "sensor_type": "pressure",
      "timeout": 2
    },
    {
      "name": "Oxygen Optode 4330IW SN 4445",
      "com_port": "COM4",
      "baudrate": 9600,
      "sensor_type": "oxygen",
      "timeout": 2
    },
    {
      "name": "Conductivity Sensor 5819C IW SN 385",
      "com_port": "COM5",
      "baudrate": 9600,
      "sensor_type": "conductivity",
      "timeout": 2
    }
  ]
}
```

The reader will also print a suggested `sensor_config.json` based on live detection.

## Finding COM Ports

### Windows
1. Open Device Manager
2. Expand "Ports (COM & LPT)"
3. Note the COM port numbers for your USB-to-Serial adapters

### Alternatively, use Python:
```python
import serial.tools.list_ports
ports = serial.tools.list_ports.comports()
for port in ports:
    print(f"{port.device}: {port.description}")
```

## Usage

### Read sensors (continuous / streaming)
```bash
python aanderaa_sensor_reader_custom.py
```

### Configure faster automatic streaming (sensor-side)

If you are only getting a new data point every ~30 seconds, that is typically controlled by the sensor's `Interval` setting.
You can configure the sensors for automatic streaming (polled mode off) and set a faster interval using:

```bash
python configure_streaming_mode.py --from-config --interval 5
```

Or specify ports directly:

```bash
python configure_streaming_mode.py --ports COM12 COM13 COM14 --interval 2
```

Notes:
- This changes settings on the sensor (it sends `Set Interval(...)`, `Set Enable Polled Mode(no)`, `Save`, and optionally `Reset`).
- You need a bidirectional cable/adapter; some RS-422/field cables are RX-only and cannot accept configuration commands.

## Script Features

- **Automatic sensor wake-up** from communication sleep mode
- **Sensor identification** - reads product name, serial number, and software version
- **Continuous measurement reading** - prints when new frames arrive
- **Auto-detect protocol** - supports tab-delimited streaming mode (NI/VISA-like)
- **Auto-identification** - detects ProductNumber + SerialNumber from frames
- **Graceful shutdown** with Ctrl+C

## Output

The script will display:
1. Connection status for each sensor
2. Sensor information (product name, serial number, software version)
3. Real-time measurements from all connected sensors
4. Timestamp for each measurement cycle

Example output:
```
============================================================
Connecting to Aanderaa Sensors...
============================================================

Connected to Pressure Sensor 4117B on COM3
Connected to Oxygen Optode 4330 on COM4
Connected to Conductivity Sensor 5819 on COM5

============================================================
Sensor Information
============================================================

Pressure Sensor 4117B SN 2378:
----------------------------------------
  ProductName: 4117B
  SerialNumber: 2378
  SWVersion: 1.0.0

Oxygen Optode 4330IW SN 4445:
----------------------------------------
  ProductName: 4330IW
  SerialNumber: 4445
  SWVersion: 2.1.0

Conductivity Sensor 5819C IW SN 385:
----------------------------------------
  ProductName: 5819C
  SerialNumber: 385
  SWVersion: 1.5.0

============================================================
Reading Measurements
============================================================

Timestamp: 2025-12-19 10:30:15
------------------------------------------------------------

Pressure Sensor 4117B SN 2378:
  Pressure: 10132.5 mbar
  Temperature: 15.3 °C

Oxygen Optode 4330IW SN 4445:
  O2Concentration: 250.5 µM
  O2Saturation: 95.2 %
  Temperature: 15.1 °C

Conductivity Sensor 5819C IW SN 385:
  Conductivity: 52.5 mS/cm
  Salinity: 35.2 PSU
  Temperature: 15.2 °C
```

## Diagnostic Tools

Before running the main script, use these diagnostic tools to identify connection issues:

### 1. Comprehensive Connection Test (Recommended)
```bash
python test_sensor_connection.py
```
This will:
- Scan for all COM ports
- Test each port for Aanderaa sensors
- Identify sensor types and serial numbers (tab-delimited streaming mode, with Terminal fallback)
- Generate a sensor_config.json automatically

## Troubleshooting

### Script Stuck at "Connecting to Sensors"

This is the most common issue. Causes:

1. **Wrong COM port**: 
   - Run `test_sensor_connection.py` to find correct ports
   - Check Device Manager (Windows) → Ports (COM & LPT)
   
2. **Sensor not powered**: 
   - Aanderaa sensors require 6-14V DC power
   - Check power supply is ON and connected
   
3. **Wrong cable type**: 
   - Must use proper RS-232 cable (not just any serial cable)
   - Aanderaa cables: 3855 (lab), 4865 (field), or 4762 (free end)
   
4. **Sensor in wrong mode**:
  - Some devices may be configured for a different protocol/mode
  - Start with `python test_sensor_connection.py` to see what the device is emitting

5. **Baudrate mismatch**:
  - Default is 9600 (most common)
  - If needed, try: 9600, 19200, 57600, 115200

### Connection Issues

1. **Check COM port**: Verify the correct COM port in Device Manager
2. **Check baudrate**: Default is 9600, verify in sensor documentation
3. **Check cables**: Ensure RS-232 cables are properly connected
4. **Check drivers**: Install FTDI or Prolific drivers if needed
5. **Check permissions**: Run as administrator if access is denied
6. **Timeout too short**: Increase timeout in sensor_config.json to 5 seconds

### No Data Received

1. The sensors may be in a different communication mode (AiCaP vs Terminal)
2. Try sending wake-up commands multiple times
3. Check that sensors are powered (6-14V DC)
4. Verify cable pinout matches sensor requirements
5. Some sensors need longer wake-up time (up to 2 seconds)

### Wrong Data Format

- The sensors may need to be configured for Smart Sensor Terminal mode
- Use Aanderaa's Real-Time Collector software to verify sensor settings
- Check the Mode property: should be "Terminal" not "AiCaP"

## Smart Sensor Terminal Commands

The script uses these commands (from the manuals):

- `$GET PropertyName` - Read a property value
- `$SET PropertyName=Value` - Write a property value
- `DO` - Perform a measurement
- `HELP` - List available commands

## Additional Resources

- Aanderaa manuals in `documentation/` folder
- Sensor datasheets
- TD302 manual for Pressure Sensor
- Oxygen Optode 4330 manual
- Conductivity Sensor 5819 manual

## Notes

- Sensors use RS-232 protocol with 9600 baud, 8 data bits, no parity, 1 stop bit
- Communication timeout is set to 2 seconds
- Sensors may enter sleep mode if no communication for a period
- The script sends wake-up signals automatically
