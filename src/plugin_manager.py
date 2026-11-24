"""Installs and loads and manages plugins shipped as zip files
Plugin code runs with full app privileges and is not sandboxed"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Optional

import action_library
import trigger_library
from storage import CONFIG_DIR

PLUGINS_DIR = os.path.join(CONFIG_DIR, "plugins")
STATE_PATH = os.path.join(PLUGINS_DIR, "_state.json")

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_DEFAULT_CATEGORY_ICON = "sc-puzzle-symbolic"


class PluginError(Exception):
    """Anything wrong with a plugin zip or its manifest or code
    the message is shown to the user as is"""


@dataclass
class PluginInfo:
    id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    entry: str = "actions.py"
    category: Optional[str] = None
    enabled: bool = True
    action_count: int = 0
    trigger_count: int = 0


# Enabled state

def _load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state):
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, STATE_PATH)


def _plugin_dirs():
    if not os.path.isdir(PLUGINS_DIR):
        return []
    return sorted(
        d for d in os.listdir(PLUGINS_DIR)
        if os.path.isdir(os.path.join(PLUGINS_DIR, d)) and not d.startswith("_") and not d.startswith(".")
    )


# Manifest handling

def _read_manifest_file(plugin_dir):
    with open(os.path.join(plugin_dir, "manifest.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_manifest(manifest):
    """Returns plugin_id and name and version and entry
    raises PluginError for anything missing or malformed"""
    plugin_id = str(manifest.get("id", "")).strip()
    name = str(manifest.get("name", "")).strip()
    version = str(manifest.get("version", "")).strip()

    if not _ID_PATTERN.match(plugin_id):
        raise PluginError(
            "manifest.json's \u201cid\u201d must be 2-64 characters, lowercase "
            "letters/numbers/\u201c-\u201d/\u201c_\u201d only, e.g. \u201ckde-integration\u201d."
        )
    if not name:
        raise PluginError("manifest.json is missing a \u201cname\u201d.")
    if not version:
        raise PluginError("manifest.json is missing a \u201cversion\u201d.")

    entry = str(manifest.get("entry") or "actions.py")
    if "/" in entry or "\\" in entry or not entry.endswith(".py"):
        raise PluginError("manifest.json's \u201centry\u201d must be a plain .py filename.")

    return plugin_id, name, version, entry


def _info_from_manifest(plugin_id, name, version, entry, manifest, enabled, action_count, trigger_count=0):
    return PluginInfo(
        id=plugin_id, name=name, version=version,
        author=str(manifest.get("author", "")).strip(),
        description=str(manifest.get("description", "")).strip(),
        entry=entry, category=manifest.get("category") or None,
        enabled=enabled, action_count=action_count, trigger_count=trigger_count,
    )


def peek_manifest(zip_path):
    """Reads and validates manifest.json from a zip without extracting anything
    lets the caller preview an install before any plugin code runs"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            prefix = _find_root_prefix(names)
            with zf.open(f"{prefix}manifest.json") as f:
                manifest = json.load(f)
    except zipfile.BadZipFile as exc:
        raise PluginError("That file isn't a valid zip archive.") from exc
    except json.JSONDecodeError as exc:
        raise PluginError(f"manifest.json isn't valid JSON: {exc}") from exc

    plugin_id, name, version, entry = _validate_manifest(manifest)
    return _info_from_manifest(plugin_id, name, version, entry, manifest, enabled=True, action_count=0)


# Safe zip extraction

def _find_root_prefix(names):
    """Returns the zip root prefix as empty or a single top level folder
    raises otherwise"""
    if "manifest.json" in names:
        return ""
    top_folders = {n.split("/", 1)[0] for n in names if "/" in n}
    for folder in top_folders:
        if f"{folder}/manifest.json" in names:
            return f"{folder}/"
    raise PluginError("Couldn't find manifest.json at the zip's root (or one folder inside it).")


