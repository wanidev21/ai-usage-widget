"""Claude 구독 플랜 한도 (세션 5시간 / 주간 / 추가 사용 크레딧).

Claude Code의 /usage 화면과 같은 데이터. Claude Code가 저장한 OAuth 토큰을 읽기만 하며,
비공식 엔드포인트라 예고 없이 바뀔 수 있다.
"""
import json
import os
import time

from .base import Provider, ProviderError, Row, fmt_until, fmt_usd, http_json, parse_iso

CREDENTIALS = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
LIMIT_LABELS = {"session": "세션 (5시간)", "weekly_all": "주간 (전체)"}
LEGACY_WINDOWS = (
    ("five_hour", "세션 (5시간)"),
    ("seven_day", "주간 (전체)"),
    ("seven_day_opus", "주간 (Opus)"),
    ("seven_day_sonnet", "주간 (Sonnet)"),
)


class ClaudePlan(Provider):
    type = "claude_plan"
    title = "Claude 플랜"
    interval = 180

    def fetch(self):
        path = self.options.get("credentials_path") or CREDENTIALS
        try:
            with open(path, encoding="utf-8") as f:
                oauth = json.load(f)["claudeAiOauth"]
        except (OSError, KeyError, ValueError):
            raise ProviderError("Claude Code 로그인 정보 없음 (claude → /login)") from None
        if oauth.get("expiresAt", 0) / 1000 < time.time():
            raise ProviderError("토큰 만료 — Claude Code를 한 번 실행하면 갱신됨")
        plan = oauth.get("subscriptionType")
        if plan:
            self.title = f"Claude {plan.capitalize()}"

        data = http_json(USAGE_URL, {
            "Authorization": "Bearer " + oauth["accessToken"],
            "anthropic-beta": "oauth-2025-04-20",
        })

        rows = []
        for lim in data.get("limits") or []:
            if lim.get("percent") is None:
                continue
            label = LIMIT_LABELS.get(lim.get("kind")) or f"주간 ({lim.get('scope') or lim.get('kind')})"
            rows.append(Row(label, f"{lim['percent']:.0f}%", lim["percent"],
                            fmt_until(parse_iso(lim.get("resets_at")))))
        if not rows:
            for key, label in LEGACY_WINDOWS:
                win = data.get(key) or {}
                if win.get("utilization") is not None:
                    rows.append(Row(label, f"{win['utilization']:.0f}%", win["utilization"],
                                    fmt_until(parse_iso(win.get("resets_at")))))

        extra = data.get("extra_usage") or {}
        if extra.get("is_enabled") and extra.get("monthly_limit"):
            scale = 10 ** extra.get("decimal_places", 2)
            used, limit = (extra.get("used_credits") or 0) / scale, extra["monthly_limit"] / scale
            rows.append(Row("추가 사용 크레딧", f"{fmt_usd(used)} / {fmt_usd(limit)}",
                            extra.get("utilization"), "이번 달"))

        shares = [r for r in (data.get("seven_day_breakdown") or {}).get("rows", []) if r.get("percent")]
        if shares:
            rows.append(Row("주간 비중", " · ".join(f"{r['display_name']} {r['percent']}%" for r in shares)))

        if not rows:
            raise ProviderError("표시할 한도 정보 없음")
        return rows
