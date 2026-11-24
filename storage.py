import json
import os

from models import ActionInstance, Automation, Shortcut

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "shortcuts-app")
STORE_PATH = os.path.join(CONFIG_DIR, "shortcuts.json")

DEFAULT_FOLDERS = ["Audio", "Display", "Session", "Power"]


def _starter_shortcuts():
    starters = [
        ("Volume Up", "system.volume_up", "audio-volume-high-symbolic", "tile-blue", "Audio"),
        ("Volume Down", "system.volume_down", "audio-volume-low-symbolic", "tile-blue", "Audio"),
        ("Mute", "system.mute", "audio-volume-muted-symbolic", "tile-blue", "Audio"),
        ("Brightness Up", "system.brightness_up", "display-brightness-symbolic", "tile-yellow", "Display"),
        ("Brightness Down", "system.brightness_down", "display-brightness-symbolic", "tile-yellow", "Display"),
        ("Lock Screen", "system.lock_screen", "system-lock-screen-symbolic", "tile-gray", "Session"),
        ("Sleep", "system.sleep", "weather-clear-night-symbolic", "tile-gray", "Session"),
        ("Log Out", "system.log_out", "system-log-out-symbolic", "tile-orange", "Power"),
        ("Restart", "system.restart", "system-reboot-symbolic", "tile-orange", "Power"),
        ("Shut Down", "system.shutdown", "system-shutdown-symbolic", "tile-red", "Power"),
    ]
    result = []
    for name, action_id, icon, color, folder in starters:
        result.append(Shortcut(name=name, steps=[ActionInstance(action_id=action_id)],
                                icon_name=icon, color_class=color, folder=folder))
    return result


def load():
    """Returns shortcuts and folders and automations"""
    if not os.path.exists(STORE_PATH):
        shortcuts = _starter_shortcuts()
        folders = list(DEFAULT_FOLDERS)
        automations = []
        save(shortcuts, folders, automations)
        return shortcuts, folders, automations

    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        shortcuts = [Shortcut.from_dict(d) for d in data.get("shortcuts", [])]
        folders = data.get("folders") or list(DEFAULT_FOLDERS)
        automations = [Automation.from_dict(d) for d in data.get("automations", [])]
        return shortcuts, folders, automations
    except (json.JSONDecodeError, KeyError, OSError):
        return _starter_shortcuts(), list(DEFAULT_FOLDERS), []


def save(shortcuts, folders, automations):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = {
        "shortcuts": [s.to_dict() for s in shortcuts],
        "folders": folders,
        "automations": [a.to_dict() for a in automations],
    }
    tmp_path = STORE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, STORE_PATH)
