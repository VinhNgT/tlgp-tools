import tkinter as tk
from tkinter import messagebox, ttk


class ImportingDialog(tk.Toplevel):
    """Self-dismissing progress indicator shown during background import operations."""

    def __init__(self, parent, message="Importing..."):
        super().__init__(parent)
        self.title("Please Wait")
        self.geometry("280x80")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center relative to parent window
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - 280) // 2
        y = parent_y + (parent_h - 80) // 2
        self.geometry(f"+{x}+{y}")

        lbl = ttk.Label(self, text=message, font=("", 10), anchor="center")
        lbl.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
        self.update()


class ScreenInfoDialog(tk.Toplevel):
    """Modal form dialog for editing screen name and functional description."""

    def __init__(self, parent, screen_name="", description=""):
        super().__init__(parent)
        self.title("Screen Information")
        self.geometry("450x240")
        self.resizable(False, False)

        self.result = None

        self.transient(parent)
        self.grab_set()

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        x = px + (pw - 450) // 2
        y = py + (ph - 240) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame, text="Screen Name (e.g. Product Details Screen):", anchor="w"
        ).pack(fill=tk.X, pady=(0, 5))

        self.entry_name = ttk.Entry(frame, width=50)
        self.entry_name.insert(0, screen_name)
        self.entry_name.pack(fill=tk.X, pady=(0, 10))
        self.entry_name.focus_set()

        ttk.Label(frame, text="Functional Description:", anchor="w").pack(
            fill=tk.X, pady=(0, 5)
        )

        self.text_desc = tk.Text(
            frame,
            height=4,
            width=50,
            highlightthickness=1,
            highlightbackground="#cccccc",
            relief="flat",
        )
        self.text_desc.insert("1.0", description)
        self.text_desc.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        btn_cancel = ttk.Button(
            btn_frame,
            text="Cancel",
            command=self.on_cancel,
            width=10,
        )
        btn_cancel.pack(side=tk.RIGHT, padx=(5, 0))

        btn_save = ttk.Button(
            btn_frame,
            text="Save",
            command=self.on_save,
            width=10,
        )
        btn_save.pack(side=tk.RIGHT)

        self.bind(
            "<Return>",
            lambda e: self.on_save() if self.focus_get() != self.text_desc else None,
        )
        self.bind("<Escape>", lambda e: self.on_cancel())
        self.wait_window(self)

    def on_save(self, event=None):
        name = self.entry_name.get().strip()
        desc = self.text_desc.get("1.0", tk.END).strip()

        if not name:
            messagebox.showwarning(
                "Warning", "Please enter a screen name!", parent=self
            )
            return

        self.result = {"screen_name": name, "description": desc}
        self.grab_release()
        self.destroy()

    def on_cancel(self, event=None):
        self.grab_release()
        self.destroy()