def _safe_extract(zf, names, prefix, dest_dir):
    """Copies members under prefix into dest_dir and refuses paths escaping it"""
    dest_root = os.path.realpath(dest_dir)
    to_extract = []
    for name in names:
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):]
        if not rel:
            continue
        target = os.path.realpath(os.path.join(dest_root, rel))
        if not (target == dest_root or target.startswith(dest_root + os.sep)):
            raise PluginError(f"Zip contains an unsafe path: \u201c{name}\u201d.")
        to_extract.append((name, target))

    for name, target in to_extract:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(name) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


# Loading plugin code

def _load_plugin_contributions(plugin_dir, plugin_id, entry, manifest):
    """Executes entry from plugin_dir and returns actions and triggers and category info
    plugin_dir is temporarily on sys.path for sibling imports"""
    entry_path = os.path.join(plugin_dir, entry)
    if not os.path.isfile(entry_path):
        raise PluginError(f"manifest.json points to \u201c{entry}\u201d, which isn't in the plugin.")

    module_name = f"shortcuts_plugin_{plugin_id}".replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    if spec is None or spec.loader is None:
        raise PluginError(f"Couldn't load \u201c{entry}\u201d.")
    module = importlib.util.module_from_spec(spec)

    sys.path.insert(0, plugin_dir)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginError(f"\u201c{entry}\u201d raised an error while loading: {exc}") from exc
    finally:
        sys.modules.pop(module_name, None)
        try:
            sys.path.remove(plugin_dir)
        except ValueError:
            pass

    actions = getattr(module, "ACTIONS", None) or []
    triggers = getattr(module, "TRIGGERS", None) or []
    if not isinstance(actions, list):
        raise PluginError(f"\u201c{entry}\u201d's ACTIONS must be a list.")
    if not isinstance(triggers, list):
        raise PluginError(f"\u201c{entry}\u201d's TRIGGERS must be a list.")
    if not actions and not triggers:
        raise PluginError(f"\u201c{entry}\u201d must define a non-empty ACTIONS and/or TRIGGERS list.")
    for a in actions:
        if not isinstance(a, action_library.ActionType):
            raise PluginError(f"\u201c{entry}\u201d's ACTIONS must be built with plugin_api.action(...).")
    for t in triggers:
        if not isinstance(t, trigger_library.TriggerType):
            raise PluginError(f"\u201c{entry}\u201d's TRIGGERS must be built with plugin_api.trigger(...).")

    category = manifest.get("category") or None
    category_icon = manifest.get("category_icon") or _DEFAULT_CATEGORY_ICON
    return actions, triggers, category, category_icon


# Public API

def list_installed():
    """PluginInfo for every installed plugin including ones that fail to load"""
    state = _load_state()
    actions_registered = set(action_library.registered_plugin_ids())
    triggers_registered = set(trigger_library.registered_plugin_ids())
    infos = []
    for plugin_id in _plugin_dirs():
        plugin_dir = os.path.join(PLUGINS_DIR, plugin_id)
        try:
            manifest = _read_manifest_file(plugin_dir)
            _, name, version, entry = _validate_manifest(manifest)
        except (OSError, json.JSONDecodeError, PluginError):
            manifest, name, version, entry = {}, plugin_id, "?", "actions.py"

        enabled = state.get(plugin_id, {}).get("enabled", True)
        action_count = len(action_library.plugin_action_ids(plugin_id)) if plugin_id in actions_registered else 0
        trigger_count = len(trigger_library.plugin_trigger_ids(plugin_id)) if plugin_id in triggers_registered else 0
        infos.append(_info_from_manifest(
            plugin_id, name, version, entry, manifest, enabled, action_count, trigger_count))

    infos.sort(key=lambda p: p.name.lower())
    return infos


