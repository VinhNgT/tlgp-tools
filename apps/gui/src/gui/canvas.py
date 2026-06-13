import tkinter as tk
from typing import Optional
from PIL import Image, ImageTk

from .api_client import EngineClient
from models import WorkspaceState, Bounds

class AnnotationCanvas(tk.Canvas):
    """
    A dumb canvas that simply renders the WorkspaceState.
    Instead of complex backend logic, all mutations are fired directly to the Engine.
    """
    def __init__(self, parent, client: EngineClient):
        super().__init__(parent, bg="#121212", highlightthickness=0)
        self.client = client
        self.bg_image: Optional[Image.Image] = None
        self.bg_photo: Optional[ImageTk.PhotoImage] = None
        
        self.drag_data = {"item_id": None, "start_x": 0, "start_y": 0, "comp_id": None}
        
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)

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
            
            # Draw box
            rect_id = self.create_rectangle(
                b.left, b.top, b.right, b.bottom,
                outline="red", width=2,
                tags=("component", str(comp_id))
            )
            
            # Draw number pill
            self.create_rectangle(
                b.left, b.top, b.left + 30, b.top + 20,
                fill="white", outline="red", width=2
            )
            self.create_text(
                b.left + 15, b.top + 10,
                text=comp.number, fill="red", font=("Arial", 10, "bold")
            )

    # ── Interaction ────────────────────────────────────────────────────
    
    def on_press(self, event):
        # Convert window coords to canvas coords
        cx, cy = self.canvasx(event.x), self.canvasy(event.y)
        
        # Find if we clicked a component
        items = self.find_withtag("current")
        if not items:
            return
            
        tags = self.gettags(items[0])
        if "component" in tags:
            self.drag_data["item_id"] = items[0]
            self.drag_data["comp_id"] = tags[1]
            self.drag_data["start_x"] = cx
            self.drag_data["start_y"] = cy

    def on_drag(self, event):
        if not self.drag_data["item_id"]:
            return
            
        cx, cy = self.canvasx(event.x), self.canvasy(event.y)
        dx = cx - self.drag_data["start_x"]
        dy = cy - self.drag_data["start_y"]
        
        # Visually move the rectangle immediately for responsiveness
        self.move(self.drag_data["item_id"], dx, dy)
        
        self.drag_data["start_x"] = cx
        self.drag_data["start_y"] = cy

    def on_release(self, event):
        if not self.drag_data["item_id"]:
            return
            
        # Extract new coordinates
        coords = self.coords(self.drag_data["item_id"])
        new_x, new_y = int(coords[0]), int(coords[1])
        comp_id = self.drag_data["comp_id"]
        
        # We don't save local state. We blast the intent to the Engine!
        try:
            self.client.move_component(comp_id, new_x, new_y)
        except Exception as e:
            print(f"Failed to move: {e}")
            
        self.drag_data = {"item_id": None, "start_x": 0, "start_y": 0, "comp_id": None}
