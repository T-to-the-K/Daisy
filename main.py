import os
import signal
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk
from Xlib import X

import ops
from monitor import HotkeyGrab, XMonitor
from wheel import WheelWindow

DRAG_THRESHOLD = 8
MODIFIER_KIND = {"shift": "convert", "ctrl": "tool", "alt": "action"}
HOTKEY = ("w", X.ControlMask | X.Mod1Mask)


class FileWheel:
    def __init__(self):
        ops.build()
        self.button_down = False
        self.press_at = (0, 0)
        self.dragging = False
        self.slider_live = False
        self.pointer = (0, 0)
        self.wheel_kind = None
        self.wheel = WheelWindow(self._on_pick, self._on_paths)
        self.monitor = XMonitor(self._on_x_event)
        self.monitor.start()
        self.hotkey = HotkeyGrab(HOTKEY[0], HOTKEY[1], self._on_hotkey)
        self.hotkey.start()

    def _on_hotkey(self):
        GLib.idle_add(self._hotkey_show)

    def _hotkey_show(self):
        visible = self.wheel.get_visible()
        print(
            "hotkey_show visible=%s dragging=%s button=%s kind=%s"
            % (visible, self.dragging, self.button_down, self.wheel_kind),
            flush=True,
        )
        if visible:
            self._hide_wheel()
            return
        seat = Gdk.Display.get_default().get_default_seat()
        pointer = seat.get_pointer()
        _screen, x, y = pointer.get_position()
        self.pointer = (x, y)
        self._show_wheel("convert")

    def _on_x_event(self, kind, *args):
        GLib.idle_add(self._handle, kind, *args)

    def _handle(self, kind, *args):
        if kind == "press":
            self.button_down = True
            self.press_at = (args[0], args[1])
            self.dragging = False
            if self.wheel.get_visible() and self.wheel.slider_hit(*self.press_at):
                self.slider_live = True
                self.wheel.slider_begin(*self.press_at)
        elif kind == "motion":
            x, y = args
            self.pointer = (x, y)
            if self.slider_live:
                self.wheel.slider_set(x, y)
            elif self.wheel.get_visible():
                self.wheel.ring_hover(x, y)
            if self.button_down and not self.dragging and not self.slider_live:
                dx = x - self.press_at[0]
                dy = y - self.press_at[1]
                if (dx * dx + dy * dy) ** 0.5 > DRAG_THRESHOLD:
                    self.dragging = True
        elif kind == "scroll":
            delta = args[0]
            if self.wheel.get_visible():
                self.wheel.page_by(delta)
        elif kind == "release":
            x, y = args[0], args[1]
            if self.slider_live:
                self.slider_live = False
                self.wheel.slider_set(x, y)
                self.wheel.slider_end()
                self.button_down = False
                self.dragging = False
                print(
                    "compression=%.2f" % self.wheel.compression,
                    flush=True,
                )
                if self.wheel.mode == "level":
                    self._finish_level()
                return False
            was_dragging = self.dragging
            self.button_down = False
            self.dragging = False
            if self.wheel.get_visible() and self.wheel.mode == "level":
                return False
            if was_dragging and self.wheel.get_visible():
                if not self.wheel.commit():
                    self._hide_wheel()
            elif not was_dragging and self.wheel.get_visible():
                index = self.wheel.wedge_at(x, y)
                if index >= 0:
                    self.wheel.hover = index
                    self.wheel.commit()
            elif was_dragging:
                self._hide_wheel()
        elif kind == "key":
            name = args[0]
            if name == "escape":
                self._hide_wheel()
            elif self.dragging and name in MODIFIER_KIND:
                self._show_wheel(MODIFIER_KIND[name])
        elif kind == "keyup":
            pass
        return False

    def _show_wheel(self, kind):
        entries = ops.ops_for(kind)
        if not entries:
            return
        if self.wheel_kind == kind and self.wheel.get_visible():
            return
        self.wheel_kind = kind
        self.wheel.place(self.pointer, entries)
        GLib.timeout_add(45000, self._watchdog)

    def _watchdog(self):
        if self.wheel.mode == "level" and self.wheel.get_visible():
            return True
        if self.wheel.get_visible() and not self.button_down:
            self._hide_wheel()
        return False

    def _hide_wheel(self):
        self.wheel_kind = None
        if self.wheel.mode == "level":
            self.wheel.cancel_level()
        if self.wheel.get_visible():
            self.wheel.hide()

    def _on_paths(self, paths):
        if not self.wheel_kind:
            return
        entries = ops.ops_for(self.wheel_kind, paths)
        if entries:
            self.wheel.set_entries(entries)

    def _on_pick(self, entry, paths):
        if entry.get("leveled"):
            self.wheel.prompt_level(entry, paths)
            return
        self._hide_wheel()
        threading.Thread(
            target=self._run_job, args=(entry, paths, None), daemon=True
        ).start()

    def _finish_level(self):
        pending = self.wheel.pending
        level = self.wheel.compression
        self.wheel.cancel_level()
        self._hide_wheel()
        if not pending:
            return
        entry, paths = pending
        threading.Thread(
            target=self._run_job, args=(entry, paths, level), daemon=True
        ).start()

    def _run_job(self, entry, paths, level=None):
        try:
            made = ops.run_op(entry, paths, level)
        except Exception as error:
            notify("FileWheel", "%s failed: %s" % (entry["label"], error))
            return
        if made:
            names = ", ".join(os.path.basename(p) for p in made[:3])
            if len(made) > 3:
                names += " and %d more" % (len(made) - 3)
            notify("%s done" % entry["label"], names)
        else:
            notify("%s done" % entry["label"], "clipboard updated")


def notify(title, body):
    subprocess.Popen(
        ["notify-send", "--icon=folder-download", title, body],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    app = FileWheel()
    signal.signal(signal.SIGTERM, lambda *a: Gtk.main_quit())
    signal.signal(signal.SIGINT, lambda *a: Gtk.main_quit())
    try:
        Gtk.main()
    finally:
        app.monitor.stop()
        app.hotkey.stop()


if __name__ == "__main__":
    main()
