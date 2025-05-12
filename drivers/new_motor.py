# motor.py
import serial
from PyQt5.QtCore import QThread, pyqtSignal
import utils

# Motor control constants for Oriental Motor AZ series (Modbus)
TrackerSpeed   = 10000        # Motor rotation speed (steps/s)
TrackerCurrent = 1000         # Motor current limit (in 0.1% units, 1000 = 100.0%)
SlaveID        = 2            # Modbus slave address of the motor controller
BaudRateList   = [9600, 19200, 38400, 57600, 115200, 230400]

class MotorConnectThread(QThread):
    """Thread to attempt motor serial connection with baud auto-detection."""
    result_signal = pyqtSignal(object, int, str)  # will emit (serial_obj or None, baud_rate, message)

    def __init__(self, port_name, parent=None):
        super().__init__(parent)
        self.port_name = port_name

    def run(self):
        found_serial = None
        found_baud   = 0
        message      = ""

        # Try each baud rate with 8E1 (even parity, 1 stop bit)
        for baud in BaudRateList:
            try:
                ser = serial.Serial(
                    self.port_name,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_EVEN,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.5
                )
                # Read 2 registers at 0x0058 (original working test)
                base_cmd = bytes([SlaveID, 0x03, 0x00, 0x58, 0x00, 0x02])
                crc_val  = utils.modbus_crc16(base_cmd)
                ser.reset_input_buffer()
                ser.write(base_cmd + crc_val.to_bytes(2, 'little'))

                # Just look for *any* response bytes
                response = ser.read(5)
                if response:
                    found_serial = ser
                    found_baud   = baud
                    message = f"Motor connected on {self.port_name} at {baud} baud."
                    break
                ser.close()
            except Exception:
                continue

        if not found_serial:
            message = f"No response from motor on {self.port_name}."

        # Emit (Serial object or None, baud, status message)
        self.result_signal.emit(found_serial, found_baud, message)


def send_move_command(serial_obj, angle: int) -> bool:
    """Send a move command to the motor to go to the specified angle (degrees)."""
    # Build Modbus Write Multiple Registers at 0x0058
    base_cmd = bytes([SlaveID, 0x10, 0x00, 0x58, 0x00, 0x12, 0x24] + [0x00]*12)
    # Insert angle, speed, mid‐params, current, end‐params
    angle_bytes   = angle.to_bytes(4, 'big', signed=True)
    speed_bytes   = TrackerSpeed.to_bytes(4, 'big', signed=True)
    mid_bytes     = bytes([0x00,0x00,0x1F,0x40, 0x00,0x00,0x1F,0x40])
    current_bytes = TrackerCurrent.to_bytes(4, 'big', signed=True)
    end_bytes     = bytes([0x00,0x00,0x00,0x01, 0x00,0x00,0x00,0x01])

    full_cmd = base_cmd + angle_bytes + speed_bytes + mid_bytes + current_bytes + end_bytes
    crc_val  = utils.modbus_crc16(full_cmd).to_bytes(2, 'little')

    try:
        serial_obj.reset_input_buffer()
        serial_obj.write(full_cmd + crc_val)
        resp = serial_obj.read(8)
        return bool(resp and len(resp) >= 6 and resp[1] == 0x10)
    except Exception:
        return False
