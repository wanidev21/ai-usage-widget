# AI 사용량 위젯

화면 구석에 항상 떠 있는 작은 창에 AI 툴 사용량을 표시하는 Windows용 위젯입니다.
Python 표준 라이브러리(tkinter)만 사용하며, 새 AI는 플러그인 파일 하나로 추가할 수 있습니다.

> **English:** An always-on-top Windows desktop widget that shows your AI usage limits (Claude plan & Claude Code, Grok app, Anthropic / OpenAI / xAI API costs) with threshold notifications. Pure Python (tkinter), no dependencies, extensible via drop-in plugins. UI text is Korean.

```
┌ AI 사용량              ⟳ ◐ — ✕ ┐      최소화하면
│ Claude Pro             방금    │      ┌ Claude 49% · Grok 95%  ⟳ ◐ □ ✕ ┐
│ 세션 (5시간)             48%   │
│ ██████░░░░░   3시간 2분 후 리셋 │
│ 주간 (전체)              29%   │
│ 추가 사용 크레딧  $38 / $40    │
│ Grok 앱                방금    │
│ 주간 사용량              95%   │
│ ███████████░  4일 18시간 후 리셋│
└────────────────────────────────┘
```

## 요구 사항

- Windows 10/11
- Python 3.10 이상 (python.org 설치본, tkinter 포함)

## 실행

```
git clone https://github.com/wanidev21/ai-usage-widget.git
```

`ai_usage_widget.pyw`를 더블클릭하면 실행됩니다(또는 `pythonw ai_usage_widget.pyw`). 처음 실행하면 `config.example.json`과 같은 내용으로 `config.json`이 만들어집니다. 이미 실행 중이면 새로 뜨지 않습니다.

| 조작 | 동작 |
|---|---|
| 드래그 | 이동 (위치 기억) |
| ⟳ | 지금 새로고침 |
| ◐ | 불투명 ↔ 투명 전환 |
| 마우스 휠 | 투명도 미세 조절 (◐가 마지막 투명 단계를 기억) |
| — / □ | 최소화 / 펼치기 (최소화 요약을 클릭해도 펼쳐짐) |
| 섹션 제목 클릭 | 그 섹션만 접기/펼치기 |
| 우클릭 | 새로고침 · 투명도 · 최소화 · 설정 열기/다시 불러오기 · **한도 알림** · **전체화면일 때 숨기기** · **Windows 시작 시 실행** · 종료 |

### 전체화면일 때 자동 숨김

위젯이 있는 모니터에서 영상·게임·브라우저(F11)가 전체화면이 되면 위젯을 숨겼다가, 전체화면이 끝나면 다시 표시합니다(포커스를 빼앗지 않음). 다른 모니터에서 작업하느라 전체화면 창에서 포커스가 빠져도 그 창이 전체화면인 동안은 계속 숨겨 둡니다. 다른 모니터의 전체화면에는 반응하지 않으며, 최대화한 일반 창은 전체화면으로 치지 않습니다. 우클릭 메뉴에서 끌 수 있습니다.

### 한도 알림

막대(%)가 있는 항목이 80%, 90%를 넘으면 Windows 알림을 한 번 띄웁니다. 같은 단계는 다시 알리지 않고, 리셋되어 내려가면 다음에 다시 알립니다. 우클릭 메뉴에서 끄고 켤 수 있고, 임계값은 `config.json`의 `"alerts": {"enabled": true, "thresholds": [80, 90]}`로 바꿉니다. 알림 발신자는 "Windows PowerShell"로 표시됩니다(추가 설치 없이 알림을 띄우는 방식).

## 지원하는 사용량

| 섹션 (`type`) | 내용 | 필요한 것 |
|---|---|---|
| Claude (`claude`) | 플랜 한도: 세션(5시간)·주간 %, 리셋 시간, 추가 사용 크레딧 (챗과 Claude Code 공용) | Claude Code 로그인 (자동으로 읽음) |
| Grok 앱 (`grok_web`) | 주간 사용량 %, 리셋 시간, 제품별 비중(Imagine/Chat 등), 선불 크레딧 | 동봉된 크롬 확장 |
| Anthropic API (`anthropic_api`) | 조직 API 비용 (오늘·이번 달, 예산 대비 %) | Admin API 키 |
| OpenAI API (`openai_api`) | 조직 API 비용 (오늘·이번 달, 예산 대비 %) | Admin 키 |
| Grok xAI API (`xai_api`) | 오늘·이번 달 비용, 선불 잔액, 후불 한도 % | xAI Management 키 + team ID |
| 범용 (`push`) | 외부(확장·스크립트)가 보내 주는 값을 그대로 표시 | 아래 "새 AI 추가하기" |

Claude 섹션은 기본으로 한도만 보여 줍니다. `config.json`의 claude 항목에 다음 옵션을 넣으면 더 볼 수 있습니다.

- `"show_breakdown": true` — 주간 사용 비중 (예: Claude Code 97% · Chats 3%)
- `"show_code_usage": true` — Claude Code 로컬 로그의 오늘/7일 토큰과 API 단가 환산 비용

### Grok 앱 — 크롬 확장 설치 (한 번만)

grok.com의 "설정 → 사용량" 데이터는 공개 API가 없어서, 동봉된 크롬 확장이 본인 로그인 상태로 3분마다 조회해 이 PC의 위젯(`127.0.0.1:47321`)으로만 보냅니다.

