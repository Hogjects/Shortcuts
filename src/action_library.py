import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from gi.repository import Gio, GLib

import system_actions
from models import ActionInstance, ParamValue


@dataclass
class ParamSpec:
    key: str
    label: str
    type: str = "text"  # text or number or bool or choice
    default: Any = ""
    choices: Any = None  # list of strings or value label pairs or a callable returning either
    placeholder: str = ""
    min_value: float = -1000000  # number type only and must match any clamping in run
    max_value: float = 1000000
    app_icons: bool = False  # "choice" type only: show each choice's installed-app icon


@dataclass
class ActionType:
    id: str
    name: str
    category: str
    icon_name: str
    color_class: str
    params: List[ParamSpec] = field(default_factory=list)
    control: Optional[str] = None  # if or repeat or none
    run: Optional[Callable] = None
    required_command: Optional[str] = None


# Sidebar categories in display order
# todo make dynamic
CATEGORIES = [
    ("System", "sc-gear-symbolic"),
    ("Scripting", "sc-terminal-symbolic"),
    ("Variables", "sc-variable-symbolic"),
    ("Logic", "sc-branch-symbolic"),
]


def _discover_installed_apps():
    found = {}
    for app_info in Gio.AppInfo.get_all():
        if not app_info.should_show():
            continue
        name = app_info.get_display_name() or app_info.get_name()
        if name and name not in found:
            found[name] = app_info
    return dict(sorted(found.items(), key=lambda kv: kv[0].lower()))


INSTALLED_APPS = _discover_installed_apps()


# Live shortcut registry for the Run Shortcut action
# main_window sets a provider once so lookups never go stale
_get_shortcuts = lambda: []  # noqa: E731


def set_shortcuts_provider(get_shortcuts):
    global _get_shortcuts
    _get_shortcuts = get_shortcuts


def _shortcut_choices():
    pairs = [(s.uid, s.name) for s in _get_shortcuts()]
    return pairs or [("", "No shortcuts yet")]


def get_shortcut_by_uid(uid):
    for s in _get_shortcuts():
        if s.uid == uid:
            return s
    return None


def _to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _sys_run(fn, required_command=None):
    def runner(params, ctx):
        if required_command and not system_actions.is_command_available(required_command):
            raise RuntimeError(f"\u201c{required_command}\u201d isn't installed or on PATH.")
        fn()
        return None
    return runner


def _sys_run_with_value(fn, extractor, required_command=None):
    def runner(params, ctx):
        if required_command and not system_actions.is_command_available(required_command):
            raise RuntimeError(f"\u201c{required_command}\u201d isn't installed or on PATH.")
        fn(extractor(params))
        return None
    return runner


def _run_shell(params, ctx):
    result = subprocess.run(params.get("command", ""), shell=True, capture_output=True, text=True)
    if result.returncode != 0 and result.stderr:
        raise RuntimeError(result.stderr.strip() or f"exited with status {result.returncode}")
    return result.stdout.strip()


def _delay(params, ctx):
    try:
        seconds = float(params.get("seconds") or 0)
    except (TypeError, ValueError):
        seconds = 0
    time.sleep(max(0.0, seconds))
    return None


def _open_app(params, ctx):
    name = params.get("app", "")
    app_info = INSTALLED_APPS.get(name)
    if app_info is None:
        raise RuntimeError(f"App \u201c{name}\u201d wasn't found on this system.")
    try:
        launched = app_info.launch()
    except GLib.Error as exc:
        raise RuntimeError(str(exc)) from exc
    if not launched:
        raise RuntimeError(f"Failed to launch \u201c{name}\u201d.")
    return None


def _open_url(params, ctx):
    if not system_actions.is_command_available("xdg-open"):
        raise RuntimeError("\u201cxdg-open\u201d isn't installed or on PATH.")
    subprocess.Popen(["xdg-open", params.get("url", "")])
    return None


