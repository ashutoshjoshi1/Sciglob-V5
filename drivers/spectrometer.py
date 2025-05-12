import os
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
import ctypes
import sys

# Force DLL loading from same directory as main.py
try:
    dll_dir = os.path.dirname(os.path.abspath(__file__))
    if dll_dir not in sys.path:
        sys.path.append(dll_dir)
    os.environ['PATH'] = dll_dir + os.pathsep + os.environ['PATH']
    from avaspec import *
except ImportError as e:
    raise ImportError("AvaSpec SDK import failed. Make sure avaspec.pyd and avaspec DLL are in the same directory as main.py.") from e

class StopMeasureThread(QThread):
    finished_signal = pyqtSignal()
    def __init__(self, spec_handle, parent=None):
        super().__init__(parent)
        self.spec_handle = spec_handle
    def run(self):
        AVS_StopMeasure(self.spec_handle)
        self.finished_signal.emit()

def connect_spectrometer():
    try:
        print("[DEBUG] Calling AVS_Init(0)...")
        ret = AVS_Init(0)
    except Exception as e:
        raise Exception(f"Spectrometer initialization failed: {e}")
    if ret <= 0:
        AVS_Done()
        if ret == 0:
            raise Exception("No spectrometer found.")
        elif 'ERR_ETHCONN_REUSE' in globals() and ret == ERR_ETHCONN_REUSE:
            raise Exception("Spectrometer already in use by another program.")
        else:
            raise Exception(f"AVS_Init error (code {ret}).")

    dev_count = AVS_UpdateUSBDevices()
    if dev_count < 1:
        AVS_Done()
        raise Exception("No spectrometer found after update.")

    id_list = AVS_GetList(dev_count)
    if not id_list:
        AVS_Done()
        raise Exception("Failed to retrieve spectrometer list.")

    dev_id = id_list[0]
    serial_str = dev_id.SerialNumber.decode().strip() if hasattr(dev_id.SerialNumber, 'decode') else str(dev_id.SerialNumber)

    avs_id = AvsIdentityType()
    avs_id.SerialNumber = dev_id.SerialNumber
    avs_id.UserFriendlyName = b"\x00"
    avs_id.Status = b'\x01'
    spec_handle = AVS_Activate(avs_id)
    if spec_handle == INVALID_AVS_HANDLE_VALUE:
        AVS_Done()
        raise Exception(f"Error opening spectrometer (Serial: {serial_str})")

    device_data = AVS_GetParameter(spec_handle, 63484)
    if device_data is None:
        AVS_Done()
        raise Exception("Failed to get spectrometer parameters.")

    num_pixels = device_data.m_Detector_m_NrPixels
    start_pixel = getattr(device_data, 'm_StandAlone_m_Meas_m_StartPixel', 0)
    stop_pixel = getattr(device_data, 'm_StandAlone_m_Meas_m_StopPixel', num_pixels - 1)
    if start_pixel < 0:
        start_pixel = 0
    if stop_pixel <= start_pixel or stop_pixel > num_pixels - 1:
        stop_pixel = num_pixels - 1

    wavelengths = AVS_GetLambda(spec_handle)
    if wavelengths:
        wavelengths = np.ctypeslib.as_array(wavelengths)
    else:
        wavelengths = list(range(num_pixels))

    return spec_handle, wavelengths, num_pixels, serial_str

def prepare_measurement(spec_handle, num_pixels, integration_time_ms=50.0, averages=1):
    meas_cfg = MeasConfigType()
    meas_cfg.m_StartPixel = 0
    meas_cfg.m_StopPixel = num_pixels - 1
    meas_cfg.m_IntegrationTime = float(integration_time_ms)
    meas_cfg.m_IntegrationDelay = 0
    meas_cfg.m_NrAverages = averages
    meas_cfg.m_CorDynDark_m_Enable = 0
    meas_cfg.m_CorDynDark_m_ForgetPercentage = 0
    meas_cfg.m_Smoothing_m_SmoothPix = 0
    meas_cfg.m_Smoothing_m_SmoothModel = 0
    meas_cfg.m_SaturationDetection = 0
    meas_cfg.m_Trigger_m_Mode = 0
    meas_cfg.m_Trigger_m_Source = 0
    meas_cfg.m_Trigger_m_SourceType = 0
    meas_cfg.m_Control_m_StrobeControl = 0
    meas_cfg.m_Control_m_LaserDelay = 0
    meas_cfg.m_Control_m_LaserWidth = 0
    meas_cfg.m_Control_m_LaserWaveLength = 0.0
    meas_cfg.m_Control_m_StoreToRam = 0
    return AVS_PrepareMeasure(spec_handle, meas_cfg)

def start_measurement(spec_handle, callback_func, num_scans=-1):
    cb_ptr = AVS_MeasureCallbackFunc(callback_func)
    return AVS_MeasureCallback(spec_handle, cb_ptr, num_scans)

def stop_measurement(spec_handle):
    AVS_StopMeasure(spec_handle)

def close_spectrometer():
    AVS_Done()