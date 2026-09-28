"""
BGMI PERFORMANCE MONITOR
=========================
A single-file Kivy application that provides:
  - Floating (draggable, always-on-top-of-app) FPS counter
  - Live CPU / RAM / Battery / Temperature monitoring
  - Network ping + jitter graph
  - Session history (start/stop a session, stats get saved to disk)
  - Device performance benchmark (CPU / RAM / rendering test)
  - Game-specific graphics profiles (BGMI presets + recommendation engine)

Works on Desktop (Windows/Linux/Mac) for testing with `python main.py`
and can be packaged into an Android APK with Buildozer (see buildozer.spec
and BUILD_APK_README.txt / the provided .bat helper + Colab notebook).

Author: Generated for user request.
"""

import os
import io
import json
import time
import socket
import statistics
import threading
from collections import deque
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.utils import platform

# ----------------------------------------------------------------------
# Optional dependencies - the app must still run even if these are absent
# (e.g. on a bare desktop test run or a minimal Android build)
# ----------------------------------------------------------------------
try:
    import psutil
except Exception:
    psutil = None

try:
    from plyer import battery as plyer_battery
except Exception:
    plyer_battery = None

IS_ANDROID = platform == "android"

if not IS_ANDROID:
    try:
        Window.size = (420, 760)
    except Exception:
        pass

# ------------------------------------------------------------------
# COLORS / THEME
# ------------------------------------------------------------------
BG_DARK = (0.06, 0.07, 0.09, 1)
CARD_BG = (0.12, 0.13, 0.16, 1)
ACCENT = (1.0, 0.65, 0.0, 1)
GREEN = (0.25, 0.85, 0.35, 1)
YELLOW = (0.95, 0.85, 0.2, 1)
RED = (0.95, 0.25, 0.25, 1)
TEXT_MUTED = (0.7, 0.7, 0.75, 1)

Window.clearcolor = BG_DARK


# ------------------------------------------------------------------
# DATA STORAGE HELPERS
# ------------------------------------------------------------------
def get_data_dir():
    try:
        app = App.get_running_app()
        if app is not None:
            d = app.user_data_dir
            os.makedirs(d, exist_ok=True)
            return d
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


def get_data_file():
    return os.path.join(get_data_dir(), "bgmi_monitor_data.json")


DEFAULT_DATA = {
    "sessions": [],
    "active_profile": "Balanced",
    "custom_profiles": {},
    "last_benchmark": None,
    "ping_host": "8.8.8.8",
}


def load_data():
    path = get_data_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_DATA.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULT_DATA)


def save_data(data):
    try:
        with open(get_data_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Failed to save data:", e)


# ------------------------------------------------------------------
# SYSTEM METRIC HELPERS (with safe fallbacks so it works everywhere)
# ------------------------------------------------------------------
def get_cpu_percent():
    if psutil:
        try:
            return psutil.cpu_percent(interval=None)
        except Exception:
            pass
    try:
        with open("/proc/stat", "r") as f1:
            l1 = f1.readline().split()[1:]
        time.sleep(0.15)
        with open("/proc/stat", "r") as f2:
            l2 = f2.readline().split()[1:]
        l1 = list(map(int, l1))
        l2 = list(map(int, l2))
        idle1, idle2 = l1[3], l2[3]
        total1, total2 = sum(l1), sum(l2)
        diff_idle = idle2 - idle1
        diff_total = total2 - total1
        if diff_total <= 0:
            return 0.0
        return round((1 - diff_idle / diff_total) * 100, 1)
    except Exception:
        return None


def get_ram_percent():
    if psutil:
        try:
            return psutil.virtual_memory().percent
        except Exception:
            pass
    try:
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])
        total = meminfo.get("MemTotal")
        avail = meminfo.get("MemAvailable")
        if total and avail:
            return round((1 - avail / total) * 100, 1)
    except Exception:
        pass
    return None


def get_temperature():
    # Desktop / Linux sensors
    if psutil and hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            for _, entries in temps.items():
                if entries:
                    return round(entries[0].current, 1)
        except Exception:
            pass
    # Android: thermal zones exposed under /sys are usually readable
    try:
        for i in range(0, 6):
            path = f"/sys/class/thermal/thermal_zone{i}/temp"
            if os.path.exists(path):
                with open(path, "r") as f:
                    raw = f.read().strip()
                val = float(raw)
                if val > 1000:
                    val = val / 1000.0
                if 0 < val < 120:
                    return round(val, 1)
    except Exception:
        pass
    return None


