"""Claude Code 로컬 로그(~/.claude/projects/**/*.jsonl)에서 토큰 사용량과 API 환산 비용 집계."""
import glob
import json
import os
import time
from collections import defaultdict
from datetime import datetime

from .base import Provider, Row, fmt_tokens, fmt_usd
from .pricing import cost_of

WEEK_SECS = 7 * 86400


def _log_roots(extra):
    home = os.path.expanduser("~")
    cands = list(extra or [])
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        cands += [os.path.join(p.strip(), "projects") for p in env.split(",") if p.strip()]
    cands += [os.path.join(home, ".claude", "projects"), os.path.join(home, ".config", "claude", "projects")]
    return [p for p in dict.fromkeys(cands) if os.path.isdir(p)]


class ClaudeCode(Provider):
    type = "claude_code"
    title = "Claude Code (로컬 로그)"
    interval = 60

    def __init__(self, options):
        super().__init__(options)
        self._files = {}  # path -> [읽은 바이트 오프셋, [(ts, model, tokens, cost, key), ...]]

    def _read_new(self, path, offset, out):
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read()
        end = chunk.rfind(b"\n") + 1  # 아직 쓰는 중인 마지막 줄은 다음 번에
        pricing = self.options.get("pricing")
        for line in chunk[:end].splitlines():
            if b'"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") or {}
            usage, model = msg.get("usage"), msg.get("model")
            if d.get("type") != "assistant" or not usage or not model or model.startswith("<"):
                continue
            try:
                ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()
            except (KeyError, ValueError, AttributeError):
                continue
            tokens = sum(usage.get(k) or 0 for k in (
                "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            out.append((ts, model, tokens, cost_of(model, usage, pricing), f"{msg.get('id')}:{d.get('requestId')}"))
        return offset + end

    def _entries_since(self, since):
        seen, entries = set(), []
        for root in _log_roots(self.options.get("log_dirs")):
            for path in glob.iglob(os.path.join(root, "**", "*.jsonl"), recursive=True):
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if st.st_mtime < since:
                    self._files.pop(path, None)
                    continue
                rec = self._files.get(path)
                if rec is None or st.st_size < rec[0]:
                    rec = self._files[path] = [0, []]
                if st.st_size > rec[0]:
                    rec[0] = self._read_new(path, rec[0], rec[1])
                for e in rec[1]:
                    if e[0] >= since and e[4] not in seen:
                        seen.add(e[4])
                        entries.append(e)
        entries.sort(key=lambda e: e[0])
        return entries

    def fetch(self):
        now = time.time()
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        entries = self._entries_since(min(midnight, now - WEEK_SECS))
        today = [e for e in entries if e[0] >= midnight]

        def summary(es):
            return f"{fmt_tokens(sum(e[2] for e in es))} · {fmt_usd(sum(e[3] for e in es))}"

        rows = [Row("Code 오늘", summary(today)), Row("Code 7일", summary(entries), note="비용은 API 단가 환산 추정치")]
        if today:
            by_model = defaultdict(float)
            for e in today:
                by_model[e[1]] += e[3]
            total = sum(by_model.values())
            if total:
                model, cost = max(by_model.items(), key=lambda kv: kv[1])
                rows[0].note = f"{model.replace('claude-', '')} {cost / total * 100:.0f}%"
        return rows
