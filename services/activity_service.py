import json
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from ..repositories.card_repository import CardRepository


class ActivityService:

    @staticmethod
    async def log_activity(
        session: AsyncSession,
        board_id: str,
        user_id: str,
        action_type: str,
        card_id: Optional[str] = None,
        details: Optional[Any] = None
    ):
        details_str = json.dumps(details) if isinstance(details, (dict, list)) else (str(details) if details else None)
        return await CardRepository.add_activity(
            session=session,
            board_id=str(board_id),
            user_id=user_id,
            action_type=action_type,
            card_id=str(card_id) if card_id else None,
            details=details_str
        )
