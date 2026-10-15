"""Grok 앱(grok.com / SuperGrok) 사용량 — 크롬 확장(grok_extension/)이 보내 주는 데이터를 표시.

확장이 grok.com 내부 RPC(GetGrokCreditsConfig) 응답을 127.0.0.1로 보내면 여기서 받아 해석한다.
비공식 경로라 grok.com이 바뀌면 동작이 멈출 수 있다.
"""
import base64
import struct
import time
from datetime import datetime, timezone
from urllib.parse import unquote

from . import bridge
from .base import Provider, ProviderError, Row, fmt_until, fmt_usd

STALE_SECS = 15 * 60

PRODUCTS = {1: "API", 2: "Build", 3: "Plugins", 4: "Chat", 5: "Imagine", 6: "Voice",
            7: "App Builder", 8: "Tasks", 9: "Bot", 10: "Cursor", 11: "Bugbot"}
PERIODS = {1: "월간", 2: "주간"}


# ---- protobuf / gRPC-web 해석 ----
def _varint(b, i):
    result = shift = 0
    while True:
        c = b[i]
        i += 1
        result |= (c & 0x7F) << shift
        shift += 7
        if c < 0x80:
            return result, i


def _fields(b):
    """필드 번호 → 값 목록. varint는 int, length-delimited는 bytes, fixed32는 4바이트 bytes."""
    out, i = {}, 0
    while i < len(b):
        key, i = _varint(b, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _varint(b, i)
        elif wire == 2:
            n, i = _varint(b, i)
            val, i = b[i:i + n], i + n
        elif wire == 5:
            val, i = b[i:i + 4], i + 4
        elif wire == 1:
            val, i = b[i:i + 8], i + 8
        else:
            raise ValueError(f"wire type {wire}")
        out.setdefault(num, []).append(val)
    return out


def _first(fields, num, default=None):
    return fields.get(num, [default])[0]


def _float(raw):
    return struct.unpack("<f", raw)[0] if raw else 0.0


def _timestamp(raw):
    if not raw:
        return None
    return datetime.fromtimestamp(_first(_fields(raw), 1, 0), timezone.utc)


def _cents(raw):
    return _first(_fields(raw), 1, 0) / 100 if raw else 0.0


def _grpc_web_message(blob):
    i, message, status, err = 0, None, None, ""
    while i + 5 <= len(blob):
        flag, n = blob[i], int.from_bytes(blob[i + 1:i + 5], "big")
        body = blob[i + 5:i + 5 + n]
        i += 5 + n
        if flag & 0x80:  # 트레일러
            for line in body.decode("utf-8", "replace").splitlines():
                k, _, v = line.partition(":")
                if k.strip().lower() == "grpc-status":
                    status = v.strip()
                elif k.strip().lower() == "grpc-message":
                    err = unquote(v.strip())
        elif message is None:
            message = body
    if status not in (None, "0"):
        raise ProviderError(f"grok.com 오류 (grpc {status}) {err}".strip())
    if message is None:
        raise ProviderError("grok.com 응답이 비어 있음")
    return message


def decode_credits(blob):
    config = _fields(_first(_fields(_grpc_web_message(blob)), 1, b""))
    period = _fields(_first(config, 8, b""))
    return {
        "percent": _float(_first(config, 1)),
        "period_type": _first(period, 1, 0),
        "period_end": _timestamp(_first(period, 3)) or _timestamp(_first(config, 5)),
        "products": [(PRODUCTS.get(_first(p, 1, 0), f"#{_first(p, 1, 0)}"), _float(_first(p, 2)))
                     for p in map(_fields, config.get(7, []))],
        "on_demand_cap": _cents(_first(config, 2)),
        "on_demand_used": _cents(_first(config, 3)),
        "prepaid": _cents(_first(config, 12)),
    }


class GrokWeb(Provider):
    type = "grok_web"
    title = "Grok 앱"
    short = "Grok"
    interval = 30  # 로컬 파일만 읽으므로 짧게

    def __init__(self, options):
        super().__init__(options)
        self.port = options.get("port", bridge.DEFAULT_PORT)
        bridge.ensure_server(self.port)

    def fetch(self):
        err = bridge.ensure_server(self.port)
        if err:
            raise ProviderError(err)
        latest = bridge.read("grok")
        if latest is None:
            raise ProviderError("크롬 확장 연결 대기 중 (README의 Grok 설정 참고)")

        if not latest.get("ok"):
            if latest.get("status") in (401, 403):
                raise ProviderError("grok.com 로그인이 필요함")
            raise ProviderError(latest.get("error") or latest.get("grpcMessage")
                                or f"grok.com HTTP {latest.get('status')}")
        try:
            info = decode_credits(base64.b64decode(latest.get("b64") or ""))
        except (ValueError, IndexError, struct.error):
            raise ProviderError("응답 형식이 바뀐 듯함 — grok.com 업데이트 확인 필요") from None

        label = f"{PERIODS.get(info['period_type'], '')} 사용량".strip()
        rows = [Row(label, f"{info['percent']:.0f}%", info["percent"], fmt_until(info["period_end"]))]
        products = [(name, pct) for name, pct in info["products"] if pct >= 0.5]
        if products:
            rows.append(Row("구성", " · ".join(f"{n} {p:.0f}%" for n, p in sorted(products, key=lambda x: -x[1]))))
        if info["on_demand_cap"] > 0:
            rows.append(Row("추가 사용", f"{fmt_usd(info['on_demand_used'])} / {fmt_usd(info['on_demand_cap'])}",
                            info["on_demand_used"] / info["on_demand_cap"] * 100))
        if info["prepaid"] > 0:
            rows.append(Row("선불 크레딧", fmt_usd(info["prepaid"])))

        age = time.time() - float(latest.get("ts") or 0)
        if age > STALE_SECS:
            rows.append(Row("", note=f"{int(age // 60)}분 전 데이터 — 크롬이 꺼져 있나요?"))
        return rows
