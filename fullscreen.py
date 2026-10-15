"""모니터·전체화면 도우미 — 듀얼 모니터 작업 영역 계산과, 위젯이 있는 모니터에
전체화면 창(영상·게임·F11 브라우저)이 있으면 숨기기 위한 감지.

최대화한 일반 창은 작업표시줄이 보이므로 전체화면으로 치지 않는다(모니터 전체를 덮어야 함).
"""
import ctypes
import ctypes.wintypes as W

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


# user32 함수 선언은 프로세스 전체에서 공유되므로 이 모듈 한 곳에서만 한다
user32.GetForegroundWindow.restype = W.HWND
user32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
user32.MonitorFromWindow.restype = W.HMONITOR
user32.MonitorFromPoint.argtypes = [W.POINT, W.DWORD]
user32.MonitorFromPoint.restype = W.HMONITOR
user32.GetMonitorInfoW.argtypes = [W.HMONITOR, ctypes.POINTER(_MonitorInfo)]
user32.GetAncestor.argtypes = [W.HWND, ctypes.c_uint]
user32.GetAncestor.restype = W.HWND
user32.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]

MONITOR_DEFAULTTONEAREST = 2
GA_ROOT = 2
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = W.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
DWMWA_CLOAKED = 14
# 바탕화면과 작업표시줄도 모니터를 덮으므로 제외
IGNORED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def _monitor_info(monitor):
    info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    return info


def work_area(x, y, nearest=True):
    """(x, y)가 있는 모니터의 작업 영역(작업표시줄 제외). 보조 모니터의 음수 좌표도 처리.
    nearest=False면 그 점이 어느 모니터에도 없을 때 None."""
    monitor = user32.MonitorFromPoint(W.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST if nearest else 0)
    return _monitor_info(monitor).rcWork if monitor else None


def toplevel(hwnd):
    return user32.GetAncestor(hwnd, GA_ROOT)


def monitor_of(hwnd):
    return user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)


def _cloaked(hwnd):
    value = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return value.value != 0


def is_fullscreen(hwnd, ignore=None):
    if not hwnd or hwnd == ignore or not user32.IsWindow(hwnd):
        return False
    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or _cloaked(hwnd):
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in IGNORED_CLASSES:
        return False
    rect = W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    m = _monitor_info(monitor_of(hwnd)).rcMonitor
    return rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom


class FullscreenWatcher:
    """check()가 True면 위젯을 숨겨야 한다."""

    def __init__(self, own_hwnd):
        self.own = own_hwnd
        self.last = None  # 포커스가 다른 모니터로 가도 계속 전체화면인지 따라가기 위해 기억

    def check(self):
        fg = user32.GetForegroundWindow()
        if is_fullscreen(fg, self.own):
            self.last = fg
        elif not is_fullscreen(self.last, self.own):
            self.last = None
        return self.last is not None and monitor_of(self.last) == monitor_of(self.own)


def hide(hwnd):
    user32.ShowWindow(hwnd, SW_HIDE)


def show(hwnd):
    """포커스를 빼앗지 않고 다시 표시하고 맨 위로."""
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
