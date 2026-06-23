"""Qt-based dialog service — production implementation of DialogService.

Provides PySide6 implementations for file dialogs,
message boxes, and custom modal dialogs.
"""

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from annotator.models import Component

from .cut_editor import CutEditorDialog
from .dialog_service import DialogService, ProgressIndicator


class _QtProgressIndicator:
    """Wraps a QDialog that acts as a progress indicator."""

    def __init__(self, dialog: QDialog):
        self._dialog = dialog

    def dismiss(self) -> None:
        self._dialog.close()
        self._dialog.deleteLater()


class _ImportingDialog(QDialog):
    """Non-interactive progress dialog shown during background import operations."""

    def __init__(self, parent, message="Importing..."):
        super().__init__(parent)
        self.setWindowTitle("Please Wait")
        self.setFixedSize(280, 80)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)

        layout = QVBoxLayout(self)
        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 10pt;")
        layout.addWidget(lbl)

        self.show()


class _ScreenInfoDialog(QDialog):
    """Modal form dialog for editing screen name and functional description."""

    def __init__(self, parent, screen_name="", description=""):
        super().__init__(parent)
        self.setWindowTitle("Screen Information")
        self.resize(450, 240)
        self.setModal(True)

        self.result = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        lbl_name = QLabel("Screen Name (e.g. Product Details Screen):")
        layout.addWidget(lbl_name)

        self.entry_name = QLineEdit()
        self.entry_name.setText(screen_name)
        layout.addWidget(self.entry_name)

        lbl_desc = QLabel("Functional Description:")
        layout.addWidget(lbl_desc)

        self.text_desc = QTextEdit()
        self.text_desc.setPlainText(description)
        layout.addWidget(self.text_desc, stretch=1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.entry_name.setFocus()

    def _on_save(self):
        name = self.entry_name.text().strip()
        desc = self.text_desc.toPlainText().strip()

        if not name:
            QMessageBox.warning(self, "Warning", "Please enter a screen name!")
            return

        self.result = {"screen_name": name, "description": desc}
        self.accept()


class QtDialogService(DialogService):
    """Production implementation of DialogService using PySide6 dialogs."""

    def ask_open_filename(
        self,
        parent: QWidget,
        title: str,
        filetypes: list[tuple[str, str]],
    ) -> str | None:
        filter_str = self._filetypes_to_filter(filetypes)
        path, _ = QFileDialog.getOpenFileName(parent, title, "", filter_str)
        return path if path else None

    def ask_save_as_filename(
        self,
        parent: QWidget,
        title: str,
        filetypes: list[tuple[str, str]],
        defaultextension: str,
    ) -> str | None:
        filter_str = self._filetypes_to_filter(filetypes)
        path, _ = QFileDialog.getSaveFileName(parent, title, "", filter_str)
        return path if path else None

    def show_error(self, parent: QWidget, title: str, message: str) -> None:
        QMessageBox.critical(parent, title, message)

    def show_warning(self, parent: QWidget, title: str, message: str) -> None:
        QMessageBox.warning(parent, title, message)

    def show_info(self, parent: QWidget, title: str, message: str) -> None:
        QMessageBox.information(parent, title, message)

    def show_importing_dialog(
        self, parent: QWidget, message: str
    ) -> ProgressIndicator:
        dialog = _ImportingDialog(parent, message=message)
        return _QtProgressIndicator(dialog)

    def show_cut_editor(
        self,
        parent: QWidget,
        image: Image.Image,
        initial_cuts: list[int],
        components: list[Component],
    ) -> list[int] | None:
        dialog = CutEditorDialog(
            parent, image=image, initial_cuts=initial_cuts, components=components
        )
        dialog.exec()
        return dialog.result

    def show_screen_info(
        self, parent: QWidget, screen_name: str, description: str
    ) -> dict[str, str] | None:
        dialog = _ScreenInfoDialog(parent, screen_name=screen_name, description=description)
        dialog.exec()
        return dialog.result

    @staticmethod
    def _filetypes_to_filter(filetypes: list[tuple[str, str]]) -> str:
        """Convert generic legacy filetypes list to Qt filter string."""
        parts = []
        for label, pattern in filetypes:
            parts.append(f"{label} ({pattern})")
        return ";;".join(parts)
