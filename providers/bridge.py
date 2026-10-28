"""로컬 수신 서버 — 브라우저 확장 등이 127.0.0.1로 보내는 데이터를 받아 data/<이름>.json에 저장.

  POST /grok          Grok 확장 (원본 응답, grok_web이 해석)
  POST /push/<이름>   범용: {"rows": [{"label", "value", "percent", "note"}, ...]} 또는 {"error": "..."}

웹페이지가 몰래 보내지 못하도록 X-Usage-Widget: 1 헤더를 요구한다
(커스텀 헤더는 CORS 사전 요청이 필요한데 여기서는 응답하지 않으므로 브라우저가 막는다).
"""
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HERE, "data")
DEFAULT_PORT = 47321
MAX_BODY = 256 * 1024
NAME_RE = re.compile(r"^/push/([a-z0-9_-]{1,40})$")

_lock = threading.Lock()
_server = None
_server_error = None
on_receive = None  # 데이터를 저장한 뒤 수신 스레드에서 on_receive(name)을 부른다 (위젯이 해당 워커를 바로 깨움)


def _path_for(name):
    return os.path.join(DATA_DIR, f"{name}.json")


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        name = "grok" if self.path == "/grok" else (NAME_RE.match(self.path) or [None, None])[1]
        length = int(self.headers.get("Content-Length") or 0)
        if not name or self.headers.get("X-Usage-Widget") != "1" or not 0 < length <= MAX_BODY:
            self.send_response(403)
            self.end_headers()
            return
        try:
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError
            data.setdefault("ts", time.time())
            os.makedirs(DATA_DIR, exist_ok=True)
            with _lock, open(_path_for(name), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self.send_response(204)
        except (ValueError, OSError):
            self.send_response(400)
            name = None
        self.end_headers()
        if name and on_receive:
            try:
                on_receive(name)
            except Exception:  # noqa: BLE001 — 수신 서버는 계속 살아 있어야 함
                pass

    def log_message(self, *args):
        pass


def ensure_server(port=DEFAULT_PORT):
    """처음 호출될 때 한 번만 서버를 띄운다. 실패하면 오류 문자열을 돌려준다."""
    global _server, _server_error
    with _lock:
        if _server is None and _server_error is None:
            try:
                _server = ThreadingHTTPServer(("127.0.0.1", int(port)), _Handler)
                threading.Thread(target=_server.serve_forever, daemon=True).start()
            except OSError as e:
                _server_error = f"포트 {port} 사용 불가: {e.strerror}"
    return _server_error


def read(name):
    try:
        with _lock, open(_path_for(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
