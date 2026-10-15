"""OpenAI API 조직 비용 (공식 Costs API). Admin 키가 필요하다.

platform.openai.com → Settings → Organization → Admin keys 에서 발급.
ChatGPT(웹/앱) 구독의 사용 한도는 공개 API가 없어 여기서는 다루지 않는다.
"""
import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from .base import Provider, ProviderError, Row, fmt_usd, http_json

COSTS_URL = "https://api.openai.com/v1/organization/costs"


class OpenAIApi(Provider):
    type = "openai_api"
    title = "OpenAI API"
    short = "OpenAI"
    interval = 600

    def fetch(self):
        key = os.environ.get("OPENAI_ADMIN_KEY") or self.options.get("admin_key")
        if not key:
            raise ProviderError("Admin 키 필요 (OPENAI_ADMIN_KEY)")
        headers = {"Authorization": "Bearer " + key}
        start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        params = {"start_time": int(start.timestamp()), "bucket_width": "1d", "limit": 31}

        buckets, page = [], None
        while True:
            query = dict(params, **({"page": page} if page else {}))
            data = http_json(f"{COSTS_URL}?{urlencode(query)}", headers)
            buckets += data.get("data") or []
            page = data.get("next_page")
            if not data.get("has_more") or not page:
                break

        def dollars(bucket):
            return sum(float((r.get("amount") or {}).get("value") or 0) for r in bucket.get("results") or [])

        buckets.sort(key=lambda b: b.get("start_time", 0))
        month = sum(dollars(b) for b in buckets)
        rows = [Row("오늘 (UTC)", fmt_usd(dollars(buckets[-1]) if buckets else 0))]
        budget = self.options.get("monthly_budget_usd")
        if budget:
            rows.append(Row("이번 달", f"{fmt_usd(month)} / {fmt_usd(budget)}", month / budget * 100))
        else:
            rows.append(Row("이번 달", fmt_usd(month)))
        return rows