def get_battery():
    """Returns (percent, is_charging, temperature_or_None)"""
    if plyer_battery:
        try:
            status = plyer_battery.status
            pct = status.get("percentage")
            charging = status.get("isCharging")
            temp = status.get("temperature")
            return pct, charging, temp
        except Exception:
            pass
    if psutil and hasattr(psutil, "sensors_battery"):
        try:
            b = psutil.sensors_battery()
            if b:
                return round(b.percent, 1), b.power_plugged, None
        except Exception:
            pass
    return None, None, None


def measure_latency(host="8.8.8.8", port=53, timeout=1.5):
    """Pseudo-ping using a raw TCP connect - works without shell/ping binary
    permissions, which is important on modern Android."""
    start = time.time()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return round((time.time() - start) * 1000, 1)
    except Exception:
        return None


# ------------------------------------------------------------------
# REUSABLE WIDGETS
# ------------------------------------------------------------------
class Card(BoxLayout):
    """A rounded, dark card container."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.padding = dp(10)
        self.spacing = dp(4)
        with self.canvas.before:
            Color(*CARD_BG)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._update, size=self._update)

    def _update(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size


class StatCard(Card):
    """Small card that shows a title and a big value (used on dashboard)."""

    def __init__(self, title, unit="", **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.title_lbl = Label(
            text=title, font_size="12sp", color=TEXT_MUTED, size_hint_y=0.4, bold=True
        )
        self.value_lbl = Label(text="--" + unit, font_size="22sp", color=(1, 1, 1, 1), bold=True)
        self.unit = unit
        self.add_widget(self.title_lbl)
        self.add_widget(self.value_lbl)

    def set_value(self, value, color=None, suffix=None):
        suffix = self.unit if suffix is None else suffix
        if value is None:
            self.value_lbl.text = "N/A"
        else:
            self.value_lbl.text = f"{value}{suffix}"
        if color:
            self.value_lbl.color = color


def status_color(value, warn=60, danger=85, invert=False):
    if value is None:
        return TEXT_MUTED
    if invert:
        if value <= 30:
            return RED
        if value <= 60:
            return YELLOW
        return GREEN
    if value >= danger:
        return RED
    if value >= warn:
        return YELLOW
    return GREEN


class SectionTitle(Label):
    def __init__(self, text="", **kwargs):
        super().__init__(
            text=text,
            font_size="18sp",
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=dp(36),
            halign="left",
            valign="middle",
            **kwargs,
        )
        self.bind(size=self._update_align)

    def _update_align(self, *a):
        self.text_size = self.size


class NavButton(Button):
    def __init__(self, text, **kwargs):
        super().__init__(
            text=text,
            font_size="12sp",
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            color=TEXT_MUTED,
            **kwargs,
        )

    def set_active(self, active):
        self.color = ACCENT if active else TEXT_MUTED


class PingGraph(Widget):
    """Simple canvas-based line graph for ping history."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = deque(maxlen=60)
        self.bind(size=self.redraw, pos=self.redraw)

    def add_point(self, value):
        self.data.append(value if value is not None else 0)
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        with self.canvas:
            Color(0.09, 0.10, 0.13, 1)
            Rectangle(pos=self.pos, size=self.size)
            pts = list(self.data)
            if len(pts) >= 2:
                maxv = max(max(pts), 50)
                x0, y0 = self.pos
                w, h = self.size
                n = len(pts)
                points = []
                for i, v in enumerate(pts):
                    x = x0 + (i / (n - 1)) * w
                    ratio = min(v / maxv, 1.0)
                    y = y0 + ratio * (h - dp(10)) + dp(5)
                    points.extend([x, y])
                Color(*GREEN)
                Line(points=points, width=dp(1.6))
            # baseline
            Color(0.3, 0.3, 0.35, 1)
            Line(points=[self.pos[0], self.pos[1] + dp(5),
                         self.pos[0] + self.size[0], self.pos[1] + dp(5)], width=1)


