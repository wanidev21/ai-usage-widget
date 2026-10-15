"""Claude 통합 — 플랜 한도(챗·Claude Code 공용)를 표시.

옵션 (config.json의 claude 항목):
  "show_code_usage": true  Claude Code 로컬 로그의 오늘/7일 토큰과 API 환산 비용도 표시
  "show_breakdown": true   주간 사용 비중(Claude Code n% · Chats n%)도 표시

플랜 한도 API는 요청 제한(429)이 있어서, 마지막 응답을 data/claude_plan.json에 저장해
재시작해도 바로 다시 조회하지 않고, 제한에 걸리면 간격을 늘려 재시도한다.
"""
import json
import os
import time

from . import bridge
from .base import Provider, ProviderError, Row
from .claude_code import ClaudeCode
from .claude_plan import ClaudePlan

CACHE_PATH = os.path.join(bridge.DATA_DIR, "claude_plan.json")
MIN_REFRESH_SECS = 60           # ⟳ 버튼으로도 이보다 자주 조회하지 않음
BACKOFF_SECS = (300, 1800)      # 429일 때 재시도 간격: 5분부터 두 배씩, 최대 30분


class Claude(Provider):
    type = "claude"
    title = "Claude"
    short = "Claude"
    interval = 60

    def __init__(self, options):
        super().__init__(options)
        self.plan = ClaudePlan(options)
        self.code = ClaudeCode(options)
        self.plan_interval = options.get("plan_interval", ClaudePlan.interval)
        self._data, self._data_at, self._err, self._backoff = None, 0.0, None, 0
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                cache = json.load(f)
            self._data, self._data_at = cache["data"], float(cache["ts"])
            self.plan.title = cache.get("title") or self.plan.title
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self._next_at = self._data_at + self.plan_interval

    def invalidate(self):
        self._next_at = max(min(self._next_at, time.time()), self._data_at + MIN_REFRESH_SECS)

    def _refresh_plan(self, now):
        try:
            self._data, self._data_at = self.plan.fetch_raw(), now
        except ProviderError as e:
            self._err = str(e)
            if e.status == 429:
                self._backoff = min(max(self._backoff * 2, BACKOFF_SECS[0]), BACKOFF_SECS[1])
                self._next_at = now + self._backoff
            else:
                self._next_at = now + MIN_REFRESH_SECS
            return
        self._err, self._backoff = None, 0
        self._next_at = now + self.plan_interval
        try:
            os.makedirs(bridge.DATA_DIR, exist_ok=True)
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({"ts": now, "title": self.plan.title, "data": self._data}, f)
        except OSError:
            pass

    def fetch(self):
        now = time.time()
        if now >= self._next_at:
            self._refresh_plan(now)
        self.title = self.plan.title

        rows = []
        if self._data is not None:
            try:
                rows = self.plan.rows(self._data)
            except ProviderError as e:
                self._err = self._err or str(e)
        if self.options.get("show_code_usage"):
            try:
                rows += self.code.fetch()
            except ProviderError as e:
                rows.append(Row("", note=f"⚠ Claude Code: {e}"))
        if not rows:
            raise ProviderError(self._err or "불러오는 중")
        if self._err:
            age = int((now - self._data_at) // 60) if self._data is not None else None
            suffix = f" · {age}분 전 데이터" if age else ""
            rows.append(Row("", note=f"⚠ {self._err}{suffix}"))
        return rows
