"""Handler for IO commands decoupled from the main controller."""

import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from PySide6.QtCore import QObject, Signal, Slot

from annotator.workspace import WorkspaceManager


class _MainThreadInvoker(QObject):
    """Thread-safe bridge for posting callables from worker threads to the main thread."""

    _call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._call.connect(self._execute)

    def invoke(self, fn):
        self._call.emit(fn)

    @Slot(object)
    def _execute(self, fn):
        fn()


class IOCommandHandler:
    """Handles asynchronous I/O commands."""

    def __init__(self, workspace: WorkspaceManager, dialog_service, view):
        self.workspace = workspace
        self.dialog_service = dialog_service
        self.view = view
        self._io_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="annotator-io"
        )
        self._invoker = _MainThreadInvoker(self.view)

    def shutdown(self):
        self._io_pool.shutdown(wait=False)

    def handle_import_zip(self):
        path = self.dialog_service.ask_open_filename(
            self.view, title="Select workspace zip", filetypes=[("Zip files", "*.zip")]
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Importing workspace..."
        )

        def do_import():
            with open(path, "rb") as f:
                self.workspace.import_zip(f.read())

        future = self._io_pool.submit(do_import)
        future.add_done_callback(
            lambda f: self._invoker.invoke(
                lambda: self._handle_io_result(
                    f, dialog, "Import Failed", "Failed to import workspace"
                )
            )
        )

    def handle_import_image(self):
        path = self.dialog_service.ask_open_filename(
            self.view,
            title="Select raw image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg")],
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Importing raw image..."
        )

        def do_import():
            with open(path, "rb") as f:
                self.workspace.import_image(f.read(), os.path.basename(path))

        future = self._io_pool.submit(do_import)
        future.add_done_callback(
            lambda f: self._invoker.invoke(
                lambda: self._handle_io_result(
                    f, dialog, "Import Failed", "Failed to import raw image"
                )
            )
        )

    def handle_export_zip(self):
        if not self.view.canvas.full_pil_img:
            return
        path = self.dialog_service.ask_save_as_filename(
            self.view,
            title="Save workspace zip",
            filetypes=[("Zip files", "*.zip")],
            defaultextension=".zip",
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Exporting workspace..."
        )

        def do_export():
            zip_bytes = self.workspace.export_zip()
            with open(path, "wb") as f:
                f.write(zip_bytes)

        future = self._io_pool.submit(do_export)
        future.add_done_callback(
            lambda f: self._invoker.invoke(
                lambda: self._handle_io_result(
                    f,
                    dialog,
                    "Export Failed",
                    "Failed to export workspace",
                    success_msg="Workspace zip exported successfully.",
                )
            )
        )

    def handle_export_images(self):
        if not self.view.canvas.full_pil_img:
            return

        def on_options_selected(
            mode: Literal["annotated", "both", "raw"] | None, format_val: str | None
        ):
            if not mode or not format_val:
                return

            export_name = self.workspace.get_default_export_name(mode)

            if format_val == "zip":
                default_filename = f"{export_name}.zip"

                dest_file = self.dialog_service.ask_save_as_filename(
                    self.view,
                    title="Save Exported Images Zip",
                    filetypes=[("Zip files", "*.zip")],
                    defaultextension=".zip",
                    initial_filename=default_filename,
                )
                if not dest_file:
                    return

                dialog = self.dialog_service.show_importing_dialog(
                    self.view, message="Exporting component images..."
                )

                def do_export():
                    zip_bytes = self.workspace.export_images(mode)
                    with open(dest_file, "wb") as f:
                        f.write(zip_bytes)
            else:
                dest_dir = self.dialog_service.ask_directory(
                    self.view,
                    title="Select Directory to Export Images",
                )
                if not dest_dir:
                    return

                dialog = self.dialog_service.show_importing_dialog(
                    self.view, message="Exporting component images..."
                )

                def do_export():
                    export_path = os.path.join(dest_dir, export_name)
                    os.makedirs(export_path, exist_ok=True)

                    zip_bytes = self.workspace.export_images(mode)
                    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                        zf.extractall(export_path)

            future = self._io_pool.submit(do_export)
            future.add_done_callback(
                lambda f: self._invoker.invoke(
                    lambda: self._handle_io_result(
                        f,
                        dialog,
                        "Export Failed",
                        "Failed to export component images",
                        success_msg="Component images exported successfully.",
                    )
                )
            )

        self.dialog_service.ask_export_images_options(self.view, on_options_selected)

    def _handle_io_result(
        self, future, dialog, error_title, error_prefix, success_msg=None
    ):
        dialog.dismiss()
        exc = future.exception()
        if exc:
            self.dialog_service.show_error(
                self.view, error_title, f"{error_prefix}:\n{exc}"
            )
        elif success_msg:
            self.dialog_service.show_info(self.view, "Success", success_msg)
