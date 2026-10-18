import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import EpicModel, EpicStatus, CardModel
from .activity_service import ActivityService


class EpicService:

    @staticmethod
    async def list_epics(
        session: AsyncSession,
        board_id: str,
        status: Optional[str] = None
    ) -> List[EpicModel]:
        stmt = (
            select(EpicModel)
            .where(EpicModel.board_id == str(board_id))
            .options(selectinload(EpicModel.cards))
            .order_by(EpicModel.created_at.asc())
        )
        if status:
            try:
                st = EpicStatus(status)
                stmt = stmt.where(EpicModel.status == st)
            except ValueError:
                pass

        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_epic(session: AsyncSession, epic_id: str) -> Optional[EpicModel]:
        stmt = (
            select(EpicModel)
            .where(EpicModel.id == str(epic_id))
            .options(selectinload(EpicModel.cards))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def create_epic(
        session: AsyncSession,
        board_id: str,
        title: str,
        description: Optional[str] = None,
        color: str = "#8B5CF6",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None
    ) -> EpicModel:
        epic = EpicModel(
            id=str(uuid.uuid4()),
            board_id=str(board_id),
            title=title.strip(),
            description=description.strip() if description else None,
            color=color.strip() or "#8B5CF6",
            start_date=start_date,
            end_date=end_date,
            status=EpicStatus.PLANNED,
            progress_percent=0,
            created_by=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(epic)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            user_id=user_id or "system",
            action_type="epic_created",
            details={"epic_id": epic.id, "title": epic.title}
        )

        return epic

    @staticmethod
    async def update_epic(
        session: AsyncSession,
        epic_id: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Optional[EpicModel]:
        epic = await session.get(EpicModel, str(epic_id))
        if not epic:
            return None

        for k, v in kwargs.items():
            if hasattr(epic, k) and k not in ("id", "board_id", "created_at"):
                setattr(epic, k, v)

        epic.updated_at = datetime.utcnow()
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=epic.board_id,
            user_id=user_id or "system",
            action_type="epic_updated",
            details=kwargs
        )

        return epic

    @staticmethod
    async def delete_epic(
        session: AsyncSession,
        epic_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        epic = await EpicService.get_epic(session, str(epic_id))
        if not epic:
            return False

        for c in epic.cards:
            c.epic_id = None

        board_id = epic.board_id
        await session.delete(epic)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=board_id,
            user_id=user_id or "system",
            action_type="epic_deleted",
            details={"epic_id": epic_id}
        )

        return True

    @staticmethod
    async def recalculate_epic_progress(
        session: AsyncSession,
        epic_id: str
    ) -> Optional[EpicModel]:
        epic = await EpicService.get_epic(session, str(epic_id))
        if not epic:
            return None

        cards = epic.cards or []
        if not cards:
            epic.progress_percent = 0
        else:
            total_cards = len(cards)
            completed_cards = sum(1 for c in cards if c.is_completed)
            total_progress = sum(c.progress_percent or (100 if c.is_completed else 0) for c in cards)
            epic.progress_percent = int(total_progress / total_cards)
            if completed_cards == total_cards:
                epic.status = EpicStatus.COMPLETED
            elif any(c.is_completed or (c.progress_percent and c.progress_percent > 0) for c in cards):
                epic.status = EpicStatus.IN_PROGRESS

            # Ajuster les bornes temporelles de l'Epic pour englober ses cartes
            card_starts = [c.start_date for c in cards if c.start_date]
            card_ends = [c.due_date for c in cards if c.due_date]
            if card_starts:
                epic.start_date = min(card_starts)
            if card_ends:
                epic.end_date = max(card_ends)

        epic.updated_at = datetime.utcnow()
        await session.flush()
        return epic
