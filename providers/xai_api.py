"""Grok (xAI API) 사용 비용·크레딧. xAI Console → Settings → Management Keys 에서 만든 키 필요.

grok.com / X 앱의 SuperGrok 구독 한도는 공개 API가 없어 표시할 수 없다.
"""
import os
from datetime import datetime, timedelta

from .base import Provider, ProviderError, Row, fmt_usd, http_json

BASE = "https://management-api.x.ai/v1/billing/teams/{}"
TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _cents(obj):
    try:
        return int((obj or {}).get("val") or 0) / 100
    except (TypeError, ValueError):
        return 0.0


class XaiApi(Provider):
    type = "xai_api"
    title = "Grok (xAI API)"
    interval = 600

    def fetch(self):
        key = os.environ.get("XAI_MANAGEMENT_KEY") or self.options.get("management_key")
        team = os.environ.get("XAI_TEAM_ID") or self.options.get("team_id")
        if not key or not team:
            raise ProviderError("Management 키와 team_id 필요")
        headers = {"Authorization": "Bearer " + key}
        base = BASE.format(team)
        rows, errors = [], []

        now = datetime.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            data = http_json(base + "/usage", headers, {"analyticsRequest": {
                "timeRange": {"startTime": start.strftime(TIME_FMT), "endTime": end.strftime(TIME_FMT),
                              "timezone": self.options.get("timezone") or "Asia/Seoul"},
                "timeUnit": "TIME_UNIT_DAY",
                "values": [{"name": "usd", "aggregation": "AGGREGATION_SUM"}],
                "groupBy": [],
                "filters": [],
            }})
            daily = {}
            for series in data.get("timeSeries") or []:
                for point in series.get("dataPoints") or []:
                    daily[point["timestamp"]] = daily.get(point["timestamp"], 0) + sum(point.get("values") or [0])
            today = daily[max(daily)] if daily else 0  # 마지막 버킷 = 오늘(현지 시간대 기준)
            rows += [Row("오늘", fmt_usd(today)), Row("이번 달", fmt_usd(sum(daily.values())))]
        except ProviderError as e:
            errors.append(f"사용량: {e}")

        try:
            balance = http_json(base + "/prepaid/balance", headers)
            rows.append(Row("선불 크레딧 잔액", fmt_usd(-_cents(balance.get("total")))))  # 구매는 음수로 기록됨
        except ProviderError as e:
            errors.append(f"잔액: {e}")

        try:
            preview = http_json(base + "/postpaid/invoice/preview", headers)
            limit = int(preview.get("effectiveSpendingLimit") or 0) / 100
            used = _cents((preview.get("coreInvoice") or {}).get("totalWithCorr"))
            if limit > 0:
                rows.append(Row("후불 한도", f"{fmt_usd(used)} / {fmt_usd(limit)}", used / limit * 100, "이번 달"))
        except ProviderError as e:
            errors.append(f"한도: {e}")

        if not rows:
            raise ProviderError(errors[0] if errors else "데이터 없음")
        return rows
