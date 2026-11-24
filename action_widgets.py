import shutil

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GObject, Gtk

import action_library as lib
from models import ParamValue

def build_library_row(action_type, on_click):
    row = Gtk.Button()
    row.set_has_frame(False)
    row.add_css_class("library-row")

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box.set_margin_top(5)
    box.set_margin_bottom(5)
    box.set_margin_start(6)
    box.set_margin_end(6)

    swatch = Gtk.Box()
    swatch.add_css_class("library-row-swatch")
    swatch.add_css_class(action_type.color_class)
    icon = Gtk.Image.new_from_icon_name(action_type.icon_name)
    icon.set_pixel_size(15)
    swatch.append(icon)
    box.append(swatch)

    label = Gtk.Label(label=action_type.name)
    label.set_xalign(0.0)
    label.set_hexpand(True)
    box.append(label)

    if action_type.required_command and not shutil.which(action_type.required_command):
        row.add_css_class("library-row-unavailable")
        row.set_tooltip_text(
            f"Needs \u201c{action_type.required_command}\u201d, not found on this system."
        )
        row.set_sensitive(False)
    else:
        # Drag onto the canvas to add it or click
        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        press_pos = {"x": 0, "y": 0}

        def on_prepare(source, x, y):
            press_pos["x"], press_pos["y"] = x, y
            return Gdk.ContentProvider.new_for_value(GObject.Value(str, action_type.id))

        def on_drag_begin(source, drag):
            source.set_icon(Gtk.WidgetPaintable.new(row), int(press_pos["x"]), int(press_pos["y"]))

        drag_source.connect("prepare", on_prepare)
        drag_source.connect("drag-begin", on_drag_begin)
        row.add_controller(drag_source)

    row.set_child(box)
    row.connect("clicked", lambda b: on_click(action_type.id))
    return row


def build_add_button(on_click):
    btn = Gtk.Button(label="+  Add Action")
    btn.add_css_class("add-action-button")
    btn.set_halign(Gtk.Align.START)
    btn.connect("clicked", lambda b: on_click())
    return btn


def show_action_picker(anchor_widget, on_choose):
    """Searchable popover for adding an action into a branch"""
    popover = Gtk.Popover()
    popover.set_parent(anchor_widget)
    popover.set_autohide(True)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.set_margin_top(6)
    box.set_margin_bottom(6)
    box.set_margin_start(6)
    box.set_margin_end(6)

    search = Gtk.SearchEntry()
    search.set_placeholder_text("Search Actions")
    box.append(search)

    list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    scroller = Gtk.ScrolledWindow()
    scroller.set_min_content_height(320)
    scroller.set_min_content_width(260)
    scroller.set_child(list_box)
    box.append(scroller)

    def refresh(*_a):
        child = list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            list_box.remove(child)
            child = nxt
        for action_type in lib.search_actions(search.get_text()):
            row = build_library_row(action_type, lambda aid: (popover.popdown(), on_choose(aid)))
            list_box.append(row)

    search.connect("search-changed", refresh)
    refresh()

    popover.set_child(box)
    popover.popup()


def _make_field_control(spec, param_value, on_literal_changed):
    if spec.type == "number":
        adjustment = Gtk.Adjustment(lower=spec.min_value, upper=spec.max_value, step_increment=1)
        widget = Gtk.SpinButton(adjustment=adjustment, climb_rate=1, digits=0)
        try:
            widget.set_value(float(param_value.value or 0))
        except (TypeError, ValueError):
            widget.set_value(0)
        widget.connect("value-changed", lambda w: on_literal_changed(w.get_value()))
        return widget

    if spec.type == "bool":
        widget = Gtk.Switch()
        widget.set_active(bool(param_value.value))
        widget.set_valign(Gtk.Align.CENTER)
        widget.connect("notify::active", lambda w, p: on_literal_changed(w.get_active()))
        return widget

    if spec.type == "choice":
        # choices can be a list or value label pairs or a callable
        # resolved on every render so dynamic sources stay fresh
        raw = spec.choices() if callable(spec.choices) else (spec.choices or [""])
        if raw and isinstance(raw[0], tuple):
            values = [v for v, _label in raw]
            labels = [label for _v, label in raw]
        else:
            values = labels = list(raw) or [""]

        widget = Gtk.DropDown(model=Gtk.StringList.new(labels))
        try:
            idx = values.index(param_value.value)
        except ValueError:
            idx = 0
        widget.set_selected(idx)
        widget.connect("notify::selected", lambda w, p: on_literal_changed(values[w.get_selected()]))
        return widget

    widget = Gtk.Entry()
    widget.set_text("" if param_value.value is None else str(param_value.value))
    widget.set_placeholder_text(spec.placeholder)
    widget.connect("changed", lambda w: on_literal_changed(w.get_text()))
    return widget


