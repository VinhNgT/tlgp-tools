import json
import tkinter as tk
from datetime import datetime
from tkinter import ttk


class BackendDebugWindow(tk.Toplevel):
    """Developer window that logs outgoing and incoming messages from the backend."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Backend Logs")
        self.geometry("600x400")
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.transient(parent)
        self.withdraw()

        header = ttk.Frame(self)
        header.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        lbl = ttk.Label(header, text="Backend Logs", font=("", 9, "bold"))
        lbl.pack(side=tk.LEFT)

        self.btn_clear = ttk.Button(header, text="Clear", command=self.clear_logs, width=6)
        self.btn_clear.pack(side=tk.RIGHT)

        text_frame = ttk.Frame(self)
        text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.text_area = tk.Text(text_frame, wrap=tk.WORD, state=tk.DISABLED, width=40, height=10)

        scroll = ttk.Scrollbar(text_frame, command=self.text_area.yview)
        self.text_area.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def log_message(self, direction: str, message: dict | str):
        self.text_area.configure(state=tk.NORMAL)
        if isinstance(message, dict):
            try:
                msg_str = json.dumps(message, indent=2)
            except Exception:
                msg_str = str(message)
        else:
            try:
                parsed = json.loads(message)
                msg_str = json.dumps(parsed, indent=2)
            except Exception:
                msg_str = str(message)

        now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.text_area.insert(tk.END, f"[{now_str}] [{direction}]\n{msg_str}\n{'-'*40}\n")
        self.text_area.see(tk.END)
        self.text_area.configure(state=tk.DISABLED)

    def clear_logs(self):
        self.text_area.configure(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        self.text_area.configure(state=tk.DISABLED)

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_window(self):
        self.withdraw()
