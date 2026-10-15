"""Provider 공통 타입과 헬퍼.

새 AI 툴을 추가하려면 Provider를 상속해 fetch()에서 Row 목록을 돌려주고,
providers/__init__.py의 REGISTRY에 등록하면 된다.
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Row:
    label: str
    value: str = ""
    percent: Optional[float] = None  # 0~100이면 막대로 표시
    note: str = ""                   # 막대 옆 작은 글씨 (예: 리셋까지 남은 시간)


class ProviderError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류."""


class Provider:
    type = ""
    title = ""
    short = ""      # 최소화 모드 요약에 쓰는 짧은 이름
    interval = 120  # 초

    def __init__(self, options: dict):
        self.options = options

    def fetch(self) -> list:
        raise NotImplementedError

    def invalidate(self):
        """새로고침 버튼을 눌렀을 때 캐시를 비운다 (필요한 프로바이더만 재정의)."""


HTTP_MESSAGES = {
    401: "인증 실패 (키/토큰 확인)",
    403: "권한 없음 (키 권한 확인)",
    404: "엔드포인트/ID를 찾을 수 없음",
    429: "요청 제한 중 — 다음 갱신 때 재시도",
}


def http_json(url, headers, body=None, timeout=20):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    h = {"User-Agent": "ai-usage-widget/1.0", "Accept": "application/json", **headers}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read()[:160].decode("utf-8", "replace")
        raise ProviderError(HTTP_MESSAGES.get(e.code, f"HTTP {e.code}: {detail}")) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("네트워크 오류") from None


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_until(dt):
    if dt is None:
        return ""
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "곧 리셋"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}일 {h}시간 후 리셋"
    if h:
        return f"{h}시간 {m}분 후 리셋"
    return f"{m}분 후 리셋"


def fmt_tokens(n):
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


def fmt_usd(x):
    return f"${x:,.2f}" if x < 1000 else f"${x:,.0f}"