class FloatingFPSWidget(BoxLayout):
    """A draggable, semi-transparent FPS badge that floats above every
    screen of the app (added directly to the root FloatLayout)."""

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(6), **kwargs)
        with self.canvas.before:
            Color(0, 0, 0, 0.65)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._update_rect, size=self._update_rect)
        self.label = Label(text="FPS: --", font_size="16sp", bold=True, color=GREEN)
        self.sub_label = Label(text="drag me", font_size="9sp", color=TEXT_MUTED)
        self.add_widget(self.label)
        self.add_widget(self.sub_label)
        self._dragging = False
        self._offset = (0, 0)

    def _update_rect(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._dragging = True
            self._offset = (touch.x - self.x, touch.y - self.y)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._dragging:
            self.x = touch.x - self._offset[0]
            self.y = touch.y - self._offset[1]
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self._dragging:
            self._dragging = False
            return True
        return super().on_touch_up(touch)

    def set_fps(self, fps):
        self.label.text = f"FPS: {fps}"
        if fps >= 45:
            self.label.color = GREEN
        elif fps >= 25:
            self.label.color = YELLOW
        else:
            self.label.color = RED


# ------------------------------------------------------------------
# GAME PROFILES
# ------------------------------------------------------------------
PRESET_PROFILES = {
    "Battery Saver": {
        "Graphics": "Smooth", "FrameRate": "Medium", "Style": "Classic",
        "desc": "Lowest load, longest battery life. Best for weak / hot devices.",
        "min_score": 0,
    },
    "Balanced": {
        "Graphics": "Balanced", "FrameRate": "High", "Style": "Classic",
        "desc": "Good mix of visuals and smoothness for mid-range phones.",
        "min_score": 35,
    },
    "Performance": {
        "Graphics": "Smooth", "FrameRate": "Ultra", "Style": "Classic",
        "desc": "Prioritizes FPS for competitive play on solid hardware.",
        "min_score": 55,
    },
    "Extreme Performance": {
        "Graphics": "Smooth", "FrameRate": "Extreme", "Style": "Classic",
        "desc": "Maximum FPS. Requires a flagship-tier CPU/GPU.",
        "min_score": 80,
    },
    "HD Visuals": {
        "Graphics": "HD", "FrameRate": "High", "Style": "Realistic",
        "desc": "Sharper textures & lighting for high-end devices.",
        "min_score": 65,
    },
    "HDR Ultra": {
        "Graphics": "HDR", "FrameRate": "High", "Style": "Realistic",
        "desc": "Best possible visuals. Needs a very powerful device.",
        "min_score": 85,
    },
}


def recommend_profile(score):
    best = "Battery Saver"
    for name, p in PRESET_PROFILES.items():
        if score >= p["min_score"]:
            if p["min_score"] >= PRESET_PROFILES[best]["min_score"]:
                best = name
    return best


# ------------------------------------------------------------------
# SCREENS
# ------------------------------------------------------------------
class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))

        title = SectionTitle("BGMI Performance Monitor")
        subtitle = Label(
            text="Live device stats", font_size="12sp", color=TEXT_MUTED,
            size_hint_y=None, height=dp(20), halign="left"
        )
        subtitle.bind(size=lambda i, v: setattr(i, "text_size", v))
        root.add_widget(title)
        root.add_widget(subtitle)

        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, row_default_height=dp(90))
        grid.bind(minimum_height=grid.setter("height"))

        self.fps_card = StatCard("FPS")
        self.cpu_card = StatCard("CPU", unit="%")
        self.ram_card = StatCard("RAM", unit="%")
        self.battery_card = StatCard("BATTERY", unit="%")
        self.temp_card = StatCard("TEMPERATURE", unit=" C")
        self.ping_card = StatCard("PING", unit=" ms")

        for c in (self.fps_card, self.cpu_card, self.ram_card,
                  self.battery_card, self.temp_card, self.ping_card):
            grid.add_widget(c)

        root.add_widget(grid)

        # Session controls
        session_card = Card(orientation="vertical", size_hint_y=None, height=dp(120))
        session_title = Label(text="Session Recorder", bold=True, size_hint_y=None,
                               height=dp(24), color=(1, 1, 1, 1))
        self.session_status = Label(text="No active session", color=TEXT_MUTED,
                                     size_hint_y=None, height=dp(20), font_size="12sp")
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        self.session_btn = Button(text="Start Session", background_color=ACCENT,
                                   bold=True, on_release=self.toggle_session)
        btn_row.add_widget(self.session_btn)
        session_card.add_widget(session_title)
        session_card.add_widget(self.session_status)
        session_card.add_widget(btn_row)
        root.add_widget(session_card)

        toggle_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        self.fps_toggle_btn = Button(text="Hide Floating FPS", background_color=(0.2, 0.2, 0.25, 1),
                                      on_release=self.toggle_fps_widget)
        overlay_btn = Button(text="Enable System Overlay", background_color=(0.2, 0.2, 0.25, 1),
                              on_release=self.request_overlay_permission)
        toggle_row.add_widget(self.fps_toggle_btn)
        toggle_row.add_widget(overlay_btn)
        root.add_widget(toggle_row)

        root.add_widget(Widget())  # spacer
        self.add_widget(root)

    def toggle_session(self, *a):
        app = App.get_running_app()
        if not app.session_active:
            app.start_session()
            self.session_btn.text = "Stop Session"
            self.session_btn.background_color = RED
        else:
            app.stop_session()
            self.session_btn.text = "Start Session"
            self.session_btn.background_color = ACCENT

    def toggle_fps_widget(self, *a):
        app = App.get_running_app()
        visible = app.toggle_floating_fps()
        self.fps_toggle_btn.text = "Hide Floating FPS" if visible else "Show Floating FPS"

    def request_overlay_permission(self, *a):
        app = App.get_running_app()
        app.try_enable_system_overlay()


class NetworkScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        root.add_widget(SectionTitle("Network Monitor"))

        host_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.host_input = TextInput(text="8.8.8.8", multiline=False, font_size="14sp")
        set_btn = Button(text="Set Host", size_hint_x=0.35, background_color=ACCENT,
                          on_release=self.set_host)
        host_row.add_widget(self.host_input)
        host_row.add_widget(set_btn)
        root.add_widget(host_row)

        self.graph = PingGraph(size_hint_y=None, height=dp(200))
        root.add_widget(self.graph)

        stats_grid = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(90))
        self.ping_card = StatCard("PING", unit=" ms")
        self.jitter_card = StatCard("JITTER", unit=" ms")
        self.loss_card = StatCard("LOSS", unit="%")
        stats_grid.add_widget(self.ping_card)
        stats_grid.add_widget(self.jitter_card)
        stats_grid.add_widget(self.loss_card)
        root.add_widget(stats_grid)

        root.add_widget(Widget())
        self.add_widget(root)

    def set_host(self, *a):
        app = App.get_running_app()
        host = self.host_input.text.strip() or "8.8.8.8"
        app.ping_host = host
        app.data["ping_host"] = host
        save_data(app.data)
        app.ping_history.clear()
        self.graph.data.clear()


class HistoryScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        top_row = BoxLayout(size_hint_y=None, height=dp(36))
        top_row.add_widget(SectionTitle("Session History"))
        clear_btn = Button(text="Clear", size_hint=(None, None), size=(dp(70), dp(32)),
                            background_color=(0.3, 0.1, 0.1, 1), on_release=self.clear_history)
        top_row.add_widget(clear_btn)
        root.add_widget(top_row)

        scroll = ScrollView()
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=(0, dp(4)))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll.add_widget(self.list_box)
        root.add_widget(scroll)
        self.add_widget(root)

    def refresh(self):
        self.list_box.clear_widgets()
        app = App.get_running_app()
        sessions = list(reversed(app.data.get("sessions", [])))
        if not sessions:
            self.list_box.add_widget(Label(text="No sessions recorded yet.", color=TEXT_MUTED,
                                            size_hint_y=None, height=dp(40)))
            return
        for s in sessions:
            card = Card(orientation="vertical", size_hint_y=None, height=dp(120))
            header = Label(text=f"[b]{s.get('start','?')}[/b]  ({s.get('duration_sec',0)}s)",
                            markup=True, size_hint_y=None, height=dp(22),
                            color=(1, 1, 1, 1), font_size="13sp", halign="left")
            header.bind(size=lambda i, v: setattr(i, "text_size", v))
            stats = Label(
                text=(f"Avg FPS: {s.get('avg_fps','-')}  Min/Max: {s.get('min_fps','-')}/{s.get('max_fps','-')}\n"
                      f"Avg CPU: {s.get('avg_cpu','-')}%   Avg RAM: {s.get('avg_ram','-')}%\n"
                      f"Avg Ping: {s.get('avg_ping','-')} ms   Jitter: {s.get('avg_jitter','-')} ms"),
                color=TEXT_MUTED, font_size="12sp", halign="left", valign="top",
                size_hint_y=None, height=dp(78)
            )
            stats.bind(size=lambda i, v: setattr(i, "text_size", v))
            card.add_widget(header)
            card.add_widget(stats)
            self.list_box.add_widget(card)

    def clear_history(self, *a):
        app = App.get_running_app()
        app.data["sessions"] = []
        save_data(app.data)
        self.refresh()

    def on_pre_enter(self, *a):
        self.refresh()


class BenchmarkScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
        root.add_widget(SectionTitle("Device Benchmark"))
        desc = Label(
            text="Runs a short CPU, RAM and rendering test, then rates your\n"
                 "device and suggests the best BGMI graphics profile.",
            color=TEXT_MUTED, font_size="12sp", size_hint_y=None, height=dp(50), halign="left"
        )
        desc.bind(size=lambda i, v: setattr(i, "text_size", v))
        root.add_widget(desc)

        self.status_lbl = Label(text="Press 'Run Benchmark' to start", color=(1, 1, 1, 1),
                                 size_hint_y=None, height=dp(30))
        root.add_widget(self.status_lbl)

        self.run_btn = Button(text="Run Benchmark", background_color=ACCENT, bold=True,
                               size_hint_y=None, height=dp(48), on_release=self.start_benchmark)
        root.add_widget(self.run_btn)

        result_card = Card(orientation="vertical", size_hint_y=None, height=dp(230))
        self.cpu_res = Label(text="CPU Score: --", color=(1, 1, 1, 1), size_hint_y=None, height=dp(30))
        self.ram_res = Label(text="RAM Score: --", color=(1, 1, 1, 1), size_hint_y=None, height=dp(30))
        self.gpu_res = Label(text="Rendering Score: --", color=(1, 1, 1, 1), size_hint_y=None, height=dp(30))
        self.overall_res = Label(text="Overall Score: --", bold=True, color=ACCENT,
                                  size_hint_y=None, height=dp(34), font_size="18sp")
        self.tier_res = Label(text="Tier: --", color=(1, 1, 1, 1), size_hint_y=None, height=dp(30))
        self.rec_res = Label(text="Recommended Profile: --", color=GREEN, size_hint_y=None, height=dp(40),
                              halign="left")
        self.rec_res.bind(size=lambda i, v: setattr(i, "text_size", v))
        for w in (self.cpu_res, self.ram_res, self.gpu_res, self.overall_res, self.tier_res, self.rec_res):
            result_card.add_widget(w)
        root.add_widget(result_card)

        root.add_widget(Widget())
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        last = app.data.get("last_benchmark")
        if last:
            self.show_results(last, saved=True)

    def start_benchmark(self, *a):
        self.run_btn.disabled = True
        self.status_lbl.text = "Running CPU test..."
        app = App.get_running_app()
        threading.Thread(target=self._run_benchmark_thread, args=(app,), daemon=True).start()

    def _run_benchmark_thread(self, app):
        # CPU test
        cpu_score = self._cpu_bench(1.5)
        Clock.schedule_once(lambda dt: setattr(self.status_lbl, "text", "Running RAM test..."))
        ram_score = self._ram_bench(1.0)
        Clock.schedule_once(lambda dt: setattr(self.status_lbl, "text", "Running rendering test..."))
        gpu_score = self._gpu_bench_sync(app)

        overall = round(cpu_score * 0.4 + ram_score * 0.25 + gpu_score * 0.35, 1)
        tier = self._tier_for_score(overall)
        rec = recommend_profile(overall)

        result = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cpu_score": cpu_score, "ram_score": ram_score, "gpu_score": gpu_score,
            "overall": overall, "tier": tier, "recommended": rec,
        }
        app.data["last_benchmark"] = result
        save_data(app.data)
        Clock.schedule_once(lambda dt: self.show_results(result))

    def _cpu_bench(self, duration):
        start = time.time()
        x = 0
        count = 0
        while time.time() - start < duration:
            x = (x * 1103515245 + 12345) % 2147483647
            x ^= (x << 3) & 0xFFFFFFFF
            count += 1
        ops_per_sec = count / duration
        score = min(100, ops_per_sec / 90000 * 100)
        return round(score, 1)

    def _ram_bench(self, duration):
        start = time.time()
        count = 0
        buf = deque(maxlen=3000)
        while time.time() - start < duration:
            buf.append(bytearray(2048))
            count += 1
        ops_per_sec = count / duration
        score = min(100, ops_per_sec / 4000 * 100)
        return round(score, 1)

    def _gpu_bench_sync(self, app):
        # Measure real app FPS while it's under light synthetic load
        app.benchmark_mode = True
        samples = []
        end_time = time.time() + 2.0
        while time.time() < end_time:
            samples.append(app.current_fps)
            time.sleep(0.2)
        app.benchmark_mode = False
        avg_fps = statistics.mean(samples) if samples else 30
        score = min(100, avg_fps / 60 * 100)
        return round(score, 1)

    def _tier_for_score(self, score):
        if score >= 85:
            return "Flagship"
        if score >= 65:
            return "High-End"
        if score >= 40:
            return "Mid-Range"
        return "Entry-Level"

    def show_results(self, result, saved=False):
        self.run_btn.disabled = False
        self.status_lbl.text = "Last result (saved)" if saved else "Benchmark complete!"
        self.cpu_res.text = f"CPU Score: {result['cpu_score']}"
        self.ram_res.text = f"RAM Score: {result['ram_score']}"
        self.gpu_res.text = f"Rendering Score: {result['gpu_score']}"
        self.overall_res.text = f"Overall Score: {result['overall']}"
        self.tier_res.text = f"Tier: {result['tier']}"
        self.rec_res.text = f"Recommended Profile: {result['recommended']}"


class ProfilesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        root.add_widget(SectionTitle("Game Profiles (BGMI)"))
        self.info_lbl = Label(text="", color=GREEN, size_hint_y=None, height=dp(24), font_size="12sp")
        root.add_widget(self.info_lbl)

        scroll = ScrollView()
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll.add_widget(self.list_box)
        root.add_widget(scroll)
        self.add_widget(root)

    def on_pre_enter(self, *a):
        self.refresh()

    def refresh(self):
        app = App.get_running_app()
        active = app.data.get("active_profile", "Balanced")
        last_bench = app.data.get("last_benchmark")
        if last_bench:
            self.info_lbl.text = f"Recommended based on benchmark: {last_bench['recommended']}"
        else:
            self.info_lbl.text = "Run a benchmark for a personalized recommendation."

        self.list_box.clear_widgets()
        for name, p in PRESET_PROFILES.items():
            card = Card(orientation="vertical", size_hint_y=None, height=dp(120))
            top = BoxLayout(size_hint_y=None, height=dp(26))
            name_lbl = Label(text=name, bold=True, color=(1, 1, 1, 1), halign="left")
            name_lbl.bind(size=lambda i, v: setattr(i, "text_size", v))
            top.add_widget(name_lbl)
            if name == active:
                tag = Label(text="ACTIVE", color=ACCENT, size_hint_x=None, width=dp(70), font_size="11sp", bold=True)
                top.add_widget(tag)
            card.add_widget(top)

            details = Label(
                text=f"Graphics: {p['Graphics']}  |  FPS: {p['FrameRate']}  |  Style: {p['Style']}\n{p['desc']}",
                color=TEXT_MUTED, font_size="11sp", halign="left", valign="top", size_hint_y=None, height=dp(50)
            )
            details.bind(size=lambda i, v: setattr(i, "text_size", v))
            card.add_widget(details)

            btn = Button(text="Apply Profile", size_hint_y=None, height=dp(34),
                         background_color=(0.2, 0.2, 0.25, 1),
                         on_release=lambda inst, n=name: self.apply_profile(n))
            card.add_widget(btn)
            self.list_box.add_widget(card)

    def apply_profile(self, name):
        app = App.get_running_app()
        app.data["active_profile"] = name
        save_data(app.data)
        self.refresh()


