import json
import re
from collections.abc import Iterator

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.repositories import chat_repository
from app.schemas.chat import ChatConversationResponse, ChatMessageResponse, ChatRequest, ChatResponse
from app.services.openai_chat_service import OpenAIChatService


TITLE_STOPWORDS = {
    "a",
    "agora",
    "ai",
    "as",
    "ao",
    "aos",
    "apenas",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "essa",
    "esse",
    "isso",
    "isto",
    "eu",
    "me",
    "meu",
    "minha",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "pra",
    "q",
    "que",
    "quero",
    "tipo",
    "um",
    "uma",
    "the",
    "to",
    "with",
}


def _build_title(message: str) -> str:
    compact = " ".join(message.split())
    clean = re.sub(r"[^\wÀ-ÿ\s-]", " ", compact)
    words = [word.strip("-_") for word in clean.split() if word.strip("-_")]
    summary_words = [
        word
        for word in words
        if len(word) > 2 and word.lower() not in TITLE_STOPWORDS
    ]
    title_words = summary_words[:6] if len(summary_words) >= 2 else words[:7]
    title = " ".join(title_words).strip()
    if not title:
        return "Nova conversa"
    if len(title) > 54:
        title = f"{title[:51].rstrip()}..."
    return title[0].upper() + title[1:]


def send_chat_message(db: Session, payload: ChatRequest) -> ChatResponse:
    if payload.conversation_id:
        conversation = chat_repository.get_conversation(db, payload.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversa nao encontrada.",
            )
    else:
        conversation = chat_repository.create_conversation(db, title=_build_title(payload.message))

    user_message = chat_repository.add_message(
        db=db,
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    )

    history = chat_repository.list_messages(db, conversation.id)
    openai_service = OpenAIChatService()

    try:
        assistant_text, openai_response_id, tool_calls = openai_service.generate_reply(
            messages=history,
            system_prompt=payload.system_prompt,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha ao consultar a OpenAI: {exc}",
        ) from exc

    assistant_message = chat_repository.add_message(
        db=db,
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_text,
        model=openai_service.model,
        openai_response_id=openai_response_id,
        tool_calls_json=json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
    )
    db.commit()
    db.refresh(conversation)
    db.refresh(user_message)
    db.refresh(assistant_message)

    return ChatResponse(
        conversation=conversation,
        user_message=user_message,
        assistant_message=assistant_message,
    )


def stream_chat_message_events(db: Session, payload: ChatRequest) -> Iterator[dict]:
    if payload.conversation_id:
        conversation = chat_repository.get_conversation(db, payload.conversation_id)
        if conversation is None:
            yield {"type": "error", "message": "Conversa nao encontrada."}
            return
    else:
        conversation = chat_repository.create_conversation(db, title=_build_title(payload.message))

    user_message = chat_repository.add_message(
        db=db,
        conversation_id=conversation.id,
        role="user",
        content=payload.message,
    )
    db.commit()
    db.refresh(conversation)
    db.refresh(user_message)

    yield {
        "type": "user_message",
        "conversation": jsonable_encoder(ChatConversationResponse.model_validate(conversation)),
        "user_message": jsonable_encoder(ChatMessageResponse.model_validate(user_message)),
    }

    history = chat_repository.list_messages(db, conversation.id)
    openai_service = OpenAIChatService()
    final_reply: dict | None = None

    try:
        for event in openai_service.iter_reply_events(
            messages=history,
            system_prompt=payload.system_prompt,
        ):
            if event["type"] == "reply_finished":
                final_reply = event
            else:
                yield event
    except Exception as exc:
        db.rollback()
        yield {"type": "error", "message": f"Falha ao consultar a OpenAI: {exc}"}
        return

    if final_reply is None:
        yield {"type": "error", "message": "Falha ao consultar a OpenAI: resposta final nao gerada."}
        return

    assistant_message = chat_repository.add_message(
        db=db,
        conversation_id=conversation.id,
        role="assistant",
        content=final_reply["assistant_text"],
        model=openai_service.model,
        openai_response_id=final_reply["openai_response_id"],
        tool_calls_json=json.dumps(final_reply["tool_calls"], ensure_ascii=False) if final_reply["tool_calls"] else None,
    )
    db.commit()
    db.refresh(conversation)
    db.refresh(assistant_message)

    response = ChatResponse(
        conversation=conversation,
        user_message=user_message,
        assistant_message=assistant_message,
    )
    yield {"type": "final", "response": jsonable_encoder(response)}
