from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    system_prompt: str | None = None


class ChatMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    model: str | None = None
    openai_response_id: str | None = None
    tool_calls_json: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatConversationResponse(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    conversation: ChatConversationResponse
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
