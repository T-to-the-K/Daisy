import math
import time
import urllib.parse

import cairo
from gi.repository import Gdk, GLib, Gtk

R_OUTER = 170
R_INNER = 78
SIZE = 2 * (R_OUTER + 26)
PAGE = 8

FILL = (0.10, 0.10, 0.12, 0.86)
STROKE = (1.0, 1.0, 1.0, 0.22)
HOT_FILL = (1.0, 0.45, 0.10, 0.95)
HOT_STROKE = (1.0, 0.75, 0.45, 0.9)
TEXT = (0.92, 0.92, 0.94, 1.0)
HOT_TEXT = (0.12, 0.08, 0.05, 1.0)


class WheelWindow(Gtk.Window):
    def __init__(self, on_pick, on_paths):
        Gtk.Window.__init__(self, type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_app_paintable(True)
        self.set_size_request(SIZE, SIZE)
        self.resize(SIZE, SIZE)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        self.entries = []
        self.all_entries = []
        self.page = 0
        self.center = (0, 0)
        self.pointer = (0, 0)
        self.hover = -1
        self.paths = None
        self.dropping = False
        self.on_pick = on_pick
        self.on_paths = on_paths
        self.open_t = 0.0
        self._anim_id = None
        self._hot_amount = 0.0
        self._last_hover = -1

        self.connect("draw", self._draw)
        self.connect("drag-motion", self._drag_motion)
        self.connect("drag-drop", self._drag_drop)
        self.connect("drag-data-received", self._drag_data)
        self.connect("drag-leave", self._drag_leave)
        self.connect("scroll-event", self._scroll)
        self.connect("hide", lambda *a: self._stop_anim())

        self.drag_dest_set(
            Gtk.DestDefaults.MOTION,
            [Gtk.TargetEntry.new("text/uri-list", 0, 0)],
            Gdk.DragAction.COPY,
        )

    def place(self, center, entries):
        self.center = center
        self.all_entries = entries
        self.page = 0
        self._apply_page()
        self.hover = -1
        self.paths = None
        self.dropping = False
        self._peeking = False
        self._hot_amount = 0.0
        self.open_t = 0.0
        x = center[0] - SIZE // 2
        y = center[1] - SIZE // 2
        self.move(x, y)
        self.show_all()
        self._start_anim()
        self.queue_draw()

    def _start_anim(self):
        if self._anim_id is None:
            self.open_t = time.time()
            self._anim_id = GLib.timeout_add(16, self._tick)

    def _stop_anim(self):
        if self._anim_id is not None:
            GLib.source_remove(self._anim_id)
            self._anim_id = None

    def _tick(self):
        target = 1.0 if self.hover >= 0 else 0.0
        self._hot_amount += (target - self._hot_amount) * 0.35
        if abs(target - self._hot_amount) < 0.01:
            self._hot_amount = target
        self.queue_draw()
        return True

    def set_entries(self, entries):
        self.all_entries = entries
        self.page = 0
        self._apply_page()
        self.hover = -1
        self.queue_draw()

    def _apply_page(self):
        pages = max((len(self.all_entries) + PAGE - 1) // PAGE, 1)
        if self.page >= pages:
            self.page = pages - 1
        if self.page < 0:
            self.page = 0
        start = self.page * PAGE
        self.entries = self.all_entries[start:start + PAGE]

    def _page_count(self):
        return max((len(self.all_entries) + PAGE - 1) // PAGE, 1)

    def _scroll(self, widget, event):
        if self._page_count() <= 1:
            return False
        if event.direction == Gdk.ScrollDirection.UP:
            self.page -= 1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.page += 1
        else:
            return False
        self._apply_page()
        self.hover = -1
        self.queue_draw()
        return True

    def page_by(self, delta):
        if self._page_count() <= 1:
            return False
        self.page += delta
        self._apply_page()
        self.hover = -1
        self.queue_draw()
        return True

    def _wedge_for(self, px, py):
        if not self.entries:
            return -1
        cx, cy = self.center
        dx, dy = px - cx, py - cy
        dist = math.hypot(dx, dy)
        if dist < R_INNER * 0.55 or dist > R_OUTER + 20:
            return -1
        angle = math.degrees(math.atan2(dy, dx)) % 360
        step = 360.0 / len(self.entries)
        start = -90.0 - step / 2.0
        index = int((angle - start) % 360.0 // step)
        return index if 0 <= index < len(self.entries) else -1

    def _drag_motion(self, widget, context, x, y, time):
        px = self.center[0] - SIZE // 2 + x
        py = self.center[1] - SIZE // 2 + y
        self.pointer = (px, py)
        index = self._wedge_for(px, py)
        if index != self.hover:
            self.hover = index
            self.queue_draw()
        if self.paths is None and not self._peeking:
            self._peeking = True
            target = Gdk.Atom.intern("text/uri-list", False)
            self.drag_get_data(context, target, time)
        Gdk.drag_status(context, Gdk.DragAction.COPY, time)
        return True

    def _drag_drop(self, widget, context, x, y, time):
        self.dropping = True
        if self.paths is None:
            target = Gdk.Atom.intern("text/uri-list", False)
            self.drag_get_data(context, target, time)
            return True
        return self._finish(context, time)

    def commit(self):
        if not self.paths or not (0 <= self.hover < len(self.entries)):
            return False
        entry = self.entries[self.hover]
        paths = self.paths
        GLib.idle_add(self.on_pick, entry, paths)
        return True

    def _drag_data(self, widget, context, x, y, data, info, time):
        paths = []
        uris = data.get_uris()
        if uris:
            for uri in uris:
                if uri.startswith("file://"):
                    paths.append(urllib.parse.unquote(uri[7:]))
        if not paths:
            text = data.get_text() or ""
            paths = [
                urllib.parse.unquote(line.strip()[7:])
                for line in text.splitlines()
                if line.strip().startswith("file://")
            ]
        paths = [p for p in paths if p]
        self.paths = paths
        self._peeking = False
        if self.dropping:
            self.dropping = False
            self._finish(context, time)
        else:
            self.on_paths(paths)

    def _finish(self, context, time):
        ok = self.commit()
        Gtk.drag_finish(context, ok, False, time)
        return True

    def _drag_leave(self, widget, context, time):
        if self.hover != -1:
            self.hover = -1
            self.queue_draw()

    def _wedge_path(self, cr, index, grow, extra_inner=0.0):
        count = max(len(self.entries), 1)
        step = 2 * math.pi / count
        mid = -math.pi / 2 + index * step
        half = step / 2 * 0.86
        outer = R_OUTER + grow
        inner = R_INNER - grow * 0.3 + extra_inner
        cx, cy = SIZE / 2.0, SIZE / 2.0
        a0, a1 = mid - half, mid + half
        cr.new_sub_path()
        cr.arc(cx, cy, outer, a0, a1)
        cr.arc_negative(cx, cy, inner, a1, a0)
        cr.close_path()

    def _draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        now = time.time()
        if self.open_t:
            progress = min((now - self.open_t) / 0.18, 1.0)
        else:
            progress = 1.0
        ease = 1.0 - (1.0 - progress) ** 3
        alpha = ease
        inner_extra = (1.0 - ease) * R_INNER * 0.4
        pulse = 0.5 + 0.5 * math.sin(now * 5.0)

        for index, entry in enumerate(self.entries):
            hot = index == self.hover
            heat = self._hot_amount if hot else 0.0
            grow = (10 + 3 * pulse) * heat
            cr.new_path()
            self._wedge_path(cr, index, grow, inner_extra)
            if hot:
                cr.set_source_rgba(1.0, 0.45, 0.10, 0.95 * alpha)
                cr.fill_preserve()
                glow = 0.75 + 0.25 * pulse
                cr.set_source_rgba(1.0, 0.75 * glow, 0.45 * glow, 0.9 * alpha)
            else:
                cr.set_source_rgba(FILL[0], FILL[1], FILL[2], FILL[3] * alpha)
                cr.fill_preserve()
                cr.set_source_rgba(STROKE[0], STROKE[1], STROKE[2], STROKE[3] * alpha)
            cr.set_line_width(1.2)
            cr.stroke()

            count = max(len(self.entries), 1)
            step = 2 * math.pi / count
            mid = -math.pi / 2 + index * step
            radius = (R_INNER + R_OUTER) / 2.0 + grow * 0.5
            tx = SIZE / 2.0 + math.cos(mid) * radius
            ty = SIZE / 2.0 + math.sin(mid) * radius
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(15 + 2 * heat)
            label = entry["label"]
            box = cr.text_extents(label)
            if hot:
                cr.set_source_rgba(0.12, 0.08, 0.05, alpha)
            else:
                cr.set_source_rgba(TEXT[0], TEXT[1], TEXT[2], TEXT[3] * alpha)
            cr.move_to(tx - box.width / 2.0 - box.x_bearing * 0, ty + box.height / 2.0)
            cr.show_text(label)

        cr.new_path()
        cr.arc(SIZE / 2.0, SIZE / 2.0, R_INNER * 0.55, 0, 2 * math.pi)
        cr.set_source_rgba(0.05, 0.05, 0.07, 0.80 * alpha)
        cr.fill()

        spin = now * 0.8
        cr.new_path()
        cr.arc(SIZE / 2.0, SIZE / 2.0, R_INNER * 0.42, spin, spin + math.pi * 0.7)
        cr.set_source_rgba(1.0, 0.62, 0.28, (0.35 + 0.25 * pulse) * alpha)
        cr.set_line_width(2.0)
        cr.stroke()
        cr.new_path()
        cr.arc(SIZE / 2.0, SIZE / 2.0, R_INNER * 0.42, spin + math.pi, spin + math.pi * 1.7)
        cr.stroke()

        pages = self._page_count()
        if pages > 1:
            cr.select_font_face(
                "Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
            )
            cr.set_font_size(13)
            label = "%d / %d" % (self.page + 1, pages)
            box = cr.text_extents(label)
            cr.set_source_rgba(TEXT[0], TEXT[1], TEXT[2], TEXT[3] * alpha)
            cr.move_to(SIZE / 2.0 - box.width / 2.0, SIZE / 2.0 + box.height / 2.0)
            cr.show_text(label)
        return False
