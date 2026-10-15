"""AI 사용량 위젯 — 화면 위에 항상 떠 있는 작은 사용량 표시 창.

실행: 이 파일을 더블클릭하거나 `pythonw ai_usage_widget.pyw`
조작: 드래그로 이동 · 섹션 제목 클릭으로 접기/펼치기 · 우클릭 메뉴
"""
import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback

import providers
from alerts import AlertTracker, show_toast
from providers import ProviderError

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "state.json")
LOG_PATH = os.path.join(HERE, "widget.log")
STARTUP_PATH = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                            "AI Usage Widget.vbs")

DEFAULT_CONFIG = {
    "opacity": 0.92,
    "alerts": {"enabled": True, "thresholds": [80, 90]},
    "providers": [
        {"type": "claude", "enabled": True, "interval": 60, "plan_interval": 180},
        {"type": "grok_web", "enabled": True, "port": 47321},
        {"type": "anthropic_api", "enabled": False, "interval": 600, "admin_key": "", "monthly_budget_usd": 0},
        {"type": "openai_api", "enabled": False, "interval": 600, "admin_key": "", "monthly_budget_usd": 0},
        {"type": "xai_api", "enabled": False, "interval": 600, "management_key": "", "team_id": "",
         "timezone": "Asia/Seoul"},
    ],
}

BG, FG, MUTED, ACCENT, TRACK = "#1e2128", "#e8eaed", "#9aa0a6", "#d97757", "#3a3f4a"
GREEN, AMBER, RED = "#4caf7a", "#e0a030", "#e05252"
FONT = ("Malgun Gothic", 9)
FONT_BOLD = ("Malgun Gothic", 9, "bold")
FONT_SMALL = ("Malgun Gothic", 8)
BAR_W, BAR_H = 150, 6


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _Rect), ("rcWork", _Rect), ("dwFlags", ctypes.c_ulong)]


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_user32 = ctypes.windll.user32
_user32.MonitorFromPoint.argtypes = [_Point, ctypes.c_ulong]
_user32.MonitorFromPoint.restype = ctypes.c_void_p
_user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]


def work_area(x, y, nearest=True):
    """(x, y)가 있는 모니터의 작업 영역(작업표시줄 제외). 듀얼 모니터의 음수 좌표도 처리.
    nearest=False면 그 점이 어느 모니터에도 없을 때 None."""
    monitor = _user32.MonitorFromPoint(_Point(int(x), int(y)), 2 if nearest else 0)
    if not monitor:
        return None
    info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    _user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    return info.rcWork


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:  # 메모장이 붙이는 BOM 허용
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log(text):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + text + "\n")


def log_exception():
    log(traceback.format_exc())


def bar_color(pct):
    return GREEN if pct < 70 else AMBER if pct < 90 else RED


def ago(ts):
    s = int(time.time() - ts)
    return "방금" if s < 60 else f"{s // 60}분 전" if s < 3600 else f"{s // 3600}시간 전"


class Worker(threading.Thread):
    def __init__(self, idx, provider, interval, out):
        super().__init__(daemon=True)
        self.idx, self.provider, self.interval, self.out = idx, provider, interval, out
        self.wake = threading.Event()
        self.alive = True

    def run(self):
        while self.alive:
            rows, err = None, None
            try:
                rows = self.provider.fetch()
            except ProviderError as e:
                err = str(e)
            except Exception as e:  # noqa: BLE001 — 위젯은 계속 살아 있어야 함
                log_exception()
                err = f"오류: {e}"
            if self.alive:
                self.out.put((self.idx, self.provider.title, rows, err, time.time()))
            self.wake.wait(self.interval)
            self.wake.clear()


