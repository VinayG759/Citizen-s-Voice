"""Provider-neutral conversation types. The clerk speaks only these; adapters translate."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Msg:
    role: Literal["user", "model", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # role == "model"
    tool_call_id: str = ""  # role == "tool"
    tool_name: str = ""  # role == "tool"
    tool_result: dict | None = None  # role == "tool"
    images: list[tuple[str, bytes]] = field(default_factory=list)  # role == "user": (mime type, bytes)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema, lower-case types ("object", "string", …)


@dataclass
class LLMReply:
    text: str
    tool_calls: list[ToolCall]
    provider: str
    model: str
    ms: int
    thought: str = ""  # the model's visible reasoning, when the provider returns it


class LLMError(Exception):
    """A provider failed, timed out, or returned something unusable."""
