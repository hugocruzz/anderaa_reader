"""
Aanderaa Sensor Communication Script
Communicates with multiple Aanderaa sensors via RS-232/COM ports
Supports: Pressure Sensor 4117B, Oxygen Optode 4330, Conductivity Sensor 5819
"""

import serial
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SensorConfig:
    """Configuration for each sensor"""
    name: str
    com_port: str
    baudrate: int = 9600
    timeout: int = 2
    sensor_type: str = ""


class AanderaaSensor:
    """Class to handle communication with Aanderaa Smart Sensors"""
    
    def __init__(self, config: SensorConfig):
        self.config = config
        self.serial_port: Optional[serial.Serial] = None
        self.is_connected = False
        
    def connect(self) -> bool:
        """Establish connection with the sensor"""
        try:
            self.serial_port = serial.Serial(
                port=self.config.com_port,
                baudrate=self.config.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.config.timeout
            )
            
            # Wake up sensor from communication sleep
            self.wake_up_sensor()
            
            self.is_connected = True
            logger.info(f"Connected to {self.config.name} on {self.config.com_port}")
            return True
            
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.config.name}: {e}")
            return False
    
    def wake_up_sensor(self):
        """Wake up sensor from communication sleep mode"""
        # Wake-up protocol per Aanderaa documentation:
        # 1. Send multiple carriage returns
        # 2. Send '%' character to wake from communication sleep
        # 3. Wait for '!' ready indicator
        
        for _ in range(5):
            self.serial_port.write(b'\r\n')
            time.sleep(0.15)
        
        # Send '%' to wake from communication sleep mode
        self.serial_port.write(b'%')
        time.sleep(0.3)
        
        # Clear any buffered data
        self.serial_port.flushInput()
        self.serial_port.flushOutput()
        
        # Wait for communication ready indicator '!'
        time.sleep(0.7)
    
    def send_command(self, command: str) -> str:
        """Send command to sensor and receive response"""
        if not self.is_connected or not self.serial_port:
            logger.error(f"Sensor {self.config.name} not connected")
            return ""
        
        try:
            # Clear buffers
            self.serial_port.flushInput()
            self.serial_port.flushOutput()
            
            # Send command
            cmd = command + '\r\n'
            self.serial_port.write(cmd.encode('ascii'))
            logger.debug(f"Sent to {self.config.name}: {command}")
            
            # Wait for response
            time.sleep(0.3)
            
            # Read response
            response = ""
            while self.serial_port.in_waiting > 0:
                response += self.serial_port.read(self.serial_port.in_waiting).decode('ascii', errors='ignore')
                time.sleep(0.1)
            
            logger.debug(f"Received from {self.config.name}: {response}")
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error communicating with {self.config.name}: {e}")
            return ""
    
    def get_sensor_info(self) -> Dict[str, str]:
        """Get basic sensor information"""
        info = {}
        
        # Get product name
        response = self.send_command('$GET ProductName')
        if response:
            info['ProductName'] = self.parse_response(response)
        
        # Get serial number
        response = self.send_command('$GET SerialNumber')
        if response:
            info['SerialNumber'] = self.parse_response(response)
        
        # Get software version
        response = self.send_command('$GET SWVersion')
        if response:
            info['SWVersion'] = self.parse_response(response)
        
        return info
    
    def get_measurement(self) -> Dict[str, str]:
        """Get current measurement from sensor"""
        # Send DO command to get measurement
        response = self.send_command('DO')
        
        if not response:
            return {}
        
        # Parse the measurement response
        measurements = self.parse_measurement(response)
        return measurements
    
    def parse_response(self, response: str) -> str:
        """Parse GET command response"""
        # Response format: RESULT GET PropertyName=Value
        lines = response.split('\n')
        for line in lines:
            if '=' in line:
                return line.split('=', 1)[1].strip()
        return response.strip()
    
    def parse_measurement(self, response: str) -> Dict[str, str]:
        """Parse measurement response"""
        measurements = {}
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                measurements[key.strip()] = value.strip()
        
        return measurements
    
    def disconnect(self):
        """Close the serial connection"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.is_connected = False
            logger.info(f"Disconnected from {self.config.name}")


class PressureSensor(AanderaaSensor):
    """Specific class for Pressure/Tide/Wave Sensor 4117B"""
    
    def get_measurement(self) -> Dict[str, str]:
        """Get pressure measurement"""
        measurements = super().get_measurement()
        
        # Also try to get specific pressure parameters
        response = self.send_command('$GET Pressure')
        if response:
            measurements['Pressure'] = self.parse_response(response)
        
        response = self.send_command('$GET Temperature')
        if response:
            measurements['Temperature'] = self.parse_response(response)
        
        return measurements


class OxygenOptode(AanderaaSensor):
    """Specific class for Oxygen Optode 4330"""
    
    def get_measurement(self) -> Dict[str, str]:
        """Get oxygen measurement"""
        measurements = super().get_measurement()
        
        # Try to get specific oxygen parameters
        response = self.send_command('$GET O2Concentration')
        if response:
            measurements['O2Concentration'] = self.parse_response(response)
        
        response = self.send_command('$GET O2Saturation')
        if response:
            measurements['O2Saturation'] = self.parse_response(response)
        
        response = self.send_command('$GET Temperature')
        if response:
            measurements['Temperature'] = self.parse_response(response)
        
        return measurements


class ConductivitySensor(AanderaaSensor):
    """Specific class for Conductivity Sensor 5819"""
    
    def get_measurement(self) -> Dict[str, str]:
        """Get conductivity measurement"""
        measurements = super().get_measurement()
        
        # Try to get specific conductivity parameters
        response = self.send_command('$GET Conductivity')
        if response:
            measurements['Conductivity'] = self.parse_response(response)
        
        response = self.send_command('$GET Salinity')
        if response:
            measurements['Salinity'] = self.parse_response(response)
        
        response = self.send_command('$GET Temperature')
        if response:
            measurements['Temperature'] = self.parse_response(response)
        
        return measurements


def main():
    """Main function to read from all sensors"""
    
    # Configure your sensors here - UPDATE COM PORTS AS NEEDED
    sensor_configs = [
        SensorConfig(
            name="Pressure Sensor 4117B",
            com_port="COM5",  # UPDATE THIS
            baudrate=9600,
            sensor_type="pressure"
        ),
        SensorConfig(
            name="Oxygen Optode 4330",
            com_port="COM4",  # UPDATE THIS
            baudrate=9600,
            sensor_type="oxygen"
        ),
        SensorConfig(
            name="Conductivity Sensor 5819",
            com_port="COM6",  # UPDATE THIS
            baudrate=9600,
            sensor_type="conductivity"
        )
    ]
    
    # Create sensor objects
    sensors = []
    for config in sensor_configs:
        if config.sensor_type == "pressure":
            sensor = PressureSensor(config)
        elif config.sensor_type == "oxygen":
            sensor = OxygenOptode(config)
        elif config.sensor_type == "conductivity":
            sensor = ConductivitySensor(config)
        else:
            sensor = AanderaaSensor(config)
        sensors.append(sensor)
    
    # Connect to all sensors
    print("\n" + "="*60)
    print("Connecting to Aanderaa Sensors...")
    print("="*60 + "\n")
    
    connected_sensors = []
    for sensor in sensors:
        if sensor.connect():
            connected_sensors.append(sensor)
            time.sleep(0.5)
    
    if not connected_sensors:
        logger.error("No sensors connected. Exiting.")
        return
    
    # Get sensor information
    print("\n" + "="*60)
    print("Sensor Information")
    print("="*60 + "\n")
    
    for sensor in connected_sensors:
        print(f"\n{sensor.config.name}:")
        print("-" * 40)
        info = sensor.get_sensor_info()
        for key, value in info.items():
            print(f"  {key}: {value}")
    
    # Read measurements
    print("\n" + "="*60)
    print("Reading Measurements")
    print("="*60 + "\n")
    
    try:
        while True:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"\nTimestamp: {timestamp}")
            print("-" * 60)
            
            for sensor in connected_sensors:
                print(f"\n{sensor.config.name}:")
                measurements = sensor.get_measurement()
                
                if measurements:
                    for key, value in measurements.items():
                        print(f"  {key}: {value}")
                else:
                    print("  No data received")
            
            print("\n" + "-"*60)
            print("Waiting 10 seconds... (Press Ctrl+C to stop)")
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\nStopping measurement...")
    
    finally:
        # Disconnect all sensors
        print("\nDisconnecting sensors...")
        for sensor in connected_sensors:
            sensor.disconnect()
        
        print("Done!")


if __name__ == "__main__":
    main()
