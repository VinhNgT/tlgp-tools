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
        ...

    @abstractmethod
    def ask_save_as_filename(
        self,
        parent: Any,
        title: str,
        filetypes: list[tuple[str, str]],
        defaultextension: str,
        initial_filename: str = "",
    ) -> str | None:
        """Prompts the user to specify a path to save a file."""
        ...

    @abstractmethod
    def show_error(self, parent: Any, title: str, message: str) -> None:
        """Displays a modal error message dialog."""
        ...

    @abstractmethod
    def show_warning(self, parent: Any, title: str, message: str) -> None:
        """Displays a modal warning message dialog."""
        ...

    @abstractmethod
    def show_info(self, parent: Any, title: str, message: str) -> None:
        """Displays a modal informational dialog."""
        ...

    @abstractmethod
    def show_importing_dialog(self, parent: Any, message: str) -> ProgressIndicator:
        """Displays a transient progress or importing indicator."""
        ...

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
        ...

    @abstractmethod
    def show_screen_info(
        self,
        parent: Any,
        screen_name: str,
        description: str,
        on_save: Callable[[dict[str, str]], None],
    ) -> None:
        """Opens the screen info editor dialog."""
        ...

    @abstractmethod
    def ask_export_images_options(
        self,
        parent: Any,
        on_selected: Callable[[str | None, str | None], None],
    ) -> None:
        """Prompts the user to select export mode and format.

        Calls on_selected with (mode, format), or (None, None) if cancelled.
        """
        ...

    @abstractmethod
    def ask_directory(
        self,
        parent: Any,
        title: str,
    ) -> str | None:
        """Prompts the user to select an existing directory."""
        ...
