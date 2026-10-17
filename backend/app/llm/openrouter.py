"""Gemma 4 through OpenRouter (OpenAI-compatible format). Used only as the fallback."""

import base64
import json
import time

import httpx

from app.llm.types import LLMError, LLMReply, Msg, ToolCall, ToolSpec

URL = "https://openrouter.ai/api/v1/chat/completions"


def _messages(system: str, messages: list[Msg]) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "user" and m.images:
            out.append({"role": "user", "content": [{"type": "text", "text": m.text}] + [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}
                for mime, data in m.images]})
        elif m.role == "user":
            out.append({"role": "user", "content": m.text})
        elif m.role == "model":
            msg: dict = {"role": "assistant", "content": m.text or None}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.args)}}
                    for c in m.tool_calls
                ]
            out.append(msg)
        else:
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": json.dumps(m.tool_result or {})})
    return out


def generate(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[Msg],
    tools: list[ToolSpec],
    max_tokens: int = 400,
    timeout_s: float = 8.0,
) -> LLMReply:
    body: dict = {
        "model": model,
        "messages": _messages(system, messages),
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "reasoning": {"enabled": False},
    }
    if tools:
        body["tools"] = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ]
    t0 = time.perf_counter()
    try:
        r = httpx.post(URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=timeout_s)
    except httpx.HTTPError as e:
        raise LLMError(f"openrouter {type(e).__name__}") from e
    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code != 200:
        raise LLMError(f"openrouter HTTP {r.status_code}")
    try:
        msg = r.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError("openrouter returned no choice") from e

    calls = []
    for c in msg.get("tool_calls") or []:
        try:
            args = json.loads(c["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append(ToolCall(c.get("id") or c["function"]["name"], c["function"]["name"], args))
    return LLMReply((msg.get("content") or "").strip(), calls, "openrouter", model, ms)
