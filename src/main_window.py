import uuid

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk

import action_library
import automation_engine
import automation_widgets
import plugin_manager
import runner
import storage
import system_actions
from automation_editor_window import AutomationEditorWindow
from dialogs import (show_automation_details_dialog, show_confirm_dialog,
                      show_details_dialog, show_message_dialog, show_prompt_dialog)
from editor_window import EditorWindow
from models import Automation, Shortcut
from plugins_window import PluginsWindow

CONFIRM_REQUIRED_ACTIONS = {"system.log_out", "system.restart", "system.shutdown"}
AUTOMATIONS_VIEW = "__automations__"  # sentinel for current_folder and never a real folder


def _shortcut_needs_confirm(item):
    """True if the item confirm toggle is on or it has a dangerous action"""
    if getattr(item, "confirm", False):
        return True

    def walk(steps):
        for s in steps:
            if s.action_id in CONFIRM_REQUIRED_ACTIONS:
                return True
            if walk(s.then_steps) or walk(s.else_steps) or walk(s.body_steps):
                return True
        return False
    return walk(item.steps)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Shortcuts")
        self.set_default_size(1040, 680)

        self.shortcuts, self.folders, self.automations = storage.load()
        self.current_folder = None
        self.search_text = ""

        action_library.set_shortcuts_provider(lambda: self.shortcuts)
        # Registers enabled plugin actions before any editor opens
        # failures are skipped and shown in a dialog later
        plugin_load_errors = plugin_manager.load_all_enabled()

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_child(root)

        content = self._build_content()
        sidebar = self._build_sidebar()

        root.append(sidebar)
        root.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        root.append(content)

        self.automation_engine = automation_engine.AutomationEngine(
            lambda: self.automations, self._on_automation_fired)
        self.automation_engine.start()

        self.connect("close-request", self._on_close_request)

        if plugin_load_errors:
            GLib.idle_add(lambda: self._show_plugin_load_errors(plugin_load_errors))

    def _persist(self):
        storage.save(self.shortcuts, self.folders, self.automations)

    def _on_close_request(self, _win):
        self.automation_engine.stop()
        return False

    def _show_plugin_load_errors(self, errors):
        lines = "\n".join(f"\u201c{plugin_id}\u201d: {message}" for plugin_id, message in errors)
        show_message_dialog(self, "Some plugins didn\u2019t load", lines)
        return False

    def _on_open_plugins(self):
        def on_changed():
            self._rebuild_nav()
            self._rebuild_content()
        PluginsWindow(self, on_changed).present()

    # Sidebar
    def _build_sidebar(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("sidebar")
        outer.set_size_request(230, -1)

        title = Gtk.Label(label="Shortcuts")
        title.add_css_class("sidebar-title")
        title.set_xalign(0.0)
        outer.append(title)

        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.add_css_class("nav-list")
        self.nav_list.connect("row-selected", self._on_nav_selected)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(self.nav_list)
        outer.append(scroller)

        new_folder_btn = Gtk.Button(label="+  New Folder")
        new_folder_btn.set_has_frame(False)
        new_folder_btn.add_css_class("new-folder-button")
        new_folder_btn.connect("clicked", lambda b: self._on_new_folder())
        outer.append(new_folder_btn)

        plugins_btn = Gtk.Button()
        plugins_btn.set_has_frame(False)
        plugins_btn.add_css_class("new-folder-button")
        plugins_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        plugins_icon = Gtk.Image.new_from_icon_name("application-x-addon-symbolic")
        plugins_box.append(plugins_icon)
        plugins_box.append(Gtk.Label(label="Plugins"))
        plugins_btn.set_child(plugins_box)
        plugins_btn.connect("clicked", lambda b: self._on_open_plugins())
        outer.append(plugins_btn)

        self._rebuild_nav()
        return outer

    def _rebuild_nav(self, select_category="__keep__"):
        if select_category == "__keep__":
            select_category = self.current_folder

        child = self.nav_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.nav_list.remove(child)
            child = nxt

        all_row = self._build_nav_row("view-grid-symbolic", "All Shortcuts", len(self.shortcuts), None)
        self.nav_list.append(all_row)
        self.nav_list.append(self._build_section_label_row("Folders"))

        row_to_select = all_row
        for folder_name in self.folders:
            count = sum(1 for s in self.shortcuts if s.folder == folder_name)
            row = self._build_nav_row("folder-symbolic", folder_name, count, folder_name)
            self.nav_list.append(row)
            if folder_name == select_category:
                row_to_select = row

        self.nav_list.append(self._build_section_label_row("Automations"))
        automations_row = self._build_nav_row(
            "emblem-synchronizing-symbolic", "Automations", len(self.automations), AUTOMATIONS_VIEW)
        self.nav_list.append(automations_row)
        if select_category == AUTOMATIONS_VIEW:
            row_to_select = automations_row

        self.nav_list.select_row(row_to_select)

    def _build_nav_row(self, icon_name, text, count, category):
        row = Gtk.ListBoxRow()
        row.add_css_class("sidebar-row")
        row.category = category

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(8)
        box.set_margin_end(8)

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(18)
        icon.add_css_class("sidebar-row-icon")
        box.append(icon)

        label = Gtk.Label(label=text)
        label.set_xalign(0.0)
        label.set_hexpand(True)
        box.append(label)

        count_label = Gtk.Label(label=str(count))
        count_label.add_css_class("nav-count")
        box.append(count_label)

        row.set_child(box)

        # Only real folders can be renamed or deleted or reordered
        if category is not None and category != AUTOMATIONS_VIEW:
            self._attach_folder_row_interactions(row, category)

        return row

    def _attach_folder_row_interactions(self, row, folder_name):
        right_click = Gtk.GestureClick()
        right_click.set_button(Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", lambda gesture, n_press, x, y:
                             self._show_folder_context_menu(row, folder_name, x, y))
        row.add_controller(right_click)

        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        press_pos = {"x": 0, "y": 0}

        def on_prepare(source, x, y):
            press_pos["x"], press_pos["y"] = x, y
            return Gdk.ContentProvider.new_for_value(GObject.Value(str, folder_name))

        def on_drag_begin(source, drag):
            row.add_css_class("folder-row-dragging")
            source.set_icon(Gtk.WidgetPaintable.new(row), int(press_pos["x"]), int(press_pos["y"]))

        def on_drag_end(source, drag, delete_data):
            row.remove_css_class("folder-row-dragging")

        drag_source.connect("prepare", on_prepare)
        drag_source.connect("drag-begin", on_drag_begin)
        drag_source.connect("drag-end", on_drag_end)
        row.add_controller(drag_source)

        drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

        def on_enter(_t, _x, _y):
            row.add_css_class("sidebar-row-drop-target")
            return Gdk.DragAction.MOVE

        def on_leave(_t):
            row.remove_css_class("sidebar-row-drop-target")

        def on_drop(_t, value, _x, _y):
            row.remove_css_class("sidebar-row-drop-target")
            if self._on_folder_dropped(value, folder_name):
                return True
            return self._move_shortcut_to_folder(value, folder_name)

        drop_target.connect("enter", on_enter)
        drop_target.connect("leave", on_leave)
        drop_target.connect("drop", on_drop)
        row.add_controller(drop_target)

    def _on_folder_dropped(self, source_name, target_name):
        if source_name == target_name or source_name not in self.folders or target_name not in self.folders:
            return False
        self.folders.remove(source_name)
        self.folders.insert(self.folders.index(target_name), source_name)
        self._persist()
        self._rebuild_nav(select_category=self.current_folder)
        return True

    def _move_shortcut_to_folder(self, shortcut_uid, folder_name):
        for s in self.shortcuts:
            if s.uid == shortcut_uid:
                if s.folder == folder_name:
                    return False
                s.folder = folder_name
                self._persist()
                self._rebuild_nav()
                self._rebuild_content()
                return True
        return False

    def _show_folder_context_menu(self, row, folder_name, x, y):
        popover = Gtk.Popover()
        popover.set_parent(row)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def item(label_text, handler, sensitive=True):
            b = Gtk.Button(label=label_text)
            b.set_has_frame(False)
            b.add_css_class("popover-menu-item")
            b.get_child().set_xalign(0.0)
            b.set_sensitive(sensitive)

            def wrapped(_b):
                popover.popdown()
                handler()

            b.connect("clicked", wrapped)
            box.append(b)

        idx = self.folders.index(folder_name)
        item("Move Up", lambda: self._move_folder(folder_name, -1), sensitive=idx > 0)
        item("Move Down", lambda: self._move_folder(folder_name, 1), sensitive=idx < len(self.folders) - 1)
        item("Rename", lambda: self._on_rename_folder(folder_name))
        item("Delete", lambda: self._on_delete_folder(folder_name))

        popover.set_child(box)
        popover.popup()

    def _move_folder(self, folder_name, delta):
        idx = self.folders.index(folder_name)
        new_idx = idx + delta
        if not (0 <= new_idx < len(self.folders)):
            return
        self.folders[idx], self.folders[new_idx] = self.folders[new_idx], self.folders[idx]
        self._persist()
        self._rebuild_nav(select_category=self.current_folder)

    def _on_rename_folder(self, folder_name):
        def done(text):
            new_name = (text or "").strip()
            if not new_name or new_name == folder_name:
                return
            if new_name in self.folders:
                show_message_dialog(self, f"\u201c{new_name}\u201d already exists",
                                     "Choose a different folder name.")
                return
            self.folders[self.folders.index(folder_name)] = new_name
            for s in self.shortcuts:
                if s.folder == folder_name:
                    s.folder = new_name
            if self.current_folder == folder_name:
                self.current_folder = new_name
            self._persist()
            self._rebuild_nav(select_category=self.current_folder)
            self._rebuild_content()
        show_prompt_dialog(self, "Rename folder", folder_name, done)

    def _on_delete_folder(self, folder_name):
        def confirmed():
            self.folders = [f for f in self.folders if f != folder_name]
            if self.current_folder == folder_name:
                self.current_folder = None
            self._persist()
            self._rebuild_nav()
            self._rebuild_content()

        count = sum(1 for s in self.shortcuts if s.folder == folder_name)
        message = (f"The {count} shortcut{'s' if count != 1 else ''} inside will still be in All Shortcuts."
                   if count else "This folder will be deleted.")
        show_confirm_dialog(self, f"Delete \u201c{folder_name}\u201d?", message, confirmed)

    def _build_section_label_row(self, text):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        row.category = None

        label = Gtk.Label(label=text.upper())
        label.add_css_class("sidebar-section-label")
        label.set_xalign(0.0)
        row.set_child(label)
        return row

    def _on_nav_selected(self, _listbox, row):
        if row is None:
            return
        self.current_folder = getattr(row, "category", None)
        self._rebuild_content()

    def _on_new_folder(self):
        def done(text):
            name = (text or "").strip()
            if not name:
                return
            if name in self.folders:
                show_message_dialog(self, f"\u201c{name}\u201d already exists",
                                     "Choose a different folder name.")
                return
            self.folders.append(name)
            self._persist()
            self._rebuild_nav(select_category=name)
        show_prompt_dialog(self, "New folder name", "", done)

    # Content area
    def _build_content(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("content-area")
        outer.set_hexpand(True)
        outer.set_vexpand(True)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_margin_top(28)
        header.set_margin_start(32)
        header.set_margin_end(32)
        header.set_margin_bottom(8)

        self.page_title_label = Gtk.Label(label="All Shortcuts")
        self.page_title_label.add_css_class("page-title")
        self.page_title_label.set_xalign(0.0)
        self.page_title_label.set_hexpand(True)
        header.append(self.page_title_label)

        self.new_item_btn = Gtk.Button(label="+  New Shortcut")
        self.new_item_btn.add_css_class("new-shortcut-button")
        self.new_item_btn.connect("clicked", lambda b: self._on_new_item())
        header.append(self.new_item_btn)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search")
        self.search_entry.add_css_class("content-search")
        self.search_entry.connect("search-changed", self._on_search_changed)
        header.append(self.search_entry)

        outer.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_margin_top(8)
        self.content_box.set_margin_bottom(28)
        self.content_box.set_margin_start(32)
        self.content_box.set_margin_end(32)
        scrolled.set_child(self.content_box)

        outer.append(scrolled)
        self._rebuild_content()
        return outer

    def _on_search_changed(self, entry):
        self.search_text = entry.get_text().strip().lower()
        self._rebuild_content()

    def _on_new_item(self):
        if self.current_folder == AUTOMATIONS_VIEW:
            self._on_new_automation()
        else:
            self._on_new_shortcut()

    def _visible_shortcuts(self):
        items = self.shortcuts
        if self.current_folder is not None:
            items = [s for s in items if s.folder == self.current_folder]
        if self.search_text:
            items = [s for s in items if self.search_text in s.name.lower()]
        return items

    def _visible_automations(self):
        items = self.automations
        if self.search_text:
            items = [a for a in items if self.search_text in a.name.lower()]
        return items

    def _rebuild_content(self):
        is_automations = self.current_folder == AUTOMATIONS_VIEW
        title_text = "Automations" if is_automations else (self.current_folder or "All Shortcuts")
        self.page_title_label.set_label(title_text)
        self.new_item_btn.set_label("+  New Automation" if is_automations else "+  New Shortcut")

        child = self.content_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.content_box.remove(child)
            child = nxt

        items = self._visible_automations() if is_automations else self._visible_shortcuts()

        if not items:
            noun = "automations" if is_automations else "shortcuts"
            empty_text = (f"No {noun} match \u201c{self.search_text}\u201d" if self.search_text
                          else ("No automations yet" if is_automations else "No shortcuts here yet"))
            empty_label = Gtk.Label(label=empty_text)
            empty_label.add_css_class("empty-state")
            empty_label.set_xalign(0.0)
            self.content_box.append(empty_label)
            return

        flow_box = Gtk.FlowBox()
        flow_box.set_valign(Gtk.Align.START)
        flow_box.set_max_children_per_line(5)
        flow_box.set_min_children_per_line(2)
        flow_box.set_homogeneous(True)
        flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        flow_box.set_row_spacing(16)
        flow_box.set_column_spacing(16)

        build_tile = self._build_automation_tile if is_automations else self._build_tile
        for item in items:
            flow_box.append(build_tile(item))

        self.content_box.append(flow_box)

    # Shortcut tiles
    def _build_tile(self, shortcut):
        button = Gtk.Button()
        button.set_has_frame(False)
        button.add_css_class("shortcut-tile")
        button.add_css_class(shortcut.color_class)
        unavailable = action_library.find_unavailable_step(shortcut.steps)
        if unavailable is not None:
            button.add_css_class("tile-disabled")
            button.set_tooltip_text(
                f"\u201c{unavailable.name}\u201d needs \u201c{unavailable.required_command}\u201d, "
                f"which isn't installed. Running this may fail."
            )
        button.set_size_request(150, 104)
        button.connect("clicked", lambda b: self._on_run_item_requested(shortcut, b))
        self._attach_tile_drag(button, shortcut.uid)

        overlay = Gtk.Overlay()

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.add_css_class("tile-content")
        content.set_hexpand(True)
        content.set_vexpand(True)

        icon = Gtk.Image.new_from_icon_name(shortcut.icon_name)
        icon.set_pixel_size(26)
        icon.set_halign(Gtk.Align.START)
        icon.set_valign(Gtk.Align.START)
        content.append(icon)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        content.append(spacer)

        label = Gtk.Label(label=shortcut.name)
        label.set_wrap(True)
        label.set_xalign(0.0)
        label.set_justify(Gtk.Justification.LEFT)
        label.add_css_class("tile-label")
        content.append(label)

        button.set_child(content)
        overlay.set_child(button)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("view-more-symbolic")
        menu_button.set_has_frame(False)
        menu_button.add_css_class("tile-menu-dot")
        menu_button.set_halign(Gtk.Align.END)
        menu_button.set_valign(Gtk.Align.START)
        menu_button.set_popover(self._build_tile_popover(shortcut))
        overlay.add_overlay(menu_button)

        self._attach_tile_drop(overlay, self.shortcuts, shortcut)
        return overlay

    # Drag to reorder for shortcut and automation tiles
    # reordering works on the master list since filtering never reorders
    def _attach_tile_drag(self, widget, uid):
        # Set an explicit drag icon or GTK shows the uid text instead of the tile
        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        press_pos = {"x": 0, "y": 0}

        def on_prepare(source, x, y):
            press_pos["x"], press_pos["y"] = x, y
            return Gdk.ContentProvider.new_for_value(GObject.Value(str, uid))

        def on_drag_begin(source, drag):
            widget.add_css_class("shortcut-tile-dragging")
            source.set_icon(Gtk.WidgetPaintable.new(widget), int(press_pos["x"]), int(press_pos["y"]))

        def on_drag_end(source, drag, delete_data):
            widget.remove_css_class("shortcut-tile-dragging")

        drag_source.connect("prepare", on_prepare)
        drag_source.connect("drag-begin", on_drag_begin)
        drag_source.connect("drag-end", on_drag_end)
        widget.add_controller(drag_source)

    def _attach_tile_drop(self, widget, master_list, target_item):
        drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

        def on_enter(_t, _x, _y):
            widget.add_css_class("shortcut-tile-drop-target")
            return Gdk.DragAction.MOVE

        def on_leave(_t):
            widget.remove_css_class("shortcut-tile-drop-target")

        def on_drop(_t, value, _x, _y):
            widget.remove_css_class("shortcut-tile-drop-target")
            if self._reorder_item(master_list, value, target_item):
                self._persist()
                self._rebuild_content()
                return True
            return False

        drop_target.connect("enter", on_enter)
        drop_target.connect("leave", on_leave)
        drop_target.connect("drop", on_drop)
        widget.add_controller(drop_target)

    def _reorder_item(self, master_list, dragged_uid, target_item):
        if target_item.uid == dragged_uid:
            return False
        src_idx = next((i for i, item in enumerate(master_list) if item.uid == dragged_uid), None)
        if src_idx is None:
            return False
        dst_idx = master_list.index(target_item)
        popped = master_list.pop(src_idx)
        if src_idx < dst_idx:
            dst_idx -= 1
        master_list.insert(dst_idx, popped)
        return True

    def _move_visible(self, item, master_list, visible_list, delta):
        """Move item up or down relative to its visible neighbor
        same as dragging a tile onto it"""
        idx = visible_list.index(item)
        swap_idx = idx + delta
        if not (0 <= swap_idx < len(visible_list)):
            return
        other = visible_list[swap_idx]
        if delta < 0:
            self._reorder_item(master_list, item.uid, other)
        else:
            self._reorder_item(master_list, other.uid, item)
        self._persist()
        self._rebuild_content()

    def _build_tile_popover(self, shortcut):
        popover = Gtk.Popover()
        popover.set_has_arrow(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def item(label_text, handler, sensitive=True):
            b = Gtk.Button(label=label_text)
            b.set_has_frame(False)
            b.add_css_class("popover-menu-item")
            b.get_child().set_xalign(0.0)
            b.set_sensitive(sensitive)

            def wrapped(_b):
                popover.popdown()
                handler()

            b.connect("clicked", wrapped)
            box.append(b)

        visible = self._visible_shortcuts()
        idx = visible.index(shortcut) if shortcut in visible else -1

        item("Run", lambda: self._on_run_item_requested(shortcut))
        item("Move Up", lambda: self._move_visible(shortcut, self.shortcuts, self._visible_shortcuts(), -1),
             sensitive=idx > 0)
        item("Move Down", lambda: self._move_visible(shortcut, self.shortcuts, self._visible_shortcuts(), 1),
             sensitive=0 <= idx < len(visible) - 1)
        item("Edit", lambda: self._on_edit_shortcut(shortcut))
        item("Duplicate", lambda: self._on_duplicate_shortcut(shortcut))
        item("Rename", lambda: self._on_rename_shortcut(shortcut))
        item("Details", lambda: show_details_dialog(self, shortcut))
        item("Delete", lambda: self._on_delete_shortcut(shortcut))

        popover.set_child(box)
        return popover

    # Shortcut actions
    def _on_new_shortcut(self):
        folder = self.current_folder or (self.folders[0] if self.folders else "My Shortcuts")
        self._open_editor(Shortcut(name="New Shortcut", folder=folder), is_new=True)

    def _on_edit_shortcut(self, shortcut):
        self._open_editor(shortcut, is_new=False)

    def _open_editor(self, shortcut, is_new):
        def on_save(edited):
            if is_new:
                if edited.folder not in self.folders:
                    self.folders.append(edited.folder)
                self.shortcuts.append(edited)
            else:
                for i, s in enumerate(self.shortcuts):
                    if s.uid == edited.uid:
                        self.shortcuts[i] = edited
                        break
            self._persist()
            self._rebuild_nav()
            self._rebuild_content()

        def on_cancel():
            pass

        editor = EditorWindow(self, shortcut, on_save, on_cancel)
        editor.present()

    def _on_duplicate_shortcut(self, shortcut):
        copy = Shortcut.from_dict(shortcut.to_dict())
        copy.uid = uuid.uuid4().hex[:8]
        copy.name = f"{shortcut.name} Copy"
        self.shortcuts.append(copy)
        self._persist()
        self._rebuild_nav()
        self._rebuild_content()

    def _on_rename_shortcut(self, shortcut):
        def done(text):
            name = (text or "").strip()
            if name:
                shortcut.name = name
                self._persist()
                self._rebuild_content()
        show_prompt_dialog(self, "Rename shortcut", shortcut.name, done)

    def _on_delete_shortcut(self, shortcut):
        def confirmed():
            self.shortcuts = [s for s in self.shortcuts if s.uid != shortcut.uid]
            self._persist()
            self._rebuild_nav()
            self._rebuild_content()
        show_confirm_dialog(self, f"Delete \u201c{shortcut.name}\u201d?",
                             "This shortcut will be deleted.", confirmed)

    # Running for shortcuts and automations
    def _on_run_item_requested(self, item, button=None):
        if _shortcut_needs_confirm(item):
            show_confirm_dialog(self, f"Run \u201c{item.name}\u201d?",
                                 f"Are you sure you want to run {item.name.lower()}?",
                                 lambda: self._run_and_flash(item, button))
        else:
            self._run_and_flash(item, button)

    def _run_and_flash(self, item, button):
        # No op actions give no feedback so flash the drop ring as a ran signal
        if button is not None:
            button.add_css_class("shortcut-tile-drop-target")
            GLib.timeout_add(220, lambda: (button.remove_css_class("shortcut-tile-drop-target"), False)[1])
        runner.run_async(self, item)

    # Automation tiles
    def _build_automation_tile(self, automation):
        button = Gtk.Button()
        button.set_has_frame(False)
        button.add_css_class("shortcut-tile")
        button.add_css_class(automation_widgets.trigger_color_class(automation.trigger_type))
        unavailable = action_library.find_unavailable_step(automation.steps)
        if not automation.enabled or unavailable is not None:
            button.add_css_class("tile-disabled")
        if unavailable is not None:
            button.set_tooltip_text(
                f"\u201c{unavailable.name}\u201d needs \u201c{unavailable.required_command}\u201d, "
                f"which isn't installed. Running this may fail."
            )
        button.set_size_request(150, 104)
        button.connect("clicked", lambda b: self._on_run_item_requested(automation, b))
        self._attach_tile_drag(button, automation.uid)

        overlay = Gtk.Overlay()

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.add_css_class("tile-content")
        content.set_hexpand(True)
        content.set_vexpand(True)

        icon = Gtk.Image.new_from_icon_name(automation_widgets.trigger_icon_name(automation.trigger_type))
        icon.set_pixel_size(26)
        icon.set_halign(Gtk.Align.START)
        icon.set_valign(Gtk.Align.START)
        content.append(icon)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        content.append(spacer)

        label = Gtk.Label(label=automation.name)
        label.set_wrap(True)
        label.set_xalign(0.0)
        label.set_justify(Gtk.Justification.LEFT)
        label.add_css_class("tile-label")
        content.append(label)

        trigger_label = Gtk.Label(label=automation_widgets.describe_trigger(automation))
        trigger_label.set_wrap(True)
        trigger_label.set_xalign(0.0)
        trigger_label.set_justify(Gtk.Justification.LEFT)
        trigger_label.add_css_class("tile-sublabel")
        content.append(trigger_label)

        button.set_child(content)
        overlay.set_child(button)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("view-more-symbolic")
        menu_button.set_has_frame(False)
        menu_button.add_css_class("tile-menu-dot")
        menu_button.set_halign(Gtk.Align.END)
        menu_button.set_valign(Gtk.Align.START)
        menu_button.set_popover(self._build_automation_popover(automation))
        overlay.add_overlay(menu_button)

        self._attach_tile_drop(overlay, self.automations, automation)
        return overlay

    def _build_automation_popover(self, automation):
        popover = Gtk.Popover()
        popover.set_has_arrow(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        def item(label_text, handler, sensitive=True):
            b = Gtk.Button(label=label_text)
            b.set_has_frame(False)
            b.add_css_class("popover-menu-item")
            b.get_child().set_xalign(0.0)
            b.set_sensitive(sensitive)

            def wrapped(_b):
                popover.popdown()
                handler()

            b.connect("clicked", wrapped)
            box.append(b)

        visible = self._visible_automations()
        idx = visible.index(automation) if automation in visible else -1

        item("Run", lambda: self._on_run_item_requested(automation))
        item("Move Up", lambda: self._move_visible(automation, self.automations, self._visible_automations(), -1),
             sensitive=idx > 0)
        item("Move Down", lambda: self._move_visible(automation, self.automations, self._visible_automations(), 1),
             sensitive=0 <= idx < len(visible) - 1)
        item("Edit", lambda: self._on_edit_automation(automation))
        item("Duplicate", lambda: self._on_duplicate_automation(automation))
        item("Rename", lambda: self._on_rename_automation(automation))
        item("Turn Off" if automation.enabled else "Turn On", lambda: self._on_toggle_automation(automation))
        item("Details", lambda: show_automation_details_dialog(
            self, automation, automation_widgets.describe_trigger(automation)))
        item("Delete", lambda: self._on_delete_automation(automation))

        popover.set_child(box)
        return popover

    # Automation actions
    def _on_new_automation(self):
        self._open_automation_editor(Automation(name="New Automation"), is_new=True)

    def _on_edit_automation(self, automation):
        self._open_automation_editor(automation, is_new=False)

    def _open_automation_editor(self, automation, is_new):
        def on_save(edited):
            if is_new:
                self.automations.append(edited)
            else:
                for i, a in enumerate(self.automations):
                    if a.uid == edited.uid:
                        self.automations[i] = edited
                        break
            self._persist()
            self._rebuild_nav()
            self._rebuild_content()

        def on_cancel():
            pass

        editor = AutomationEditorWindow(self, automation, on_save, on_cancel)
        editor.present()

    def _on_duplicate_automation(self, automation):
        copy = Automation.from_dict(automation.to_dict())
        copy.uid = uuid.uuid4().hex[:8]
        copy.name = f"{automation.name} Copy"
        self.automations.append(copy)
        self._persist()
        self._rebuild_nav()
        self._rebuild_content()

    def _on_rename_automation(self, automation):
        def done(text):
            name = (text or "").strip()
            if name:
                automation.name = name
                self._persist()
                self._rebuild_content()
        show_prompt_dialog(self, "Rename automation", automation.name, done)

    def _on_toggle_automation(self, automation):
        automation.enabled = not automation.enabled
        self._persist()
        self._rebuild_content()

    def _on_delete_automation(self, automation):
        def confirmed():
            self.automations = [a for a in self.automations if a.uid != automation.uid]
            self._persist()
            self._rebuild_nav()
            self._rebuild_content()
        show_confirm_dialog(self, f"Delete \u201c{automation.name}\u201d?",
                             "This automation will be deleted.", confirmed)

    # Called on the GLib main loop when a trigger fires
    def _on_automation_fired(self, automation):
        if automation.ask_before_running or _shortcut_needs_confirm(automation):
            self.present()  # surface the prompt even if minimized
            show_confirm_dialog(self, automation.name, "Run this automation now?",
                                 lambda: runner.run_async(self, automation))
        else:
            system_actions.notify("Running Automation", automation.name)
            runner.run_async(self, automation)