def build_param_row(spec, step, editor):
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    row.add_css_class("param-row")

    label = Gtk.Label(label=spec.label)
    label.add_css_class("param-label")
    label.set_xalign(0.0)
    label.set_size_request(90, -1)
    row.append(label)

    slot = Gtk.Box()
    slot.set_hexpand(True)
    row.append(slot)

    def set_literal(value):
        step.params[spec.key] = ParamValue.literal(value)

    def render_slot():
        child = slot.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            slot.remove(child)
            child = nxt

        pv = step.params.get(spec.key) or ParamValue.literal(spec.default)
        step.params[spec.key] = pv

        if pv.kind == "variable":
            chip = Gtk.Button(label=f"\u25c6 {pv.name}")
            chip.add_css_class("variable-chip")
            chip.set_tooltip_text("Click to replace with a typed value")

            def clear(_b):
                step.params[spec.key] = ParamValue.literal(spec.default)
                render_slot()

            chip.connect("clicked", clear)
            slot.append(chip)
        else:
            control = _make_field_control(spec, pv, set_literal)
            control.set_hexpand(True)
            slot.append(control)

    render_slot()

    if spec.type in ("text", "number"):
        var_btn = Gtk.MenuButton()
        var_btn.set_icon_name("insert-link-symbolic")
        var_btn.add_css_class("variable-toggle")
        var_btn.set_has_frame(False)
        var_btn.set_tooltip_text("Insert a variable")

        def build_var_popover():
            popover = Gtk.Popover()
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            vbox.set_margin_top(4)
            vbox.set_margin_bottom(4)
            vbox.set_margin_start(4)
            vbox.set_margin_end(4)

            names = editor.available_variables_before(step.uid)
            for name in names:
                b = Gtk.Button(label=name)
                b.set_has_frame(False)
                b.add_css_class("popover-menu-item")
                b.get_child().set_xalign(0.0)

                def choose(_b, n=name):
                    step.params[spec.key] = ParamValue.variable(n)
                    render_slot()
                    popover.popdown()

                b.connect("clicked", choose)
                vbox.append(b)

            popover.set_child(vbox)
            return popover

        var_btn.set_popover(build_var_popover())
        row.append(var_btn)

    return row

# Step cards

def _step_header(step, action_type, editor, steps_list, frame):
    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

    grip = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
    grip.set_pixel_size(16)
    grip.set_margin_end(2)
    grip.add_css_class("step-drag-handle")
    grip.set_tooltip_text("Drag to reorder")
    header.append(grip)

    # Drag source covers the whole card since a small grip is hard to grab
    # buttons and entries inside still take their own clicks
    frame.set_cursor_from_name("grab")
    press_pos = {"x": 0, "y": 0}

    def on_prepare(source, x, y):
        press_pos["x"], press_pos["y"] = x, y
        return Gdk.ContentProvider.new_for_value(GObject.Value(str, step.uid))

    def on_drag_begin(source, drag, frame=frame):
        frame.add_css_class("step-card-dragging")
        # Ghost the whole card at the grab point as a translucent preview
        source.set_icon(Gtk.WidgetPaintable.new(frame), int(press_pos["x"]), int(press_pos["y"]))

    def on_drag_end(source, drag, delete_data, frame=frame):
        frame.remove_css_class("step-card-dragging")

    card_drag = Gtk.DragSource()
    card_drag.set_actions(Gdk.DragAction.MOVE)
    card_drag.connect("prepare", on_prepare)
    card_drag.connect("drag-begin", on_drag_begin)
    card_drag.connect("drag-end", on_drag_end)
    frame.add_controller(card_drag)

    icon = Gtk.Image.new_from_icon_name(action_type.icon_name)
    icon.set_pixel_size(16)
    header.append(icon)

    name = Gtk.Label(label=action_type.name)
    name.add_css_class("step-title")
    name.set_xalign(0.0)
    name.set_hexpand(True)
    header.append(name)

    idx = steps_list.index(step)

    up_btn = Gtk.Button()
    up_btn.set_icon_name("go-up-symbolic")
    up_btn.set_has_frame(False)
    up_btn.add_css_class("step-icon-button")
    up_btn.set_tooltip_text("Move up")
    up_btn.set_sensitive(idx > 0)
    up_btn.connect("clicked", lambda b: (
        steps_list.insert(idx - 1, steps_list.pop(idx)), editor.request_refresh()))
    header.append(up_btn)

    down_btn = Gtk.Button()
    down_btn.set_icon_name("go-down-symbolic")
    down_btn.set_has_frame(False)
    down_btn.add_css_class("step-icon-button")
    down_btn.set_tooltip_text("Move down")
    down_btn.set_sensitive(idx < len(steps_list) - 1)
    down_btn.connect("clicked", lambda b: (
        steps_list.insert(idx + 1, steps_list.pop(idx)), editor.request_refresh()))
    header.append(down_btn)

    del_btn = Gtk.Button()
    del_btn.set_icon_name("user-trash-symbolic")
    del_btn.set_has_frame(False)
    del_btn.add_css_class("step-icon-button")
    del_btn.set_tooltip_text("Delete step")
    del_btn.connect("clicked", lambda b: (steps_list.remove(step), editor.request_refresh()))
    header.append(del_btn)

    return header


