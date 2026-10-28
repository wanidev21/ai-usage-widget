// grok.com 설정 → 사용량 화면과 같은 내부 RPC를 본인 로그인 상태로 호출하고,
// 응답(gRPC-web 바이너리)을 그대로 로컬 위젯에 넘긴다. 해석은 위젯(providers/grok_web.py)이 한다.
// Gemini·ChatGPT는 사용자가 연 사용량 화면의 글자를 넘긴다(usage_page.js, 아래 PAGES).
const RPC_URL = "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig";
const WIDGET_BASE = "http://127.0.0.1:47321";
const WIDGET_URL = WIDGET_BASE + "/grok";
const PERIOD_MINUTES = 3;

// 공개 API가 없는 사용량 화면 — 창을 따로 열지 않고, 사용자가 직접 연 사용량 페이지의 글자만 받는다.
// 해석은 위젯(providers/web_usage.py)이 한다.
const PAGES = [
  { name: "gemini_web", host: "gemini.google.com" },
  { name: "chatgpt_web", host: "chatgpt.com" },
];
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
  await send(WIDGET_URL, payload);
}

async function send(url, payload) {
  payload.ts = Date.now() / 1000;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Usage-Widget": "1" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    // 위젯이 꺼져 있으면 조용히 넘어간다
  }
}

// Gemini·ChatGPT 사용량 페이지를 사용자가 직접 열었을 때 usage_page.js가 읽은 글자를 받아 위젯으로 넘긴다.
// 어느 서비스인지는 메시지 내용이 아니라 보낸 탭의 주소로 정한다.
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.type !== "usage_text" || typeof msg.text !== "string") return;
  let host;
  try {
    host = new URL(sender.url || "").host;
  } catch (e) {
    return;
  }
  const page = PAGES.find((p) => p.host === host);
  if (page) send(`${WIDGET_BASE}/push/${page.name}`, { ok: true, text: msg.text.slice(0, 4000) });
});

function start() {
  chrome.alarms.create("poll", { periodInMinutes: PERIOD_MINUTES });
  chrome.alarms.clear("pages"); // 1.2.0이 만든 창 열기 알람 정리
  poll();
}

chrome.runtime.onInstalled.addListener(start);
chrome.runtime.onStartup.addListener(start);
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "poll") poll();
});
