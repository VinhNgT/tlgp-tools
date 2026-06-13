import io
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk

from PIL import Image
from tlgp_logger import get_logger

from .api_client import EngineClient
from .canvas import AnnotationCanvas

logger = get_logger(__name__)


class TlgpApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TLGP Annotation Client (Thin GUI)")
        self.geometry("1000x700")

        # Initialize the Engine Client
        # We pass a callback to trigger a full UI refresh when the Engine broadcasts state
        self.client = EngineClient(on_state_changed=self.on_state_sync)

        self.create_widgets()

    def create_widgets(self):
        # Top toolbar
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        btn_import = ttk.Button(
            toolbar, text="Import Session...", command=self.do_import
        )
        btn_import.pack(side=tk.LEFT, padx=2)

        btn_import_img = ttk.Button(
            toolbar, text="Import Image...", command=self.do_import_image
        )
        btn_import_img.pack(side=tk.LEFT, padx=2)

        self.lbl_status = ttk.Label(toolbar, text="Connecting to Engine...")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        # Main Layout (PanedWindow)
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left Sidebar (Treeview)
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        tree_scroll = ttk.Scrollbar(left_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(
            left_frame, yscrollcommand=tree_scroll.set, selectmode="browse"
        )
        self.tree.heading("#0", text="Components", anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.tree.yview)

        # Right Area (Canvas)
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        self.canvas = AnnotationCanvas(right_frame, self.client)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def on_state_sync(self):
        """Called by the background EngineClient thread whenever a JSON Patch is received."""
        # Must schedule UI updates on the main thread
        self.after(0, self._refresh_ui)

    def _refresh_ui(self):
        if not self.client.state:
            return

        self.lbl_status.config(
            text=f"Connected | Session: {self.client.state.sessionId}"
        )

        # Reload background image if missing or changed
        # In a real implementation, we'd cache the image
        try:
            req = urllib.request.urlopen(self.client.get_raw_image_url())
            img_data = req.read()
            img = Image.open(io.BytesIO(img_data))
            self.canvas.set_background_image(img)
        except Exception as e:
            logger.error("Could not load image from Engine", error=str(e))

        # Draw all components
        self.canvas.render_state(self.client.state)

        # Rebuild Tree
        self._rebuild_tree()

    def _rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.client.state:
            return

        def insert_node(parent_tvid, comp_id):
            comp = self.client.state.components.get(str(comp_id))
            if not comp:
                return

            node_text = f"{comp.number} {comp.label}" if comp.number else comp.label
            tvid = self.tree.insert(parent_tvid, tk.END, text=node_text, open=True)

            for child_id in comp.childrenIds:
                insert_node(tvid, child_id)

        for root_id in self.client.state.rootComponents:
            insert_node("", root_id)

    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select session zip", filetypes=[("Zip files", "*.zip")]
        )
        if not path:
            return
        try:
            self.client.import_zip(path)
            messagebox.showinfo("Success", "Workspace imported to Engine!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import: {e}")

    def do_import_image(self):
        path = filedialog.askopenfilename(
            title="Select raw image", filetypes=[("Image files", "*.png *.jpg *.jpeg")]
        )
        if not path:
            return
        try:
            self.client.import_image(path)
            messagebox.showinfo("Success", "Image imported to Engine!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import image: {e}")


def main():
    app = TlgpApp()
    app.mainloop()


if __name__ == "__main__":
    main()
