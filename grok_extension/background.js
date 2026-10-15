// grok.com 설정 → 사용량 화면과 같은 내부 RPC를 본인 로그인 상태로 호출하고,
// 응답(gRPC-web 바이너리)을 그대로 로컬 위젯에 넘긴다. 해석은 위젯(providers/grok_web.py)이 한다.
const RPC_URL = "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig";
const WIDGET_URL = "http://127.0.0.1:47321/grok";
const PERIOD_MINUTES = 3;
const COOKIE_RULE_ID = 1;

function toBase64(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

// 서비스 워커의 fetch에는 grok.com 로그인 쿠키가 붙지 않아 익명 사용자로 처리된다.
// 그래서 grok.com에 보낼 쿠키를 읽어, 이 확장이 보내는(탭이 아닌) RPC 요청에만 직접 붙인다.
// 쿠키 값은 브라우저 안에서만 쓰이고 위젯으로는 보내지 않는다.
async function attachLoginCookies() {
  const cookies = await chrome.cookies.getAll({ url: "https://grok.com/" });
  const header = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  await chrome.declarativeNetRequest.updateSessionRules({
    removeRuleIds: [COOKIE_RULE_ID],
    addRules: header ? [{
      id: COOKIE_RULE_ID,
      priority: 1,
      action: { type: "modifyHeaders", requestHeaders: [{ header: "cookie", operation: "set", value: header }] },
      condition: {
        urlFilter: "|https://grok.com/grok_api_v2.",
        tabIds: [chrome.tabs.TAB_ID_NONE],
        resourceTypes: ["xmlhttprequest", "other"],
      },
    }] : [],
  });
  return cookies.length;
}

async function poll() {
  let payload;
  try {
    const cookieCount = await attachLoginCookies();
    if (!cookieCount) {
      payload = { ok: false, status: 401, error: "grok.com 로그인 쿠키 없음 — 크롬에서 grok.com에 로그인하세요" };
    } else {
      const res = await fetch(RPC_URL, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/grpc-web+proto", "X-Grpc-Web": "1" },
        body: new Uint8Array([0, 0, 0, 0, 0]), // 빈 요청 메시지 1개 프레임
      });
      const bytes = new Uint8Array(await res.arrayBuffer());
      payload = { ok: res.ok, status: res.status, b64: toBase64(bytes), cookieCount,
                  grpcStatus: res.headers.get("grpc-status"), grpcMessage: res.headers.get("grpc-message") };
    }
  } catch (e) {
    payload = { ok: false, error: String(e) };
  }
  payload.ts = Date.now() / 1000;
  try {
    await fetch(WIDGET_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Usage-Widget": "1" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    // 위젯이 꺼져 있으면 조용히 넘어간다
  }
}

function start() {
  chrome.alarms.create("poll", { periodInMinutes: PERIOD_MINUTES });
  poll();
}

chrome.runtime.onInstalled.addListener(start);
chrome.runtime.onStartup.addListener(start);
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "poll") poll(); });
