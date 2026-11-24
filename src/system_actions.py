import os
import shutil
import subprocess


def is_command_available(command):
    """True if command is found on PATH"""
    return shutil.which(command) is not None


def _run(command):
    subprocess.run(command, check=True)


def volume_up():
    _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"])


def volume_down():
    _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"])


def toggle_mute():
    _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])


def brightness_up():
    _run(["brightnessctl", "set", "+5%"])


def brightness_down():
    _run(["brightnessctl", "set", "5%-"])


def lock_screen():
    _run(["loginctl", "lock-session"])


def suspend():
    _run(["systemctl", "suspend"])


def log_out():
    session_id = os.environ.get("XDG_SESSION_ID")
    if not session_id:
        raise RuntimeError("XDG_SESSION_ID not set; cannot determine session")
    _run(["loginctl", "terminate-session", session_id])


def restart():
    _run(["systemctl", "reboot"])


def shutdown():
    _run(["systemctl", "poweroff"])


# Audio

def unmute():
    _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])


def set_volume(percent):
    _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])


def adjust_volume(percent):
    sign = "+" if percent >= 0 else "-"
    _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{abs(percent)}%"])


def restart_audio():
    _run(["systemctl", "--user", "restart", "pipewire", "pipewire-pulse"])


# Microphone

def toggle_mic_mute():
    _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"])


def mic_mute():
    _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"])


def mic_unmute():
    _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"])


def set_mic_volume(percent):
    _run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{percent}%"])


def adjust_mic_volume(percent):
    sign = "+" if percent >= 0 else "-"
    _run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{sign}{abs(percent)}%"])


# Media playback

def media_play_pause():
    _run(["playerctl", "play-pause"])


def media_next():
    _run(["playerctl", "next"])


def media_previous():
    _run(["playerctl", "previous"])


def media_stop():
    _run(["playerctl", "stop"])


# Display

def set_brightness(percent):
    _run(["brightnessctl", "set", f"{percent}%"])


def adjust_brightness(percent):
    sign = "+" if percent >= 0 else "-"
    _run(["brightnessctl", "set", f"{abs(percent)}%{sign}"])


def screen_off():
    _run(["xset", "dpms", "force", "off"])


def screen_on():
    _run(["xset", "dpms", "force", "on"])


# Network

def wifi_on():
    _run(["nmcli", "radio", "wifi", "on"])


def wifi_off():
    _run(["nmcli", "radio", "wifi", "off"])


def airplane_mode_on():
    _run(["nmcli", "radio", "all", "off"])


def airplane_mode_off():
    _run(["nmcli", "radio", "all", "on"])


# Bluetooth

def bluetooth_on():
    _run(["rfkill", "unblock", "bluetooth"])


def bluetooth_off():
    _run(["rfkill", "block", "bluetooth"])


# Power

def hibernate():
    _run(["systemctl", "hibernate"])


def hybrid_sleep():
    _run(["systemctl", "hybrid-sleep"])


# Screenshots

def screenshot_full():
    _run(["gnome-screenshot"])


def screenshot_window():
    _run(["gnome-screenshot", "-w"])


def screenshot_area():
    _run(["gnome-screenshot", "-a"])


def screenshot_to_clipboard():
    _run(["gnome-screenshot", "-c"])


# Clipboard

def clear_clipboard():
    _run(["wl-copy", "--clear"])


# Maintenance

def empty_trash():
    _run(["gio", "trash", "--empty"])


def flush_dns_cache():
    _run(["resolvectl", "flush-caches"])


# Notifications

def enable_do_not_disturb():
    _run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "false"])


def disable_do_not_disturb():
    _run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "true"])


# Appearance

def enable_dark_mode():
    _run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-dark"])


def disable_dark_mode():
    _run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-light"])


# Automation trigger pickers

def list_known_wifi_networks():
    """Saved WiFi connection names for the automation trigger network picker"""
    if not is_command_available("nmcli"):
        return []
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
            capture_output=True, text=True, timeout=5, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    names = []
    for line in out.splitlines():
        name, _, conn_type = line.rpartition(":")
        if conn_type == "802-11-wireless" and name:
            names.append(name)
    return names


def list_paired_bluetooth_devices():
    """Paired Bluetooth device names for the automation trigger device picker"""
    if not is_command_available("bluetoothctl"):
        return []
    try:
        out = subprocess.run(["bluetoothctl", "devices", "Paired"],
                              capture_output=True, text=True, timeout=5, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    names = []
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3:
            names.append(parts[2])
    return names


# Background notifications

def notify(title, message=""):
    """Best effort desktop notification that does nothing without notify-send"""
    if not is_command_available("notify-send"):
        return
    subprocess.run(["notify-send", title, message], check=False)
