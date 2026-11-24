import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib


def show_error_dialog(parent, message):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Action failed",
        secondary_text=message,
    )
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.show()


def show_details_dialog(parent, shortcut):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=shortcut.name,
        secondary_text=f"Folder: {shortcut.folder}\nSteps: {len(shortcut.steps)}",
    )
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.show()


def show_automation_details_dialog(parent, automation, trigger_description):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=automation.name,
        secondary_text=f"Trigger: {trigger_description}\nSteps: {len(automation.steps)}",
    )
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.show()


def show_message_dialog(parent, title, message):
    """OK only dialog explaining why something did not happen"""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text=title,
        secondary_text=message,
    )
    dialog.connect("response", lambda d, r: d.destroy())
    dialog.show()


def show_confirm_dialog(parent, title, message, on_confirmed):
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text=title,
        secondary_text=message,
    )

    def on_response(dlg, response):
        dlg.destroy()
        if response == Gtk.ResponseType.OK:
            on_confirmed()

    dialog.connect("response", on_response)
    dialog.show()


def show_prompt_dialog(parent, prompt, default_text, on_done):
    """Small text entry dialog calling on_done with the text or the default if cancelled"""
    dialog = Gtk.Dialog(transient_for=parent, modal=True, title=prompt)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("OK", Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)

    content = dialog.get_content_area()
    content.set_margin_top(14)
    content.set_margin_bottom(14)
    content.set_margin_start(14)
    content.set_margin_end(14)
    content.set_spacing(8)

    label = Gtk.Label(label=prompt)
    label.set_xalign(0.0)
    content.append(label)

    entry = Gtk.Entry()
    entry.set_text(default_text or "")
    entry.set_activates_default(True)
    entry.set_width_chars(28)
    content.append(entry)

    def on_response(dlg, response):
        text = entry.get_text() if response == Gtk.ResponseType.OK else default_text
        dlg.destroy()
        on_done(text)

    dialog.connect("response", on_response)
    dialog.show()
    entry.grab_focus()


def make_ask_text(parent):
    """Returns a callable for RunContext.ask_text that prompts on the main thread
    and blocks the worker thread until answered"""
    def ask_text(prompt, default):
        result = {}
        done = threading.Event()

        def show():
            show_prompt_dialog(parent, prompt, default,
                                lambda text: (result.update(value=text), done.set()))
            return False

        GLib.idle_add(show)
        done.wait()
        return result.get("value", default)
    return ask_text
