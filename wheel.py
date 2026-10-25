import io
import math
import time
import urllib.parse

import cairo
from PIL import Image, ImageFilter
from gi.repository import Gdk, GLib, Gtk

R_OUTER = 170
R_INNER = 78
SIZE = 2 * (R_OUTER + 26)
PAGE = 8
R_DIAL = R_OUTER + 14
RING_START = math.radians(135)
RING_SWEEP = math.radians(270)

ACCENT = (1.0, 0.56, 0.22)
TEXT = (0.98, 0.98, 1.0, 1.0)
HOT_TEXT = (0.11, 0.07, 0.03, 1.0)


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
        self._backdrop = None
        self._peeking = False
        self.compression = 0.5
        self.mode = "pick"
        self.dial_active = False
        self.dial_t = 0.0
        self.pending = None
        self._slider_active = False
        self._ring_hot = False
        self._font_options = cairo.FontOptions()
        self._font_options.set_antialias(cairo.ANTIALIAS_GRAY)

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
        self._reset_dial()
        self.hover = -1
        self.paths = None
        self.dropping = False
        self._peeking = False
        self._ring_hot = False
        self._slider_active = False
        self._hot_amount = 0.0
        self.open_t = 0.0
        if not self.get_visible():
            self._backdrop = self._grab_backdrop(center)
        x = center[0] - SIZE // 2
        y = center[1] - SIZE // 2
        self.move(x, y)
        self.show_all()
        self._start_anim()
        self.queue_draw()

    def _grab_backdrop(self, center):
        try:
            root = Gdk.get_default_root_window()
            x = center[0] - SIZE // 2
            y = center[1] - SIZE // 2
            pixbuf = Gdk.pixbuf_get_from_window(root, x, y, SIZE, SIZE)
            if pixbuf is None:
                return None
            ok, data = pixbuf.save_to_bufferv("png", [], [])
            if not ok:
                return None
            image = Image.open(io.BytesIO(data)).convert("RGB")
            small = image.resize(
                (max(1, SIZE // 6), max(1, SIZE // 6)), Image.BILINEAR
            ).filter(ImageFilter.GaussianBlur(5))
            image = small.resize((SIZE, SIZE), Image.BILINEAR)
            tint = Image.new("RGB", image.size, (22, 24, 34))
            image = Image.blend(image, tint, 0.20)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            buffer.seek(0)
            return cairo.ImageSurface.create_from_png(buffer)
        except Exception:
            return None

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

    def wedge_at(self, px, py):
        return self._wedge_for(px, py)

    def _reset_dial(self):
        self.mode = "pick"
        self.dial_active = False
        self.dial_t = 0.0
        self.pending = None
        self._slider_active = False
        self._ring_hot = False

    def prompt_level(self, entry, paths):
        self.mode = "level"
        self.dial_active = True
        self.dial_t = time.time()
        self.pending = (entry, paths)
        self.hover = -1
        self._hot_amount = 0.0
        self.queue_draw()

    def cancel_level(self):
        self.pending = None
        self._reset_dial()
        self.queue_draw()

    def slider_hit(self, px, py):
        if not self.dial_active:
            return False
        cx, cy = self.center
        dist = math.hypot(px - cx, py - cy)
        return abs(dist - R_DIAL) <= 13

    def slider_set(self, px, py):
        cx, cy = self.center
        angle = math.atan2(py - cy, px - cx)
        t = ((angle - RING_START) % (2 * math.pi)) / RING_SWEEP
        self.compression = max(0.0, min(1.0, t))
        self.queue_draw()
        return self.compression

    def slider_begin(self, px, py):
        self._slider_active = True
        self._ring_hot = True
        self.slider_set(px, py)

    def slider_end(self):
        self._slider_active = False
        self.queue_draw()

    def ring_hover(self, px, py):
        if not self.dial_active:
            return
        hot = self.slider_hit(px, py)
        if hot != self._ring_hot:
            self._ring_hot = hot
            self.queue_draw()

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
        half = step / 2 * 0.84
        outer = R_OUTER + grow
        inner = R_INNER - grow * 0.3 + extra_inner
        cx, cy = SIZE / 2.0, SIZE / 2.0
        a0, a1 = mid - half, mid + half
        cr.new_sub_path()
        cr.arc(cx, cy, outer, a0, a1)
        cr.arc_negative(cx, cy, inner, a1, a0)
        cr.close_path()

    def _draw_shadow(self, cr, alpha):
        cx, cy = SIZE / 2.0, SIZE / 2.0
        for i in range(12):
            radius = R_OUTER + 4 + i * 2.4
            strength = 0.032 * (1.0 - i / 12.0) * alpha
            cr.new_path()
            cr.arc(cx, cy + 4, radius, 0, 2 * math.pi)
            cr.set_source_rgba(0.0, 0.0, 0.0, strength)
            cr.fill()

    def _draw_backplate(self, cr, alpha, now):
        cx, cy = SIZE / 2.0, SIZE / 2.0
        radius = R_OUTER + 7

        cr.save()
        cr.new_path()
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.clip()

        if self._backdrop is not None:
            cr.set_source_surface(self._backdrop, 0, 0)
            cr.paint_with_alpha(1.0 * alpha)
        else:
            shade = cairo.RadialGradient(cx, cy - 40, 20, cx, cy, radius)
            shade.add_color_stop_rgba(0.0, 0.20, 0.21, 0.26, 0.92 * alpha)
            shade.add_color_stop_rgba(1.0, 0.06, 0.06, 0.09, 0.94 * alpha)
            cr.set_source(shade)
            cr.paint()

        depth = cairo.LinearGradient(0, cy - radius, 0, cy + radius)
        depth.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.11 * alpha)
        depth.add_color_stop_rgba(0.45, 0.0, 0.0, 0.0, 0.0)
        depth.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.26 * alpha)
        cr.set_source(depth)
        cr.paint()

        vignette = cairo.RadialGradient(cx, cy, radius * 0.52, cx, cy, radius)
        vignette.add_color_stop_rgba(0.0, 0.0, 0.0, 0.0, 0.0)
        vignette.add_color_stop_rgba(0.82, 0.0, 0.0, 0.0, 0.0)
        vignette.add_color_stop_rgba(1.0, 0.0, 0.0, 0.0, 0.26 * alpha)
        cr.set_source(vignette)
        cr.paint()

        sweep = cx + math.sin(now * 0.55) * radius * 0.8
        sheen = cairo.LinearGradient(sweep - 100, cy - radius, sweep + 100, cy + radius)
        sheen.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.0)
        sheen.add_color_stop_rgba(0.5, 1.0, 1.0, 1.0, 0.09 * alpha)
        sheen.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.0)
        cr.set_source(sheen)
        cr.paint()

        count = max(len(self.entries), 1)
        step = 2 * math.pi / count
        for i in range(count):
            angle = -math.pi / 2 + (i + 0.5) * step
            dx, dy = math.cos(angle), math.sin(angle)
            cr.new_path()
            cr.move_to(cx + dx * (R_INNER + 2), cy + dy * (R_INNER + 2))
            cr.line_to(cx + dx * (R_OUTER + 4), cy + dy * (R_OUTER + 4))
            cr.set_line_width(2.2)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.20 * alpha)
            cr.stroke()
            cr.new_path()
            cr.move_to(cx + dx * (R_INNER + 2) - dy * 1.2, cy + dy * (R_INNER + 2) + dx * 1.2)
            cr.line_to(cx + dx * (R_OUTER + 4) - dy * 1.2, cy + dy * (R_OUTER + 4) + dx * 1.2)
            cr.set_line_width(0.9)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.14 * alpha)
            cr.stroke()

        cr.restore()

        cr.new_path()
        cr.arc(cx, cy, radius - 0.8, 0, 2 * math.pi)
        cr.set_line_width(1.1)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.22 * alpha)
        cr.stroke()

        cr.new_path()
        cr.arc(cx, cy, radius - 0.8, math.radians(-152), math.radians(-28))
        cr.set_line_width(1.9)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.72 * alpha)
        cr.stroke()

        cr.new_path()
        cr.arc(cx, cy, radius - 0.8, math.radians(28), math.radians(152))
        cr.set_line_width(1.2)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.10 * alpha)
        cr.stroke()

    def _draw_wedge(self, cr, index, entry, alpha, now, pulse):
        hot = index == self.hover
        heat = self._hot_amount if hot else 0.0
        grow = (9 + 3 * pulse) * heat
        cx, cy = SIZE / 2.0, SIZE / 2.0

        self._wedge_path(cr, index, grow)
        base = cairo.LinearGradient(0, cy - R_OUTER, 0, cy + R_OUTER)
        base.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.075 * alpha)
        base.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.02 * alpha)
        cr.set_source(base)
        cr.fill()

        if hot:
            glow = 0.7 + 0.3 * pulse
            for spread, strength in ((22, 0.05), (14, 0.08), (7, 0.12)):
                self._wedge_path(cr, index, grow + spread * 0.35)
                cr.set_line_join(cairo.LINE_JOIN_ROUND)
                cr.set_line_width(spread)
                cr.set_source_rgba(ACCENT[0], ACCENT[1], ACCENT[2], strength * alpha)
                cr.stroke()

            self._wedge_path(cr, index, grow)
            blob = cairo.LinearGradient(0, cy - R_OUTER, 0, cy + R_OUTER)
            blob.add_color_stop_rgba(0.0, 1.0, 0.87, 0.66, 0.97 * alpha)
            blob.add_color_stop_rgba(0.30, ACCENT[0], ACCENT[1] + 0.14, ACCENT[2] + 0.20, 0.96 * alpha)
            blob.add_color_stop_rgba(0.72, ACCENT[0], ACCENT[1] - 0.02, ACCENT[2] - 0.02, 0.94 * alpha)
            blob.add_color_stop_rgba(1.0, 0.86, 0.36, 0.12, 0.95 * alpha)
            cr.set_source(blob)
            cr.fill_preserve()
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.set_line_width(14)
            cr.stroke()

            self._wedge_path(cr, index, grow)
            cr.save()
            cr.clip()
            dome = cairo.RadialGradient(
                cx, cy - R_OUTER * 0.55, 4, cx, cy - R_OUTER * 0.2, R_OUTER
            )
            dome.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.42 * alpha)
            dome.add_color_stop_rgba(0.5, 1.0, 1.0, 1.0, 0.06 * alpha)
            dome.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.0)
            cr.set_source(dome)
            cr.paint()
            cr.restore()

            self._wedge_path(cr, index, grow)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.set_line_width(1.6)
            cr.set_source_rgba(1.0, 0.94 * glow, 0.80 * glow, 0.95 * alpha)
            cr.stroke()

        count = max(len(self.entries), 1)
        step = 2 * math.pi / count
        mid = -math.pi / 2 + index * step
        radius = (R_INNER + R_OUTER) / 2.0 + grow * 0.5
        tx = cx + math.cos(mid) * radius
        ty = cy + math.sin(mid) * radius
        cr.set_font_options(self._font_options)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(15 + 2 * heat)
        label = entry["label"]
        box = cr.text_extents(label)
        size = 15 + 2 * heat
        while box.width > 96 and size > 11:
            size -= 1.5
            cr.set_font_size(size)
            box = cr.text_extents(label)
        lx = tx - box.width / 2.0
        ly = ty + box.height / 2.0
        cr.set_source_rgba(0.0, 0.0, 0.0, (0.50 if not hot else 0.26) * alpha)
        cr.move_to(lx + 0.8, ly + 0.9)
        cr.show_text(label)
        if hot:
            cr.set_source_rgba(HOT_TEXT[0], HOT_TEXT[1], HOT_TEXT[2], alpha)
        else:
            cr.set_source_rgba(TEXT[0], TEXT[1], TEXT[2], TEXT[3] * alpha)
        cr.move_to(lx, ly)
        cr.show_text(label)

    def _draw_core(self, cr, alpha, now, pulse):
        cx, cy = SIZE / 2.0, SIZE / 2.0
        radius = R_INNER * 0.60

        cr.new_path()
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.30 * alpha)
        cr.fill()

        glass = cairo.RadialGradient(
            cx - radius * 0.3, cy - radius * 0.4, 2, cx, cy, radius
        )
        glass.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.26 * alpha)
        glass.add_color_stop_rgba(0.35, 0.55, 0.58, 0.66, 0.34 * alpha)
        glass.add_color_stop_rgba(1.0, 0.05, 0.06, 0.09, 0.55 * alpha)
        cr.new_path()
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source(glass)
        cr.fill()

        cr.new_path()
        cr.arc(cx, cy, radius - 0.7, math.radians(-200), math.radians(-20))
        cr.set_line_width(1.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.55 * alpha)
        cr.stroke()

        cr.new_path()
        cr.arc(cx, cy, radius - 0.7, math.radians(20), math.radians(160))
        cr.set_line_width(1.0)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.12 * alpha)
        cr.stroke()

        spin = now * 0.8
        cr.set_line_width(2.6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.new_path()
        cr.arc(cx, cy, radius * 0.74, spin, spin + math.pi * 0.66)
        cr.set_source_rgba(ACCENT[0], ACCENT[1], ACCENT[2], (0.50 + 0.28 * pulse) * alpha)
        cr.stroke()
        cr.new_path()
        cr.arc(cx, cy, radius * 0.74, spin + math.pi, spin + math.pi * 1.66)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.18 * alpha)
        cr.stroke()

        pages = self._page_count()
        if pages > 1:
            gap = 10.0
            total = (pages - 1) * gap
            y = cy + radius * 0.44
            cr.new_path()
            for dot in range(pages):
                dx = cx - total / 2.0 + dot * gap
                cr.new_sub_path()
                cr.arc(dx, y, 2.1, 0, 2 * math.pi)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.28 * alpha)
            cr.fill()
            cr.new_path()
            cr.arc(cx - total / 2.0 + self.page * gap, y, 2.1, 0, 2 * math.pi)
            cr.set_source_rgba(ACCENT[0], ACCENT[1], ACCENT[2], 0.95 * alpha)
            cr.fill()

    def _draw_slider(self, cr, alpha):
        if not self.dial_active:
            return
        cx, cy = SIZE / 2.0, SIZE / 2.0
        now = time.time()
        prog = min(max((now - self.dial_t) / 0.26, 0.0), 1.0)
        if prog < 1.0:
            c1 = 2.2
            p = prog - 1.0
            ease = 1.0 + c1 * p ** 3 + (c1 + 1.0) * p ** 2
            grow = ease
        else:
            grow = 1.0
        alpha = alpha * prog
        start = RING_START
        end = RING_START + RING_SWEEP * grow
        span = (end - start) / RING_SWEEP
        hot = self._slider_active or self._ring_hot

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.new_path()
        cr.arc(cx, cy, R_DIAL, start, end)
        cr.set_line_width(11.0)
        cr.set_source_rgba(0.02, 0.03, 0.05, 0.34 * alpha)
        cr.stroke()
        cr.new_path()
        cr.arc(cx, cy, R_DIAL, start, end)
        cr.set_line_width(3.4)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.12 * alpha)
        cr.stroke()

        for i in range(11):
            major = i % 5 == 0
            a = start + RING_SWEEP * (i / 10.0) * grow
            r0 = R_DIAL + (5.2 if major else 4.0)
            r1 = R_DIAL + (8.2 if major else 6.4)
            cr.new_path()
            cr.move_to(cx + math.cos(a) * r0, cy + math.sin(a) * r0)
            cr.line_to(cx + math.cos(a) * r1, cy + math.sin(a) * r1)
            cr.set_line_width(1.4 if major else 1.0)
            cr.set_source_rgba(1.0, 1.0, 1.0, (0.30 if major else 0.15) * alpha)
            cr.stroke()

        value = start + RING_SWEEP * self.compression * grow
        if self.compression > 0.004:
            cr.new_path()
            cr.arc(cx, cy, R_DIAL, start, value)
            cr.set_line_width(4.4)
            cr.set_source_rgba(ACCENT[0], ACCENT[1], ACCENT[2], 0.92 * alpha)
            cr.stroke()

        if prog > 0.55:
            kx = cx + math.cos(value) * R_DIAL
            ky = cy + math.sin(value) * R_DIAL
            cr.new_path()
            cr.arc(kx, ky, 8.4, 0, 2 * math.pi)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.36 * alpha)
            cr.fill()
            knob = cairo.RadialGradient(kx - 2, ky - 3, 1, kx, ky, 6.6)
            knob.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.99 * alpha)
            knob.add_color_stop_rgba(0.55, 0.86, 0.88, 0.93, 0.96 * alpha)
            knob.add_color_stop_rgba(1.0, 0.40, 0.43, 0.50, 0.96 * alpha)
            cr.new_path()
            cr.arc(kx, ky, 6.0, 0, 2 * math.pi)
            cr.set_source(knob)
            cr.fill()
            cr.new_path()
            cr.arc(kx, ky, 6.0, 0, 2 * math.pi)
            cr.set_line_width(1.0)
            cr.set_source_rgba(ACCENT[0], ACCENT[1], ACCENT[2], (0.95 if hot else 0.55) * alpha)
            cr.stroke()

        if prog > 0.86:
            pct = "%d%%" % int(round(self.compression * 100))
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_options(self._font_options)
            cr.set_font_size(15)
            box = cr.text_extents(pct)
            tx = cx - box.width / 2.0
            ty = cy + 5
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.55 * alpha)
            cr.move_to(tx + 0.8, ty + 0.9)
            cr.show_text(pct)
            cr.set_source_rgba(ACCENT[0], ACCENT[1], ACCENT[2], 0.98 * alpha)
            cr.move_to(tx, ty)
            cr.show_text(pct)

    def _draw(self, widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        now = time.time()
        if self.open_t:
            progress = min((now - self.open_t) / 0.22, 1.0)
        else:
            progress = 1.0
        if progress >= 1.0:
            scale = 1.0
        else:
            c1 = 1.4
            c3 = c1 + 1.0
            p = progress - 1.0
            scale = 0.86 + 0.14 * (1.0 + c3 * p ** 3 + c1 * p ** 2)
        alpha = min(max(progress * 1.6, 0.0), 1.0)
        pulse = 0.5 + 0.5 * math.sin(now * 5.0)

        cr.save()
        cr.translate(SIZE / 2.0, SIZE / 2.0)
        cr.scale(scale, scale)
        cr.translate(-SIZE / 2.0, -SIZE / 2.0)

        self._draw_shadow(cr, alpha)
        self._draw_backplate(cr, alpha, now)
        cr.save()
        cr.new_path()
        cr.arc(SIZE / 2.0, SIZE / 2.0, R_OUTER + 7, 0, 2 * math.pi)
        cr.clip()
        for index, entry in enumerate(self.entries):
            self._draw_wedge(cr, index, entry, alpha, now, pulse)
        cr.restore()
        self._draw_core(cr, alpha, now, pulse)
        self._draw_slider(cr, alpha)
        cr.restore()
        return False