def _notify(params, ctx):
    if not system_actions.is_command_available("notify-send"):
        raise RuntimeError("\u201cnotify-send\u201d isn't installed or on PATH.")
    subprocess.run(["notify-send", params.get("title", ""), params.get("message", "")])
    return None


def _run_shortcut_step(params, ctx):
    import run_engine  # local import to avoid a cycle with run_engine

    target_uid = params.get("shortcut", "")
    target = get_shortcut_by_uid(target_uid)
    if target is None:
        raise RuntimeError("No shortcut selected, or it no longer exists.")
    if target_uid in ctx.call_stack:
        raise RuntimeError(f"\u201c{target.name}\u201d can't run itself (circular reference).")

    nested = run_engine.RunContext(ask_text=ctx.ask_text)
    nested.log = ctx.log
    nested.call_stack = ctx.call_stack
    run_engine.run_shortcut(target, nested)
    return nested.previous_result


def _comment(params, ctx):
    return None


def _text(params, ctx):
    return params.get("text", "")


def _set_variable(params, ctx):
    name = (params.get("name") or "").strip() or "Variable"
    value = params.get("value", "")
    ctx.variables[name] = value
    return value


def _ask_text(params, ctx):
    if ctx.ask_text is None:
        return params.get("default", "")
    return ctx.ask_text(params.get("prompt", "Input"), params.get("default", ""))


