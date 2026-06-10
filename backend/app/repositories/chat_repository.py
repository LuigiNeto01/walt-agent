from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.chat import ChatConversation, ChatMessage


def create_conversation(db: Session, title: str | None = None) -> ChatConversation:
    conversation = ChatConversation(title=title)
    db.add(conversation)
    db.flush()
    return conversation


def get_conversation(db: Session, conversation_id: str) -> ChatConversation | None:
    return db.get(ChatConversation, conversation_id)


def delete_conversation(db: Session, conversation: ChatConversation) -> None:
    db.delete(conversation)


def list_conversations(db: Session) -> list[ChatConversation]:
    statement = select(ChatConversation).order_by(ChatConversation.updated_at.desc())
    return list(db.scalars(statement).all())


def list_messages(db: Session, conversation_id: str) -> list[ChatMessage]:
    statement = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(db.scalars(statement).all())


def get_conversation_with_messages(db: Session, conversation_id: str) -> ChatConversation | None:
    statement = (
        select(ChatConversation)
        .options(selectinload(ChatConversation.messages))
        .where(ChatConversation.id == conversation_id)
    )
    return db.scalar(statement)


def add_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    model: str | None = None,
    openai_response_id: str | None = None,
    tool_calls_json: str | None = None,
) -> ChatMessage:
    message = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        model=model,
        openai_response_id=openai_response_id,
        tool_calls_json=tool_calls_json,
    )
    db.add(message)
    db.flush()
    return message
