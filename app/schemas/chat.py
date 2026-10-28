"""The reply shape required by the assignment (section 2.6)."""
from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc_id: str
    section: str


class ToolCallLog(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: str  # success | error | pending_confirmation


class ChatReply(BaseModel):
    request_id: str
    answer: str
    route: str  # answer | clarify | no_answer | out_of_scope
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolCallLog] = Field(default_factory=list)
    pending_confirmation: bool = False
