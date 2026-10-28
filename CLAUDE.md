# AI 사용량 위젯

화면 구석에 항상 떠 있는 작은 창에 AI 툴 사용량(Claude 플랜 한도, Grok 앱, Anthropic/OpenAI/xAI API 비용)을 보여 주는 Windows 전용 데스크톱 위젯. Python 표준 라이브러리(tkinter, ctypes, urllib)만 사용하고 외부 의존성은 없다. UI 문자열과 주석은 한국어로 쓴다.

## 실행

- 요구 사항: Windows 10/11, Python 3.10 이상(tkinter 포함)
- 실행: `pythonw ai_usage_widget.pyw` 또는 파일 더블클릭. 콘솔 출력이 없으므로 오류는 `widget.log`에서 확인한다.
- 빌드 단계나 테스트 스위트는 없다. 동작은 위젯을 직접 띄워서 확인한다.
- 중복 실행 방지: 이름 있는 뮤텍스 `AIUsageWidget_SingleInstance`를 쓴다. 이미 떠 있으면 새 인스턴스는 바로 종료되므로, 코드를 고친 뒤에는 기존 위젯을 먼저 끄고(우클릭 → 종료) 다시 실행해야 한다.
- `config.json`이 없으면 처음 실행할 때 `DEFAULT_CONFIG`(`ai_usage_widget.pyw`)로 만든다. 설정을 바꾼 뒤에는 우클릭 → "설정 다시 불러오기"를 누른다(`Widget.load()`가 워커와 섹션을 다시 만들고 플러그인도 다시 읽는다).

## 구조

```
ai_usage_widget.pyw   메인. Widget(tk 창, 메뉴, 드래그, 최소화, 투명도), Section(섹션 UI), Worker(프로바이더별 스레드)
fullscreen.py         Win32 ctypes: 모니터 작업 영역, 전체화면 감지(FullscreenWatcher), 포커스 없이 숨기기/보이기
alerts.py             AlertTracker(임계값 80/90% 한 번만 알림), show_toast(PowerShell로 Windows 알림)
providers/
  __init__.py         discover(): providers/와 plugins/에서 Provider 하위 클래스를 자동 등록해 REGISTRY에 넣음
  base.py             Row, ProviderError, Provider 기반 클래스, http_json, fmt_until/fmt_usd/fmt_tokens/parse_iso
  claude.py           type "claude": ClaudePlan과 ClaudeCode를 묶음. data/claude_plan.json 캐시, 429일 때 백오프
  claude_plan.py      ~/.claude/.credentials.json의 OAuth 토큰으로 api.anthropic.com/api/oauth/usage 조회(비공식)
  claude_code.py      ~/.claude/projects/**/*.jsonl 로그를 읽어 증분 집계(파일별 바이트 오프셋 캐시)
  pricing.py          모델별 단가 PRICES (입력, 출력, 캐시 읽기 $/MTok), cost_of()
  bridge.py           127.0.0.1:47321 로컬 HTTP 수신 서버. POST /grok, /push/<id> → data/<이름>.json
  grok_web.py         type "grok_web": 확장이 보낸 gRPC-web/protobuf 원본을 직접 해석
  push.py             type "push": 외부에서 보낸 rows를 그대로 표시
  web_usage.py        type "gemini_web"/"chatgpt_web": 확장이 보낸 사용량 화면 글자(/push/<이름>의 text)를 parse_limits()로 해석
  anthropic_api.py / openai_api.py / xai_api.py   Admin/Management 키로 API 비용 조회
plugins/_example.py   새 프로바이더 템플릿(`_`로 시작하므로 로드되지 않음)
grok_extension/       크롬 MV3 확장. 3분마다 grok.com 내부 RPC 결과를 위젯으로 POST. usage_page.js는 사용자가 연 Gemini·ChatGPT 사용량 페이지의 % 주변 글자만 보냄(창을 따로 열지 않음 — 사용자가 불편해해서 뺐다)
```

### 데이터 흐름

1. `Widget.load()`가 `config.json`의 `providers` 중 `enabled`인 항목마다 `REGISTRY[type](opts)`를 만들고 `Worker` 스레드를 띄운다(간격은 `max(30, interval)`초).
2. `Worker`가 `provider.fetch()`를 호출해 `(idx, title, rows, err, ts)`를 큐에 넣는다.
3. 메인 스레드의 `_poll()`(500ms 간격)이 큐를 비우면서 `Section.update()`, 최소화 요약, 알림 검사를 처리한다.
4. 섹션 키는 `"{type}:{index}"` 형식이고, 접힘 상태와 알림 상태가 이 키로 `state.json`에 저장된다.

## 프로바이더 작성 규칙

