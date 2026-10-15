"""범용 푸시 프로바이더 — API가 없는 AI 웹앱용.

브라우저 확장이나 스크립트가 다음처럼 보내면 그대로 표시한다.

  POST http://127.0.0.1:47321/push/<id>
  헤더: Content-Type: application/json, X-Usage-Widget: 1
  본문: {"rows": [{"label": "주간", "value": "42%", "percent": 42, "note": "3일 후 리셋"}]}
        (실패를 알릴 때는 {"error": "로그인 필요"})

config.json:  {"type": "push", "id": "<id>", "title": "표시 이름", "short": "짧은 이름"}
"""
import time

from . import bridge
from .base import Provider, ProviderError, Row

STALE_SECS = 15 * 60


class Push(Provider):
    type = "push"
    interval = 30

    def __init__(self, options):
        super().__init__(options)
        self.id = str(options.get("id") or "").strip().lower()
        self.title = options.get("title") or self.id or "푸시"
        self.short = options.get("short") or self.title
        self.port = options.get("port", bridge.DEFAULT_PORT)
        bridge.ensure_server(self.port)

    def fetch(self):
        if not bridge.NAME_RE.match(f"/push/{self.id}"):
            raise ProviderError('config의 "id"는 영문 소문자·숫자·-·_ 1~40자')
        err = bridge.ensure_server(self.port)
        if err:
            raise ProviderError(err)
        data = bridge.read(self.id)
        if data is None:
            raise ProviderError(f"데이터 대기 중 (POST 127.0.0.1:{self.port}/push/{self.id})")
        if data.get("error"):
            raise ProviderError(str(data["error"]))

        rows = []
        for r in data.get("rows") or []:
            if not isinstance(r, dict):
                continue
            pct = r.get("percent")
            rows.append(Row(str(r.get("label", "")), str(r.get("value", "")),
                            float(pct) if isinstance(pct, (int, float)) else None, str(r.get("note", ""))))
        if not rows:
            raise ProviderError("받은 데이터에 rows가 없음")
        age = time.time() - float(data.get("ts") or 0)
        if age > STALE_SECS:
            rows.append(Row("", note=f"{int(age // 60)}분 전 데이터"))
        return rows
