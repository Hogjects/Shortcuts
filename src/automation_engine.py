"""Background triggers for Automations
Polls system events and hands matching automations to a main thread callback"""
import glob
import subprocess
import threading
import time

from gi.repository import Gio, GLib

import system_actions
import trigger_library

POLL_INTERVAL = 5  # seconds between battery and network state checks
TIME_CHECK_INTERVAL = 20  # seconds between time of day checks


class AutomationEngine:
    def __init__(self, get_automations, on_fire):
        """get_automations is polled every tick
        on_fire runs on the GLib main loop when a trigger fires"""
        self._get_automations = get_automations
        self._on_fire = on_fire
        self._stop_event = threading.Event()
        self._fired_minute = {}  # automation uid to last fired minute to dedupe checks

    def start(self):
        for target in (self._time_loop, self._wifi_loop, self._bluetooth_loop,
                       self._battery_loop, self._sleep_wake_loop, self._plugin_trigger_loop):
            threading.Thread(target=target, daemon=True).start()
        GLib.idle_add(self._fire_startup_automations)

    def stop(self):
        self._stop_event.set()

    def _enabled(self, trigger_type):
        return [a for a in self._get_automations() if a.enabled and a.trigger_type == trigger_type]

    def _fire_startup_automations(self):
        for auto in self._enabled("startup"):
            self._maybe_fire(auto)
        return False

    def _maybe_fire(self, auto):
        GLib.idle_add(self._on_fire, auto)

    # Time of Day
    def _time_loop(self):
        while not self._stop_event.is_set():
            now = time.localtime()
            stamp = f"{now.tm_hour:02d}:{now.tm_min:02d}"
            for auto in self._enabled("time"):
                p = auto.trigger_params
                days = p.get("days") or []
                if days and now.tm_wday not in days:
                    continue
                if p.get("hour") == now.tm_hour and p.get("minute") == now.tm_min:
                    if self._fired_minute.get(auto.uid) != stamp:
                        self._fired_minute[auto.uid] = stamp
                        self._maybe_fire(auto)
            self._stop_event.wait(TIME_CHECK_INTERVAL)

    # WiFi
    def _active_ssids(self):
        try:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                capture_output=True, text=True, timeout=5).stdout
        except (subprocess.SubprocessError, OSError):
            return set()
        return {line.split(":", 1)[1] for line in out.splitlines() if line.startswith("yes:")}

    def _wifi_loop(self):
        if not system_actions.is_command_available("nmcli"):
            return
        state = self._active_ssids()
        while not self._stop_event.is_set():
            self._stop_event.wait(POLL_INTERVAL)
            current = self._active_ssids()
            self._fire_on_diff("wifi", "ssid", connected=current - state, disconnected=state - current)
            state = current

    # Bluetooth
    def _connected_bt_devices(self):
        try:
            out = subprocess.run(["bluetoothctl", "devices", "Connected"],
                                  capture_output=True, text=True, timeout=5).stdout
        except (subprocess.SubprocessError, OSError):
            return set()
        names = set()
        for line in out.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3:
                names.add(parts[2])
        return names

    def _bluetooth_loop(self):
        if not system_actions.is_command_available("bluetoothctl"):
            return
        state = self._connected_bt_devices()
        while not self._stop_event.is_set():
            self._stop_event.wait(POLL_INTERVAL)
            current = self._connected_bt_devices()
            self._fire_on_diff("bluetooth", "device", connected=current - state, disconnected=state - current)
            state = current

    def _fire_on_diff(self, trigger_type, name_key, connected, disconnected):
        for auto in self._enabled(trigger_type):
            p = auto.trigger_params
            target = p.get(name_key, "")
            changed = connected if p.get("event", "connects") == "connects" else disconnected
            if target:
                if target in changed:
                    self._maybe_fire(auto)
            elif changed:
                self._maybe_fire(auto)

    # Battery
    def _battery_path(self):
        paths = glob.glob("/sys/class/power_supply/BAT*")
        return paths[0] if paths else None

    def _battery_reading(self, base):
        try:
            with open(f"{base}/capacity") as f:
                percent = int(f.read().strip())
            with open(f"{base}/status") as f:
                status = f.read().strip()
            return percent, status in ("Charging", "Full")
        except (OSError, ValueError):
            return None, None

    def _battery_loop(self):
        base = self._battery_path()
        if base is None:
            return
        percent, charging = self._battery_reading(base)
        if percent is None:
            return
        while not self._stop_event.is_set():
            self._stop_event.wait(POLL_INTERVAL)
            new_percent, new_charging = self._battery_reading(base)
            if new_percent is None:
                continue
            for auto in self._enabled("battery"):
                p = auto.trigger_params
                cond = p.get("condition")
                threshold = p.get("percent", 20)
                if cond == "drops_below" and percent >= threshold > new_percent:
                    self._maybe_fire(auto)
                elif cond == "rises_above" and percent <= threshold < new_percent:
                    self._maybe_fire(auto)
                elif cond == "charger_connected" and not charging and new_charging:
                    self._maybe_fire(auto)
                elif cond == "charger_disconnected" and charging and not new_charging:
                    self._maybe_fire(auto)
            percent, charging = new_percent, new_charging

    # Sleep and wake
    def _sleep_wake_loop(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error:
            return

        def on_signal(_conn, _sender, _path, _iface, _signal, params, *_a):
            event = "sleeps" if params.unpack()[0] else "wakes"
            for auto in self._enabled("sleep_wake"):
                if auto.trigger_params.get("event") == event:
                    self._maybe_fire(auto)

        bus.signal_subscribe(
            "org.freedesktop.login1", "org.freedesktop.login1.Manager",
            "PrepareForSleep", "/org/freedesktop/login1", None,
            Gio.DBusSignalFlags.NONE, on_signal)

        # Keeps bus and its subscription alive for the app lifetime
        self._stop_event.wait()

    # Plugin triggers
    def _plugin_trigger_loop(self):
        """Generic polling for plugin triggers that define poll
        built in kinds have their own loops above"""
        states = {}  # automation uid to the last poll result
        while not self._stop_event.is_set():
            self._stop_event.wait(POLL_INTERVAL)
            for auto in self._get_automations():
                if not auto.enabled:
                    continue
                ttype = trigger_library.get_trigger_type(auto.trigger_type)
                if ttype is None or ttype.poll is None:
                    continue
                try:
                    fired, new_state = ttype.poll(states.get(auto.uid), auto.trigger_params)
                except Exception:
                    continue  # a bad plugin trigger must not kill the loop
                states[auto.uid] = new_state
                if fired:
                    self._maybe_fire(auto)
