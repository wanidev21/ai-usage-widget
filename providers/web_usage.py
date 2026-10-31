"""Gemini 앱 사용량 — 공개 API가 없어서 크롬 확장이 사용량 화면의 글자를 읽어 보낸다.

창을 따로 열지 않고, 사용자가 사용량 페이지를 직접 열었을 때 확장(grok_extension/usage_page.js)이
"N% 사용됨" / "N% 남음" 줄 주변의 글자만 POST /push/<이름>으로 넘긴다. 해석은 여기서 한다.
그래서 값은 사용자가 그 페이지를 마지막으로 연 시점 기준이다.
화면 문구가 바뀌면 parse_limits()의 정규식만 고치면 된다.

  Gemini   gemini.google.com/usage             현재 사용량(5시간마다 초기화), 주간 한도

ChatGPT는 확장이 사용량 API를 직접 조회한다(providers/chatgpt_web.py).
"""
import re
import time

from . import bridge
from .base import Provider, ProviderError, Row

STALE_SECS = 60 * 60  # 이보다 오래되면 사용량 페이지를 열어 달라고 안내

LABEL_RE = re.compile(r"한도|사용량|limit|usage", re.I)
PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*%\s*(남음|사용됨|remaining|left|used)?", re.I)
RESET_RE = re.compile(r"초기화|reset", re.I)
WEEKLY_RE = re.compile(r"주간|weekly", re.I)


def parse_limits(text):
    """사용량 화면 글자에서 [(이름, 사용 %, 초기화 안내)]를 뽑는다.

    "N%" 줄마다 바로 위의 한도 이름 줄을 찾고, 그 이름부터 다음 이름 전까지에서 초기화 안내 줄을 찾는다.
    안내가 % 위에 올 때도 아래에 올 때도 있어서 구간으로 찾는다.
    """
    lines = [line.strip() for line in text.splitlines()]
    labels = [i for i, line in enumerate(lines) if LABEL_RE.search(line) and not PCT_RE.match(line)]
    found, seen = [], set()
    for i, line in enumerate(lines):
        m = PCT_RE.match(line)
        before = [j for j in labels if j < i]
        # "사용됨/남음"이 없는 %는 한도가 아니다 (그래프 축 등)
        if not m or not m.group(2) or not before:
            continue
        start = before[-1]
        end = next((j for j in labels if j > start), len(lines))
        label = lines[start]
        if label in seen:
            continue
        seen.add(label)
        pct = float(m.group(1))
        if (m.group(2) or "").lower() in ("남음", "remaining", "left"):
            pct = 100 - pct
        note = next((lines[j] for j in range(start + 1, end)
                     if RESET_RE.search(lines[j]) and not PCT_RE.match(lines[j])), "")
        found.append((label, pct, note))
    return found


class WebUsage(Provider):
    """확장이 보낸 사용량 화면 글자를 해석하는 공통 부분. 하위 클래스는 name과 site만 정한다."""
    interval = 300  # 데이터가 도착하면 bridge가 바로 깨우므로, 이 간격은 "N시간 전" 표시 갱신용
    name = ""
    site = ""
    usage_url = ""

    def __init__(self, options):
        super().__init__(options)
        self.bridge_name = self.name
        self.port = options.get("port", bridge.DEFAULT_PORT)
        bridge.ensure_server(self.port)

    def fetch(self):
        err = bridge.ensure_server(self.port)
        if err:
            raise ProviderError(err)
        data = bridge.read(self.name)
        # usage_page.js는 성공한 글자만 보낸다. ok가 아닌 데이터는 창을 열던 옛 확장(1.2.0)이 남긴 것이다.
        if data is None or not data.get("ok"):
            raise ProviderError(f"크롬에서 {self.usage_url} 를 한 번 열어 주세요")

        limits = parse_limits(str(data.get("text") or ""))
        if not limits:
            raise ProviderError(f"{self.site} 사용량 화면 형식이 바뀐 듯함")
        rows = [Row(label, f"{pct:.0f}%", pct, note, "주간" if i and WEEKLY_RE.search(label) else False)
                for i, (label, pct, note) in enumerate(limits)]

        self.updated_at = float(data.get("ts") or 0) or None
        age = time.time() - (self.updated_at or 0)
        if age > STALE_SECS:
            rows.append(Row("", note=f"{fmt_age(age)} 전 값 — {self.usage_url} 를 열면 갱신"))
        return rows


def fmt_age(secs):
    if secs < 86400:
        return f"{int(secs // 3600)}시간"
    return f"{int(secs // 86400)}일"


class GeminiWeb(WebUsage):
    type = "gemini_web"
    title = "Gemini 앱"
    short = "Gemini"
    name = "gemini_web"
    site = "gemini.google.com"
    usage_url = "gemini.google.com/usage"

