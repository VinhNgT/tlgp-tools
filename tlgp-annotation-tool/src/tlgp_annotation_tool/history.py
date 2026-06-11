import copy
from typing import List, Tuple
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession


class HistoryManager:
    def __init__(self, session: ScreenSession):
        self.session = session
        # Each snapshot: (components_deepcopy, screen_name, description, cut_lines_copy)
        self.history: List[Tuple[List[AnnotationBox], str, str, List[int]]] = []
        self.pointer: int = -1
        self.save_snapshot()

    def save_snapshot(self):
        # Discard any redo history
        if self.pointer < len(self.history) - 1:
            self.history = self.history[:self.pointer + 1]

        components_copy = copy.deepcopy(self.session.components)
        snapshot = (
            components_copy,
            self.session.screen_name,
            self.session.description,
            list(self.session.cut_lines),
        )
        self.history.append(snapshot)
        self.pointer += 1

    def undo(self) -> bool:
        if self.pointer > 0:
            self.pointer -= 1
            self._restore_current_snapshot()
            return True
        return False

    def redo(self) -> bool:
        if self.pointer < len(self.history) - 1:
            self.pointer += 1
            self._restore_current_snapshot()
            return True
        return False

    def _restore_current_snapshot(self):
        snapshot = self.history[self.pointer]
        self.session.components = copy.deepcopy(snapshot[0])
        self.session.screen_name = snapshot[1]
        self.session.description = snapshot[2]
        self.session.cut_lines = list(snapshot[3])
