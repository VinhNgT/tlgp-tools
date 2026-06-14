import tkinter as tk
from tkinter import filedialog, messagebox

from models import Component
from PIL import Image

from .cut_editor import CutEditorDialog
from .dialog_service import DialogService, ProgressIndicator
from .views.dialogs import ImportingDialog, ScreenInfoDialog


class TkinterDialogService(DialogService):
    """Production implementation of DialogService wrapping standard Tkinter dialog boxes and custom modal views."""

    def ask_open_filename(
        self,
        parent: tk.Widget,
        title: str,
        filetypes: list[tuple[str, str]],
    ) -> str | None:
        res = filedialog.askopenfilename(
            parent=parent, title=title, filetypes=filetypes
        )
        return res if res else None

    def ask_save_as_filename(
        self,
        parent: tk.Widget,
        title: str,
        filetypes: list[tuple[str, str]],
        defaultextension: str,
    ) -> str | None:
        res = filedialog.asksaveasfilename(
            parent=parent,
            title=title,
            filetypes=filetypes,
            defaultextension=defaultextension,
        )
        return res if res else None

    def show_error(self, parent: tk.Widget, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=parent)

    def show_warning(self, parent: tk.Widget, title: str, message: str) -> None:
        messagebox.showwarning(title, message, parent=parent)

    def show_info(self, parent: tk.Widget, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=parent)

    def show_importing_dialog(
        self, parent: tk.Widget, message: str
    ) -> ProgressIndicator:
        return ImportingDialog(parent, message=message)

    def show_cut_editor(
        self,
        parent: tk.Widget,
        image: Image.Image,
        initial_cuts: list[int],
        components: list[Component],
    ) -> list[int] | None:
        dialog = CutEditorDialog(
            parent,
            image=image,
            initial_cuts=initial_cuts,
            components=components,
        )
        return dialog.result

    def show_screen_info(
        self, parent: tk.Widget, screen_name: str, description: str
    ) -> dict[str, str] | None:
        dialog = ScreenInfoDialog(
            parent, screen_name=screen_name, description=description
        )
        return dialog.result
