from datetime import datetime
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.card_repository import CardRepository
from .activity_service import ActivityService


class ChecklistService:

    @staticmethod
    async def create_checklist(
        session: AsyncSession,
        card_id: str,
        title: str = "Checklist",
        user_id: str = "system"
    ):
        cl = await CardRepository.create_checklist(session, str(card_id), title)
        card = await CardRepository.get_card_by_id(session, str(card_id))
        if card:
            await ActivityService.log_activity(
                session=session,
                board_id=card.board_id,
                card_id=str(card_id),
                user_id=user_id,
                action_type="checklist_created",
                details={"checklist_id": cl.id, "title": cl.title}
            )
        return cl

    @staticmethod
    async def delete_checklist(session: AsyncSession, checklist_id: str, user_id: str = "system") -> bool:
        return await CardRepository.delete_checklist(session, str(checklist_id))

    @staticmethod
    async def add_item(
        session: AsyncSession,
        checklist_id: str,
        title: str,
        due_date: Optional[datetime] = None,
        user_id: str = "system"
    ):
        return await CardRepository.add_checklist_item(session, str(checklist_id), title, due_date)

    @staticmethod
    async def toggle_item(session: AsyncSession, item_id: str, user_id: str = "system"):
        return await CardRepository.toggle_checklist_item(session, str(item_id))

    @staticmethod
    async def delete_item(session: AsyncSession, item_id: str, user_id: str = "system") -> bool:
        return await CardRepository.delete_checklist_item(session, str(item_id))
