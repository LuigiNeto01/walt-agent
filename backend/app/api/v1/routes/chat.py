from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories import chat_repository
from app.schemas.chat import ChatConversationResponse, ChatMessageResponse, ChatRequest, ChatResponse
from app.services.chat_service import send_chat_message

router = APIRouter()


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat_message(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return send_chat_message(db, payload)


@router.get("/conversations", response_model=list[ChatConversationResponse])
def list_chat_conversations(db: Session = Depends(get_db)) -> list[ChatConversationResponse]:
    return chat_repository.list_conversations(db)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageResponse])
def list_chat_messages(conversation_id: str, db: Session = Depends(get_db)) -> list[ChatMessageResponse]:
    conversation = chat_repository.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversa nao encontrada.",
        )
    return chat_repository.list_messages(db, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_conversation(conversation_id: str, db: Session = Depends(get_db)) -> None:
    conversation = chat_repository.get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversa nao encontrada.",
        )
    chat_repository.delete_conversation(db, conversation)
    db.commit()
