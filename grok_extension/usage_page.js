// gemini.google.com 페이지에서 실행된다. 사용자가 사용량 페이지를 열어 둔 동안에만
// "N% 사용됨/남음" 줄 앞 4줄 ~ 뒤 2줄을 모아 background.js로 넘긴다. 대화 목록 같은 다른 글자는 보내지 않는다.
// 페이지 새로고침 없이 주소만 바뀌므로 주기적으로 주소를 확인한다.
const USAGE_PATHS = ["/usage"];
const CHECK_MS = 3000;
const RESEND_MS = 60000; // 값이 그대로여도 이 간격으로 다시 보내 "N분 전"이 갱신되게 한다

function extractUsageLines() {
  const lines = (document.querySelector("main") || document.body).innerText.split("\n").map((l) => l.trim());
  const keep = new Set();
  lines.forEach((l, i) => {
    if (/^\d+(\.\d+)?\s*%/.test(l)) for (let j = Math.max(0, i - 4); j <= Math.min(lines.length - 1, i + 2); j++) keep.add(j);
  });
  return [...keep].sort((a, b) => a - b).map((i) => lines[i]).join("\n");
}

let lastText = "";
let lastSent = 0;

setInterval(() => {
  if (!USAGE_PATHS.includes(location.pathname) || document.visibilityState !== "visible") return;
  const text = extractUsageLines();
  if (!text || (text === lastText && Date.now() - lastSent < RESEND_MS)) return;
  lastText = text;
  lastSent = Date.now();
  chrome.runtime.sendMessage({ type: "usage_text", text }).catch(() => {});
}, CHECK_MS);
