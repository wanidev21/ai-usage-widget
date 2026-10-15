"""새 AI 프로바이더 예제 — 이 파일을 복사해 `plugins/내AI.py`로 저장하면 자동으로 등록된다.
(이름이 _로 시작하는 파일은 무시되므로 이 예제 자체는 로드되지 않는다.)

그다음 config.json의 providers에 추가하고, 위젯 우클릭 → "설정 다시 불러오기":
    {"type": "example_ai", "enabled": true, "interval": 300}

API가 없고 웹앱에서만 볼 수 있는 사용량이라면, 이 파일 대신 범용 "push" 프로바이더와
브라우저 확장 조합을 쓰면 된다 (README의 "새 AI 추가하기" 참고).
"""
import os

from providers.base import Provider, ProviderError, Row, fmt_until, fmt_usd, http_json, parse_iso


class ExampleAI(Provider):
    type = "example_ai"     # config.json에서 쓸 이름 (다른 프로바이더와 겹치지 않게)
    title = "Example AI"    # 섹션 제목
    short = "Example"       # 최소화 모드 요약에 쓰는 짧은 이름
    interval = 300          # 기본 갱신 주기(초). config의 "interval"이 우선

    def fetch(self):
        # 키는 환경변수 우선, 없으면 config.json의 값 (self.options = config의 이 프로바이더 항목)
        key = os.environ.get("EXAMPLE_AI_KEY") or self.options.get("api_key")
        if not key:
            raise ProviderError("API 키 필요 (EXAMPLE_AI_KEY)")  # 위젯에 ⚠로 표시됨

        data = http_json("https://api.example.com/v1/usage", {"Authorization": f"Bearer {key}"})
        # 오류 응답(401, 429, 네트워크)은 http_json이 알아서 ProviderError로 바꿔 준다

        used, limit = data["used"], data["limit"]
        return [
            # percent가 있으면 막대가 그려지고, 최소화 요약에는 첫 번째 막대 항목이 쓰인다
            Row("월간 사용량", f"{used / limit * 100:.0f}%", used / limit * 100,
                fmt_until(parse_iso(data.get("resets_at")))),
            Row("이번 달 비용", fmt_usd(data.get("cost_usd", 0))),
        ]
