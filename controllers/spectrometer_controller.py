import os
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QWidget, QVBoxLayout as QVBoxLayout2
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

        # Spectral plots in tabs
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.tab_widget = QTabWidget()
        # Tab 1: Wavelength vs Intensity
        tab1 = QWidget()
        layout1 = QVBoxLayout2(tab1)
        self.plot_wl = pg.PlotWidget()
        # self.plot_wl.getViewBox().enableAutoRange(axis='both',enable = True)
        self.plot_wl.setLabel('bottom', 'Wavelength', 'nm')
        self.plot_wl.setLabel('left', 'Intensity', 'counts')
        self.plot_wl.showGrid(x=True, y=True, alpha=0.3)
        self.plot_wl.getViewBox().enableAutoRange(ViewBox.XYAxes,True)
        self.curve_wl = self.plot_wl.plot([], [], pen=pg.mkPen('#2986cc', width=1))
        layout1.addWidget(self.plot_wl)
        self.tab_widget.addTab(tab1, "Wavelength vs Intensity")
        # Tab 2: Pixel vs Count
        tab2 = QWidget()
        layout2 = QVBoxLayout2(tab2)
        self.plot_px = pg.PlotWidget()
        self.plot_px.setXRange(0,2048)
        # self.plot_px.enableAutoRange(axis='y',enable=True)
        self.plot_px.setLabel('bottom', 'Pixel', 'Index')
        self.plot_px.setLabel('left', 'Count', '')
        self.plot_px.getViewBox().enableAutoRange(ViewBox.YAxis, True)
        self.plot_px.showGrid(x=True, y=True, alpha=0.3)
        self.curve_px = self.plot_px.plot([], [], pen=pg.mkPen('#d22c2c', width=1))
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
        code = prepare_measurement(self.handle, self.npix, integration_time_ms=50.0, averages=1)
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
        self.status_signal.emit("Measurement started")

    def _cb(self, p_data, p_user):
        # Spectrometer driver callback (on new scan)
        status_code = p_user[0]
        if status_code == 0:
            _, data = AVS_GetScopeData(self.handle)
            # Ensure intensities list has correct length
            full = [0.0] * self.npix
            full[:len(data)] = data
            self.intens = full
            # Enable snapshot save and continuous save after first data received
            self.save_btn.setEnabled(True)
            self.toggle_btn.setEnabled(True)
        else:
            self.status_signal.emit(f"Spectrometer error code {status_code}")

    def _update_plot(self):
        if not self.intens:
            return
        # Update both plots
        self.curve_wl.setData(self.wls, self.intens)
        self.curve_px.setData(list(range(len(self.intens))), self.intens)

    def stop(self):
        if not getattr(self, 'measure_active', False):
            return
        self.stop_btn.setEnabled(False)
        stopper = StopMeasureThread(self.handle, parent=self)
        stopper.finished_signal.connect(self._on_stopped)
        stopper.start()

    def _on_stopped(self):
        self.measure_active = False
        self.start_btn.setEnabled(True)
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
