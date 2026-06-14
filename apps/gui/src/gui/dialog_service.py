from abc import ABC, abstractmethod
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image

from models import Component

from .cut_editor import CutEditorDialog
from .views.dialogs import ImportingDialog, ScreenInfoDialog


class DialogService(ABC):
    """Abstract interface defining standard file and dialog notifications."""

    @abstractmethod
    def ask_open_filename(
        self,
        parent: tk.Widget,
        title: str,
        filetypes: list[tuple[str, str]],
    ) -> str | None:
        """Prompts the user to select an existing file path."""
        pass

    @abstractmethod
    def ask_save_as_filename(
        self,
        parent: tk.Widget,
        title: str,
        filetypes: list[tuple[str, str]],
        defaultextension: str,
    ) -> str | None:
        """Prompts the user to specify a path to save a file."""
        pass

    @abstractmethod
    def show_error(self, parent: tk.Widget, title: str, message: str) -> None:
        """Displays a modal error message dialog."""
        pass

    @abstractmethod
    def show_warning(self, parent: tk.Widget, title: str, message: str) -> None:
        """Displays a modal warning message dialog."""
        pass

    @abstractmethod
    def show_info(self, parent: tk.Widget, title: str, message: str) -> None:
        """Displays a modal informational dialog."""
        pass

    @abstractmethod
    def show_importing_dialog(self, parent: tk.Widget, message: str) -> Any:
        """Displays a transient progress or importing indicator."""
        pass

    @abstractmethod
    def show_cut_editor(
        self,
        parent: tk.Widget,
        image: Image.Image,
        initial_cuts: list[int],
        components: list[Component],
    ) -> list[int] | None:
        """Opens the screen cut editor dialog."""
        pass

    @abstractmethod
    def show_screen_info(
        self, parent: tk.Widget, screen_name: str, description: str
    ) -> dict[str, str] | None:
        """Opens the screen info editor dialog."""
        pass


class TkinterDialogService(DialogService):
    """Production implementation of DialogService wrapping standard Tkinter dialog boxes and custom modal views."""

    def ask_open_filename(
        self,
        parent: tk.Widget,
        title: str,
        filetypes: list[tuple[str, str]],
    ) -> str | None:
        res = filedialog.askopenfilename(parent=parent, title=title, filetypes=filetypes)
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

    def show_importing_dialog(self, parent: tk.Widget, message: str) -> Any:
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