ACTION_LIBRARY = [
    # System
    ActionType("system.volume_up", "Volume Up", "System", "sc-volume-up-symbolic", "tile-blue",
               run=_sys_run(system_actions.volume_up, "pactl"), required_command="pactl"),
    ActionType("system.volume_down", "Volume Down", "System", "sc-volume-down-symbolic", "tile-blue",
               run=_sys_run(system_actions.volume_down, "pactl"), required_command="pactl"),
    ActionType("system.mute", "Mute", "System", "sc-volume-mute-symbolic", "tile-blue",
               run=_sys_run(system_actions.toggle_mute, "pactl"), required_command="pactl"),
    ActionType("system.brightness_up", "Brightness Up", "System", "sc-brightness-up-symbolic", "tile-yellow",
               run=_sys_run(system_actions.brightness_up, "brightnessctl"), required_command="brightnessctl"),
    ActionType("system.brightness_down", "Brightness Down", "System", "sc-brightness-down-symbolic", "tile-yellow",
               run=_sys_run(system_actions.brightness_down, "brightnessctl"), required_command="brightnessctl"),
    ActionType("system.lock_screen", "Lock Screen", "System", "sc-lock-symbolic", "tile-gray",
               run=_sys_run(system_actions.lock_screen, "loginctl"), required_command="loginctl"),
    ActionType("system.sleep", "Sleep", "System", "sc-sleep-symbolic", "tile-gray",
               run=_sys_run(system_actions.suspend, "systemctl"), required_command="systemctl"),
    ActionType("system.log_out", "Log Out", "System", "sc-log-out-symbolic", "tile-orange",
               run=_sys_run(system_actions.log_out, "loginctl"), required_command="loginctl"),
    ActionType("system.restart", "Restart", "System", "sc-restart-symbolic", "tile-orange",
               run=_sys_run(system_actions.restart, "systemctl"), required_command="systemctl"),
    ActionType("system.shutdown", "Shut Down", "System", "sc-power-symbolic", "tile-red",
               run=_sys_run(system_actions.shutdown, "systemctl"), required_command="systemctl"),

    # System audio
    ActionType("system.unmute", "Unmute", "System", "sc-volume-unmute-symbolic", "tile-blue",
               run=_sys_run(system_actions.unmute, "pactl"), required_command="pactl"),
    ActionType("system.set_volume", "Set Volume", "System", "sc-volume-set-symbolic", "tile-blue",
               params=[ParamSpec("percent", "Percent", "number", 50, min_value=0, max_value=100)],
               run=_sys_run_with_value(
                   system_actions.set_volume,
                   lambda p: max(0, min(100, _to_int(p.get("percent"), 50))),
                   "pactl"),
               required_command="pactl"),
    ActionType("system.adjust_volume", "Adjust Volume", "System", "sc-volume-adjust-symbolic", "tile-blue",
               params=[ParamSpec("percent", "Percent \u00b1", "number", 10)],
               run=_sys_run_with_value(
                   system_actions.adjust_volume,
                   lambda p: _to_int(p.get("percent"), 10),
                   "pactl"),
               required_command="pactl"),
    ActionType("system.restart_audio", "Restart Audio Service", "System", "sc-audio-restart-symbolic", "tile-blue",
               run=_sys_run(system_actions.restart_audio, "systemctl"), required_command="systemctl"),

    # System microphone
    ActionType("system.mic_toggle_mute", "Toggle Mic Mute", "System", "sc-mic-toggle-symbolic", "tile-blue",
               run=_sys_run(system_actions.toggle_mic_mute, "pactl"), required_command="pactl"),
    ActionType("system.mic_mute", "Mute Microphone", "System", "sc-mic-mute-symbolic", "tile-blue",
               run=_sys_run(system_actions.mic_mute, "pactl"), required_command="pactl"),
    ActionType("system.mic_unmute", "Unmute Microphone", "System", "sc-mic-symbolic", "tile-blue",
               run=_sys_run(system_actions.mic_unmute, "pactl"), required_command="pactl"),
    ActionType("system.set_mic_volume", "Set Microphone Volume", "System", "sc-mic-set-symbolic", "tile-blue",
               params=[ParamSpec("percent", "Percent", "number", 50, min_value=0, max_value=100)],
               run=_sys_run_with_value(
                   system_actions.set_mic_volume,
                   lambda p: max(0, min(100, _to_int(p.get("percent"), 50))),
                   "pactl"),
               required_command="pactl"),
    ActionType("system.adjust_mic_volume", "Adjust Microphone Volume", "System", "sc-mic-adjust-symbolic", "tile-blue",
               params=[ParamSpec("percent", "Percent \u00b1", "number", 10)],
               run=_sys_run_with_value(
                   system_actions.adjust_mic_volume,
                   lambda p: _to_int(p.get("percent"), 10),
                   "pactl"),
               required_command="pactl"),

    # System media playback
    ActionType("system.media_play_pause", "Play/Pause Media", "System", "sc-play-pause-symbolic", "tile-teal",
               run=_sys_run(system_actions.media_play_pause, "playerctl"), required_command="playerctl"),
    ActionType("system.media_next", "Next Track", "System", "sc-next-symbolic", "tile-teal",
               run=_sys_run(system_actions.media_next, "playerctl"), required_command="playerctl"),
    ActionType("system.media_previous", "Previous Track", "System", "sc-previous-symbolic", "tile-teal",
               run=_sys_run(system_actions.media_previous, "playerctl"), required_command="playerctl"),
    ActionType("system.media_stop", "Stop Media", "System", "sc-stop-symbolic", "tile-teal",
               run=_sys_run(system_actions.media_stop, "playerctl"), required_command="playerctl"),

    # System display
    ActionType("system.set_brightness", "Set Brightness", "System", "sc-brightness-set-symbolic", "tile-yellow",
               params=[ParamSpec("percent", "Percent", "number", 50, min_value=0, max_value=100)],
               run=_sys_run_with_value(
                   system_actions.set_brightness,
                   lambda p: max(0, min(100, _to_int(p.get("percent"), 50))),
                   "brightnessctl"),
               required_command="brightnessctl"),
    ActionType("system.adjust_brightness", "Adjust Brightness", "System", "sc-brightness-adjust-symbolic", "tile-yellow",
               params=[ParamSpec("percent", "Percent \u00b1", "number", 10)],
               run=_sys_run_with_value(
                   system_actions.adjust_brightness,
                   lambda p: _to_int(p.get("percent"), 10),
                   "brightnessctl"),
               required_command="brightnessctl"),
    ActionType("system.screen_off", "Turn Off Screen", "System", "sc-screen-off-symbolic", "tile-yellow",
               run=_sys_run(system_actions.screen_off, "xset"), required_command="xset"),
    ActionType("system.screen_on", "Turn On Screen", "System", "sc-screen-on-symbolic", "tile-yellow",
               run=_sys_run(system_actions.screen_on, "xset"), required_command="xset"),

    # System network
    ActionType("system.wifi_on", "Wi-Fi On", "System", "sc-wifi-symbolic", "tile-purple",
               run=_sys_run(system_actions.wifi_on, "nmcli"), required_command="nmcli"),
    ActionType("system.wifi_off", "Wi-Fi Off", "System", "sc-wifi-off-symbolic", "tile-purple",
               run=_sys_run(system_actions.wifi_off, "nmcli"), required_command="nmcli"),
    ActionType("system.airplane_mode_on", "Airplane Mode On", "System", "sc-airplane-symbolic", "tile-purple",
               run=_sys_run(system_actions.airplane_mode_on, "nmcli"), required_command="nmcli"),
    ActionType("system.airplane_mode_off", "Airplane Mode Off", "System", "sc-airplane-off-symbolic", "tile-purple",
               run=_sys_run(system_actions.airplane_mode_off, "nmcli"), required_command="nmcli"),

    # System bluetooth
    ActionType("system.bluetooth_on", "Bluetooth On", "System", "sc-bluetooth-symbolic", "tile-purple",
               run=_sys_run(system_actions.bluetooth_on, "rfkill"), required_command="rfkill"),
    ActionType("system.bluetooth_off", "Bluetooth Off", "System", "sc-bluetooth-off-symbolic", "tile-purple",
               run=_sys_run(system_actions.bluetooth_off, "rfkill"), required_command="rfkill"),

    # System power
    ActionType("system.hibernate", "Hibernate", "System", "sc-hibernate-symbolic", "tile-gray",
               run=_sys_run(system_actions.hibernate, "systemctl"), required_command="systemctl"),
    ActionType("system.hybrid_sleep", "Hybrid Sleep", "System", "sc-hybrid-sleep-symbolic", "tile-gray",
               run=_sys_run(system_actions.hybrid_sleep, "systemctl"), required_command="systemctl"),

    # System screenshots
    ActionType("system.screenshot_full", "Take Screenshot", "System", "sc-screenshot-full-symbolic", "tile-teal",
               run=_sys_run(system_actions.screenshot_full, "gnome-screenshot"), required_command="gnome-screenshot"),
    ActionType("system.screenshot_window", "Screenshot Window", "System", "sc-screenshot-window-symbolic", "tile-teal",
               run=_sys_run(system_actions.screenshot_window, "gnome-screenshot"), required_command="gnome-screenshot"),
    ActionType("system.screenshot_area", "Screenshot Area", "System", "sc-screenshot-area-symbolic", "tile-teal",
               run=_sys_run(system_actions.screenshot_area, "gnome-screenshot"), required_command="gnome-screenshot"),
    ActionType("system.screenshot_clipboard", "Screenshot to Clipboard", "System", "sc-screenshot-clipboard-symbolic", "tile-teal",
               run=_sys_run(system_actions.screenshot_to_clipboard, "gnome-screenshot"), required_command="gnome-screenshot"),

    # System clipboard
    ActionType("system.clear_clipboard", "Clear Clipboard", "System", "sc-clipboard-clear-symbolic", "tile-teal",
               run=_sys_run(system_actions.clear_clipboard, "wl-copy"), required_command="wl-copy"),

    # System maintenance
    ActionType("system.empty_trash", "Empty Trash", "System", "sc-trash-symbolic", "tile-gray",
               run=_sys_run(system_actions.empty_trash, "gio"), required_command="gio"),
    ActionType("system.flush_dns", "Flush DNS Cache", "System", "sc-server-symbolic", "tile-gray",
               run=_sys_run(system_actions.flush_dns_cache, "resolvectl"), required_command="resolvectl"),

    # System notifications
    ActionType("system.dnd_on", "Enable Do Not Disturb", "System", "sc-dnd-symbolic", "tile-gray",
               run=_sys_run(system_actions.enable_do_not_disturb, "gsettings"), required_command="gsettings"),
    ActionType("system.dnd_off", "Disable Do Not Disturb", "System", "sc-bell-symbolic", "tile-gray",
               run=_sys_run(system_actions.disable_do_not_disturb, "gsettings"), required_command="gsettings"),

    # System appearance
    ActionType("system.dark_mode_on", "Enable Dark Mode", "System", "sc-moon-symbolic", "tile-yellow",
               run=_sys_run(system_actions.enable_dark_mode, "gsettings"), required_command="gsettings"),
    ActionType("system.dark_mode_off", "Disable Dark Mode", "System", "sc-sun-symbolic", "tile-yellow",
               run=_sys_run(system_actions.disable_dark_mode, "gsettings"), required_command="gsettings"),

    # Scripting
    ActionType("script.run_shell", "Run Shell Script", "Scripting", "sc-terminal-symbolic", "tile-purple",
               params=[ParamSpec("command", "Script", "text", "", placeholder="echo hello")],
               run=_run_shell),
    ActionType("script.delay", "Wait", "Scripting", "sc-hourglass-symbolic", "tile-purple",
               params=[ParamSpec("seconds", "Seconds", "number", 1, min_value=0)],
               run=_delay),
    ActionType("script.open_app", "Open App", "Scripting", "sc-apps-symbolic", "tile-purple",
               params=[ParamSpec("app", "App", "choice",
                                  next(iter(INSTALLED_APPS), ""),
                                  choices=list(INSTALLED_APPS.keys()) or [""],
                                  app_icons=True)],
               run=_open_app),
    ActionType("script.open_url", "Open URL", "Scripting", "sc-globe-symbolic", "tile-purple",
               params=[ParamSpec("url", "URL", "text", "", placeholder="https://example.com")],
               run=_open_url, required_command="xdg-open"),
    ActionType("script.notify", "Show Notification", "Scripting", "sc-notify-symbolic", "tile-purple",
               params=[ParamSpec("title", "Title", "text", "Shortcuts"), ParamSpec("message", "Message", "text", "")],
               run=_notify, required_command="notify-send"),
    ActionType("script.run_shortcut", "Run Shortcut", "Scripting", "sc-run-symbolic", "tile-purple",
               params=[ParamSpec("shortcut", "Shortcut", "choice", "", choices=_shortcut_choices)],
               run=_run_shortcut_step),
    ActionType("script.comment", "Comment", "Scripting", "sc-comment-symbolic", "tile-purple",
               params=[ParamSpec("text", "Comment", "text", "")],
               run=_comment),

    # Variables
    ActionType("var.text", "Text", "Variables", "sc-text-symbolic", "tile-teal",
               params=[ParamSpec("text", "Text", "text", "")],
               run=_text),
    ActionType("var.set", "Set Variable", "Variables", "sc-variable-symbolic", "tile-teal",
               params=[ParamSpec("name", "Name", "text", "Variable"), ParamSpec("value", "Value", "text", "")],
               run=_set_variable),
    ActionType("var.ask", "Ask for Text", "Variables", "sc-ask-symbolic", "tile-teal",
               params=[ParamSpec("prompt", "Prompt", "text", "Input"), ParamSpec("default", "Default answer", "text", "")],
               run=_ask_text),

    # Logic
    ActionType("logic.if", "If", "Logic", "sc-repeat-symbolic", "tile-orange",
               params=[
                   ParamSpec("left", "Input", "text", ""),
                   ParamSpec("operator", "Condition", "choice", "is",
                             choices=["is", "is not", "contains", "is greater than", "is less than"]),
                   ParamSpec("right", "Value", "text", ""),
               ],
               control="if"),
    ActionType("logic.repeat", "Repeat", "Logic", "sc-repeat-symbolic", "tile-orange",
               params=[ParamSpec("count", "Times", "number", 2, min_value=0)],
               control="repeat"),
]

