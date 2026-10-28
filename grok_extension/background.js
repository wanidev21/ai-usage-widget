// grok.com 설정 → 사용량 화면과 같은 내부 RPC를 본인 로그인 상태로 호출하고,
// 응답(gRPC-web 바이너리)을 그대로 로컬 위젯에 넘긴다. 해석은 위젯(providers/grok_web.py)이 한다.
// ChatGPT는 chatgpt.com 사용량 화면이 부르는 /backend-api/wham/usage(Codex CLI와 같은 주소)를 같은 주기로 호출한다.
// Gemini는 사용자가 연 사용량 화면의 글자를 넘긴다(usage_page.js, 아래 PAGES).
const RPC_URL = "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig";
const WIDGET_BASE = "http://127.0.0.1:47321";
const WIDGET_URL = WIDGET_BASE + "/grok";
const PERIOD_MINUTES = 3;

// 공개 API가 없는 사용량 화면 — 창을 따로 열지 않고, 사용자가 직접 연 사용량 페이지의 글자만 받는다.
// 해석은 위젯(providers/web_usage.py)이 한다.
const PAGES = [
  { name: "gemini_web", host: "gemini.google.com" },
];
const COOKIE_RULE_ID = 1;
const CHATGPT = {
  site: "https://chatgpt.com/",
  session: "https://chatgpt.com/api/auth/session",
  usage: "https://chatgpt.com/backend-api/wham/usage",
  cookieRule: { id: 2, regexFilter: "^https://chatgpt\\.com/(api/auth/session|backend-api/wham/usage)$" },
};
// 위젯으로 보내지 않을 신원 정보 키
const IDENTITY_KEYS = new Set(["email", "user_id", "account_id", "user", "account", "name"]);

function toBase64(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

// 서비스 워커의 fetch에는 사이트 로그인 쿠키가 붙지 않아 익명 사용자로 처리된다.
// 그래서 그 사이트 쿠키를 읽어, 이 확장이 보내는(탭이 아닌) 사용량 요청에만 직접 붙인다.
// 쿠키 값은 브라우저 안에서만 쓰이고 위젯으로는 보내지 않는다.
async function attachLoginCookies(site, rule) {
  const cookies = await chrome.cookies.getAll({ url: site });
  const header = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  const { id, ...filter } = rule;
  await chrome.declarativeNetRequest.updateSessionRules({
    removeRuleIds: [id],
    addRules: header ? [{
      id,
      priority: 1,
      action: { type: "modifyHeaders", requestHeaders: [{ header: "cookie", operation: "set", value: header }] },
      condition: { ...filter, tabIds: [chrome.tabs.TAB_ID_NONE], resourceTypes: ["xmlhttprequest", "other"] },
    }] : [],
  });
  return cookies.length;
}

function stripIdentity(value) {
  if (Array.isArray(value)) return value.map(stripIdentity);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).filter(([k]) => !IDENTITY_KEYS.has(k)).map(([k, v]) => [k, stripIdentity(v)]));
}

// 세션에서 받은 accessToken은 이 함수 안에서만 쓰고 저장하거나 위젯으로 보내지 않는다.
async function pollChatGPT() {
  let payload;
  try {
    if (!(await attachLoginCookies(CHATGPT.site, CHATGPT.cookieRule))) {
      payload = { ok: false, status: 401, error: "chatgpt.com 로그인 쿠키 없음 — 크롬에서 chatgpt.com에 로그인하세요" };
    } else {
      const session = await (await fetch(CHATGPT.session, { credentials: "include" })).json().catch(() => ({}));
      if (!session.accessToken) {
        payload = { ok: false, status: 401, error: "chatgpt.com 로그인이 필요함" };
      } else {
        const headers = { Authorization: `Bearer ${session.accessToken}` };
        if (session.account && session.account.id) headers["ChatGPT-Account-Id"] = session.account.id;
        const res = await fetch(CHATGPT.usage, { headers, credentials: "include" });
        let usage = null;
        try {
          usage = await res.json();
        } catch (e) {
          // Cloudflare 확인 화면 등 JSON이 아닌 응답
        }
        payload = { ok: res.ok && !!usage, status: res.status, usage: stripIdentity(usage) };
        if (!payload.ok) payload.error = res.ok ? "chatgpt.com 응답 형식이 바뀐 듯함" : `chatgpt.com HTTP ${res.status}`;
      }
    }
  } catch (e) {
    payload = { ok: false, error: String(e) };
  }
  await send(`${WIDGET_BASE}/push/chatgpt_web`, payload);
}

async function poll() {
  pollChatGPT();
  let payload;
  try {
    const cookieCount = await attachLoginCookies("https://grok.com/", { id: COOKIE_RULE_ID, urlFilter: "|https://grok.com/grok_api_v2." });
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
