"""ChatGPT 플랜 사용량 (Codex·Work 등이 함께 쓰는 한도. 일반 채팅은 ChatGPT가 사용량을 보여 주지 않아 제외).

크롬 확장(grok_extension/background.js)이 3분마다 chatgpt.com 사용량 화면이 부르는
/backend-api/wham/usage(Codex CLI와 같은 주소)를 본인 로그인 상태로 호출하고, 신원 정보를 뺀 응답을
POST /push/chatgpt_web의 "usage"로 넘긴다. 비공식 엔드포인트라 예고 없이 바뀔 수 있다.

응답 예 (Codex CLI의 RateLimitStatusPayload 기준):
  {"plan_type": "plus", "rate_limit": {"limit_reached": false,
     "primary_window": {"used_percent": 42, "limit_window_seconds": 18000, "reset_at": 1793210000},
     "secondary_window": {"used_percent": 30, "limit_window_seconds": 604800, "reset_at": ...}},
   "credits": {"has_credits": false, "balance": "0"}}
필드 위치가 바뀌어도 찾도록 "used_percent"가 있는 객체를 전부 훑는다.
"""
import time
from datetime import datetime, timezone

from . import bridge
from .base import Provider, ProviderError, Row, fmt_until

STALE_SECS = 15 * 60
HOUR, DAY = 3600, 86400


def window_label(secs):
    if not secs:
        return "한도"
    if secs < DAY:
        return f"{round(secs / HOUR)}시간 한도"
    if round(secs / DAY) == 7:
        return "주간 한도"
    if secs >= 28 * DAY:
        return "월 한도"
    return f"{round(secs / DAY)}일 한도"


def find_windows(obj, prefix=""):
    """used_percent가 있는 객체를 [(이름 앞에 붙일 말, 객체)]로 모은다. 추가 한도는 limit_name을 붙인다."""
    found = []
    if isinstance(obj, list):
        for v in obj:
            found += find_windows(v, prefix)
    elif isinstance(obj, dict):
        if isinstance(obj.get("used_percent"), (int, float)):
            found.append((prefix, obj))
        name = obj.get("limit_name") or obj.get("metered_feature")
        for v in obj.values():
            found += find_windows(v, f"{name} " if isinstance(name, str) and name else prefix)
    return found


def parse_usage(usage, received_at):
    rows, seen = [], set()
    for prefix, w in find_windows(usage):
        secs = w.get("limit_window_seconds") or 0
        reset_at = w.get("reset_at")
        if not isinstance(reset_at, (int, float)) and isinstance(w.get("reset_after_seconds"), (int, float)):
            reset_at = received_at + w["reset_after_seconds"]
        key = (prefix, secs, w["used_percent"], reset_at)
        if key in seen:
            continue
        seen.add(key)
        label = prefix + window_label(secs)
        reset = datetime.fromtimestamp(reset_at, timezone.utc) if isinstance(reset_at, (int, float)) else None
        pct = max(0.0, min(100.0, float(w["used_percent"])))
        rows.append(Row(label, f"{pct:.0f}%", pct, fmt_until(reset),
                        "주간" if rows and round(secs / DAY) == 7 else False))
    return rows


class ChatGPTWeb(Provider):
    type = "chatgpt_web"
    title = "ChatGPT (Codex·Work, 채팅 제외)"
    short = "GPT"
    interval = 60  # 데이터가 도착하면 bridge가 바로 깨우므로, 이 간격은 리셋까지 남은 시간 표시 갱신용
    bridge_name = "chatgpt_web"

    def __init__(self, options):
        super().__init__(options)
        self.port = options.get("port", bridge.DEFAULT_PORT)
        bridge.ensure_server(self.port)

    def fetch(self):
        err = bridge.ensure_server(self.port)
        if err:
            raise ProviderError(err)
        data = bridge.read(self.bridge_name)
        if data is None or "usage" not in data and data.get("ok"):
            raise ProviderError("크롬 확장 연결 대기 중 (확장을 1.4.0으로 새로고침하세요)")
        if not data.get("ok"):
            raise ProviderError(data.get("error") or "chatgpt.com 사용량을 읽지 못함")

        self.updated_at = float(data.get("ts") or 0) or None
        rows = parse_usage(data.get("usage"), self.updated_at or time.time())
        if not rows:
            raise ProviderError("chatgpt.com 응답 형식이 바뀐 듯함")
        plan = (data.get("usage") or {}).get("plan_type")
        if isinstance(plan, str) and plan:
            self.title = f"ChatGPT {plan.capitalize()} (Codex·Work, 채팅 제외)"

        age = time.time() - (self.updated_at or 0)
        if age > STALE_SECS:
            rows.append(Row("", note=f"{int(age // 60)}분 전 데이터 — 크롬이 꺼져 있나요?"))
        return rows
