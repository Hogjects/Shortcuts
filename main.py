import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, Gdk

from main_window import MainWindow

APP_ID = "com.local.shortcuts"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(BASE_DIR, "style.css")


class ShortcutsApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", False)
        self._load_css()

    def do_activate(self):
        window = self.get_active_window() or MainWindow(self)
        window.present()

    def _load_css(self):
        provider = Gtk.CssProvider()
        with open(CSS_PATH, "rb") as f:
            provider.load_from_data(f.read())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


if __name__ == "__main__":
    app = ShortcutsApp()
    sys.exit(app.run(sys.argv))
