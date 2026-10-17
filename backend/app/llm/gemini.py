"""Gemma 4 through Google's Gemini API (native format — the only one that can switch thinking off)."""

import base64
import time
import uuid

import httpx

from app.llm.types import LLMError, LLMReply, Msg, ToolCall, ToolSpec

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _schema(s: dict) -> dict:
    """Gemini wants upper-case type names ("OBJECT", "STRING")."""
    out = {}
    for k, v in s.items():
        if k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif isinstance(v, dict):
            out[k] = {kk: _schema(vv) for kk, vv in v.items()} if k == "properties" else _schema(v)
        elif isinstance(v, list) and k == "items":
            out[k] = [_schema(x) for x in v]
        else:
            out[k] = v
    return out


def _contents(messages: list[Msg]) -> list[dict]:
    contents = []
    for m in messages:
        if m.role == "user":
            parts = [{"text": m.text}] + [{"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}
                                         for mime, data in m.images]
            contents.append({"role": "user", "parts": parts})
        elif m.role == "model":
            parts = [{"text": m.text}] if m.text else []
            for c in m.tool_calls:
                parts.append({"functionCall": {"name": c.name, "args": c.args, "id": c.id}})
            contents.append({"role": "model", "parts": parts})
        else:
            part = {"functionResponse": {"name": m.tool_name, "response": m.tool_result or {}, "id": m.tool_call_id}}
            # Consecutive tool results belong in one user turn.
            if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][0]:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
    return contents


def generate(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[Msg],
    tools: list[ToolSpec],
    thinking: str = "minimal",
    max_tokens: int = 400,
    timeout_s: float = 8.0,
) -> LLMReply:
    body: dict = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": _contents(messages),
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
            "thinkingConfig": {"thinkingLevel": thinking, "includeThoughts": True},
        },
    }
    if tools:
        body["tools"] = [{"functionDeclarations": [
            {"name": t.name, "description": t.description, "parameters": _schema(t.parameters)} for t in tools
        ]}]
    t0 = time.perf_counter()
    try:
        # Key in a header, never in the URL: URLs end up in logs.
        r = httpx.post(URL.format(model=model), headers={"x-goog-api-key": api_key}, json=body, timeout=timeout_s)
    except httpx.HTTPError as e:
        raise LLMError(f"gemini {type(e).__name__}") from e
    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code != 200:
        raise LLMError(f"gemini HTTP {r.status_code}")
    try:
        parts = r.json()["candidates"][0]["content"].get("parts", [])
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError("gemini returned no candidate") from e

    text, thought, calls = [], [], []
    for p in parts:
        if p.get("thought"):
            thought.append(p.get("text", ""))
        elif "functionCall" in p:
            fc = p["functionCall"]
            calls.append(ToolCall(fc.get("id") or uuid.uuid4().hex[:12], fc["name"], fc.get("args") or {}))
        elif "text" in p:
            text.append(p["text"])
    return LLMReply("".join(text).strip(), calls, "gemini", model, ms, "".join(thought).strip())