def _attach_steps_drop(box, target_list, editor):
    """Dropping a library action appends a step and dropping a step moves it to the end
    dropping on a card is handled by that card instead"""
    drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

    def on_enter(_t, _x, _y):
        box.add_css_class("canvas-drop-active")
        return Gdk.DragAction.MOVE

    def on_leave(_t):
        box.remove_css_class("canvas-drop-active")

    def on_drop(_t, value, _x, _y):
        box.remove_css_class("canvas-drop-active")
        if lib.get_action_type(value) is not None:
            target_list.append(lib.make_instance(value))
            editor.request_refresh()
            return True
        for i, s in enumerate(target_list):
            if s.uid == value:
                target_list.append(target_list.pop(i))
                editor.request_refresh()
                return True
        return False

    drop_target.connect("enter", on_enter)
    drop_target.connect("leave", on_leave)
    drop_target.connect("drop", on_drop)
    box.add_controller(drop_target)


def _branch_section(label_text, child_steps, editor, add_target_list):
    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    label = Gtk.Label(label=label_text)
    label.add_css_class("branch-label")
    label.set_xalign(0.0)
    section.append(label)

    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    inner.add_css_class("branch-box")
    render_steps(inner, child_steps, editor)
    inner.append(build_add_button(lambda: show_action_picker(
        inner, lambda aid: (add_target_list.append(lib.make_instance(aid)), editor.request_refresh()))))
    _attach_steps_drop(inner, add_target_list, editor)
    section.append(inner)

    return section


def build_step_widget(step, editor, steps_list):
    action_type = lib.get_action_type(step.action_id)
    if action_type is None:
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add_css_class("step-card")
        frame.add_css_class("tile-gray")
        frame.append(Gtk.Label(label=f"Unknown action: {step.action_id}"))
        return frame

    frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    frame.add_css_class("step-card")
    frame.add_css_class(action_type.color_class)

    if action_type.required_command and not shutil.which(action_type.required_command):
        frame.add_css_class("step-card-unavailable")
        frame.set_tooltip_text(
            f"Needs \u201c{action_type.required_command}\u201d, which isn't installed."
        )

    frame.append(_step_header(step, action_type, editor, steps_list, frame))

    for spec in action_type.params:
        frame.append(build_param_row(spec, step, editor))

    if action_type.control == "if":
        frame.append(_branch_section("THEN", step.then_steps, editor, step.then_steps))
        frame.append(_branch_section("OTHERWISE", step.else_steps, editor, step.else_steps))
        end_label = Gtk.Label(label="END IF")
        end_label.add_css_class("branch-end-label")
        end_label.set_xalign(0.0)
        frame.append(end_label)

    elif action_type.control == "repeat":
        frame.append(_branch_section("REPEAT", step.body_steps, editor, step.body_steps))
        end_label = Gtk.Label(label="END REPEAT")
        end_label.add_css_class("branch-end-label")
        end_label.set_xalign(0.0)
        frame.append(end_label)

    _attach_step_card_drop(frame, step, steps_list, editor)
    return frame


def _attach_step_card_drop(frame, step, steps_list, editor):
    """Dropping a library action inserts it before this card
    dropping a step from the same list moves it here"""
    drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

    def on_enter(_t, _x, _y):
        frame.add_css_class("step-card-drop-target")
        return Gdk.DragAction.MOVE

    def on_leave(_t):
        frame.remove_css_class("step-card-drop-target")

    def on_drop(_t, value, _x, _y):
        frame.remove_css_class("step-card-drop-target")
        if lib.get_action_type(value) is not None:
            dst_idx = steps_list.index(step)
            steps_list.insert(dst_idx, lib.make_instance(value))
            editor.request_refresh()
            return True
        if value == step.uid:
            return False
        src_idx = next((i for i, s in enumerate(steps_list) if s.uid == value), None)
        if src_idx is None:
            return False  # dragged from a different branch is unsupported
        dst_idx = steps_list.index(step)
        popped = steps_list.pop(src_idx)
        if src_idx < dst_idx:
            dst_idx -= 1
        steps_list.insert(dst_idx, popped)
        editor.request_refresh()
        return True

    drop_target.connect("enter", on_enter)
    drop_target.connect("leave", on_leave)
    drop_target.connect("drop", on_drop)
    frame.add_controller(drop_target)


