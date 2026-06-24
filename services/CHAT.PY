from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Message
 
async def save_message(db: AsyncSession, session_id: str,
                        role: str, content: str):
    msg = Message(session_id=session_id, role=role, content=content)
    db.add(msg)
    await db.commit()
 
async def get_history(db: AsyncSession, session_id: str,
                       limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    msgs = result.scalars().all()
    return [{'role': m.role, 'content': m.content}
            for m in reversed(msgs)]

