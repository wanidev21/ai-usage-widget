"""한도 임박 알림 — 막대(%)가 있는 항목이 임계값을 넘으면 Windows 알림을 한 번 띄운다.

같은 임계값으로는 다시 알리지 않고, 사용량이 내려가면(리셋) 다시 알릴 수 있는 상태가 된다.
알림 상태는 state.json의 "alerted"에 저장되어 위젯을 다시 켜도 중복 알림이 없다.
"""
import base64
import subprocess
from xml.sax.saxutils import escape

# Windows는 등록된 앱 ID로만 알림을 띄우므로 PowerShell의 ID를 빌려 쓴다
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
SHOW_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show(
    [Windows.UI.Notifications.ToastNotification]::new($doc))
"""


def show_toast(title, body):
    xml = ('<toast><visual><binding template="ToastGeneric">'
           f"<text>{escape(title)}</text><text>{escape(body)}</text>"
           "</binding></visual></toast>")
    script = f"$appId = '{APP_ID}'\n$xml = @'\n{xml}\n'@\n{SHOW_TOAST}"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class AlertTracker:
    def __init__(self, alerted, thresholds):
        self.alerted = alerted  # state.json에 저장되는 dict: "섹션|항목" → 마지막으로 알린 임계값
        self.thresholds = sorted(int(t) for t in thresholds)

    def check(self, section_key, title, rows):
        """새로 넘은 임계값마다 (제목, 본문)을 돌려준다."""
        out = []
        for row in rows:
            if row.percent is None or not self.thresholds:
                continue
            key = f"{section_key}|{row.label}"
            pct = float(row.percent)
            last = self.alerted.get(key, 0)
            if pct < last:  # 리셋되어 내려감 → 현재 수준까지만 알린 것으로 간주
                last = max((t for t in self.thresholds if t <= pct), default=0)
            crossed = [t for t in self.thresholds if last < t <= pct]
            if crossed:
                last = crossed[-1]
                detail = f"현재 {row.value}" + (f" · {row.note}" if row.note else "")
                out.append((f"{title} · {row.label} {last}% 넘음", detail))
            if last:
                self.alerted[key] = last
            else:
                self.alerted.pop(key, None)
        return out
