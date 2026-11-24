"""Runs a Shortcut or Automation off the GTK main thread
wires up prompts and shows errors in a dialog"""
import threading

from gi.repository import GLib

import dialogs
import run_engine


def run_async(parent, item):
    ctx = run_engine.RunContext(ask_text=dialogs.make_ask_text(parent))

    def worker():
        try:
            run_engine.run_shortcut(item, ctx)
        except Exception as exc:
            error_message = str(exc)
            GLib.idle_add(lambda: dialogs.show_error_dialog(parent, error_message))

    threading.Thread(target=worker, daemon=True).start()
