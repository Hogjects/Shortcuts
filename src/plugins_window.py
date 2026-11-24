import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango

import plugin_manager
from dialogs import show_confirm_dialog, show_message_dialog


class PluginsWindow(Gtk.Window):
    """Lists installed plugins and lets the user import or toggle or remove them
    on_changed fires after any change to the action library"""

    def __init__(self, app_window, on_changed):
        super().__init__(transient_for=app_window, modal=True, title="Plugins")
        self.set_default_size(560, 480)
        self.on_changed = on_changed
        self._chooser = None  # keeps the file chooser alive until it responds

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        root.append(self._build_header())
        root.append(Gtk.Separator())

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        root.append(scroller)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._list_box.set_margin_top(16)
        self._list_box.set_margin_bottom(16)
        self._list_box.set_margin_start(20)
        self._list_box.set_margin_end(20)
        scroller.set_child(self._list_box)

        self._refresh()

    def _build_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.add_css_class("editor-header")
        header.set_margin_top(10)
        header.set_margin_bottom(10)
        header.set_margin_start(14)
        header.set_margin_end(14)

        title = Gtk.Label(label="Plugins")
        title.add_css_class("editor-name-entry")
        title.set_hexpand(True)
        title.set_xalign(0.0)
        header.append(title)

        import_btn = Gtk.Button(label="Import Plugin\u2026")
        import_btn.add_css_class("suggested-action")
        import_btn.connect("clicked", lambda b: self._on_import())
        header.append(import_btn)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda b: self.close())
        header.append(close_btn)

        return header

    def _refresh(self):
        child = self._list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt

        plugins = plugin_manager.list_installed()
        if not plugins:
            empty = Gtk.Label(label="No plugins installed yet. Import a .zip to add more actions.")
            empty.add_css_class("empty-state")
            empty.set_xalign(0.0)
            self._list_box.append(empty)
            return

        for info in plugins:
            self._list_box.append(self._build_row(info))

    # Plugin rows styled like step cards
    def _build_row(self, info):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("step-card")
        card.add_css_class("tile-gray")
        if not info.enabled:
            card.add_css_class("step-card-unavailable")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        name_label = Gtk.Label(label=f"{info.name}  \u00b7  v{info.version}")
        name_label.add_css_class("step-title")
        name_label.set_xalign(0.0)
        name_label.set_hexpand(True)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        top.append(name_label)

        switch = Gtk.Switch()
        switch.set_active(info.enabled)
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_tooltip_text("Enable this plugin's actions")
        switch.connect("notify::active", lambda w, p, pid=info.id: self._on_toggle(pid, w.get_active()))
        top.append(switch)

        remove_btn = Gtk.Button()
        remove_btn.set_icon_name("user-trash-symbolic")
        remove_btn.set_has_frame(False)
        remove_btn.add_css_class("step-icon-button")
        remove_btn.set_tooltip_text("Remove")
        remove_btn.connect("clicked", lambda b, pid=info.id, name=info.name: self._on_remove(pid, name))
        top.append(remove_btn)

        card.append(top)

        meta_bits = []
        if info.author:
            meta_bits.append(f"by {info.author}")
        if info.action_count or not info.trigger_count:
            meta_bits.append(f"{info.action_count} action{'s' if info.action_count != 1 else ''}")
        if info.trigger_count:
            meta_bits.append(f"{info.trigger_count} trigger{'s' if info.trigger_count != 1 else ''}")
        if not info.enabled:
            meta_bits.append("off")
        meta = Gtk.Label(label="  \u00b7  ".join(meta_bits))
        meta.add_css_class("tile-sublabel")
        meta.set_xalign(0.0)
        card.append(meta)

        if info.description:
            desc = Gtk.Label(label=info.description)
            desc.add_css_class("branch-end-label")
            desc.set_xalign(0.0)
            desc.set_wrap(True)
            card.append(desc)

        return card

    def _on_toggle(self, plugin_id, enabled):
        error = plugin_manager.set_enabled(plugin_id, enabled)
        if error:
            show_message_dialog(self, "Couldn\u2019t enable plugin", error)
        self._refresh()
        self.on_changed()

    def _on_remove(self, plugin_id, name):
        def confirmed():
            plugin_manager.uninstall(plugin_id)
            self._refresh()
            self.on_changed()
        show_confirm_dialog(
            self, f"Remove \u201c{name}\u201d?",
            "Its actions will disappear from the library. Any shortcut or "
            "automation step using one will stop doing anything until "
            "it's reinstalled.",
            confirmed)

    def _on_import(self):
        chooser = Gtk.FileChooserNative.new(
            "Import Plugin", self, Gtk.FileChooserAction.OPEN, "Import", "Cancel")
        zip_filter = Gtk.FileFilter()
        zip_filter.set_name("Plugin (*.zip)")
        zip_filter.add_pattern("*.zip")
        chooser.add_filter(zip_filter)

        def on_response(dlg, response):
            if response == Gtk.ResponseType.ACCEPT:
                gfile = dlg.get_file()
                path = gfile.get_path() if gfile else None
                if path:
                    self._confirm_and_install(path)
            self._chooser = None

        chooser.connect("response", on_response)
        self._chooser = chooser
        chooser.show()

    def _confirm_and_install(self, path):
        try:
            preview = plugin_manager.peek_manifest(path)
        except plugin_manager.PluginError as exc:
            show_message_dialog(self, "Can\u2019t install this plugin", str(exc))
            return

        lines = [f"{preview.name} \u00b7 v{preview.version}"]
        if preview.author:
            lines.append(f"by {preview.author}")
        if preview.description:
            lines.append(preview.description)
        lines.append(
            "\nPlugins can run any command on your computer, just like "
            "this app's own actions do. Only install plugins from people "
            "you trust."
        )

        show_confirm_dialog(self, "Install this plugin?", "\n".join(lines),
                             lambda: self._do_install(path))

    def _do_install(self, path):
        try:
            info = plugin_manager.install_from_zip(path)
        except plugin_manager.PluginError as exc:
            show_message_dialog(self, "Couldn\u2019t install plugin", str(exc))
            return
        self._refresh()
        self.on_changed()
        added_bits = []
        if info.action_count or not info.trigger_count:
            added_bits.append(f"{info.action_count} action{'s' if info.action_count != 1 else ''}")
        if info.trigger_count:
            added_bits.append(f"{info.trigger_count} trigger{'s' if info.trigger_count != 1 else ''}")
        show_message_dialog(
            self, f"\u201c{info.name}\u201d installed",
            f"Added {' and '.join(added_bits)} to the library."
        )
