import uuid


class ParamValue:

    PREVIOUS_RESULT = "Previous Result"

    def __init__(self, kind="literal", value=None, name=None):
        self.kind = kind  # literal or variable
        self.value = value
        self.name = name

    @classmethod
    def literal(cls, value):
        return cls(kind="literal", value=value)

    @classmethod
    def variable(cls, name):
        return cls(kind="variable", name=name)

    def resolve(self, ctx):
        if self.kind == "variable":
            if self.name == self.PREVIOUS_RESULT:
                return ctx.previous_result
            return ctx.variables.get(self.name, "")
        return self.value

    def to_dict(self):
        return {"kind": self.kind, "value": self.value, "name": self.name}

    @classmethod
    def from_dict(cls, d):
        if not d:
            return cls.literal("")
        return cls(kind=d.get("kind", "literal"), value=d.get("value"), name=d.get("name"))


class ActionInstance:

    def __init__(self, action_id, params=None, then_steps=None, else_steps=None,
                 body_steps=None, uid=None):
        self.uid = uid or uuid.uuid4().hex[:8]
        self.action_id = action_id
        self.params = params or {}
        self.then_steps = then_steps if then_steps is not None else []
        self.else_steps = else_steps if else_steps is not None else []
        self.body_steps = body_steps if body_steps is not None else []

    def to_dict(self):
        return {
            "uid": self.uid,
            "action_id": self.action_id,
            "params": {k: v.to_dict() for k, v in self.params.items()},
            "then_steps": [s.to_dict() for s in self.then_steps],
            "else_steps": [s.to_dict() for s in self.else_steps],
            "body_steps": [s.to_dict() for s in self.body_steps],
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            action_id=d["action_id"],
            params={k: ParamValue.from_dict(v) for k, v in d.get("params", {}).items()},
            then_steps=[cls.from_dict(s) for s in d.get("then_steps", [])],
            else_steps=[cls.from_dict(s) for s in d.get("else_steps", [])],
            body_steps=[cls.from_dict(s) for s in d.get("body_steps", [])],
            uid=d.get("uid"),
        )


class Shortcut:
    def __init__(self, name, steps=None, icon_name="bolt-symbolic",
                 color_class="tile-blue", folder="My Shortcuts", confirm=False, uid=None):
        self.uid = uid or uuid.uuid4().hex[:8]
        self.name = name
        self.steps = steps or []
        self.icon_name = icon_name
        self.color_class = color_class
        self.folder = folder
        self.confirm = confirm

    def to_dict(self):
        return {
            "uid": self.uid,
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "icon_name": self.icon_name,
            "color_class": self.color_class,
            "folder": self.folder,
            "confirm": self.confirm,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d["name"],
            steps=[ActionInstance.from_dict(s) for s in d.get("steps", [])],
            icon_name=d.get("icon_name", "bolt-symbolic"),
            color_class=d.get("color_class", "tile-blue"),
            folder=d.get("folder", "My Shortcuts"),
            confirm=d.get("confirm", False),
            uid=d.get("uid"),
        )


class Automation:
    """A shortcut that runs itself when its trigger fires
    trigger_params depends on trigger_type"""

    def __init__(self, name, trigger_type="time", trigger_params=None, steps=None,
                 ask_before_running=True, enabled=True, uid=None):
        self.uid = uid or uuid.uuid4().hex[:8]
        self.name = name
        self.trigger_type = trigger_type
        self.trigger_params = trigger_params if trigger_params is not None else {}
        self.steps = steps or []
        self.ask_before_running = ask_before_running
        self.enabled = enabled

    def to_dict(self):
        return {
            "uid": self.uid,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "trigger_params": self.trigger_params,
            "steps": [s.to_dict() for s in self.steps],
            "ask_before_running": self.ask_before_running,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d["name"],
            trigger_type=d.get("trigger_type", "time"),
            trigger_params=dict(d.get("trigger_params") or {}),
            steps=[ActionInstance.from_dict(s) for s in d.get("steps", [])],
            ask_before_running=d.get("ask_before_running", True),
            enabled=d.get("enabled", True),
            uid=d.get("uid"),
        )