# ------------------------------------------------------------------
# MAIN APP
# ------------------------------------------------------------------
class BGMIMonitorApp(App):
    def build(self):
        self.title = "BGMI Performance Monitor"
        self.data = load_data()
        self.ping_host = self.data.get("ping_host", "8.8.8.8")
        self.ping_history = deque(maxlen=60)
        self.ping_loss_count = 0
        self.ping_total_count = 0

        self.session_active = False
        self.session_start = None
        self.session_samples = {"fps": [], "cpu": [], "ram": [], "ping": []}

        self.current_fps = 0
        self._frame_count = 0
        self.benchmark_mode = False
        self._ping_running = True

        self.root_layout = FloatLayout()

        main_box = BoxLayout(orientation="vertical")
        self.sm = ScreenManager(transition=NoTransition())
        self.dashboard = DashboardScreen(name="dashboard")
        self.network = NetworkScreen(name="network")
        self.benchmark = BenchmarkScreen(name="benchmark")
        self.profiles = ProfilesScreen(name="profiles")
        self.history = HistoryScreen(name="history")
        for scr in (self.dashboard, self.network, self.benchmark, self.profiles, self.history):
            self.sm.add_widget(scr)

        main_box.add_widget(self.sm)
        main_box.add_widget(self._build_nav_bar())
        self.root_layout.add_widget(main_box)

        # Floating FPS badge on top of everything
        self.fps_widget = FloatingFPSWidget(
            size_hint=(None, None), size=(dp(90), dp(56)),
            pos=(dp(16), Window.height - dp(90))
        )
        self.root_layout.add_widget(self.fps_widget)
        self._fps_widget_visible = True

        # Kick off background loops
        Clock.schedule_interval(self._count_frame, 0)
        Clock.schedule_interval(self.update_fps, 1.0)
        Clock.schedule_interval(self.update_system_stats, 1.0)
        threading.Thread(target=self._ping_worker, daemon=True).start()

        self._request_android_permissions()

        return self.root_layout

    # ---------------- navigation bar ----------------
    def _build_nav_bar(self):
        nav = BoxLayout(size_hint_y=None, height=dp(58), padding=(dp(4), dp(4)))
        with nav.canvas.before:
            Color(0.09, 0.10, 0.12, 1)
            self._nav_rect = Rectangle(pos=nav.pos, size=nav.size)
        nav.bind(pos=lambda i, v: setattr(self._nav_rect, "pos", v),
                 size=lambda i, v: setattr(self._nav_rect, "size", v))

        self.nav_buttons = {}
        items = [
            ("dashboard", "Dashboard"),
            ("network", "Network"),
            ("benchmark", "Benchmark"),
            ("profiles", "Profiles"),
            ("history", "History"),
        ]
        for key, label in items:
            btn = NavButton(text=label, on_release=lambda inst, k=key: self.switch_screen(k))
            nav.add_widget(btn)
            self.nav_buttons[key] = btn
        self.nav_buttons["dashboard"].set_active(True)
        return nav

    def switch_screen(self, key):
        self.sm.current = key
        for k, b in self.nav_buttons.items():
            b.set_active(k == key)

    # ---------------- FPS ----------------
    def _count_frame(self, dt):
        self._frame_count += 1

    def update_fps(self, dt):
        self.current_fps = self._frame_count
        self._frame_count = 0
        self.fps_widget.set_fps(self.current_fps)
        self.dashboard.fps_card.set_value(
            self.current_fps, color=status_color(self.current_fps, warn=30, danger=15, invert=True)
        )
        if self.session_active:
            self.session_samples["fps"].append(self.current_fps)

    def toggle_floating_fps(self):
        if self._fps_widget_visible:
            self.root_layout.remove_widget(self.fps_widget)
        else:
            self.root_layout.add_widget(self.fps_widget)
        self._fps_widget_visible = not self._fps_widget_visible
        return self._fps_widget_visible

    def try_enable_system_overlay(self):
        """Attempts to open Android's 'draw over other apps' settings page
        so a *true* cross-app overlay could be implemented in the future.
        Safe no-op on desktop."""
        if not IS_ANDROID:
            self._show_popup("System Overlay",
                              "True system-wide overlay (drawing on top of BGMI itself) "
                              "is only available on an installed Android APK build, and "
                              "requires the 'Draw over other apps' permission.")
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")
            activity = PythonActivity.mActivity
            intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                             Uri.parse("package:" + activity.getPackageName()))
            activity.startActivity(intent)
        except Exception as e:
            self._show_popup("Overlay permission", f"Could not open settings: {e}")

    def _show_popup(self, title, message):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text=message, color=(1, 1, 1, 1)))
        popup = Popup(title=title, content=content, size_hint=(0.85, 0.4))
        close_btn = Button(text="OK", size_hint_y=None, height=dp(40), on_release=popup.dismiss)
        content.add_widget(close_btn)
        popup.open()

    # ---------------- system stats ----------------
    def update_system_stats(self, dt):
        cpu = get_cpu_percent()
        ram = get_ram_percent()
        temp = get_temperature()
        batt, charging, batt_temp = get_battery()
        if temp is None and batt_temp:
            temp = batt_temp

        self.dashboard.cpu_card.set_value(cpu, color=status_color(cpu))
        self.dashboard.ram_card.set_value(ram, color=status_color(ram))
        self.dashboard.temp_card.set_value(temp, color=status_color(temp, warn=40, danger=50))
        batt_text = None if batt is None else int(round(batt))
        self.dashboard.battery_card.set_value(batt_text, color=status_color(batt, invert=True) if batt is not None else TEXT_MUTED)

        if self.session_active:
            if cpu is not None:
                self.session_samples["cpu"].append(cpu)
            if ram is not None:
                self.session_samples["ram"].append(ram)

    # ---------------- networking ----------------
    def _ping_worker(self):
        while self._ping_running:
            latency = measure_latency(self.ping_host)
            Clock.schedule_once(lambda dt, v=latency: self._on_ping_result(v))
            time.sleep(1.5)

    def _on_ping_result(self, latency):
        self.ping_total_count += 1
        if latency is None:
            self.ping_loss_count += 1
        else:
            self.ping_history.append(latency)
            self.network.graph.add_point(latency)
            if self.session_active:
                self.session_samples["ping"].append(latency)

        avg_ping = round(statistics.mean(self.ping_history), 1) if self.ping_history else None
        jitter = None
        if len(self.ping_history) >= 2:
            diffs = [abs(self.ping_history[i] - self.ping_history[i - 1])
                     for i in range(1, len(self.ping_history))]
            jitter = round(statistics.pstdev(diffs) if len(diffs) > 1 else diffs[0], 1)
        loss_pct = round((self.ping_loss_count / self.ping_total_count) * 100, 1) if self.ping_total_count else 0

        self.dashboard.ping_card.set_value(latency, color=status_color(latency, warn=100, danger=180))
        self.network.ping_card.set_value(avg_ping, color=status_color(avg_ping, warn=100, danger=180))
        self.network.jitter_card.set_value(jitter, color=status_color(jitter, warn=20, danger=50))
        self.network.loss_card.set_value(loss_pct, color=status_color(loss_pct, warn=5, danger=15))

    # ---------------- sessions ----------------
    def start_session(self):
        self.session_active = True
        self.session_start = datetime.now()
        self.session_samples = {"fps": [], "cpu": [], "ram": [], "ping": []}
        self.dashboard.session_status.text = "Recording session..."

    def stop_session(self):
        self.session_active = False
        duration = int((datetime.now() - self.session_start).total_seconds()) if self.session_start else 0
        s = self.session_samples

        def avg(lst):
            return round(statistics.mean(lst), 1) if lst else None

        record = {
            "start": self.session_start.strftime("%Y-%m-%d %H:%M:%S") if self.session_start else "?",
            "duration_sec": duration,
            "avg_fps": avg(s["fps"]),
            "min_fps": min(s["fps"]) if s["fps"] else None,
            "max_fps": max(s["fps"]) if s["fps"] else None,
            "avg_cpu": avg(s["cpu"]),
            "avg_ram": avg(s["ram"]),
            "avg_ping": avg(s["ping"]),
            "avg_jitter": round(statistics.pstdev(s["ping"]), 1) if len(s["ping"]) > 1 else None,
        }
        self.data.setdefault("sessions", []).append(record)
        save_data(self.data)
        self.dashboard.session_status.text = f"Last session saved ({duration}s)"

    # ---------------- android bits ----------------
    def _request_android_permissions(self):
        if not IS_ANDROID:
            return
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.INTERNET, Permission.ACCESS_NETWORK_STATE])
        except Exception as e:
            print("Permission request skipped:", e)

    def on_stop(self):
        self._ping_running = False
        save_data(self.data)


if __name__ == "__main__":
    BGMIMonitorApp().run()
