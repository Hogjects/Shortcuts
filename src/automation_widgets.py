"""Widgets for editing an Automation trigger
Shown as one step card styled block with a Change chip and a picker popover"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

import icons
import system_actions
import trigger_library

TRIGGER_KINDS = [
    ("time", "Time of Day"),
    ("wifi", "Wi-Fi Network"),
    ("bluetooth", "Bluetooth Device"),
    ("battery", "Battery Level"),
    ("sleep_wake", "Sleep / Wake"),
    ("startup", "App Startup"),
]

TRIGGER_ICONS = {
    "time": "sc-alarm-symbolic",
    "wifi": "sc-wifi-symbolic",
    "bluetooth": "sc-bluetooth-symbolic",
    "battery": "sc-battery-symbolic",
    "sleep_wake": "sc-sleep-wake-symbolic",
    "startup": "sc-startup-symbolic",
}

TRIGGER_COLORS = {
    "time": "tile-purple",
    "wifi": "tile-blue",
    "bluetooth": "tile-blue",
    "battery": "tile-yellow",
    "sleep_wake": "tile-gray",
    "startup": "tile-teal",
}

DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _to_12h(hour24):
    """12h hour and AM or PM for a 24h value"""
    return (hour24 % 12 or 12), ("AM" if hour24 < 12 else "PM")


def _to_24h(hour12, period):
    """24h hour for a 12h hour and AM or PM"""
    return (hour12 % 12) + (12 if period == "PM" else 0)


def trigger_icon_name(trigger_type):
    """Icon name for a trigger type"""
    if trigger_type in TRIGGER_ICONS:
        return TRIGGER_ICONS[trigger_type]
    ttype = trigger_library.get_trigger_type(trigger_type)
    return ttype.icon_name if ttype else "sc-startup-symbolic"


def trigger_color_class(trigger_type):
    """Tile color class for a trigger type"""
    if trigger_type in TRIGGER_COLORS:
        return TRIGGER_COLORS[trigger_type]
    ttype = trigger_library.get_trigger_type(trigger_type)
    return ttype.color_class if ttype else "tile-gray"


def _trigger_display_name(trigger_type):
    if trigger_type in dict(TRIGGER_KINDS):
        return dict(TRIGGER_KINDS)[trigger_type]
    ttype = trigger_library.get_trigger_type(trigger_type)
    return ttype.name if ttype else "Trigger"


def _build_trigger_block_row(kind_id, kind_name, icon_name, color_class, on_choose):
    """One clickable trigger block in the picker popover
    styled like an action library row"""
    row = Gtk.Button()
    row.set_has_frame(False)
    row.add_css_class("library-row")

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box.set_margin_top(5)
    box.set_margin_bottom(5)
    box.set_margin_start(6)
    box.set_margin_end(6)

    swatch = Gtk.CenterBox()  # centres the icon in the fixed-size square without expanding
    swatch.add_css_class("library-row-swatch")
    swatch.add_css_class(color_class)
    swatch.set_halign(Gtk.Align.START)
    swatch.set_hexpand(False)
    swatch.set_valign(Gtk.Align.CENTER)
    icon = icons.image(icon_name, 15)
    icon.set_halign(Gtk.Align.CENTER)
    icon.set_valign(Gtk.Align.CENTER)
    swatch.set_center_widget(icon)
    box.append(swatch)

    label = Gtk.Label(label=kind_name)
    label.set_xalign(0.0)
    label.set_hexpand(True)
    box.append(label)

    row.set_child(box)
    row.connect("clicked", lambda b: on_choose(kind_id))
    return row


def _show_trigger_picker(anchor_widget, on_choose):
    """Popover listing every trigger kind with built ins first then plugin ones"""
    popover = Gtk.Popover()
    popover.set_parent(anchor_widget)
    popover.set_autohide(True)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    box.set_margin_top(6)
    box.set_margin_bottom(6)
    box.set_margin_start(6)
    box.set_margin_end(6)

    def choose(kind_id):
        popover.popdown()
        on_choose(kind_id)

    for kind_id, kind_name in TRIGGER_KINDS:
        box.append(_build_trigger_block_row(
            kind_id, kind_name, TRIGGER_ICONS[kind_id], TRIGGER_COLORS[kind_id], choose))

    plugin_triggers = trigger_library.all_trigger_types()
    if plugin_triggers:
        divider = Gtk.Label(label="FROM PLUGINS")
        divider.add_css_class("sidebar-section-label")
        divider.set_xalign(0.0)
        box.append(divider)
        for ttype in plugin_triggers:
            box.append(_build_trigger_block_row(ttype.id, ttype.name, ttype.icon_name, ttype.color_class, choose))

    popover.set_child(box)
    popover.popup()


def _build_trigger_header(automation, on_kind_chosen):
    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

    icon = icons.image(trigger_icon_name(automation.trigger_type), 16)
    header.append(icon)

    name = Gtk.Label(label=f"When {_trigger_display_name(automation.trigger_type)}")
    name.add_css_class("step-title")
    name.set_xalign(0.0)
    name.set_hexpand(True)
    header.append(name)

    change_btn = Gtk.Button(label="Change")
    change_btn.set_has_frame(False)
    change_btn.add_css_class("variable-chip")
    change_btn.set_tooltip_text("Change what starts this automation")
    change_btn.connect("clicked", lambda b: _show_trigger_picker(b, on_kind_chosen))
    header.append(change_btn)

    return header


def build_trigger_section(automation, on_changed):
    """The trigger shown as one step card styled block
    with a Change chip and its own param controls underneath"""
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    card.add_css_class("step-card")

    def rebuild_card():
        child = card.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            card.remove(child)
            child = nxt
        for css_class in list(card.get_css_classes()):
            if css_class.startswith("tile-"):
                card.remove_css_class(css_class)
        card.add_css_class(trigger_color_class(automation.trigger_type))

        card.append(_build_trigger_header(automation, on_kind_chosen))

        params_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.append(params_box)
        builder = _PARAM_BUILDERS.get(automation.trigger_type)
        if builder:
            builder(params_box, automation, on_changed)
        else:
            ttype = trigger_library.get_trigger_type(automation.trigger_type)
            if ttype is not None:
                _build_plugin_trigger_params(params_box, automation, on_changed, ttype)

    def on_kind_chosen(kind_id):
        if kind_id == automation.trigger_type:
            return
        automation.trigger_type = kind_id
        automation.trigger_params = {}
        rebuild_card()
        on_changed()

    rebuild_card()
    return card


def _labeled_row(text, widget):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("param-row")
    label = Gtk.Label(label=text)
    label.add_css_class("param-label")
    label.set_size_request(90, -1)
    label.set_xalign(0.0)
    row.append(label)
    row.append(widget)
    return row


def _build_generic_field(spec, get_value, set_value, on_changed):
    """Control for one plugin trigger ParamSpec bound directly to a plain value"""
    if spec.type == "number":
        adjustment = Gtk.Adjustment(lower=spec.min_value, upper=spec.max_value, step_increment=1)
        widget = Gtk.SpinButton(adjustment=adjustment, climb_rate=1, digits=0)
        try:
            widget.set_value(float(get_value()))
        except (TypeError, ValueError):
            widget.set_value(0)
        widget.connect("value-changed", lambda w: (set_value(w.get_value()), on_changed()))
        return widget

    if spec.type == "bool":
        widget = Gtk.Switch()
        widget.set_valign(Gtk.Align.CENTER)
        widget.set_active(bool(get_value()))
        widget.connect("notify::active", lambda w, p: (set_value(w.get_active()), on_changed()))
        return widget

    if spec.type == "choice":
        raw_choices = spec.choices() if callable(spec.choices) else (spec.choices or [])
        pairs = [(c, c) if isinstance(c, str) else tuple(c) for c in raw_choices] or [("", "")]
        values = [v for v, _ in pairs]
        labels = [l for _, l in pairs]
        widget = Gtk.DropDown(model=Gtk.StringList.new(labels))
        current = get_value()
        widget.set_selected(values.index(current) if current in values else 0)
        widget.connect("notify::selected", lambda w, p: (set_value(values[w.get_selected()]), on_changed()))
        return widget

    widget = Gtk.Entry()
    widget.set_text(str(get_value()))
    if spec.placeholder:
        widget.set_placeholder_text(spec.placeholder)
    widget.connect("changed", lambda w: (set_value(w.get_text()), on_changed()))
    return widget


def _build_plugin_trigger_params(box, automation, on_changed, trigger_type):
    """Renders plugin trigger params as step card fields bound to automation.trigger_params"""
    p = automation.trigger_params
    for spec in trigger_type.params:
        p.setdefault(spec.key, spec.default)
        widget = _build_generic_field(
            spec,
            get_value=lambda spec=spec: p.get(spec.key, spec.default),
            set_value=lambda value, spec=spec: p.__setitem__(spec.key, value),
            on_changed=on_changed,
        )
        box.append(_labeled_row(spec.label, widget))


def _build_time_params(box, automation, on_changed):
    p = automation.trigger_params
    p.setdefault("hour", 9)
    p.setdefault("minute", 0)
    p.setdefault("days", [])

    hour12, period = _to_12h(p["hour"])

    hour_adj = Gtk.Adjustment(lower=1, upper=12, step_increment=1, value=hour12)
    hour_spin = Gtk.SpinButton(adjustment=hour_adj, climb_rate=1, digits=0)

    minute_adj = Gtk.Adjustment(lower=0, upper=59, step_increment=1, value=p["minute"])
    minute_spin = Gtk.SpinButton(adjustment=minute_adj, climb_rate=1, digits=0)
    minute_spin.connect("value-changed", lambda w: (p.__setitem__("minute", int(w.get_value())), on_changed()))

    period_dropdown = Gtk.DropDown(model=Gtk.StringList.new(["AM", "PM"]))
    period_dropdown.set_selected(0 if period == "AM" else 1)

    def update_hour(*_a):
        new_period = "AM" if period_dropdown.get_selected() == 0 else "PM"
        p["hour"] = _to_24h(int(hour_spin.get_value()), new_period)
        on_changed()

    hour_spin.connect("value-changed", update_hour)
    period_dropdown.connect("notify::selected", update_hour)

    time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    time_row.append(hour_spin)
    time_row.append(Gtk.Label(label=":"))
    time_row.append(minute_spin)
    time_row.append(period_dropdown)
    box.append(_labeled_row("Time", time_row))

    days_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    for i, day_label in enumerate(DAY_LABELS):
        toggle = Gtk.ToggleButton(label=day_label)
        toggle.set_active(i in p["days"])

        def on_toggle(w, i=i):
            if w.get_active():
                if i not in p["days"]:
                    p["days"].append(i)
            elif i in p["days"]:
                p["days"].remove(i)
            on_changed()

        toggle.connect("toggled", on_toggle)
        days_row.append(toggle)
    box.append(_labeled_row("Days", days_row))

    hint = Gtk.Label(label="No days selected repeats every day.")
    hint.add_css_class("branch-end-label")
    hint.set_xalign(0.0)
    box.append(hint)


def _build_event_dropdown(p, on_changed, connects_label, disconnects_label):
    dropdown = Gtk.DropDown(model=Gtk.StringList.new([connects_label, disconnects_label]))
    dropdown.set_selected(0 if p.get("event", "connects") == "connects" else 1)
    dropdown.connect("notify::selected", lambda w, _p: (
        p.__setitem__("event", "connects" if w.get_selected() == 0 else "disconnects"), on_changed()))
    return dropdown


def _build_wifi_params(box, automation, on_changed):
    p = automation.trigger_params
    p.setdefault("event", "connects")
    p.setdefault("ssid", "")

    box.append(_labeled_row("Event", _build_event_dropdown(p, on_changed, "Connects to", "Disconnects from")))

    known = system_actions.list_known_wifi_networks()
    if p["ssid"] and p["ssid"] not in known:
        known.append(p["ssid"])  # keep a saved choice selectable even if no longer known
    # Placeholder for nothing saved yet same as the Run Shortcut choice
    options = ["Any Network"] + (known or ["No saved networks found"])

    ssid_dropdown = Gtk.DropDown(model=Gtk.StringList.new(options))
    ssid_dropdown.set_selected(options.index(p["ssid"]) if p["ssid"] in known else 0)
    ssid_dropdown.connect("notify::selected", lambda w, _p: (
        p.__setitem__("ssid", options[w.get_selected()] if options[w.get_selected()] in known else ""),
        on_changed()))
    box.append(_labeled_row("Network", ssid_dropdown))


def _build_bluetooth_params(box, automation, on_changed):
    p = automation.trigger_params
    p.setdefault("event", "connects")
    p.setdefault("device", "")

    box.append(_labeled_row("Event", _build_event_dropdown(p, on_changed, "Connects to", "Disconnects from")))

    known = system_actions.list_paired_bluetooth_devices()
    if p["device"] and p["device"] not in known:
        known.append(p["device"])  # keep a saved choice selectable even if no longer paired
    options = ["Any Device"] + (known or ["No paired devices found"])

    device_dropdown = Gtk.DropDown(model=Gtk.StringList.new(options))
    device_dropdown.set_selected(options.index(p["device"]) if p["device"] in known else 0)
    device_dropdown.connect("notify::selected", lambda w, _p: (
        p.__setitem__("device", options[w.get_selected()] if options[w.get_selected()] in known else ""),
        on_changed()))
    box.append(_labeled_row("Device", device_dropdown))


def _build_battery_params(box, automation, on_changed):
    p = automation.trigger_params
    p.setdefault("condition", "drops_below")
    p.setdefault("percent", 20)

    conditions = [
        ("drops_below", "Drops below"),
        ("rises_above", "Rises above"),
        ("charger_connected", "Charger connected"),
        ("charger_disconnected", "Charger disconnected"),
    ]
    ids = [c for c, _ in conditions]
    names = [n for _, n in conditions]
    cond_dropdown = Gtk.DropDown(model=Gtk.StringList.new(names))
    cond_dropdown.set_selected(ids.index(p["condition"]) if p["condition"] in ids else 0)

    percent_adj = Gtk.Adjustment(lower=1, upper=100, step_increment=1, value=p["percent"])
    percent_spin = Gtk.SpinButton(adjustment=percent_adj, climb_rate=1, digits=0)
    percent_spin.set_sensitive(p["condition"] in ("drops_below", "rises_above"))
    percent_spin.connect("value-changed", lambda w: (p.__setitem__("percent", int(w.get_value())), on_changed()))

    def on_cond_changed(w, _p):
        cond = ids[w.get_selected()]
        p["condition"] = cond
        percent_spin.set_sensitive(cond in ("drops_below", "rises_above"))
        on_changed()

    cond_dropdown.connect("notify::selected", on_cond_changed)

    box.append(_labeled_row("Condition", cond_dropdown))
    box.append(_labeled_row("Percent", percent_spin))


def _build_sleep_wake_params(box, automation, on_changed):
    p = automation.trigger_params
    p.setdefault("event", "sleeps")

    dropdown = Gtk.DropDown(model=Gtk.StringList.new(["Device sleeps", "Device wakes"]))
    dropdown.set_selected(0 if p["event"] == "sleeps" else 1)
    dropdown.connect("notify::selected", lambda w, _p: (
        p.__setitem__("event", "sleeps" if w.get_selected() == 0 else "wakes"), on_changed()))
    box.append(_labeled_row("Event", dropdown))


def _build_startup_params(box, automation, on_changed):
    hint = Gtk.Label(label="Runs once each time the app starts.")
    hint.add_css_class("branch-end-label")
    hint.set_xalign(0.0)
    box.append(hint)


_PARAM_BUILDERS = {
    "time": _build_time_params,
    "wifi": _build_wifi_params,
    "bluetooth": _build_bluetooth_params,
    "battery": _build_battery_params,
    "sleep_wake": _build_sleep_wake_params,
    "startup": _build_startup_params,
}


def describe_trigger(automation):
    """One line summary shown on an automation tile"""
    p = automation.trigger_params
    kind = automation.trigger_type

    if kind == "time":
        hour12, suffix = _to_12h(p.get("hour", 9))
        minute = p.get("minute", 0)
        days = p.get("days") or []
        when = "Every day" if not days or len(days) == 7 else ", ".join(DAY_LABELS[d] for d in days)
        return f"{when} at {hour12}:{minute:02d} {suffix}"
    if kind == "wifi":
        target = p.get("ssid") or "any network"
        return f"Wi-Fi {p.get('event', 'connects')} \u2013 {target}"
    if kind == "bluetooth":
        target = p.get("device") or "any device"
        return f"Bluetooth {p.get('event', 'connects')} \u2013 {target}"
    if kind == "battery":
        cond = p.get("condition", "drops_below")
        labels = {
            "drops_below": f"Battery drops below {p.get('percent', 20)}%",
            "rises_above": f"Battery rises above {p.get('percent', 20)}%",
            "charger_connected": "Charger connected",
            "charger_disconnected": "Charger disconnected",
        }
        return labels.get(cond, "Battery")
    if kind == "sleep_wake":
        return "Device wakes" if p.get("event") == "wakes" else "Device sleeps"
    if kind == "startup":
        return "When the app starts"

    ttype = trigger_library.get_trigger_type(kind)
    if ttype is not None:
        if ttype.describe is not None:
            try:
                return ttype.describe(p)
            except Exception:
                pass
        return ttype.name
    return ""
