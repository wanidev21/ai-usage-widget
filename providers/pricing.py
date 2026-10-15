"""Claude 모델별 API 단가 ($/MTok) — 로컬 로그의 'API 환산 비용' 추정용.

(입력, 출력, 캐시 읽기). 캐시 쓰기는 5분 TTL = 입력×1.25, 1시간 TTL = 입력×2.
모델 ID는 가장 긴 접두사로 매칭한다. config.json의 claude_code.pricing으로 덮어쓸 수 있다.
"""

PRICES = {
    "claude-fable-5-1": (10, 50, 0.25),
    "claude-mythos-5-1": (10, 50, 0.25),
    "claude-fable-5": (10, 50, 1.0),
    "claude-opus-5-5": (4, 20, 0.20),
    "claude-opus-5": (5, 25, 0.50),
    "claude-opus-4-8": (5, 25, 0.50),
    "claude-opus-4-7": (5, 25, 0.50),
    "claude-opus-4-6": (5, 25, 0.50),
    "claude-opus-4-5": (5, 25, 0.50),
    "claude-opus-4": (15, 75, 1.50),
    "claude-sonnet-5-5": (2, 10, 0.20),
    "claude-sonnet-5": (2, 10, 0.20),
    "claude-sonnet-4": (3, 15, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1, 5, 0.10),
}


def cost_of(model, usage, override=None):
    table = {**PRICES, **{k: tuple(v) for k, v in (override or {}).items()}}
    key = max((k for k in table if model.startswith(k)), key=len, default=None)
    if key is None:
        return 0.0
    p_in, p_out, p_read = table[key]
    cache = usage.get("cache_creation") or {}
    w1h = cache.get("ephemeral_1h_input_tokens") or 0
    w5m = cache.get("ephemeral_5m_input_tokens")
    if w5m is None:
        w5m = (usage.get("cache_creation_input_tokens") or 0) - w1h
    cost = (
        (usage.get("input_tokens") or 0) * p_in
        + w5m * p_in * 1.25
        + w1h * p_in * 2
        + (usage.get("cache_read_input_tokens") or 0) * p_read
        + (usage.get("output_tokens") or 0) * p_out
    ) / 1e6
    if usage.get("speed") == "fast":
        cost *= 2
    return cost
