import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb


class ScreenInfoDialog(tb.Toplevel):
    def __init__(self, parent, screen_name="", description=""):
        super().__init__(parent)
        self.title("Screen Information")
        self.geometry("450x240")
        self.resizable(False, False)

        self.result = None

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog relative to parent
        self.update_idletasks()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        x = parent_x + (parent_width - self.winfo_width()) // 2
        y = parent_y + (parent_height - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        # UI elements
        frame = tb.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        tb.Label(
            frame, text="Screen Name (e.g. Product Details Screen):", anchor="w"
        ).pack(fill=tk.X, pady=(0, 5))
        self.entry_name = tb.Entry(frame, width=50)
        self.entry_name.insert(0, screen_name)
        self.entry_name.pack(fill=tk.X, pady=(0, 10))
        self.entry_name.focus_set()

        tb.Label(frame, text="Functional Description:", anchor="w").pack(
            fill=tk.X, pady=(0, 5)
        )
        self.text_desc = tb.Text(frame, height=4, width=50)
        self.text_desc.insert("1.0", description)
        self.text_desc.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        btn_frame = tb.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        btn_cancel = tb.Button(
            btn_frame,
            text="Cancel",
            command=self.on_cancel,
            width=10,
            bootstyle="secondary",
        )
        btn_cancel.pack(side=tk.RIGHT, padx=(5, 0))

        btn_save = tb.Button(
            btn_frame, text="Save", command=self.on_save, width=10, bootstyle="primary"
        )
        btn_save.pack(side=tk.RIGHT)

        # Bind Enter and Escape keys. Do not trigger save if a multiline text area is focused.
        self.bind(
            "<Return>",
            lambda e: self.on_save() if self.focus_get() != self.text_desc else None,
        )
        self.bind("<Escape>", lambda e: self.on_cancel())

        # Wait for dialog to be closed
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


class EditLabelDialog(tb.Toplevel):
    def __init__(
        self,
        parent,
        title="Edit Component Name",
        prompt="Enter Name:",
        current_value="",
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry("350x120")
        self.resizable(False, False)

        self.result = None
        self.transient(parent)
        self.grab_set()

        # Center dialog
        self.update_idletasks()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        x = parent_x + (parent_width - self.winfo_width()) // 2
        y = parent_y + (parent_height - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        frame = tb.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        tb.Label(frame, text=prompt, anchor="w").pack(fill=tk.X, pady=(0, 5))
        self.entry = tb.Entry(frame, width=40)
        self.entry.insert(0, current_value)
        self.entry.pack(fill=tk.X, pady=(0, 10))
        self.entry.focus_set()
        self.entry.select_range(0, tk.END)

        btn_frame = tb.Frame(frame)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        btn_cancel = tb.Button(
            btn_frame,
            text="Cancel",
            command=self.on_cancel,
            width=8,
            bootstyle="secondary",
        )
        btn_cancel.pack(side=tk.RIGHT, padx=(5, 0))

        btn_ok = tb.Button(
            btn_frame, text="OK", command=self.on_save, width=8, bootstyle="primary"
        )
        btn_ok.pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self.on_save())
        self.bind("<Escape>", lambda e: self.on_cancel())

        self.wait_window(self)

    def on_save(self, event=None):
        val = self.entry.get().strip()
        self.result = val
        self.grab_release()
        self.destroy()

    def on_cancel(self, event=None):
        self.grab_release()
        self.destroy()
