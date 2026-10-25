import threading
import time

from Xlib import X, display
from Xlib.ext import record
from Xlib.protocol import rq
from Xlib.XK import string_to_keysym


class HotkeyGrab(threading.Thread):
    def __init__(self, keyname, modifiers, callback):
        super().__init__(daemon=True)
        self.keyname = keyname
        self.modifiers = modifiers
        self.callback = callback
        self._display = None
        self._last_fire = 0.0

    def run(self):
        self._display = display.Display()
        root = self._display.screen().root
        keycode = self._display.keysym_to_keycode(
            string_to_keysym(self.keyname)
        )
        locks = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]
        for lock in locks:
            root.grab_key(
                keycode,
                self.modifiers | lock,
                True,
                X.GrabModeAsync,
                X.GrabModeAsync,
            )
        self._display.sync()
        while True:
            try:
                event = self._display.next_event()
            except Exception as error:
                print("hotkey loop died:", error, flush=True)
                return
            if event.type == X.KeyPress:
                now = time.monotonic()
                if now - self._last_fire < 0.35:
                    continue
                self._last_fire = now
                print("hotkey fired", flush=True)
                self.callback()

    def stop(self):
        if self._display is None:
            return
        root = self._display.screen().root
        keycode = self._display.keysym_to_keycode(
            string_to_keysym(self.keyname)
        )
        locks = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]
        for lock in locks:
            root.ungrab_key(keycode, self.modifiers | lock)
        self._display.sync()
        self._display.close()


class XMonitor:
    def __init__(self, on_event):
        self.on_event = on_event
        self.display = display.Display()
        self.context = None
        self.keycodes = {}
        for name, symbol in (
            ("shift", "Shift_L"),
            ("ctrl", "Control_L"),
            ("alt", "Alt_L"),
            ("escape", "Escape"),
        ):
            code = self.display.keysym_to_keycode(string_to_keysym(symbol))
            self.keycodes[code] = name

    def start(self):
        self.context = self.display.record_create_context(
            0,
            [record.AllClients],
            [
                {
                    "core_requests": (0, 0),
                    "core_replies": (0, 0),
                    "ext_requests": (0, 0, 0, 0),
                    "ext_replies": (0, 0, 0, 0),
                    "delivered_events": (0, 0),
                    "device_events": (X.KeyPress, X.MotionNotify),
                    "errors": (0, 0),
                    "client_started": False,
                    "client_died": False,
                }
            ],
        )
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        self.display.record_enable_context(self.context, self._callback)

    def _callback(self, reply):
        if reply.category != record.FromServer or not reply.data:
            return
        data = reply.data
        while data:
            event, data = rq.EventField("event").parse_binary_value(
                data, self.display.display, None, None
            )
            kind = type(event).__name__
            x, y = event.root_x, event.root_y
            if kind == "ButtonPress" and event.detail == 1:
                self.on_event("press", x, y)
            elif kind == "ButtonRelease" and event.detail == 1:
                self.on_event("release", x, y)
            elif kind == "ButtonPress" and event.detail in (4, 5):
                self.on_event("scroll", -1 if event.detail == 4 else 1, x, y)
            elif kind == "MotionNotify":
                self.on_event("motion", x, y)
            elif event.detail in self.keycodes:
                name = self.keycodes[event.detail]
                if kind == "KeyPress":
                    self.on_event("key", name, x, y)
                elif kind == "KeyRelease":
                    self.on_event("keyup", name, x, y)

    def stop(self):
        if self.context:
            self.display.record_disable_context(self.context)
            self.display.flush()
