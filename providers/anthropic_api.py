"""Anthropic API 조직 비용 (Admin API cost_report). Admin 키(sk-ant-admin...)가 필요하다."""
import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from .base import Provider, ProviderError, Row, fmt_usd, http_json

COST_URL = "https://api.anthropic.com/v1/organizations/cost_report"


class AnthropicApi(Provider):
    type = "anthropic_api"
    title = "Anthropic API"
    interval = 600

    def fetch(self):
        key = os.environ.get("ANTHROPIC_ADMIN_KEY") or self.options.get("admin_key")
        if not key:
            raise ProviderError("Admin API 키 필요 (ANTHROPIC_ADMIN_KEY)")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        params = {"starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "bucket_width": "1d", "limit": 31}

        buckets, page = [], None
        while True:
            query = dict(params, **({"page": page} if page else {}))
            data = http_json(f"{COST_URL}?{urlencode(query)}", headers)
            buckets += data.get("data") or []
            page = data.get("next_page")
            if not data.get("has_more") or not page:
                break

        def dollars(bucket):  # amount는 센트 단위 문자열
            return sum(float(r.get("amount") or 0) for r in bucket.get("results") or []) / 100

        month = sum(dollars(b) for b in buckets)
        rows = [Row("오늘 (UTC)", fmt_usd(dollars(buckets[-1]) if buckets else 0))]
        budget = self.options.get("monthly_budget_usd")
        if budget:
            rows.append(Row("이번 달", f"{fmt_usd(month)} / {fmt_usd(budget)}", month / budget * 100))
        else:
            rows.append(Row("이번 달", fmt_usd(month)))
        return rows
