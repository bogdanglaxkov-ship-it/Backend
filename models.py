"""
models.py — SQLAlchemy модели
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, func, Index
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