ACTION_BY_ID = {a.id: a for a in ACTION_LIBRARY}


# Plugins
# register_actions is the only way to add actions from outside this module
_DEFAULT_PLUGIN_CATEGORY_ICON = "sc-puzzle-symbolic"
_plugin_registrations = {}  # plugin id to its action ids and categories


def register_actions(plugin_id, actions, category=None, category_icon=_DEFAULT_PLUGIN_CATEGORY_ICON):
    """Registers actions for a plugin under namespaced ids
    raises ValueError if the plugin id is already registered"""
    if plugin_id in _plugin_registrations:
        raise ValueError(f"Plugin \u201c{plugin_id}\u201d is already registered.")

    default_category = category or "Plugin"
    for a in actions:
        if not a.category:
            a.category = default_category
        a.id = f"plugin.{plugin_id}.{a.id}"
        if a.id in ACTION_BY_ID:
            raise ValueError(f"Duplicate action id \u201c{a.id}\u201d.")

    existing = dict(CATEGORIES)
    for cat_name in sorted({a.category for a in actions}):
        if cat_name not in existing:
            icon = category_icon if cat_name == default_category else _DEFAULT_PLUGIN_CATEGORY_ICON
            CATEGORIES.append((cat_name, icon))

    for a in actions:
        ACTION_LIBRARY.append(a)
        ACTION_BY_ID[a.id] = a

    _plugin_registrations[plugin_id] = {
        "action_ids": [a.id for a in actions],
        "categories": sorted({a.category for a in actions}),
    }


