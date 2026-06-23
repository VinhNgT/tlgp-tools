import json
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class BackendDebugWindow(QDialog):
    """Developer window that logs outgoing and incoming messages from the backend."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Backend Logs")
        self.resize(600, 400)
        self.setWindowFlag(Qt.WindowType.Tool)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        header = QHBoxLayout()
        lbl = QLabel("Backend Logs")
        lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        header.addWidget(lbl)
        header.addStretch()

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedWidth(60)
        btn_clear.clicked.connect(self.clear_logs)
        header.addWidget(btn_clear)
        layout.addLayout(header)

        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet(
            "font-family: 'Menlo', 'Consolas', monospace; font-size: 9pt;"
        )
        layout.addWidget(self.text_area)

    def log_message(self, direction: str, message: dict | str):
        if isinstance(message, dict):
            try:
                msg_str = json.dumps(message, indent=2)
            except Exception:
                msg_str = str(message)
        else:
            try:
                parsed = json.loads(message)
                msg_str = json.dumps(parsed, indent=2)
            except Exception:
                msg_str = str(message)

        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.text_area.appendPlainText(
            f"[{now_str}] [{direction}]\n{msg_str}\n{'-' * 40}"
        )

    def clear_logs(self):
        self.text_area.clear()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_window(self):
        self.hide()