class Section:
    def __init__(self, parent, key, title, collapsed, on_toggle):
        self.key, self.collapsed, self.on_toggle = key, collapsed, on_toggle
        self.rows, self.err, self.updated = None, None, None
        self.frame = tk.Frame(parent, bg=BG)
        self.frame.pack(fill="x", pady=(8, 0))
        head = tk.Frame(self.frame, bg=BG)
        head.pack(fill="x")
        self.title = tk.Label(head, text=title, font=FONT_BOLD, fg=ACCENT, bg=BG, anchor="w")
        self.title.pack(side="left")
        self.status = tk.Label(head, text="불러오는 중…", font=FONT_SMALL, fg=MUTED, bg=BG)
        self.status.pack(side="right")
        for w in (head, self.title, self.status):
            w.bind("<ButtonRelease-1>", self._toggle)
        self.body = tk.Frame(self.frame, bg=BG)
        self.body.columnconfigure(1, weight=1)
        if not collapsed:
            self.body.pack(fill="x")

    def _toggle(self, event):
        if not self.on_toggle(self.key, event):
            return
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
        else:
            self.body.pack(fill="x")
        self.refresh_status()

    def update(self, title, rows, err, ts):
        self.title.config(text=title)
        self.err = err
        if rows is not None:
            self.rows, self.updated = rows, ts
        self._render()
        self.refresh_status()

    def refresh_status(self):
        if self.collapsed and self.rows:
            first = next((r for r in self.rows if r.value), None)
            text = f"{first.label} {first.value}" if first else ""
        elif self.updated:
            text = ago(self.updated) + (" · 갱신 실패" if self.err else "")
        else:
            text = "" if self.err else "불러오는 중…"
        self.status.config(text=text, fg=AMBER if self.err and self.collapsed else MUTED)

    def _render(self):
        for w in self.body.winfo_children():
            w.destroy()
        r = 0
        for row in self.rows or []:
            if row.label or row.value:
                tk.Label(self.body, text=row.label, font=FONT, fg=MUTED, bg=BG, anchor="w").grid(
                    row=r, column=0, sticky="w")
                tk.Label(self.body, text=row.value, font=FONT, fg=FG, bg=BG, anchor="e").grid(
                    row=r, column=1, columnspan=2, sticky="e", padx=(12, 0))
                r += 1
            if row.percent is not None or row.note:
                line = tk.Frame(self.body, bg=BG)
                line.grid(row=r, column=0, columnspan=3, sticky="we", pady=(1, 3))
                if row.percent is not None:
                    pct = max(0.0, min(100.0, float(row.percent)))
                    bar = tk.Canvas(line, width=BAR_W, height=BAR_H, bg=TRACK, highlightthickness=0)
                    bar.create_rectangle(0, 0, BAR_W * pct / 100, BAR_H, fill=bar_color(pct), width=0)
                    bar.pack(side="left", pady=2)
                if row.note:
                    tk.Label(line, text=row.note, font=FONT_SMALL, fg=MUTED, bg=BG).pack(side="right")
                r += 1
        if self.err:
            tk.Label(self.body, text="⚠ " + self.err, font=FONT_SMALL, fg=AMBER, bg=BG, anchor="w",
                     wraplength=260, justify="left").grid(row=r, column=0, columnspan=3, sticky="w")


