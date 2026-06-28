
def pytest_configure(config):
    print("pytest_configure RUNNING!")
    from tlgp_contracts import ApiParam, NodeSpec, ScreenSpec
    from tlgp_contracts.spec import Bounds

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
            node_id = kwargs.get("id")
            children = kwargs.get("childrenIds", [])
            # Coerce to int if string
            try:
                coerced_id = int(node_id) if node_id is not None else None
            except ValueError:
                coerced_id = None

            if coerced_id == 0:
                kwargs["controlType"] = "Screen"
            elif len(children) > 0:
                kwargs["controlType"] = "Component"
            else:
                kwargs["controlType"] = "Button"
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
