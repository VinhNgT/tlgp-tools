from abc import ABC, abstractmethod
from typing import Any, Protocol

from models import Component
from PIL import Image


class ProgressIndicator(Protocol):
    """Abstract handle for control over a transient progress dialog."""

    def dismiss(self) -> None:
        """Dismisses and closes the progress dialog."""
        ...


class DialogService(ABC):
    """Abstract interface defining standard file and dialog notifications."""

    @abstractmethod
    def ask_open_filename(
        self,
        parent: Any,
        title: str,
        filetypes: list[tuple[str, str]],
    ) -> str | None:
        """Prompts the user to select an existing file path."""
        pass

    @abstractmethod
    def ask_save_as_filename(
        self,
        parent: Any,
        title: str,
        filetypes: list[tuple[str, str]],
        defaultextension: str,
    ) -> str | None:
        """Prompts the user to specify a path to save a file."""
        pass

    @abstractmethod
    def show_error(self, parent: Any, title: str, message: str) -> None:
        """Displays a modal error message dialog."""
        pass

    @abstractmethod
    def show_warning(self, parent: Any, title: str, message: str) -> None:
        """Displays a modal warning message dialog."""
        pass

    @abstractmethod
    def show_info(self, parent: Any, title: str, message: str) -> None:
        """Displays a modal informational dialog."""
        pass

    @abstractmethod
    def show_importing_dialog(self, parent: Any, message: str) -> ProgressIndicator:
        """Displays a transient progress or importing indicator."""
        pass

    @abstractmethod
    def show_cut_editor(
        self,
        parent: Any,
        image: Image.Image,
        initial_cuts: list[int],
        components: list[Component],
    ) -> list[int] | None:
        """Opens the screen cut editor dialog."""
        pass

    @abstractmethod
    def show_screen_info(
        self, parent: Any, screen_name: str, description: str
    ) -> dict[str, str] | None:
        """Opens the screen info editor dialog."""
        pass
