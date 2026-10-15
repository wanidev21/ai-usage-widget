"""Claude 통합 — 플랜 한도(챗·Claude Code 공용)와 Claude Code 로컬 사용량을 한 섹션에."""
import time

from .base import Provider, ProviderError, Row
from .claude_code import ClaudeCode
from .claude_plan import ClaudePlan


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
        self._plan_rows, self._plan_err, self._plan_at = None, None, 0.0

    def invalidate(self):
        self._plan_at = 0.0

    def fetch(self):
        # 플랜 한도는 원격 조회라 더 드물게, 로컬 로그는 매번
        if time.time() - self._plan_at >= self.plan_interval:
            self._plan_at = time.time()
            try:
                self._plan_rows, self._plan_err = self.plan.fetch(), None
            except ProviderError as e:
                self._plan_err = str(e)
        self.title = self.plan.title

        rows = list(self._plan_rows or [])
        try:
            rows += self.code.fetch()
        except ProviderError as e:
            rows.append(Row("", note=f"⚠ Claude Code: {e}"))
        if self._plan_err:
            rows.append(Row("", note=f"⚠ 플랜: {self._plan_err}"))
        return rows
