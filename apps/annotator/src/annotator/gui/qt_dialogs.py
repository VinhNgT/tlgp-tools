"""Qt-based dialog service — production implementation of DialogService.

Provides PySide6 implementations for file dialogs,
message boxes, and custom modal dialogs.
"""

from collections.abc import Callable

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
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
        font = lbl.font()
        font.setPointSize(10)
        lbl.setFont(font)
        layout.addWidget(lbl)

        self.show()


class _ScreenInfoDialog(QDialog):
    """Form dialog for editing screen name and functional description."""

    def __init__(self, parent, screen_name="", description=""):
        # Use Qt.WindowType.Tool to keep the modeless dialog on top of the parent
        # window within the application on macOS. Because the parent is passed
        # during constructor initialization, macOS automatically hides the
        # dialog when the application loses focus, preventing it from floating
        # on top of other applications.
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Screen Information")
        self.resize(450, 240)

        self.info_result = None

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
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
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

        self.info_result = {"screen_name": name, "description": desc}
        self.accept()


class _ExportImagesDialog(QDialog):
    """Dialog to choose the export mode and format for component images."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Export Images")
        self.resize(380, 220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 1. Mode selection
        lbl_mode = QLabel("Select Export Mode:")
        layout.addWidget(lbl_mode)

        self.rad_annotated = QRadioButton(
            "Annotated (skips leaves, paints child annotations)"
        )
        self.rad_annotated.setChecked(True)
        layout.addWidget(self.rad_annotated)

        self.rad_raw = QRadioButton("Raw (includes leaves, no annotations)")
        layout.addWidget(self.rad_raw)

        self.rad_both = QRadioButton("Both (exports both annotated and raw modes)")
        layout.addWidget(self.rad_both)

        # Divider line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # 2. Format selection
        lbl_format = QLabel("Select Export Format:")
        layout.addWidget(lbl_format)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rad_annotated)
        self.mode_group.addButton(self.rad_raw)
        self.mode_group.addButton(self.rad_both)

        self.format_group = QButtonGroup(self)

        self.rad_folder = QRadioButton("Folder Directory")
        self.rad_folder.setChecked(True)
        self.format_group.addButton(self.rad_folder)
        layout.addWidget(self.rad_folder)

        self.rad_zip = QRadioButton("ZIP Archive (.zip)")
        self.format_group.addButton(self.rad_zip)
        layout.addWidget(self.rad_zip)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_options(self) -> tuple[str, str]:
        # Mode
        if self.rad_annotated.isChecked():
            mode = "annotated"
        elif self.rad_raw.isChecked():
            mode = "raw"
        else:
            mode = "both"

        # Format
        format_val = "zip" if self.rad_zip.isChecked() else "folder"
        return mode, format_val


class QtDialogService(DialogService):
    """Production implementation of DialogService using PySide6 dialogs."""

    def ask_open_filename(
        self,
        parent: QWidget | None,
        title: str,
        filetypes: list[tuple[str, str]],
    ) -> str | None:
        filter_str = self._filetypes_to_filter(filetypes)
        path, _ = QFileDialog.getOpenFileName(parent, title, "", filter_str)
        return path if path else None

    def ask_save_as_filename(
        self,
        parent: QWidget | None,
        title: str,
        filetypes: list[tuple[str, str]],
        defaultextension: str,
        initial_filename: str = "",
    ) -> str | None:
        filter_str = self._filetypes_to_filter(filetypes)
        path, _ = QFileDialog.getSaveFileName(
            parent, title, initial_filename, filter_str
        )
        return path if path else None

    def show_error(self, parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.critical(parent, title, message)

    def show_warning(self, parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.warning(parent, title, message)

    def show_info(self, parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.information(parent, title, message)

    def show_importing_dialog(
        self, parent: QWidget | None, message: str
    ) -> ProgressIndicator:
        dialog = _ImportingDialog(parent, message=message)
        return _QtProgressIndicator(dialog)

    def show_cut_editor(
        self,
        parent: QWidget | None,
        image: Image.Image,
        initial_cuts: list[int],
        components: list[Component],
        on_save: Callable[[list[int]], None],
    ) -> None:
        dialog = CutEditorDialog(
            parent, image=image, initial_cuts=initial_cuts, components=components
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.accepted.connect(lambda: on_save(dialog.cut_lines_result))
        dialog.show()

    def show_screen_info(
        self,
        parent: QWidget | None,
        screen_name: str,
        description: str,
        on_save: Callable[[dict[str, str]], None],
    ) -> None:
        dialog = _ScreenInfoDialog(
            parent, screen_name=screen_name, description=description
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.accepted.connect(lambda: on_save(dialog.info_result))
        dialog.show()

    def ask_export_images_options(
        self,
        parent: QWidget | None,
        on_selected: Callable[[str | None, str | None], None],
    ) -> None:
        dialog = _ExportImagesDialog(parent)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.accepted.connect(lambda: on_selected(*dialog.get_options()))
        dialog.rejected.connect(lambda: on_selected(None, None))
        dialog.show()

    def ask_directory(
        self,
        parent: QWidget | None,
        title: str,
    ) -> str | None:
        path = QFileDialog.getExistingDirectory(parent, title)
        return path if path else None

    @staticmethod
    def _filetypes_to_filter(filetypes: list[tuple[str, str]]) -> str:
        """Convert generic legacy filetypes list to Qt filter string."""
        parts = []
        for label, pattern in filetypes:
            parts.append(f"{label} ({pattern})")
        return ";;".join(parts)
