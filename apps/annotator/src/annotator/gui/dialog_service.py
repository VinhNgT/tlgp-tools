from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Protocol

from PIL import Image

from annotator.models import Component


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
        on_save: Callable[[list[int]], None],
    ) -> None:
        """Opens the screen cut editor dialog."""
        pass

    @abstractmethod
    def show_screen_info(
        self,
        parent: Any,
        screen_name: str,
        description: str,
        on_save: Callable[[dict[str, str]], None],
    ) -> None:
        """Opens the screen info editor dialog."""
        pass

    @abstractmethod
    def ask_export_images_mode(
        self, parent: Any, on_mode_selected: Callable[[str | None], None]
    ) -> None:
        """Prompts the user to select an export mode.

        Calls on_mode_selected with 'with_annotations', 'without_annotations', or None if cancelled.
        """
        pass
