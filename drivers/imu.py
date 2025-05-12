import struct
import threading

def parse_imu_packet(packet: bytes):
    """Parse an 11-byte WitMotion IMU packet."""
    data_bytes = packet[2:10]
    packet_id = packet[1]
    if packet_id == 0x53:
        roll_raw, pitch_raw, yaw_raw, _ = struct.unpack('<hhhH', data_bytes)
        roll = roll_raw / 32768.0 * 180.0
        pitch = pitch_raw / 32768.0 * 180.0
        yaw = yaw_raw / 32768.0 * 180.0
        return ("Angle", roll, pitch, yaw)
    elif packet_id == 0x56:
        p_raw, t_raw, _, _ = struct.unpack('<hhHH', data_bytes)
        return ("Pressure", p_raw / 100.0, t_raw / 100.0)
    elif packet_id == 0x57:
        try:
            lon_raw, lat_raw = struct.unpack('<ii', data_bytes)
            return ("GPS", lat_raw / 1e7, lon_raw / 1e7)
        except:
            return ("GPS", None, None)
    elif packet_id == 0x51:
        ax, ay, az, _ = struct.unpack('<hhhH', data_bytes)
        return ("Accel", ax / 32768.0 * 16.0, ay / 32768.0 * 16.0, az / 32768.0 * 16.0)
    elif packet_id == 0x52:
        gx, gy, gz, _ = struct.unpack('<hhhH', data_bytes)
        return ("Gyro", gx / 32768.0 * 2000.0, gy / 32768.0 * 2000.0, gz / 32768.0 * 2000.0)
    elif packet_id == 0x54:
        mx, my, mz, _ = struct.unpack('<hhhH', data_bytes)
        return ("Mag", mx / 32768.0 * 1000.0, my / 32768.0 * 1000.0, mz / 32768.0 * 1000.0)
    return ("Unknown", None)

def read_from_imu(serial_obj, data_dict: dict, stop_event: threading.Event):
    buffer = []
    while serial_obj.is_open and not stop_event.is_set():
        byte = serial_obj.read()
        if not byte:
            continue
        buffer.append(byte[0] if isinstance(byte, (bytes, bytearray)) else ord(byte))
        if len(buffer) >= 11:
            if buffer[0] == 0x55 and (sum(buffer[:10]) & 0xFF) == buffer[10]:
                packet = bytes(buffer[:11])
                buffer = buffer[11:]
                label, *vals = parse_imu_packet(packet)
                if label == "Angle":
                    data_dict["rpy"] = tuple(vals)
                elif label == "Pressure":
                    data_dict["pressure"], data_dict["temperature"] = vals
                elif label == "GPS" and vals[0] is not None:
                    data_dict["latitude"], data_dict["longitude"] = vals
                elif label == "Accel":
                    data_dict["accel"] = tuple(vals)
                elif label == "Gyro":
                    data_dict["gyro"] = tuple(vals)
                elif label == "Mag":
                    data_dict["mag"] = tuple(vals)
            else:
                buffer.pop(0)

def start_imu_read_thread(serial_obj, data_dict: dict):
    stop_event = threading.Event()
    thread = threading.Thread(target=read_from_imu, args=(serial_obj, data_dict, stop_event), daemon=True)
    thread.start()
    return stop_event