def load_all_enabled():
    """Registers every enabled plugin at startup
    returns plugin_id and error pairs for plugins that failed and are skipped"""
    state = _load_state()
    errors = []
    for plugin_id in _plugin_dirs():
        if not state.get(plugin_id, {}).get("enabled", True):
            continue
        plugin_dir = os.path.join(PLUGINS_DIR, plugin_id)
        try:
            manifest = _read_manifest_file(plugin_dir)
            _, _name, _version, entry = _validate_manifest(manifest)
            actions, triggers, category, category_icon = _load_plugin_contributions(
                plugin_dir, plugin_id, entry, manifest)
            if actions:
                action_library.register_actions(plugin_id, actions, category=category, category_icon=category_icon)
            if triggers:
                trigger_library.register_triggers(plugin_id, triggers, category=category)
        except Exception as exc:  # noqa: BLE001
            errors.append((plugin_id, str(exc)))
    return errors


def install_from_zip(zip_path):
    """Validates and extracts and loads a plugin zip then persists it as enabled
    a broken update never replaces a working install"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            prefix = _find_root_prefix(names)
            with zf.open(f"{prefix}manifest.json") as f:
                manifest = json.load(f)
            plugin_id, name, version, entry = _validate_manifest(manifest)

            os.makedirs(PLUGINS_DIR, exist_ok=True)
            staging_dir = tempfile.mkdtemp(dir=PLUGINS_DIR, prefix=f".staging-{plugin_id}-")
            try:
                _safe_extract(zf, names, prefix, staging_dir)
                # Run from the staging copy so a broken plugin never touches the installed one
                actions, triggers, category, category_icon = _load_plugin_contributions(
                    staging_dir, plugin_id, entry, manifest)

                final_dir = os.path.join(PLUGINS_DIR, plugin_id)
                if plugin_id in action_library.registered_plugin_ids():
                    action_library.unregister_actions(plugin_id)
                if plugin_id in trigger_library.registered_plugin_ids():
                    trigger_library.unregister_triggers(plugin_id)
                if os.path.isdir(final_dir):
                    shutil.rmtree(final_dir)
                os.replace(staging_dir, final_dir)
            except Exception:
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise

            if actions:
                action_library.register_actions(plugin_id, actions, category=category, category_icon=category_icon)
            if triggers:
                trigger_library.register_triggers(plugin_id, triggers, category=category)
    except zipfile.BadZipFile as exc:
        raise PluginError("That file isn't a valid zip archive.") from exc
    except json.JSONDecodeError as exc:
        raise PluginError(f"manifest.json isn't valid JSON: {exc}") from exc

    state = _load_state()
    state[plugin_id] = {"enabled": True}
    _save_state(state)

    return _info_from_manifest(
        plugin_id, name, version, entry, manifest, enabled=True,
        action_count=len(actions), trigger_count=len(triggers))


def set_enabled(plugin_id, enabled):
    """Toggles a plugin and returns None or an error if enabling failed"""
    state = _load_state()
    state.setdefault(plugin_id, {})["enabled"] = enabled
    _save_state(state)

    if not enabled:
        action_library.unregister_actions(plugin_id)
        trigger_library.unregister_triggers(plugin_id)
        return None

    plugin_dir = os.path.join(PLUGINS_DIR, plugin_id)
    try:
        manifest = _read_manifest_file(plugin_dir)
        _, _name, _version, entry = _validate_manifest(manifest)
        actions, triggers, category, category_icon = _load_plugin_contributions(
            plugin_dir, plugin_id, entry, manifest)
        if actions:
            action_library.register_actions(plugin_id, actions, category=category, category_icon=category_icon)
        if triggers:
            trigger_library.register_triggers(plugin_id, triggers, category=category)
    except Exception as exc:
        state[plugin_id]["enabled"] = False
        _save_state(state)
        return str(exc)
    return None


def uninstall(plugin_id):
    if plugin_id in action_library.registered_plugin_ids():
        action_library.unregister_actions(plugin_id)
    if plugin_id in trigger_library.registered_plugin_ids():
        trigger_library.unregister_triggers(plugin_id)
    plugin_dir = os.path.join(PLUGINS_DIR, plugin_id)
    if os.path.isdir(plugin_dir):
        shutil.rmtree(plugin_dir)
    state = _load_state()
    state.pop(plugin_id, None)
    _save_state(state)