class Widget:
    def __init__(self):
        self.state = load_json(STATE_PATH, {})
        self.queue = queue.Queue()
        self.workers, self.sections = [], []
        self.drag = None
        self._save_job = None

        self.root = tk.Tk()
        self.root.title("AI 사용량")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG, highlightthickness=1, highlightbackground="#2e323b")

        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=10, pady=(6, 0))
        self.top = top
        self.title_label = tk.Label(top, text="AI 사용량", font=FONT_BOLD, fg=FG, bg=BG)
        self.title_label.pack(side="left")
        self.summary = tk.Frame(top, bg=BG, cursor="hand2")  # 최소화 때만 보임
        self._click(self.summary, self.toggle_mini)
        self.buttons = {}
        for name, text, cmd in (("quit", "✕", self.quit), ("mini", "—", self.toggle_mini),
                                ("alpha", "◐", self.toggle_opacity), ("refresh", "⟳", self.refresh_all)):
            btn = tk.Label(top, text=text, font=FONT, fg=MUTED, bg=BG, cursor="hand2", padx=4)
            btn.pack(side="right")
            self._click(btn, cmd)
            self.buttons[name] = btn
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(fill="both", padx=10, pady=(0, 8))

        self.root.bind_all("<ButtonPress-1>", self._drag_start)
        self.root.bind_all("<B1-Motion>", self._drag_move)
        self.root.bind_all("<Button-3>", self._menu)
        self.root.bind_all("<MouseWheel>", self._wheel)

        cfg = load_json(CONFIG_PATH, None) or DEFAULT_CONFIG
        self.opacity = tk.DoubleVar(value=self.state.get("opacity", cfg.get("opacity", 0.92)))
        self.root.attributes("-alpha", self.opacity.get())
        self.startup = tk.BooleanVar(value=os.path.exists(STARTUP_PATH))
        self.alerts_on = tk.BooleanVar()
        self.mini = False
        self.load()
        if self.state.get("mini"):
            self.toggle_mini()
        self._place()
        self.root.after(300, self._poll)
        self.root.after(30000, self._tick)

    # ---- 설정 / 프로바이더 ----
    def load(self):
        if not os.path.exists(CONFIG_PATH):
            save_json(CONFIG_PATH, DEFAULT_CONFIG)
        cfg = load_json(CONFIG_PATH, None) or DEFAULT_CONFIG  # JSON 형식 오류면 기본값
        alert_cfg = cfg.get("alerts", DEFAULT_CONFIG["alerts"])
        self.alerts_on.set(self.state.get("alerts_on", alert_cfg.get("enabled", True)))
        self.alerts = AlertTracker(self.state.setdefault("alerted", {}), alert_cfg.get("thresholds", [80, 90]))

        for w in self.workers:
            w.alive = False
            w.wake.set()
        for s in self.sections:
            s.frame.destroy()
        self.workers, self.sections = [], []
        self.queue = queue.Queue()

        providers.discover()
        for fname, err in providers.LOAD_ERRORS:
            log(f"플러그인 {fname} 로드 실패\n{err}")

        collapsed = set(self.state.get("collapsed", []))
        for i, opts in enumerate(p for p in cfg.get("providers", []) if p.get("enabled", True)):
            cls = providers.REGISTRY.get(opts.get("type"))
            if cls is None:
                log(f"알 수 없는 프로바이더 type: {opts.get('type')!r} (config.json 확인)")
                continue
            try:
                provider = cls(opts)
            except Exception:  # noqa: BLE001
                log_exception()
                continue
            key = f"{opts['type']}:{i}"
            section = Section(self.content, key, provider.title, key in collapsed, self._can_toggle)
            section.short = provider.short or provider.title
            self.sections.append(section)
            worker = Worker(len(self.workers), provider, max(30, opts.get("interval", cls.interval)), self.queue)
            self.workers.append(worker)
            worker.start()
        if not self.sections:
            tk.Label(self.content, text="우클릭 → 설정 열기에서 프로바이더를 켜세요", font=FONT_SMALL,
                     fg=MUTED, bg=BG).pack(pady=8)

    def _can_toggle(self, key, event):
        if self.drag and self.drag[2]:
            return False
        collapsed = set(self.state.get("collapsed", []))
        collapsed.symmetric_difference_update({key})
        self.state["collapsed"] = sorted(collapsed)
        save_json(STATE_PATH, self.state)
        return True

    def _poll(self):
        changed = False
        try:
            while True:
                idx, title, rows, err, ts = self.queue.get_nowait()
                if 0 <= idx < len(self.sections):
                    self.sections[idx].update(title, rows, err, ts)
                    changed = True
                    if rows is not None:
                        self._check_alerts(self.sections[idx], title, rows)
        except queue.Empty:
            pass
        if changed:
            self._update_summary()
            self._keep_on_screen()
        self.root.after(500, self._poll)

    def _check_alerts(self, section, title, rows):
        fired = self.alerts.check(section.key, title, rows)  # 꺼져 있어도 상태는 따라가 켤 때 몰림 방지
        if fired:
            save_json(STATE_PATH, self.state)
        if self.alerts_on.get():
            for head, body in fired:
                try:
                    show_toast(head, body)
                except OSError:
                    log_exception()

    def _toggle_alerts(self):
        self.state["alerts_on"] = self.alerts_on.get()
        save_json(STATE_PATH, self.state)

    # ---- 최소화 / 투명도 ----
    def _click(self, widget, cmd):
        widget.bind("<ButtonRelease-1>", lambda e: cmd() if not (self.drag and self.drag[2]) else None)

    def _update_summary(self):
        for w in self.summary.winfo_children():
            w.destroy()
        items = []
        for s in self.sections:
            row = next((r for r in s.rows or [] if r.percent is not None), None)
            if row:
                items.append((s.short, row.value, bar_color(float(row.percent))))
        for i, (name, value, color) in enumerate(items or [("AI 사용량", "", FG)]):
            if i:
                tk.Label(self.summary, text="·", font=FONT, fg=MUTED, bg=BG).pack(side="left", padx=4)
            tk.Label(self.summary, text=name, font=FONT, fg=MUTED, bg=BG).pack(side="left")
            tk.Label(self.summary, text=value, font=FONT_BOLD, fg=color, bg=BG).pack(side="left", padx=(3, 0))
        for w in self.summary.winfo_children():
            self._click(w, self.toggle_mini)

    def toggle_mini(self):
        self.mini = not self.mini
        if self.mini:
            self.content.pack_forget()
            self.title_label.pack_forget()
            self.summary.pack(side="left")
            self.top.pack_configure(pady=6)
            self.buttons["mini"].config(text="□")
            self._update_summary()
        else:
            self.summary.pack_forget()
            self.title_label.pack(side="left")
            self.top.pack_configure(pady=(6, 0))
            self.content.pack(fill="both", padx=10, pady=(0, 8))
            self.buttons["mini"].config(text="—")
        self.state["mini"] = self.mini
        save_json(STATE_PATH, self.state)
        self._keep_on_screen()

    def set_opacity(self, value):
        value = round(max(0.2, min(1.0, value)), 2)
        self.opacity.set(value)
        self.root.attributes("-alpha", value)
        self.state["opacity"] = value
        if value < 1.0:
            self.state["opacity_low"] = value  # ◐ 버튼이 돌아갈 투명 단계
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, lambda: save_json(STATE_PATH, self.state))

    def toggle_opacity(self):
        if self.opacity.get() >= 0.99:
            self.set_opacity(self.state.get("opacity_low", 0.5))
        else:
            self.set_opacity(1.0)

    def _wheel(self, e):
        self.set_opacity(self.opacity.get() + (0.05 if e.delta > 0 else -0.05))

    def _keep_on_screen(self):
        """창이 커져 모니터 밖으로 삐져나가면, 지금 있는 모니터 안으로만 당겨 온다."""
        self.root.update_idletasks()
        x0, y0 = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        area = work_area(x0 + w // 2, y0 + min(h, 40) // 2)
        x = max(area.left, min(x0, area.right - w))
        y = max(area.top, min(y0, area.bottom - h))
        if (x, y) != (x0, y0):
            self.root.geometry(f"+{x}+{y}")

    def _tick(self):
        for s in self.sections:
            s.refresh_status()
        self.root.after(30000, self._tick)

    def refresh_all(self):
        for w in self.workers:
            w.provider.invalidate()
            w.wake.set()

    # ---- 창 위치 / 드래그 ----
    def _place(self):
        self.root.update_idletasks()
        x, y = self.state.get("x"), self.state.get("y")
        # 저장된 위치가 어느 모니터에든 있으면 그대로 (모니터를 뺐으면 메인 모니터 오른쪽 위로)
        if x is None or y is None or work_area(x + 20, y + 10, nearest=False) is None:
            area = work_area(0, 0)
            x, y = area.right - self.root.winfo_reqwidth() - 24, area.top + 48
        self.root.geometry(f"+{x}+{y}")

    def _drag_start(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y(), False)

    def _drag_move(self, e):
        if not self.drag:
            return
        dx, dy, _ = self.drag
        x, y = e.x_root - dx, e.y_root - dy
        if abs(x - self.root.winfo_x()) + abs(y - self.root.winfo_y()) > 2:
            self.drag = (dx, dy, True)
            self.root.geometry(f"+{x}+{y}")
            self.state["x"], self.state["y"] = x, y
            if self._save_job:
                self.root.after_cancel(self._save_job)
            self._save_job = self.root.after(400, lambda: save_json(STATE_PATH, self.state))

    # ---- 우클릭 메뉴 ----
    def _menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="지금 새로고침", command=self.refresh_all)
        op = tk.Menu(m, tearoff=0)
        for v in (1.0, 0.9, 0.8, 0.7, 0.55, 0.4, 0.25):
            op.add_radiobutton(label=f"{int(v * 100)}%", value=v, variable=self.opacity,
                               command=lambda v=v: self.set_opacity(v))
        m.add_cascade(label="투명도 (휠로도 조절)", menu=op)
        m.add_command(label="펼치기" if self.mini else "최소화", command=self.toggle_mini)
        m.add_separator()
        m.add_command(label="설정 열기 (config.json)", command=lambda: os.startfile(CONFIG_PATH))
        m.add_command(label="설정 다시 불러오기", command=self.load)
        thresholds = "·".join(str(t) for t in self.alerts.thresholds)
        m.add_checkbutton(label=f"한도 알림 ({thresholds}%)", variable=self.alerts_on, command=self._toggle_alerts)
        m.add_checkbutton(label="Windows 시작 시 실행", variable=self.startup, command=self._toggle_startup)
        m.add_separator()
        m.add_command(label="종료", command=self.quit)
        m.tk_popup(e.x_root, e.y_root)

    def _toggle_startup(self):
        if self.startup.get():
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            script = os.path.abspath(__file__)
            with open(STARTUP_PATH, "w", encoding="utf-16") as f:
                f.write(f'CreateObject("WScript.Shell").Run """{pythonw}"" ""{script}""", 0, False\r\n')
        elif os.path.exists(STARTUP_PATH):
            os.remove(STARTUP_PATH)

    def quit(self):
        save_json(STATE_PATH, self.state)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    # 중복 실행 방지
    ctypes.windll.kernel32.CreateMutexW(None, False, "AIUsageWidget_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return
    os.chdir(HERE)
    Widget().run()


if __name__ == "__main__":
    main()
