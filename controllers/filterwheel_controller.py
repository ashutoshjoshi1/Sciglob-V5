import serial
from serial.tools import list_ports
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton

from drivers.filterwheel import FilterWheelConnectThread, FilterWheelCommandThread

class FilterWheelController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groupbox = QGroupBox("Filter Wheel")
        self.groupbox.setObjectName("filterwheelGroup")
        layout = QHBoxLayout()

        layout.addWidget(QLabel("COM:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        ports = [p.device for p in list_ports.comports()]
        self.port_combo.addItems(ports or [f"COM{i}" for i in range(1, 10)])

        default_port = "COM17"
        if parent is not None and hasattr(parent, 'config'):
            default_port = parent.config.get("filterwheel", default_port)
        self.port_combo.setCurrentText(default_port)
        layout.addWidget(self.port_combo)

        layout.addWidget(QLabel("Cmd:"))
        self.cmd_input = QLineEdit()
        layout.addWidget(self.cmd_input)

        self.send_btn = QPushButton("Send")
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self.send)
        layout.addWidget(self.send_btn)

        layout.addWidget(QLabel("Pos:"))
        self.pos_label = QLabel("--")
        layout.addWidget(self.pos_label)

        self.groupbox.setLayout(layout)

        self._connected = False
        self.serial = None
        self.last = None

        # Auto-connect on startup
        th = FilterWheelConnectThread(self.port_combo.currentText(), parent=self)
        th.result_signal.connect(self._on_connect)
        th.start()

    def _on_connect(self, ser, msg):
        self.status_signal.emit(msg)
        if ser:
            self.serial = ser
            self._connected = True
            self.send_btn.setEnabled(True)
            self._send("F1r")  # Reset to position 1
        else:
            self._connected = False
            self.send_btn.setEnabled(False)

    def send(self):
        cmd = self.cmd_input.text().strip()
        self._send(cmd)

    def _send(self, cmd):
        if not self._connected:
            return self.status_signal.emit("Not connected")
        self.send_btn.setEnabled(False)
        self.last = cmd
        th = FilterWheelCommandThread(self.serial, cmd, parent=self)
        th.result_signal.connect(self._on_result)
        th.start()

    def _on_result(self, pos, msg):
        self.send_btn.setEnabled(True)
        self.status_signal.emit(msg)

        if self.last:
            if self.last == "F1r":
                self.pos_label.setText("1")
            elif self.last.startswith("F1") and len(self.last) == 3 and self.last[2].isdigit():
                self.pos_label.setText(self.last[2])
            else:
                if pos is not None:
                    self.pos_label.setText(str(pos))
        self.last = None

    def get_position(self):
        try:
            return int(self.pos_label.text())
        except:
            return 0

    def is_connected(self):
        return self._connected