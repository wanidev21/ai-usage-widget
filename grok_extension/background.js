// grok.com 설정 → 사용량 화면과 같은 내부 RPC를 본인 로그인 상태로 호출하고,
// 응답(gRPC-web 바이너리)을 그대로 로컬 위젯에 넘긴다. 해석은 위젯(providers/grok_web.py)이 한다.
const RPC_URL = "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig";
const WIDGET_URL = "http://127.0.0.1:47321/grok";
const PERIOD_MINUTES = 3;

function toBase64(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

async function poll() {
  let payload;
  try {
    const res = await fetch(RPC_URL, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/grpc-web+proto", "X-Grpc-Web": "1" },
      body: new Uint8Array([0, 0, 0, 0, 0]), // 빈 요청 메시지 1개 프레임
    });
    const bytes = new Uint8Array(await res.arrayBuffer());
    payload = { ok: res.ok, status: res.status, b64: toBase64(bytes),
                grpcStatus: res.headers.get("grpc-status"), grpcMessage: res.headers.get("grpc-message") };
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

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("poll", { periodInMinutes: PERIOD_MINUTES });
  poll();
});
chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create("poll", { periodInMinutes: PERIOD_MINUTES });
  poll();
});
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "poll") poll(); });