- `Provider`를 상속하고 클래스 속성 `type`(고유), `title`, `short`, `interval`을 정한다. `fetch()`는 `Row` 목록을 반환한다.
- `Row(label, value, percent, note, mini)`: `percent`가 있으면 막대를 그리고 알림 대상이 된다. 최소화 요약에는 섹션에서 첫 번째로 `percent`가 있는 Row가 쓰인다. `mini=True`인 Row는 요약 뒤에 값이 덧붙고, `mini="주간"`처럼 문자열이면 그 이름이 값 앞에 붙는다(percent가 있으면 막대와 같은 색).
- 사용자에게 보여 줄 오류는 `ProviderError`로 던진다. 그 밖의 예외는 Worker가 `widget.log`에 traceback을 남기고 "오류: ..."로 표시한다.
- HTTP 요청은 `base.http_json`을 쓴다. 401/403/404/429와 네트워크 오류를 한국어 `ProviderError`로 바꿔 주고, `status`에 상태 코드를 담는다.
- 키는 환경변수를 config 값보다 먼저 읽는다(`ANTHROPIC_ADMIN_KEY`, `OPENAI_ADMIN_KEY`, `XAI_MANAGEMENT_KEY`, `XAI_TEAM_ID`).
- 데이터가 오래되었으면 `updated_at`(epoch)을 실제 수신 시각으로 설정한다. 그러면 섹션에 "N분 전"으로 표시된다.
- 새로고침 버튼(⟳)은 `invalidate()` 호출 후 워커를 깨운다. 캐시가 있는 프로바이더만 재정의한다.
- `claude_plan`, `claude_code`도 `type`이 있으므로 단독 type으로 등록된다(README에는 `claude`만 안내됨).

## 작업할 때 주의할 점

- **tkinter 스레드 안전**: 위젯 조작은 메인 스레드에서만 한다. 워커는 큐에만 넣는다.
- **위젯이 죽으면 안 됨**: 감시 루프, 플러그인 로드, 프로바이더 생성은 모두 넓은 `except`로 감싸고 로그만 남긴다. 이 패턴을 유지한다(`# noqa: BLE001` 주석 참고).
- **Claude 플랜 API 요청 제한(429)**: 조회 간격을 줄이거나 캐시(`data/claude_plan.json`)를 우회하지 않는다. `MIN_REFRESH_SECS=60`, 백오프 5분~30분.
- **비공식 엔드포인트**: Claude 플랜(`/api/oauth/usage`)과 Grok(`GetGrokCreditsConfig` protobuf 필드 번호)은 예고 없이 바뀔 수 있다. Grok 필드 매핑은 `grok_web.decode_credits`에 있고, 확장은 원본 바이트만 넘긴다.
- **로컬 서버 보안**: `bridge`는 `127.0.0.1`에만 바인드하고 `X-Usage-Widget: 1` 헤더가 없으면 403을 돌려준다(CORS 사전 요청으로 웹페이지를 차단). push id는 `^[a-z0-9_-]{1,40}$`. 이 검사들을 약화하지 않는다.
- **포트 47321**은 `bridge.DEFAULT_PORT`, `grok_extension/background.js`의 `WIDGET_URL`, `manifest.json`(추정: host_permissions)에 함께 들어 있다. 바꿀 때는 모두 맞춘다.
- **Grok 확장의 쿠키**: grok.com 쿠키는 확장 안에서 `declarativeNetRequest`로 RPC 요청에만 붙이고 위젯으로는 보내지 않는다. 이 원칙을 지킨다.
- **Win32 ctypes 선언**(`argtypes`/`restype`)은 프로세스 전체에서 공유되므로 `fullscreen.py` 한 곳에서만 한다.
- **듀얼 모니터**: 보조 모니터는 음수 좌표일 수 있다. 위치 복원(`_place`)은 저장 좌표가 어느 모니터에든 있으면 그대로 두고, 화면 밖으로 넘친 경우(`_keep_on_screen`)에는 현재 모니터 안으로만 당긴다.
- **DPI**: `SetProcessDpiAwareness(1)`을 켠 상태에서 좌표를 계산한다.
- **파일 인코딩**: `load_json`은 메모장이 붙이는 BOM 때문에 `utf-8-sig`로 읽는다. 시작 프로그램 `.vbs`는 `utf-16`으로 쓴다.
- **git에 올리지 않는 파일**(.gitignore): `config.json`(키 포함 가능), `state.json`, `data/`, `widget.log`. 예시 설정을 바꿀 때는 `config.example.json`과 `DEFAULT_CONFIG`를 함께 맞춘다(추정: 두 내용이 같도록 관리).
- **문서와 코드 불일치**: `providers/base.py` docstring의 "REGISTRY에 등록하면 된다"는 옛 설명이다. 지금은 자동 등록이므로 `__init__.py`를 고칠 필요가 없다.
- 기능을 추가하거나 동작을 바꾸면 `README.md`(사용자 문서, 한국어)도 함께 고친다.
- 단가는 `providers/pricing.py`의 `PRICES`에 있고, `show_code_usage` 비용은 실제 청구액이 아니라 추정치다.
