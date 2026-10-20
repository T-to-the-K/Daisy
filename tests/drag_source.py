#!/usr/bin/env python3
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk


class DragSource(Gtk.Window):
    def __init__(self, path):
        Gtk.Window.__init__(self, title="dragme")
        self.path = path
        self.set_default_size(180, 120)
        self.add(Gtk.Label(label="drag me\n" + path.split("/")[-1]))
        self.connect("button-press-event", self._press)
        self.connect("drag-data-get", self._data_get)
        self.connect("drag-end", lambda w, ctx: print("drag-end", flush=True))

    def _press(self, widget, event):
        print("press at", event.x, event.y, flush=True)
        target = Gtk.TargetEntry.new("text/uri-list", 0, 0)
        tlist = Gtk.TargetList.new([target])
        self.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [target], Gdk.DragAction.COPY)
        self.drag_begin_with_coordinates(
            tlist, Gdk.DragAction.COPY, 1, event, int(event.x), int(event.y)
        )
        print("drag_begin called", flush=True)
        return True

    def _data_get(self, widget, context, data, info, time):
        print("data_get requested, sending", self.path, flush=True)
        data.set_uris(["file://" + self.path])


if __name__ == "__main__":
    win = DragSource(sys.argv[1])
    win.show_all()
    win.move(300, 300)
    Gtk.main()