def render_steps(container_box, steps_list, editor):
    for step in steps_list:
        container_box.append(build_step_widget(step, editor, steps_list))


# Library panel and step canvas shared by both editors

class LibraryPanel:
    """Searchable action library sidebar
    on_action_chosen is called with the action_id when a row is clicked"""

    def __init__(self, on_action_chosen):
        self.on_action_chosen = on_action_chosen

        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.add_css_class("library-panel")
        self.widget.set_size_request(260, -1)

        title = Gtk.Label(label="Actions")
        title.add_css_class("sidebar-title")
        title.set_xalign(0.0)
        title.set_margin_top(14)
        title.set_margin_start(14)
        self.widget.append(title)

        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search Actions")
        search.set_margin_top(8)
        search.set_margin_start(10)
        search.set_margin_end(10)
        search.set_margin_bottom(6)
        self.widget.append(search)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self.widget.append(scroller)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._list_box.set_margin_start(8)
        self._list_box.set_margin_end(8)
        self._list_box.set_margin_bottom(12)
        scroller.set_child(self._list_box)

        search.connect("search-changed", lambda w: self._populate(w.get_text()))
        self._populate("")

    def _populate(self, query):
        child = self._list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt

        matches = lib.search_actions(query)
        by_category = {}
        for a in matches:
            by_category.setdefault(a.category, []).append(a)

        for category_name, _icon in lib.CATEGORIES:
            items = by_category.get(category_name)
            if not items:
                continue
            label = Gtk.Label(label=category_name.upper())
            label.add_css_class("sidebar-section-label")
            label.set_xalign(0.0)
            label.set_margin_top(8)
            self._list_box.append(label)
            for action_type in items:
                self._list_box.append(build_library_row(action_type, self.on_action_chosen))


class StepsCanvas:
    """Scrollable canvas of step cards with a trailing Add Action button
    editor needs request_refresh and available_variables_before"""

    def __init__(self, editor):
        self.editor = editor
        self._steps_list = []
        self._drop_attached = False

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_hexpand(True)
        outer.set_vexpand(True)
        outer.add_css_class("editor-canvas-area")

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        outer.append(scroller)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.box.set_margin_top(24)
        self.box.set_margin_bottom(40)
        self.box.set_margin_start(28)
        self.box.set_margin_end(28)
        scroller.set_child(self.box)

        self.widget = outer

    def rebuild(self, steps_list):
        self._steps_list = steps_list

        child = self.box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.box.remove(child)
            child = nxt

        if not steps_list:
            empty = Gtk.Label(label="Add an action to get started")
            empty.add_css_class("empty-state")
            self.box.append(empty)
        else:
            render_steps(self.box, steps_list, self.editor)

        self.box.append(build_add_button(lambda: show_action_picker(
            self.box, lambda aid: (steps_list.append(lib.make_instance(aid)), self.editor.request_refresh()))))

        # box persists across rebuilds so the drop target is attached once
        if not self._drop_attached:
            _attach_steps_drop(self.box, self._steps_list, self.editor)
            self._drop_attached = True


def build_toggle_row(label_text, initial, on_toggle):
    """Label and switch row that calls on_toggle with a bool"""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    label = Gtk.Label(label=label_text)
    label.add_css_class("option-row-label")
    label.set_size_request(140, -1)
    label.set_xalign(0.0)
    row.append(label)

    switch = Gtk.Switch()
    switch.set_active(initial)
    switch.set_valign(Gtk.Align.CENTER)
    switch.connect("notify::active", lambda w, p: on_toggle(w.get_active()))
    row.append(switch)

    return row


def build_dropdown_row(label_text, options, selected_index, on_change):
    """Label and dropdown row that calls on_change with the selected index"""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    label = Gtk.Label(label=label_text)
    label.add_css_class("option-row-label")
    label.set_size_request(140, -1)
    label.set_xalign(0.0)
    row.append(label)

    dropdown = Gtk.DropDown(model=Gtk.StringList.new(options))
    dropdown.set_selected(selected_index)
    dropdown.connect("notify::selected", lambda w, _p: on_change(w.get_selected()))
    row.append(dropdown)

    return row


def variables_before(steps, target_uid):
    """Every variable name set before target_uid in the step tree plus Previous Result
    branch blind so it is permissive"""
    names = [ParamValue.PREVIOUS_RESULT]

    def walk(step_list):
        for s in step_list:
            if s.uid == target_uid:
                return True
            if s.action_id == "var.set":
                pv = s.params.get("name")
                if pv and pv.kind == "literal" and pv.value:
                    names.append(str(pv.value))
            for branch in (s.then_steps, s.else_steps, s.body_steps):
                if walk(branch):
                    return True
        return False

    walk(steps)
    return names
