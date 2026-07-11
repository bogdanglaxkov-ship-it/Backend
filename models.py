"""
models.py — SQLAlchemy модели
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func, Index
from database import Base


class Message(Base):
    """Таблица для сохранения сообщений"""
    
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    __table_args__ = (
        Index("idx_session_created", "session_id", "created_at"),
    )
    
    def __repr__(self):
        return f"<Message(id={self.id}, session_id={self.session_id})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(Base):
    """Таблица пользователей (регистрация, вход, подтверждение email, сброс пароля)"""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)  # bcrypt-хеш, никогда не хранится в открытом виде

    email_verified = Column(Boolean, default=False, nullable=False)

    verification_token_hash = Column(String(64), nullable=True, index=True)
    verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    reset_token_hash = Column(String(64), nullable=True, index=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Персональный ключ для MCP-коннекторов (Claude/ChatGPT/Cursor) — "mck_..."
    mcp_key = Column(String(64), unique=True, nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "email_verified": self.email_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
