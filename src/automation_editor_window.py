import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

import action_library as lib
import action_widgets as widgets
import automation_widgets
import runner
from dialogs import show_confirm_dialog
from models import Automation


class AutomationEditorWindow(Gtk.Window):
    def __init__(self, app_window, automation, on_save, on_cancel):
        super().__init__(transient_for=app_window, modal=True, title="Edit Automation")
        self.set_default_size(980, 720)

        # Work on a copy so Cancel discards changes
        self.automation = Automation.from_dict(automation.to_dict())
        self._original = self.automation.to_dict()
        self.on_save = on_save
        self.on_cancel = on_cancel
        self._resolved = False

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        root.append(self._build_header())
        root.append(Gtk.Separator())
        root.append(self._build_trigger_area())
        root.append(Gtk.Separator())

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True, vexpand=True)
        root.append(body)

        self._library_panel = widgets.LibraryPanel(self._add_top_level_action)
        body.append(self._library_panel.widget)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        self._canvas = widgets.StepsCanvas(self)
        body.append(self._canvas.widget)

        self.connect("close-request", self._on_close_request)
        self._rebuild_canvas()

    # Header
    def _build_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.add_css_class("editor-header")
        header.set_margin_top(10)
        header.set_margin_bottom(10)
        header.set_margin_start(14)
        header.set_margin_end(14)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: self._cancel())
        header.append(cancel_btn)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(self.automation.name)
        self.name_entry.set_hexpand(True)
        self.name_entry.add_css_class("editor-name-entry")
        header.append(self.name_entry)

        run_btn = Gtk.Button(label="Run")
        run_btn.add_css_class("suggested-action")
        run_btn.connect("clicked", lambda b: runner.run_async(self, self.automation))
        header.append(run_btn)

        done_btn = Gtk.Button(label="Done")
        done_btn.add_css_class("suggested-action")
        done_btn.connect("clicked", lambda b: self._save())
        header.append(done_btn)

        return header

    # Trigger and Ask Before Running
    def _build_trigger_area(self):
        area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        area.add_css_class("editor-header")
        area.set_margin_top(4)
        area.set_margin_bottom(14)
        area.set_margin_start(14)
        area.set_margin_end(14)

        area.append(automation_widgets.build_trigger_section(self.automation, lambda: None))
        area.append(widgets.build_toggle_row(
            "Ask Before Running", self.automation.ask_before_running,
            lambda active: setattr(self.automation, "ask_before_running", active)))

        return area

    # Steps
    def _add_top_level_action(self, action_id):
        self.automation.steps.append(lib.make_instance(action_id))
        self._rebuild_canvas()

    def _rebuild_canvas(self):
        self._canvas.rebuild(self.automation.steps)

    def request_refresh(self):
        self._rebuild_canvas()

    # Variables
    def available_variables_before(self, target_uid):
        return widgets.variables_before(self.automation.steps, target_uid)

    def _save(self):
        self._resolved = True
        self.automation.name = self.name_entry.get_text().strip() or "New Automation"
        self.on_save(self.automation)
        self.close()

    def _current_dict(self):
        d = self.automation.to_dict()
        d["name"] = self.name_entry.get_text().strip() or "New Automation"
        return d

    def _is_dirty(self):
        return self._current_dict() != self._original

    def _discard_and(self, then):
        self._resolved = True
        self.on_cancel()
        then()

    def _cancel(self):
        if self._is_dirty():
            show_confirm_dialog(self, "Discard changes?",
                                 "Your edits to this automation will be lost.",
                                 lambda: self._discard_and(self.close))
        else:
            self._discard_and(self.close)

    def _on_close_request(self, _win):
        if self._resolved:
            return False
        if self._is_dirty():
            show_confirm_dialog(self, "Discard changes?",
                                 "Your edits to this automation will be lost.",
                                 lambda: self._discard_and(self.close))
            return True  # block this close and reclose once confirmed
        self._discard_and(lambda: None)
        return False
