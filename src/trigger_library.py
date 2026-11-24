"""Registry for plugin contributed automation trigger kinds
Built in kinds stay hardcoded in automation_widgets and automation_engine"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from action_library import ParamSpec  # same field spec as actions


@dataclass
class TriggerType:
    id: str
    name: str
    category: Optional[str]
    icon_name: str
    color_class: str
    params: List[ParamSpec] = field(default_factory=list)
    # poll receives state and params and returns fired and new state
    # leave unset for a trigger that never fires automatically
    poll: Optional[Callable] = None
    # describe returns the one line summary for the automation tile
    # falls back to the trigger name
    describe: Optional[Callable] = None


_DEFAULT_PLUGIN_CATEGORY_ICON = "sc-puzzle-symbolic"

TRIGGER_LIBRARY: List[TriggerType] = []
TRIGGER_BY_ID = {}
_plugin_registrations = {}  # plugin id to its trigger ids


def register_triggers(plugin_id, triggers, category=None):
    """Registers plugin trigger kinds under namespaced ids
    raises ValueError if the plugin id is already registered"""
    if plugin_id in _plugin_registrations:
        raise ValueError(f"Plugin \u201c{plugin_id}\u201d already has triggers registered.")

    default_category = category or "Plugin"
    for t in triggers:
        if not t.category:
            t.category = default_category
        t.id = f"plugin.{plugin_id}.{t.id}"
        if t.id in TRIGGER_BY_ID:
            raise ValueError(f"Duplicate trigger id \u201c{t.id}\u201d.")

    for t in triggers:
        TRIGGER_LIBRARY.append(t)
        TRIGGER_BY_ID[t.id] = t

    _plugin_registrations[plugin_id] = {"trigger_ids": [t.id for t in triggers]}


def unregister_triggers(plugin_id):
    """Removes every trigger kind a plugin registered"""
    reg = _plugin_registrations.pop(plugin_id, None)
    if reg is None:
        return
    ids = set(reg["trigger_ids"])
    TRIGGER_LIBRARY[:] = [t for t in TRIGGER_LIBRARY if t.id not in ids]
    for trigger_id in ids:
        TRIGGER_BY_ID.pop(trigger_id, None)


def registered_plugin_ids():
    return list(_plugin_registrations.keys())


def plugin_trigger_ids(plugin_id):
    reg = _plugin_registrations.get(plugin_id)
    return list(reg["trigger_ids"]) if reg else []


def get_trigger_type(trigger_id):
    return TRIGGER_BY_ID.get(trigger_id)


def all_trigger_types():
    return list(TRIGGER_LIBRARY)
