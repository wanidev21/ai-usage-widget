"""Claude 구독 플랜 한도 (세션 5시간 / 주간 / 추가 사용 크레딧).

Claude Code의 /usage 화면과 같은 데이터. Claude Code가 저장한 OAuth 토큰을 읽어 쓰고,
비공식 엔드포인트라 예고 없이 바뀔 수 있다.

토큰이 만료되면 Claude Code와 같은 방법(refresh_token → TOKEN_URL)으로 직접 갱신해 로그인 파일에 저장한다.
`claude auth status`로는 만료된 토큰이 갱신되지 않아서(실제로 41시간 멈춤) 이 방식으로 바꿨다.
Claude Code와 동시에 갱신하면 한쪽의 refresh_token이 무효가 되므로, Claude Code가 쓰는
~/.claude/oauth_refresh.lock 잠금을 잡은 뒤 파일을 다시 읽어 아직 만료 상태일 때만 갱신한다.
"""
import json
import os
import tempfile
import time

from .base import Provider, ProviderError, Row, fmt_until, fmt_usd, http_json, parse_iso

CREDENTIALS = os.path.join(os.path.expanduser("~"), ".claude", ".credentials.json")
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code의 OAuth 클라이언트 ID
REFRESH_RETRY_SECS = 600  # 갱신에 실패해도 이보다 자주 시도하지 않음
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
LIMIT_LABELS = {"session": "세션 (5시간)", "weekly_all": "주간 (전체)"}
MINI_LABELS = {"weekly_all": "주간", "seven_day": "주간"}  # 최소화 요약에 덧붙일 한도
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

    def __init__(self, options):
        super().__init__(options)
        self._refresh_retry_at = 0.0

    def fetch(self):
        return self.rows(self.fetch_raw())

    def fetch_raw(self):
        """API 원본 응답. 리셋까지 남은 시간은 rows()에서 매번 다시 계산한다."""
        oauth = self._read_oauth()
        if self._expired(oauth):
            self._refresh_token()
            oauth = self._read_oauth()
        if self._expired(oauth):
            raise ProviderError("토큰 만료 — 갱신 실패, 10분 뒤 재시도 (계속되면 claude → /login)")
        plan = oauth.get("subscriptionType")
        if plan:
            self.title = f"Claude {plan.capitalize()}"

        return http_json(USAGE_URL, {
            "Authorization": "Bearer " + oauth["accessToken"],
            "anthropic-beta": "oauth-2025-04-20",
        })

    def _path(self):
        return self.options.get("credentials_path") or CREDENTIALS

    def _read_creds(self):
        try:
            with open(self._path(), encoding="utf-8") as f:
                creds = json.load(f)
            creds["claudeAiOauth"]["accessToken"]
            return creds
        except (OSError, KeyError, TypeError, ValueError):
            raise ProviderError("Claude Code 로그인 정보 없음 (claude → /login)") from None

    def _read_oauth(self):
        return self._read_creds()["claudeAiOauth"]

    @staticmethod
    def _expired(oauth):
        return oauth.get("expiresAt", 0) / 1000 < time.time()

    def _refresh_token(self):
        """만료된 토큰을 갱신해 로그인 파일에 저장한다. 실패해도 예외 없이 넘어간다(호출한 쪽이 만료로 처리)."""
        now = time.time()
        if now < self._refresh_retry_at:
            return
        self._refresh_retry_at = now + REFRESH_RETRY_SECS
        lock = os.path.join(os.path.dirname(self._path()), "oauth_refresh.lock")
        try:
            # 잡고 있는 쪽은 몇 초마다 수정 시각을 갱신하므로, 2분 넘게 그대로면 비정상 종료로 남은 잠금이다
            if time.time() - os.path.getmtime(lock) > 120:
                os.rmdir(lock)
        except OSError:
            pass
        try:
            os.mkdir(lock)  # 이미 있으면 Claude Code가 갱신 중 — 다음에 다시 읽으면 된다
        except OSError:
            return
        try:
            creds = self._read_creds()
            oauth = creds["claudeAiOauth"]
            if not self._expired(oauth) or not oauth.get("refreshToken"):
                return
            body = {"grant_type": "refresh_token", "refresh_token": oauth["refreshToken"], "client_id": CLIENT_ID}
            if oauth.get("scopes"):
                body["scope"] = " ".join(oauth["scopes"])
            data = http_json(TOKEN_URL, {}, body, timeout=30)
            if not data.get("access_token"):
                return
            oauth["accessToken"] = data["access_token"]
            oauth["refreshToken"] = data.get("refresh_token") or oauth["refreshToken"]
            oauth["expiresAt"] = int((time.time() + float(data.get("expires_in") or 3600)) * 1000)
            if isinstance(data.get("scope"), str):
                oauth["scopes"] = data["scope"].split()
            self._write_creds(creds)
        except ProviderError:
            pass
        finally:
            try:
                os.rmdir(lock)
            except OSError:
                pass

    def _write_creds(self, creds):
        """임시 파일에 쓴 뒤 바꿔치기해서, 쓰는 도중 Claude Code가 반쯤 쓴 파일을 읽지 않게 한다."""
        path = self._path()
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".credentials.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(creds, f, separators=(",", ":"))
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def rows(self, data):
        rows = []
        for lim in data.get("limits") or []:
            if lim.get("percent") is None:
                continue
            label = LIMIT_LABELS.get(lim.get("kind")) or f"주간 ({lim.get('scope') or lim.get('kind')})"
            rows.append(Row(label, f"{lim['percent']:.0f}%", lim["percent"],
                            fmt_until(parse_iso(lim.get("resets_at"))), MINI_LABELS.get(lim.get("kind"), False)))
        if not rows:
            for key, label in LEGACY_WINDOWS:
                win = data.get(key) or {}
                if win.get("utilization") is not None:
                    rows.append(Row(label, f"{win['utilization']:.0f}%", win["utilization"],
                                    fmt_until(parse_iso(win.get("resets_at"))), MINI_LABELS.get(key, False)))

        extra = data.get("extra_usage") or {}
        if extra.get("is_enabled") and extra.get("monthly_limit"):
            scale = 10 ** extra.get("decimal_places", 2)
            used, limit = (extra.get("used_credits") or 0) / scale, extra["monthly_limit"] / scale
            rows.append(Row("추가 사용 크레딧", f"{fmt_usd(used)} / {fmt_usd(limit)}",
                            extra.get("utilization"), "이번 달"))

        shares = [r for r in (data.get("seven_day_breakdown") or {}).get("rows", []) if r.get("percent")]
        if shares and self.options.get("show_breakdown"):
            rows.append(Row("주간 비중", " · ".join(f"{r['display_name']} {r['percent']}%" for r in shares)))

        if not rows:
            raise ProviderError("표시할 한도 정보 없음")
        return rows
