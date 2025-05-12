import os
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, 
    QWidget, QVBoxLayout as QVBoxLayout2, QLabel, QSpinBox, QCheckBox
)
import pyqtgraph as pg
from pyqtgraph import ViewBox

from drivers.spectrometer import connect_spectrometer, AVS_MeasureCallback, AVS_MeasureCallbackFunc, AVS_GetScopeData, StopMeasureThread, prepare_measurement

class SpectrometerController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Group box UI
        self.groupbox = QGroupBox("Spectrometer")
        self.groupbox.setObjectName("specGroup")
        main_layout = QVBoxLayout()

        # Control buttons layout
        ctrl_layout = QHBoxLayout()
        # Continuous-save toggle
        self.toggle_btn = QPushButton("Start Saving")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self.toggle)
        ctrl_layout.addWidget(self.toggle_btn)
        # Connect button
        self.conn_btn = QPushButton("Connect")
        self.conn_btn.clicked.connect(self.connect)
        ctrl_layout.addWidget(self.conn_btn)
        # Start measurement button
        self.start_btn = QPushButton("Start")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        ctrl_layout.addWidget(self.start_btn)
        # Stop measurement button
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        ctrl_layout.addWidget(self.stop_btn)
        # Save snapshot button
        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save)
        ctrl_layout.addWidget(self.save_btn)
        main_layout.addLayout(ctrl_layout)
        
        # Integration time controls
        integ_layout = QHBoxLayout()
        integ_layout.addWidget(QLabel("Integration Time (ms):"))
        self.integ_spinbox = QSpinBox()
        self.integ_spinbox.setRange(1, 10000)  # 1ms to 10s
        self.integ_spinbox.setValue(50)  # Default 50ms
        self.integ_spinbox.setSingleStep(10)
        integ_layout.addWidget(self.integ_spinbox)
        # Averaging controls
        integ_layout.addWidget(QLabel("Averages:"))
        self.avg_spinbox = QSpinBox()
        self.avg_spinbox.setRange(1, 100)
        self.avg_spinbox.setValue(1)
        integ_layout.addWidget(self.avg_spinbox)
        # Add the Apply Settings button
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.update_measurement_settings)
        integ_layout.addWidget(self.apply_btn)
        # Auto-adjust checkbox
        self.auto_adjust_cb = QCheckBox("Auto-adjust Integration Time")
        self.auto_adjust_cb.setChecked(True)  # Enable by default
        integ_layout.addWidget(self.auto_adjust_cb)
        main_layout.addLayout(integ_layout)

        # Spectral plots in tabs
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.tab_widget = QTabWidget()

        # Tab 1: Wavelength vs Intensity
        tab1 = QWidget()
        layout1 = QVBoxLayout2(tab1)
        self.plot_wl = pg.PlotWidget()
        self.plot_wl.setLabel('bottom', 'Wavelength', 'nm')
        self.plot_wl.setLabel('left', 'Intensity', 'counts')
        self.plot_wl.showGrid(x=True, y=True, alpha=0.3)
        self.plot_wl.getViewBox().enableAutoRange(ViewBox.XYAxes, True)
        # Add a more attractive style
        self.curve_wl = self.plot_wl.plot([], [], pen=pg.mkPen('#2986cc', width=2), 
                                         symbolBrush=(41, 134, 204), symbolPen='w', symbol='o', 
                                         symbolSize=5, name="Wavelength Spectrum")
        layout1.addWidget(self.plot_wl)
        self.tab_widget.addTab(tab1, "Wavelength vs Intensity")

        # Tab 2: Pixel vs Count
        tab2 = QWidget()
        layout2 = QVBoxLayout2(tab2)
        self.plot_px = pg.PlotWidget()
        # Set fixed range for x-axis (0-2048 pixels)
        self.plot_px.setXRange(0, 2048)
        self.plot_px.setLabel('bottom', 'Pixel', '')  # Remove 'Index' from label
        self.plot_px.setLabel('left', 'Count', '')
        # Enable auto-range only for y-axis
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.getViewBox().setAutoVisible(y=True)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)

        # Configure x-axis ticks to show 0, 100, 200, etc.
        x_axis = self.plot_px.getAxis('bottom')
        x_ticks = [(i, str(i)) for i in range(0, 2049, 100)]  # Create ticks at 0, 100, 200, etc.
        x_axis.setTicks([x_ticks])

        # Add a more attractive style
        self.curve_px = self.plot_px.plot([], [], pen=pg.mkPen('#d22c2c', width=2),
                                         fillLevel=0, fillBrush=pg.mkBrush(210, 44, 44, 50),
                                         name="Pixel Counts")
        layout2.addWidget(self.plot_px)
        self.tab_widget.addTab(tab2, "Pixel vs Count")
        # Add the tab widget to the groupbox layout
        main_layout.addWidget(self.tab_widget)
        self.groupbox.setLayout(main_layout)

        # Internal state
        self._ready = False
        self.handle = None
        self.wls = []
        self.intens = []
        self.npix = 0

        # Ensure parent MainWindow's toggle_data_saving is used if parent exists
        if parent is not None:
            try:
                self.toggle_btn.clicked.disconnect(self.toggle)
            except Exception:
                pass
            self.toggle_btn.clicked.connect(parent.toggle_data_saving)

        # Data directory for snapshots
        self.csv_dir = "data"
        os.makedirs(self.csv_dir, exist_ok=True)

        # Timer for updating plot
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self._update_plot)
        self.plot_timer.start(200)  # update plot at 5 Hz

    def connect(self):
        # Emit status for feedback
        self.status_signal.emit("Connecting to spectrometer...")
        try:
            handle, wavelengths, num_pixels, serial_str = connect_spectrometer()
        except Exception as e:
            self.status_signal.emit(f"Connection failed: {e}")
            return
        self.handle = handle
        # Store wavelength calibration and number of pixels
        self.wls = wavelengths.tolist() if isinstance(wavelengths, np.ndarray) else wavelengths
        self.npix = num_pixels
        self._ready = True
        # Enable measurement start once connected
        self.start_btn.setEnabled(True)
        self.status_signal.emit(f"Spectrometer ready (SN={serial_str})")

    def start(self):
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready.")
            return
        
        # Get integration time and averages from UI
        integration_time = float(self.integ_spinbox.value())
        averages = self.avg_spinbox.value()
        
        # Store current integration time for data saving
        self.current_integration_time_us = integration_time * 1000  # Convert ms to μs
        
        # Update status with current settings
        self.status_signal.emit(f"Starting measurement (Int: {integration_time}ms, Avg: {averages})")
        
        code = prepare_measurement(self.handle, self.npix, 
                                  integration_time_ms=integration_time, 
                                  averages=averages)
        if code != 0:
            self.status_signal.emit(f"Prepare error: {code}")
            return
        self.measure_active = True
        self.cb = AVS_MeasureCallbackFunc(self._cb)
        err = AVS_MeasureCallback(self.handle, self.cb, -1)
        if err != 0:
            self.status_signal.emit(f"Callback error: {err}")
            self.measure_active = False
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)  # Enable the apply button when measurement starts
        self.status_signal.emit("Measurement started")

    def _cb(self, p_data, p_user):
        # Spectrometer driver callback (on new scan)
        status_code = p_user[0]
        if status_code == 0:
            _, data = AVS_GetScopeData(self.handle)
            # Ensure intensities list has correct length (up to 2048)
            max_pixels = min(2048, self.npix)
            full = [0.0] * max_pixels
            # Copy only the data we need (up to 2048 pixels)
            data_to_use = data[:max_pixels] if len(data) > max_pixels else data
            full[:len(data_to_use)] = data_to_use
            self.intens = full
            # Enable snapshot save and continuous save after first data received
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)
        else:
            self.status_signal.emit(f"Spectrometer error code {status_code}")

    def _update_plot(self):
        if not self.intens:
            return
        
        # Ensure we only use the first 2048 pixels (or less if that's all we have)
        max_pixels = min(2048, len(self.intens))
        pixel_indices = list(range(max_pixels))
        pixel_values = self.intens[:max_pixels]
        
        # For wavelength plot, ensure we have matching wavelength values
        wavelengths = self.wls[:max_pixels] if len(self.wls) >= max_pixels else self.wls
        
        # Update wavelength plot with limited data
        self.curve_wl.setData(wavelengths, pixel_values)
        
        # Update pixel plot with limited data and ensure it's properly scaled
        self.curve_px.setData(pixel_indices, pixel_values)
        
        # Auto-adjust y-axis range based on current data
        if max(pixel_values, default=0) > 0:
            # Add 10% padding to the top of the y-range
            max_y = max(pixel_values) * 1.1
            self.plot_px.setYRange(0, max_y)
        
        # Auto-adjust integration time based on peak value if enabled
        if hasattr(self, 'auto_adjust_cb') and self.auto_adjust_cb.isChecked():
            if not hasattr(self, '_auto_adjust_counter'):
                self._auto_adjust_counter = 0
            
            self._auto_adjust_counter += 1
            if self._auto_adjust_counter >= 10:  # Check every ~2 seconds
                self._auto_adjust_counter = 0
                self.auto_adjust_integration_time()

    def stop(self):
        if not hasattr(self, 'measure_active') or not self.measure_active:
            return
        self.measure_active = False
        th = StopMeasureThread(self.handle, parent=self)
        th.finished_signal.connect(self._on_stop)
        th.start()

    def _on_stop(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)  # Disable the apply button when measurement stops
        self.status_signal.emit("Measurement stopped")

    def save(self):
        ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        path = os.path.join(self.csv_dir, f"snapshot_{ts}.csv")
        try:
            with open(path, 'w') as f:
                f.write("Wavelength (nm),Intensity\n")
                for wl, inten in zip(self.wls, self.intens):
                    if inten != 0:
                        f.write(f"{wl:.4f},{inten:.4f}\n")
            self.status_signal.emit(f"Saved snapshot to {path}")
        except Exception as e:
            self.status_signal.emit(f"Save error: {e}")

    def toggle(self):
        # This method is overridden by MainWindow if parent is provided.
        self.status_signal.emit("Continuous-save not yet implemented")

    def is_ready(self):
        return self._ready

    def update_measurement_settings(self):
        """Update measurement settings without stopping the current measurement"""
        if not self._ready:
            self.status_signal.emit("Spectrometer not ready")
            return
        
        integration_time = float(self.integ_spinbox.value())
        averages = self.avg_spinbox.value()
        
        # Store current integration time for data saving
        self.current_integration_time_us = integration_time * 1000  # Convert ms to μs
        
        if hasattr(self, 'measure_active') and self.measure_active:
            # First stop the current measurement
            self.status_signal.emit(f"Stopping measurement to update settings...")
            self.measure_active = False
            
            # Use StopMeasureThread to properly stop the measurement
            th = StopMeasureThread(self.handle, parent=self)
            th.finished_signal.connect(lambda: self._apply_new_settings(integration_time, averages))
            th.start()
        else:
            # Just prepare the measurement with new settings
            code = prepare_measurement(self.handle, self.npix, 
                                      integration_time_ms=integration_time, 
                                      averages=averages)
            if code != 0:
                self.status_signal.emit(f"Settings update error: {code}")
                return
            self.status_signal.emit(f"Settings updated (Int: {integration_time}ms, Avg: {averages})")

    def _apply_new_settings(self, integration_time, averages):
        """Helper to apply new settings after measurement has stopped"""
        code = prepare_measurement(self.handle, self.npix, 
                                  integration_time_ms=integration_time, 
                                  averages=averages)
        if code != 0:
            self.status_signal.emit(f"Settings update error: {code}")
            return
        
        self.cb = AVS_MeasureCallbackFunc(self._cb)
        err = AVS_MeasureCallback(self.handle, self.cb, -1)
        if err != 0:
            self.status_signal.emit(f"Callback error on restart: {err}")
            self.measure_active = False
            return
        
        self.measure_active = True
        self.stop_btn.setEnabled(True)
        self.status_signal.emit(f"Settings updated (Int: {integration_time}ms, Avg: {averages})")

    def auto_adjust_integration_time(self):
        """Automatically adjust integration time based on peak value and filter wheel position"""
        if not self.intens:
            return
        
        # Get the peak value from the intensity data
        peak_value = max(self.intens)
        
        # Get the current filter wheel position
        filter_pos = 1  # Default position
        if hasattr(self, 'parent') and self.parent() is not None:
            # Try to get filter wheel position from parent (MainWindow)
            if hasattr(self.parent(), 'filter_ctrl'):
                filter_pos = self.parent().filter_ctrl.get_position() or 1
        
        # Determine the appropriate integration time
        current_integ_time = self.integ_spinbox.value()
        new_integ_time = current_integ_time
        
        if peak_value < 500 and filter_pos == 1:
            new_integ_time = 4000  # 4000ms (4s) for low signal with filter 1
        else:
            new_integ_time = 1000  # 1000ms (1s) for other cases
        
        # Only update if the integration time has changed
        if new_integ_time != current_integ_time:
            self.status_signal.emit(f"Auto-adjusting integration time to {new_integ_time}ms (Peak: {peak_value:.1f}, Filter: {filter_pos})")
            self.integ_spinbox.setValue(new_integ_time)
            
            # If measurement is active, apply the new settings
            if hasattr(self, 'measure_active') and self.measure_active:
                self.update_measurement_settings()






















