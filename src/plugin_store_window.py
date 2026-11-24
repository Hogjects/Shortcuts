import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

import plugin_manager
import plugin_store
from dialogs import show_confirm_dialog, show_message_dialog


class StoreWindow(Gtk.Window):
    """Lists the plugins the hosted catalog offers and installs or updates them
    on_changed fires after any change to the action library
    Network work runs on a worker thread and the install itself runs on the main thread"""

    def __init__(self, parent, on_changed):
        super().__init__(transient_for=parent, modal=True, title="Browse Plugins")
        self.set_default_size(560, 480)
        self.on_changed = on_changed
        self._entries = []
        self._busy = False
        self._closed = False  # set once the window closes so late network results are dropped
        self.connect("close-request", self._on_close_request)

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

        self._load_catalog()

    def _build_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.add_css_class("editor-header")
        header.set_margin_top(10)
        header.set_margin_bottom(10)
        header.set_margin_start(14)
        header.set_margin_end(14)

        title = Gtk.Label(label="Browse Plugins")
        title.add_css_class("editor-name-entry")
        title.set_hexpand(True)
        title.set_xalign(0.0)
        header.append(title)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda b: self._load_catalog())
        header.append(refresh_btn)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda b: self.close())
        header.append(close_btn)

        return header

    def _on_close_request(self, _window):
        self._closed = True
        return False

    # Background work

    def _run_async(self, work, done, discard=None):
        """Runs work on a thread then calls done with result and error on the main thread
        discard cleans up a good result nobody will use because the window closed first"""
        def worker():
            try:
                result, error = work(), None
            except plugin_store.StoreError as exc:
                result, error = None, str(exc)
            except Exception as exc:  # noqa: BLE001
                result, error = None, f"Something went wrong: {exc}"

            def deliver():
                if self._closed:
                    if discard is not None and error is None:
                        discard(result)
                else:
                    done(result, error)
                return False

            GLib.idle_add(deliver)

        threading.Thread(target=worker, daemon=True).start()

    # List

    def _clear(self):
        child = self._list_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt

    def _show_message(self, text, retry=False):
        self._clear()
        label = Gtk.Label(label=text)
        label.add_css_class("empty-state")
        label.set_xalign(0.0)
        label.set_wrap(True)
        self._list_box.append(label)
        if retry:
            retry_btn = Gtk.Button(label="Try Again")
            retry_btn.set_halign(Gtk.Align.START)
            retry_btn.connect("clicked", lambda b: self._load_catalog())
            self._list_box.append(retry_btn)

    def _load_catalog(self):
        self._show_message("Loading\u2026")
        self._run_async(plugin_store.fetch_catalog, self._on_catalog_loaded)

    def _on_catalog_loaded(self, entries, error):
        if error:
            self._show_message(error, retry=True)
            return
        self._entries = entries
        self._render()

    def _render(self):
        if not self._entries:
            self._show_message("The catalog doesn\u2019t have any plugins yet.")
            return
        self._clear()
        installed = {info.id: info for info in plugin_manager.list_installed()}
        for entry in self._entries:
            self._list_box.append(self._build_row(entry, installed.get(entry.id)))

    # Rows styled like the installed plugin cards
    def _build_row(self, entry, installed):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("step-card")
        card.add_css_class("tile-gray")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        name_label = Gtk.Label(label=f"{entry.name}  \u00b7  v{entry.version}")
        name_label.add_css_class("step-title")
        name_label.set_xalign(0.0)
        name_label.set_hexpand(True)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        top.append(name_label)

        button = Gtk.Button()
        button.set_valign(Gtk.Align.CENTER)
        if installed is None:
            button.set_label("Install")
            button.add_css_class("suggested-action")
        elif plugin_store.version_key(entry.version) > plugin_store.version_key(installed.version):
            button.set_label("Update")
            button.add_css_class("suggested-action")
        else:
            button.set_label("Installed")
            button.set_sensitive(False)
        button.connect("clicked", lambda b, e=entry: self._on_install_clicked(e, b))
        top.append(button)

        card.append(top)

        meta_bits = []
        if entry.author:
            meta_bits.append(f"by {entry.author}")
        if entry.category:
            meta_bits.append(entry.category)
        if installed is not None:
            meta_bits.append(f"installed: v{installed.version}")
        if meta_bits:
            meta = Gtk.Label(label="  \u00b7  ".join(meta_bits))
            meta.add_css_class("tile-sublabel")
            meta.set_xalign(0.0)
            card.append(meta)

        if entry.description:
            desc = Gtk.Label(label=entry.description)
            desc.add_css_class("branch-end-label")
            desc.set_xalign(0.0)
            desc.set_wrap(True)
            card.append(desc)

        return card

    # Install

    def _on_install_clicked(self, entry, button):
        if self._busy:
            return
        lines = [f"{entry.name} \u00b7 v{entry.version}"]
        if entry.author:
            lines.append(f"by {entry.author}")
        if entry.description:
            lines.append(entry.description)
        lines.append(
            "\nPlugins can run any command on your computer, just like "
            "this app's own actions do. Only install plugins from people "
            "you trust."
        )
        show_confirm_dialog(self, "Install this plugin?", "\n".join(lines),
                            lambda: self._start_install(entry, button))

    def _start_install(self, entry, button):
        self._busy = True
        button.set_sensitive(False)
        button.set_label("Installing\u2026")
        self._run_async(lambda: plugin_store.download(entry), self._on_downloaded,
                        discard=plugin_store.remove_download)

    def _on_downloaded(self, path, error):
        self._busy = False
        if error:
            show_message_dialog(self, "Couldn\u2019t install plugin", error)
            self._render()
            return
        try:
            info = plugin_manager.install_from_zip(path)  # main thread: registers actions and runs plugin code
        except plugin_manager.PluginError as exc:
            show_message_dialog(self, "Couldn\u2019t install plugin", str(exc))
            self._render()
            return
        finally:
            plugin_store.remove_download(path)

        self._render()
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