def unregister_actions(plugin_id):
    """Removes all actions a plugin registered and any category rows left empty"""
    reg = _plugin_registrations.pop(plugin_id, None)
    if reg is None:
        return

    ids = set(reg["action_ids"])
    ACTION_LIBRARY[:] = [a for a in ACTION_LIBRARY if a.id not in ids]
    for action_id in ids:
        ACTION_BY_ID.pop(action_id, None)

    remaining_categories = {a.category for a in ACTION_LIBRARY}
    for cat_name in reg["categories"]:
        if cat_name not in remaining_categories:
            CATEGORIES[:] = [(name, icon) for name, icon in CATEGORIES if name != cat_name]


def registered_plugin_ids():
    return list(_plugin_registrations.keys())


def plugin_action_ids(plugin_id):
    reg = _plugin_registrations.get(plugin_id)
    return list(reg["action_ids"]) if reg else []


def get_action_type(action_id):
    return ACTION_BY_ID.get(action_id)


def find_unavailable_step(steps):
    """First step in any branch with a missing required command or None"""
    for step in steps:
        action_type = get_action_type(step.action_id)
        if action_type is not None and action_type.required_command and \
                not system_actions.is_command_available(action_type.required_command):
            return action_type
        for branch in (step.then_steps, step.else_steps, step.body_steps):
            found = find_unavailable_step(branch)
            if found is not None:
                return found
    return None


def search_actions(query):
    q = query.strip().lower()
    if not q:
        return ACTION_LIBRARY
    return [a for a in ACTION_LIBRARY if q in a.name.lower() or q in a.category.lower()]


def make_instance(action_id):
    """Fresh ActionInstance for action_id with default params"""
    action_type = get_action_type(action_id)
    params = {spec.key: ParamValue.literal(spec.default) for spec in action_type.params}
    return ActionInstance(action_id=action_id, params=params)