1. 크롬 주소창에 `chrome://extensions` 입력
2. 오른쪽 위 **개발자 모드** 켜기
3. **압축해제된 확장 프로그램 로드** → 이 저장소의 `grok_extension` 폴더 선택
4. grok.com에 로그인되어 있으면 몇 초 안에 위젯의 **Grok 앱** 섹션이 채워집니다.

크롬이 꺼져 있으면 마지막 값이 유지되고, 15분이 지나면 "N분 전 데이터"로 표시됩니다.

### API 키 설정

`config.json`에서 해당 항목을 `"enabled": true`로 바꾸고 키를 넣거나, 환경변수를 쓰면 됩니다(환경변수가 우선). 설정을 바꾼 뒤에는 우클릭 → **설정 다시 불러오기**를 누릅니다.

- Anthropic: `ANTHROPIC_ADMIN_KEY` (Console → Settings → Admin keys, `sk-ant-admin...`)
- OpenAI: `OPENAI_ADMIN_KEY` (platform.openai.com → Settings → Organization → Admin keys)
- xAI: `XAI_MANAGEMENT_KEY`, `XAI_TEAM_ID` (console.x.ai → Settings → Management Keys, Billing 읽기 전용 권한)

## 새 AI 추가하기

### A. 공식 API가 있는 경우 — 플러그인 파일 하나

1. `plugins/_example.py`를 복사해 `plugins/myai.py`처럼 저장합니다(이름이 `_`로 시작하면 무시됨).
2. `type`, `title`, `short`를 정하고 `fetch()`에서 `Row(label, value, percent, note)` 목록을 반환합니다. 사용자에게 보여줄 오류는 `ProviderError`로 던집니다.
3. `config.json`의 `providers`에 `{"type": "myai", "enabled": true, "interval": 300}`을 추가하고, 우클릭 → **설정 다시 불러오기**를 누릅니다.

등록 코드를 고칠 필요는 없습니다. `providers/`와 `plugins/`의 클래스가 자동으로 등록됩니다. 플러그인이 깨져 있으면 그 플러그인만 빠지고, 원인은 `widget.log`에 남습니다.

### B. 웹앱에서만 보이는 경우 — 범용 push

브라우저 확장이나 스크립트가 값을 계산해 위젯으로 보내면 그대로 표시됩니다.

```
POST http://127.0.0.1:47321/push/<id>
Content-Type: application/json
X-Usage-Widget: 1

{"rows": [{"label": "주간", "value": "42%", "percent": 42, "note": "3일 후 리셋"}]}
```

실패를 알릴 때는 `{"error": "로그인 필요"}`를 보냅니다. `config.json`에는 `{"type": "push", "id": "<id>", "title": "표시 이름", "short": "짧은 이름"}`을 추가합니다. 확장을 만든다면 `grok_extension/`이 참고용 예제입니다(`host_permissions`에 대상 사이트와 `http://127.0.0.1/*` 필요).

수신 서버는 `127.0.0.1`에만 열리고, `X-Usage-Widget: 1` 헤더가 없는 요청은 거부합니다. 일반 웹페이지는 이 헤더를 붙여 보낼 수 없습니다.

## 알아둘 점

- **비공식 경로:** Claude 플랜 한도와 Grok 앱 사용량은 각 서비스 웹/앱이 내부적으로 쓰는 엔드포인트를 이용합니다. 서비스가 바뀌면 예고 없이 멈출 수 있습니다. 본인 계정의 사용량을 본인 PC에서 몇 분에 한 번 읽기만 하지만, 각 서비스 약관은 직접 확인하고 사용하세요. 이 프로젝트는 Anthropic, xAI, OpenAI와 관계가 없습니다.
- **ChatGPT, Gemini 앱 구독 한도**는 아직 지원하지 않습니다. 공개 API가 없어서, 지원하려면 Grok처럼 웹앱 내부 요청을 찾아 확장으로 연결해야 합니다(위 "범용 push" 참고).
- **Claude 요청 제한:** 플랜 한도 API는 너무 자주 부르면 일시적으로 막힙니다. 위젯은 마지막 값을 저장해 두고 재시작 때 그 값을 먼저 보여 주며, 막히면 5분~30분 간격으로 재시도하는 동안 "N분 전 데이터"를 표시합니다.
- **Claude 토큰:** Claude 플랜 한도는 Claude Code가 저장한 로그인 토큰(`~/.claude/.credentials.json`)을 읽기만 합니다. 토큰이 만료되면 Claude Code를 한 번 실행하면 갱신됩니다.
- **Claude Code 비용**(`show_code_usage`)은 실제 청구액이 아니라 API 단가로 환산한 추정치입니다. 단가는 `providers/pricing.py`에 있고, `config.json`의 claude 항목에 `"pricing": {"claude-opus-5-5": [4, 20, 0.2]}`처럼 덮어쓸 수 있습니다(입력, 출력, 캐시 읽기 $/MTok).
- **로컬 파일:** `config.json`(키 포함 가능), `state.json`(창 위치 등), `data/`(받은 사용량), `widget.log`는 이 PC에만 있으며 git에 올라가지 않습니다.

## 라이선스

MIT — [LICENSE](LICENSE) 참고.
