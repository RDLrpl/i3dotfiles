#!/usr/bin/env python3
import gi
import os
import signal
import fcntl
import time
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib
import i3ipc
import threading

ICON_SIZE = 22
TRAY_ICON_SIZE = 20
BAR_HEIGHT = 32
LOCK_PATH = "/tmp/i3-icon-bar.lock"
PID_PATH = "/tmp/i3-icon-bar.pid"


def process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def kill_old_instance():
    if not os.path.exists(PID_PATH):
        return
    try:
        with open(PID_PATH) as f:
            old_pid = int(f.read().strip() or 0)
    except (ValueError, FileNotFoundError):
        return
    if not old_pid or old_pid == os.getpid():
        return
    if not process_alive(old_pid):
        return
    try:
        os.kill(old_pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(50):
        if not process_alive(old_pid):
            return
        time.sleep(0.05)
    try:
        os.kill(old_pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    for _ in range(20):
        if not process_alive(old_pid):
            return
        time.sleep(0.05)

kill_old_instance()

lock_file = open(LOCK_PATH, "w")
fcntl.flock(lock_file, fcntl.LOCK_EX)
with open(PID_PATH, "w") as f:
    f.write(str(os.getpid()))

i3 = i3ipc.Connection()
theme = Gtk.IconTheme.get_default()
_desktop_icon_cache = {}

def find_icon_name(wm_class):
    if not wm_class:
        return None
    if wm_class in _desktop_icon_cache:
        return _desktop_icon_cache[wm_class]
    icon_name = None
    for app in Gio.AppInfo.get_all():
        try:
            startup_class = app.get_startup_wm_class()
        except AttributeError:
            startup_class = None
        if startup_class and startup_class.lower() == wm_class.lower():
            icon = app.get_icon()
            if icon:
                names = icon.get_names() if hasattr(icon, "get_names") else [str(icon)]
                icon_name = names[0] if names else None
            break
    if not icon_name and theme.has_icon(wm_class.lower()):
        icon_name = wm_class.lower()
    _desktop_icon_cache[wm_class] = icon_name
    return icon_name

def load_pixbuf(icon_name_or_wm_class, size=ICON_SIZE):
    icon_name = icon_name_or_wm_class or "application-x-executable"
    try:
        return theme.load_icon(icon_name, size, Gtk.IconLookupFlags.FORCE_SIZE)
    except GLib.Error:
        pass
    try:
        return theme.load_icon(icon_name.lower(), size, Gtk.IconLookupFlags.FORCE_SIZE)
    except GLib.Error:
        return theme.load_icon("application-x-executable", size, Gtk.IconLookupFlags.FORCE_SIZE)

class KnownApp:
    __slots__ = ("display_name", "icon_name")
    def __init__(self, display_name, icon_name):
        self.display_name = display_name
        self.icon_name = icon_name

def build_known_apps():
    known = {}
    for app in Gio.AppInfo.get_all():
        try:
            exe = app.get_executable()
        except Exception:
            exe = None
        if not exe:
            continue
        exe_name = os.path.basename(exe)
        if exe_name and exe_name not in known:
            icon = app.get_icon()
            icon_name = None
            if icon:
                names = icon.get_names() if hasattr(icon, "get_names") else [str(icon)]
                icon_name = names[0] if names else None
            known[exe_name] = KnownApp(app.get_display_name(), icon_name)
    return known

_known_apps = build_known_apps()

def make_box(orientation, spacing=0):
    box = Gtk.Box()
    box.set_orientation(orientation)
    box.set_spacing(spacing)
    return box

def make_separator(orientation):
    sep = Gtk.Separator()
    sep.set_orientation(orientation)
    return sep

class IconBar(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_keep_above(True)
        self.stick()
        screen = Gdk.Screen.get_default()
        self.screen_w = screen.get_width()
        self.screen_h = screen.get_height()
        self.set_default_size(self.screen_w, BAR_HEIGHT)
        self.root_box = make_box(Gtk.Orientation.HORIZONTAL, spacing=8)
        self.root_box.set_margin_start(6)
        self.root_box.set_margin_end(6)
        self.root_box.set_margin_top(2)
        self.root_box.set_margin_bottom(2)
        self.add(self.root_box)
        self.left_spacer = make_box(Gtk.Orientation.HORIZONTAL)
        self.root_box.pack_start(self.left_spacer, True, True, 0)
        self.box = make_box(Gtk.Orientation.HORIZONTAL, spacing=8)
        self.root_box.pack_start(self.box, False, False, 0)
        self.right_spacer = make_box(Gtk.Orientation.HORIZONTAL)
        self.root_box.pack_start(self.right_spacer, True, True, 0)
        self.connect("realize", self.on_realize)
        self.connect("destroy", lambda *_: Gtk.main_quit())
        self.show_all()

    def on_realize(self, *_):
        self.reposition()

    def reposition(self):
        self.move(0, self.screen_h - BAR_HEIGHT)

    def rebuild(self, i3conn):
        for child in self.box.get_children():
            self.box.remove(child)
        tree = i3conn.get_tree()
        workspaces = i3conn.get_workspaces()
        for ws in workspaces:
            ws_node = next((w for w in tree.workspaces() if w.name == ws.name), None)
            leaves = ws_node.leaves() if ws_node else []
            wm_class = leaves[0].window_class if leaves else None
            pixbuf = load_pixbuf(find_icon_name(wm_class))
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            num_label = Gtk.Label(label=ws.name)
            num_label.set_name("ws-number")
            item_box = make_box(Gtk.Orientation.VERTICAL, spacing=1)
            item_box.pack_start(image, False, False, 0)
            item_box.pack_start(num_label, False, False, 0)
            event_box = Gtk.EventBox()
            event_box.add(item_box)
            event_box.connect(
                "button-press-event",
                lambda _w, _e, name=ws.name: i3.command(f'workspace "{name}"'),
            )
            if ws.focused:
                event_box.set_opacity(1.0)
                num_label.set_markup(f"<b>{ws.name}</b>")
            elif ws.urgent:
                event_box.set_opacity(0.9)
                num_label.set_markup(f"<span foreground='red'>{ws.name}</span>")
            else:
                event_box.set_opacity(0.45)
                num_label.set_text(ws.name)
            self.box.pack_start(event_box, False, False, 0)
        self.show_all()
        GLib.idle_add(self.reposition)

win = IconBar()

def on_event(i3conn, e):
    GLib.idle_add(win.rebuild, i3conn)

def handle_sigterm(*_):
    GLib.idle_add(win.destroy)

signal.signal(signal.SIGTERM, handle_sigterm)

win.rebuild(i3)
for event in ["workspace", "window::new", "window::close", "window::move", "window::title"]:
    i3.on(event, on_event)

threading.Thread(target=i3.main, daemon=True).start()

Gtk.main()