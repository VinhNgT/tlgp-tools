import pytest

def pytest_configure(config):
    from doc_generator.models import NodeSpec, ScreenSpec, Bounds, ApiParam
    
    # Patch ApiParam.__init__ to inject required test defaults
    original_param_init = ApiParam.__init__
    def new_param_init(self, *args, **kwargs):
        if "description" not in kwargs:
            kwargs["description"] = "dummy description"
        if "required" not in kwargs:
            kwargs["required"] = True
        if "type" not in kwargs:
            kwargs["type"] = "string"
        original_param_init(self, *args, **kwargs)
    ApiParam.__init__ = new_param_init

    # Patch NodeSpec.__init__ to inject required test defaults
    original_node_init = NodeSpec.__init__
    def new_node_init(self, *args, **kwargs):
        if "absoluteBounds" not in kwargs:
            kwargs["absoluteBounds"] = Bounds(x=0, y=0, w=0, h=0)
        if "rawImage" not in kwargs:
            kwargs["rawImage"] = "dummy.png"
        if "controlType" not in kwargs:
            kwargs["controlType"] = "Screen"
        if "editable" not in kwargs:
            kwargs["editable"] = False
        if "description" not in kwargs:
            kwargs["description"] = "dummy description"
        if "required" not in kwargs:
            kwargs["required"] = False
        original_node_init(self, *args, **kwargs)
    NodeSpec.__init__ = new_node_init

    # Patch ScreenSpec.__init__ to inject required test defaults
    original_screen_init = ScreenSpec.__init__
    def new_screen_init(self, *args, **kwargs):
        if "sectionPrefix" not in kwargs:
            kwargs["sectionPrefix"] = "1.1"
        if "rootId" not in kwargs:
            kwargs["rootId"] = 0
        original_screen_init(self, *args, **kwargs)
    ScreenSpec.__init__ = new_screen_init
