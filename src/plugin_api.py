"""API for plugin entry files
A plugin defines ACTIONS and or TRIGGERS lists built with action and trigger"""
import shutil
import subprocess

import action_library
import trigger_library


def command_available(command):
    """True if command is found on PATH"""
    return shutil.which(command) is not None


def run_command(args, timeout=None):
    """Runs a command and returns stripped stdout
    raises RuntimeError if it is missing or times out or fails"""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"\u201c{args[0]}\u201d isn't installed or on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"\u201c{args[0]}\u201d timed out.") from exc
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or f"\u201c{args[0]}\u201d exited with status {result.returncode}"
        )
    return result.stdout.strip()


def run_background(args):
    """Starts a command without waiting for it
    raises RuntimeError if it cannot start"""
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise RuntimeError(f"\u201c{args[0]}\u201d isn't installed or on PATH.") from exc


def notify(title, message=""):
    """Best effort desktop notification that does nothing without notify-send"""
    if command_available("notify-send"):
        subprocess.run(["notify-send", title, message], check=False)


def param(key, label, type="text", default="", choices=None, placeholder="",
          min_value=-1000000, max_value=1000000):
    """One configurable action field of type text or number or bool or choice
    choices is a list or value label pairs or a callable"""
    return action_library.ParamSpec(
        key=key, label=label, type=type, default=default, choices=choices,
        placeholder=placeholder, min_value=min_value, max_value=max_value,
    )


def action(id, name, run, icon="application-x-addon-symbolic", color="tile-purple",
           category=None, params=None, control=None, required_command=None):
    """Describes one action for the library
    run receives params and ctx and returns the Previous Result or None"""
    return action_library.ActionType(
        id=id, name=name, category=category, icon_name=icon,
        color_class=color, params=params or [], control=control, run=run,
        required_command=required_command,
    )


def trigger(id, name, poll=None, icon="alarm-symbolic", color="tile-purple",
            category=None, params=None, describe=None):
    """Describes one automation trigger kind like action
    poll receives state and params and returns fired and new state"""
    return trigger_library.TriggerType(
        id=id, name=name, category=category, icon_name=icon,
        color_class=color, params=params or [], poll=poll, describe=describe,
    )
