import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import urllib.request
import io
from PIL import Image, ImageTk

from .api_client import EngineClient
from .canvas import AnnotationCanvas

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

        btn_import = ttk.Button(toolbar, text="Import Session...", command=self.do_import)
        btn_import.pack(side=tk.LEFT, padx=2)

        self.lbl_status = ttk.Label(toolbar, text="Connecting to Engine...")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        # Main Layout (Canvas)
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = AnnotationCanvas(main_frame, self.client)
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def on_state_sync(self):
        """Called by the background EngineClient thread whenever a JSON Patch is received."""
        # Must schedule UI updates on the main thread
        self.after(0, self._refresh_ui)

    def _refresh_ui(self):
        if not self.client.state:
            return
            
        self.lbl_status.config(text=f"Connected | Session: {self.client.state.sessionId}")
        
        # Reload background image if missing or changed
        # In a real implementation, we'd cache the image
        try:
            req = urllib.request.urlopen(self.client.get_raw_image_url())
            img_data = req.read()
            img = Image.open(io.BytesIO(img_data))
            self.canvas.set_background_image(img)
        except Exception as e:
            print(f"Could not load image from Engine: {e}")
            
        # Draw all components
        self.canvas.render_state(self.client.state)

    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select session zip",
            filetypes=[("Zip files", "*.zip")]
        )
        if not path:
            return
        try:
            self.client.import_zip(path)
            messagebox.showinfo("Success", "Workspace imported to Engine!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import: {e}")

def main():
    app = TlgpApp()
    app.mainloop()

if __name__ == "__main__":
    main()
