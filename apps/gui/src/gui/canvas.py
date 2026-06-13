import tkinter as tk
from tkinter import simpledialog

from models import WorkspaceState
from PIL import Image, ImageTk
from tlgp_logger import get_logger

from .api_client import EngineClient

logger = get_logger(__name__)


class AnnotationCanvas(tk.Canvas):
    """
    A dumb canvas that simply renders the WorkspaceState.
    Instead of complex backend logic, all mutations are fired directly to the Engine.
    """

    def __init__(self, parent, client: EngineClient):
        super().__init__(parent, bg="#121212", highlightthickness=0)
        self.client = client
        self.bg_image: Image.Image | None = None
        self.bg_photo: ImageTk.PhotoImage | None = None

        self.drag_data = {
            "item_id": None,
            "start_x": 0,
            "start_y": 0,
            "comp_id": None,
            "mode": None,
        }
        self.draw_rect_id = None
        self.selected_comp_id = None

        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Double-Button-1>", self.on_double_click)
        self.bind("<BackSpace>", self.on_delete_key)
        self.bind("<Delete>", self.on_delete_key)

    def set_background_image(self, img: Image.Image):
        # Very simple caching
        if self.bg_image and self.bg_image.size == img.size:
            return

        self.bg_image = img
        self.bg_photo = ImageTk.PhotoImage(img)
        self.config(scrollregion=(0, 0, img.width, img.height))

    def render_state(self, state: WorkspaceState):
        self.delete("all")

        if self.bg_photo:
            self.create_image(0, 0, anchor=tk.NW, image=self.bg_photo)

        for comp_id, comp in state.components.items():
            if not comp.visibility.visible:
                continue

            b = comp.absoluteBounds

            # Highlight if selected
            outline_color = "yellow" if str(comp_id) == self.selected_comp_id else "red"

            # Draw box
            self.create_rectangle(
                b.left,
                b.top,
                b.right,
                b.bottom,
                outline=outline_color,
                width=2,
                tags=("component", str(comp_id)),
            )

            # Draw number pill
            self.create_rectangle(
                b.left,
                b.top,
                b.left + 30,
                b.top + 20,
                fill="white",
                outline=outline_color,
                width=2,
            )
            self.create_text(
                b.left + 15,
                b.top + 10,
                text=comp.number,
                fill=outline_color,
                font=("Arial", 10, "bold"),
            )

    # ── Interaction ────────────────────────────────────────────────────

    def on_press(self, event):
        self.focus_set()
        cx, cy = self.canvasx(event.x), self.canvasy(event.y)
        self.drag_data["start_x"] = cx
        self.drag_data["start_y"] = cy

        items = self.find_withtag("current")
        if not items:
            # We didn't click anything -> start drawing a new rectangle
            self.selected_comp_id = None
            self.drag_data["mode"] = "draw"
            self.draw_rect_id = self.create_rectangle(
                cx, cy, cx, cy, outline="green", width=2
            )
            # Re-render to clear selection highlight instantly if needed
            if self.client.state:
                self.render_state(self.client.state)
            return

        tags = self.gettags(items[0])
        if "component" in tags:
            comp_id = tags[1]
            self.selected_comp_id = comp_id

            x1, y1, x2, y2 = self.coords(items[0])
            # Check if we clicked near the bottom-right corner for resizing
            if x2 - 15 <= cx <= x2 + 15 and y2 - 15 <= cy <= y2 + 15:
                self.drag_data["mode"] = "resize_br"
            else:
                self.drag_data["mode"] = "move"

            self.drag_data["item_id"] = items[0]
            self.drag_data["comp_id"] = comp_id

            # Quick visual refresh to show selection
            if self.client.state:
                self.render_state(self.client.state)

    def on_drag(self, event):
        mode = self.drag_data["mode"]
        if not mode:
            return

        cx, cy = self.canvasx(event.x), self.canvasy(event.y)

        if mode == "draw" and self.draw_rect_id:
            self.coords(
                self.draw_rect_id,
                self.drag_data["start_x"],
                self.drag_data["start_y"],
                cx,
                cy,
            )

        elif mode == "move" and self.drag_data["item_id"]:
            dx = cx - self.drag_data["start_x"]
            dy = cy - self.drag_data["start_y"]
            self.move(self.drag_data["item_id"], dx, dy)
            self.drag_data["start_x"] = cx
            self.drag_data["start_y"] = cy

        elif mode == "resize_br" and self.drag_data["item_id"]:
            x1, y1, _, _ = self.coords(self.drag_data["item_id"])
            self.coords(self.drag_data["item_id"], x1, y1, cx, cy)

    def on_release(self, event):

        mode = self.drag_data["mode"]

        if mode == "draw" and self.draw_rect_id:
            x1, y1, x2, y2 = self.coords(self.draw_rect_id)
            self.delete(self.draw_rect_id)
            self.draw_rect_id = None

            # Normalize coordinates if drawn backwards
            left, right = min(x1, x2), max(x1, x2)
            top, bottom = min(y1, y2), max(y1, y2)

            if right - left > 10 and bottom - top > 10:
                lbl = simpledialog.askstring("New Component", "Enter label:")
                if lbl:
                    bounds = {
                        "left": int(left),
                        "top": int(top),
                        "right": int(right),
                        "bottom": int(bottom),
                    }
                    try:
                        self.client.add_component(lbl, bounds)
                    except Exception as e:
                        logger.error("Failed to add", error=str(e))

        elif mode == "move" and self.drag_data["item_id"]:
            coords = self.coords(self.drag_data["item_id"])
            try:
                self.client.move_component(
                    self.drag_data["comp_id"], int(coords[0]), int(coords[1])
                )
            except Exception as e:
                logger.error("Failed to move", error=str(e))

        elif mode == "resize_br" and self.drag_data["item_id"]:
            coords = self.coords(self.drag_data["item_id"])
            bounds = {
                "left": int(coords[0]),
                "top": int(coords[1]),
                "right": int(coords[2]),
                "bottom": int(coords[3]),
            }
            try:
                self.client.update_component(self.drag_data["comp_id"], bounds=bounds)
            except Exception as e:
                logger.error("Failed to resize", error=str(e))

        self.drag_data = {
            "item_id": None,
            "start_x": 0,
            "start_y": 0,
            "comp_id": None,
            "mode": None,
        }

    def on_delete_key(self, event):
        if self.selected_comp_id:
            try:
                self.client.delete_component(self.selected_comp_id)
                self.selected_comp_id = None
            except Exception as e:
                logger.error("Failed to delete", error=str(e))

    def on_double_click(self, event):
        items = self.find_withtag("current")
        if not items:
            return

        tags = self.gettags(items[0])
        if "component" in tags:
            comp_id = tags[1]

            new_label = simpledialog.askstring("Edit Component", "Enter new label:")
            if new_label:
                try:
                    self.client.update_component(comp_id, label=new_label)
                except Exception as e:
                    logger.error("Failed to rename", error=str(e))
