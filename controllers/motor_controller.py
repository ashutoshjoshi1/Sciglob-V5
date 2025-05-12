from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QLabel, QComboBox, QPushButton, QLineEdit, QGridLayout
from serial.tools import list_ports

from drivers.motor import MotorConnectThread, send_move_command

class MotorController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groupbox = QGroupBox("Motor")
        self.groupbox.setObjectName("motorGroup")
        layout = QGridLayout()

        layout.addWidget(QLabel("COM:"), 0, 0)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports or [f"COM{i}" for i in range(1, 10)])
        layout.addWidget(self.port_combo, 0, 1)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect)
        layout.addWidget(self.connect_btn, 0, 2)

        layout.addWidget(QLabel("Angle (°):"), 1, 0)
        self.angle_input = QLineEdit()
        self.angle_input.setFixedWidth(60)
        layout.addWidget(self.angle_input, 1, 1)
        self.move_btn = QPushButton("Move")
        self.move_btn.setEnabled(False)
        self.move_btn.clicked.connect(self.move)
        layout.addWidget(self.move_btn, 1, 2)

        self.groupbox.setLayout(layout)
        self._connected = False
        self.serial = None

        # If configured port is provided, select and auto-connect
        if parent is not None and hasattr(parent, 'config'):
            cfg_port = parent.config.get("motor")
            if cfg_port:
                self.port_combo.setCurrentText(cfg_port)
                self.connect()

    def connect(self):
        port = self.port_combo.currentText().strip()
        self.connect_btn.setEnabled(False)
        thread = MotorConnectThread(port, parent=self)
        thread.result_signal.connect(self._on_connect)
        thread.start()

    def _on_connect(self, ser, baud, msg):
        self.connect_btn.setEnabled(True)
        self.status_signal.emit(msg)
        if ser:
            self.serial = ser
            self._connected = True
            self.move_btn.setEnabled(True)
        else:
            self._connected = False
            self.move_btn.setEnabled(False)

    def move(self):
        try:
            angle = int(self.angle_input.text().strip())
        except ValueError:
            self.status_signal.emit("Invalid angle")
            return
        ok = False
        if self.serial:
            ok = send_move_command(self.serial, angle)
        self.status_signal.emit("Moved" if ok else "No ACK")

    def is_connected(self):
        return self._connected
