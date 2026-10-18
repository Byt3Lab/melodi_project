from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import (
    ListModel,
    CardModel,
    CardMemberModel,
    LabelModel,
    CardLabelModel,
    ChecklistModel,
    ChecklistItemModel,
    CardCommentModel,
    ActivityModel,
    CardPriority,
    ColumnType,
)


class CardRepository:

    # -------------------------------------------------------------
    # LISTS / COLUMNS
    # -------------------------------------------------------------

    @staticmethod
    async def get_lists_by_board(session: AsyncSession, board_id: str, include_archived: bool = False) -> List[ListModel]:
        stmt = select(ListModel).where(ListModel.board_id == str(board_id))
        if not include_archived:
            stmt = stmt.where(ListModel.is_archived == False)
        stmt = stmt.order_by(ListModel.position.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_list_by_id(session: AsyncSession, list_id: str) -> Optional[ListModel]:
        return await session.get(ListModel, str(list_id))

    @staticmethod
    async def get_max_list_position(session: AsyncSession, board_id: str) -> float:
        stmt = select(func.max(ListModel.position)).where(ListModel.board_id == str(board_id))
        res = await session.execute(stmt)
        val = res.scalar()
        return float(val) if val is not None else 0.0

    @staticmethod
    async def create_list(
        session: AsyncSession,
        board_id: str,
        title: str,
        color: Optional[str] = None,
        wip_limit: Optional[int] = None,
        position: Optional[float] = None,
        column_type: ColumnType = ColumnType.IN_PROGRESS
    ) -> ListModel:
        if position is None:
            max_pos = await CardRepository.get_max_list_position(session, str(board_id))
            position = max_pos + 65536.0

        lst = ListModel(
            board_id=str(board_id),
            title=title.strip(),
            color=color,
            wip_limit=wip_limit,
            position=position,
            column_type=column_type,
            is_archived=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(lst)
        await session.flush()
        return lst

    @staticmethod
    async def update_list(session: AsyncSession, list_id: str, **kwargs) -> Optional[ListModel]:
        lst = await session.get(ListModel, str(list_id))
        if not lst:
            return None
        for k, v in kwargs.items():
            if hasattr(lst, k) and k not in ("id", "board_id", "created_at"):
                setattr(lst, k, v)
        lst.updated_at = datetime.utcnow()
        await session.flush()
        return lst

    @staticmethod
    async def delete_list(session: AsyncSession, list_id: str) -> bool:
        lst = await session.get(ListModel, str(list_id))
        if not lst:
            return False
        await session.delete(lst)
        await session.flush()
        return True

    # -------------------------------------------------------------
    # CARDS
    # -------------------------------------------------------------

    @staticmethod
    async def get_card_by_id(session: AsyncSession, card_id: str) -> Optional[CardModel]:
        stmt = (
            select(CardModel)
            .where(CardModel.id == str(card_id))
            .options(
                selectinload(CardModel.assignees),
                selectinload(CardModel.card_labels).selectinload(CardLabelModel.label),
                selectinload(CardModel.checklists).selectinload(ChecklistModel.items),
                selectinload(CardModel.comments),
                selectinload(CardModel.activities),
                selectinload(CardModel.list),
                selectinload(CardModel.sprint),
                selectinload(CardModel.epic),
                selectinload(CardModel.predecessor_links),
                selectinload(CardModel.successor_links),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_cards_by_board(session: AsyncSession, board_id: str, include_archived: bool = False) -> List[CardModel]:
        stmt = (
            select(CardModel)
            .where(CardModel.board_id == str(board_id))
            .options(
                selectinload(CardModel.assignees),
                selectinload(CardModel.card_labels).selectinload(CardLabelModel.label),
                selectinload(CardModel.checklists).selectinload(ChecklistModel.items),
                selectinload(CardModel.comments),
                selectinload(CardModel.list),
                selectinload(CardModel.sprint),
                selectinload(CardModel.epic),
            )
        )
        if not include_archived:
            stmt = stmt.where(CardModel.is_archived == False)
        stmt = stmt.order_by(CardModel.position.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_max_card_position(session: AsyncSession, list_id: str) -> float:
        stmt = select(func.max(CardModel.position)).where(CardModel.list_id == str(list_id))
        res = await session.execute(stmt)
        val = res.scalar()
        return float(val) if val is not None else 0.0

    @staticmethod
    async def create_card(
        session: AsyncSession,
        board_id: str,
        list_id: str,
        title: str,
        description: Optional[str] = None,
        priority: CardPriority = CardPriority.MEDIUM,
        due_date: Optional[datetime] = None,
        color_cover: Optional[str] = None,
        created_by: Optional[str] = None,
        position: Optional[float] = None,
        sprint_id: Optional[str] = None,
        epic_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        duration_days: float = 1.0,
        progress_percent: int = 0,
        is_milestone: bool = False,
        story_points: Optional[int] = None,
        backlog_position: Optional[float] = None,
        item_type: Optional[Any] = None
    ) -> CardModel:
        if position is None:
            max_pos = await CardRepository.get_max_card_position(session, str(list_id))
            position = max_pos + 65536.0

        card = CardModel(
            board_id=str(board_id),
            list_id=str(list_id),
            title=title.strip(),
            description=description.strip() if description else None,
            priority=priority,
            due_date=due_date,
            color_cover=color_cover,
            created_by=created_by,
            position=position,
            sprint_id=str(sprint_id) if sprint_id else None,
            epic_id=str(epic_id) if epic_id else None,
            start_date=start_date,
            duration_days=duration_days,
            progress_percent=progress_percent,
            is_milestone=is_milestone,
            story_points=story_points,
            backlog_position=backlog_position or position,
            item_type=item_type if item_type else "task",
            is_completed=False,
            is_archived=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(card)
        await session.flush()
        return card

    @staticmethod
    async def update_card(session: AsyncSession, card_id: str, **kwargs) -> Optional[CardModel]:
        card = await session.get(CardModel, str(card_id))
        if not card:
            return None
        for k, v in kwargs.items():
            if hasattr(card, k) and k not in ("id", "board_id", "created_at"):
                setattr(card, k, v)
        card.updated_at = datetime.utcnow()
        await session.flush()
        return card

    @staticmethod
    async def move_card(
        session: AsyncSession,
        card_id: str,
        target_list_id: str,
        new_position: float
    ) -> Optional[CardModel]:
        card = await session.get(CardModel, str(card_id))
        if not card:
            return None

        card.list_id = str(target_list_id)
        card.position = new_position
        card.updated_at = datetime.utcnow()
        await session.flush()
        return card

    @staticmethod
    async def toggle_completed(session: AsyncSession, card_id: str) -> Optional[CardModel]:
        card = await session.get(CardModel, str(card_id))
        if not card:
            return None
        card.is_completed = not card.is_completed
        card.completed_at = datetime.utcnow() if card.is_completed else None
        card.progress_percent = 100 if card.is_completed else 0
        card.updated_at = datetime.utcnow()
        await session.flush()
        return card

    @staticmethod
    async def delete_card(session: AsyncSession, card_id: str) -> bool:
        card = await session.get(CardModel, str(card_id))
        if not card:
            return False
        await session.delete(card)
        await session.flush()
        return True

    # -------------------------------------------------------------
    # LABELS
    # -------------------------------------------------------------

    @staticmethod
    async def get_labels_by_board(session: AsyncSession, board_id: str) -> List[LabelModel]:
        stmt = select(LabelModel).where(LabelModel.board_id == str(board_id)).order_by(LabelModel.name.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def create_label(session: AsyncSession, board_id: str, name: str, color: str) -> LabelModel:
        label = LabelModel(board_id=str(board_id), name=name.strip(), color=color or "#3B82F6")
        session.add(label)
        await session.flush()
        return label

    @staticmethod
    async def attach_label(session: AsyncSession, card_id: str, label_id: str) -> CardLabelModel:
        stmt = select(CardLabelModel).where(CardLabelModel.card_id == str(card_id), CardLabelModel.label_id == str(label_id))
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        cl = CardLabelModel(card_id=str(card_id), label_id=str(label_id))
        session.add(cl)
        await session.flush()
        return cl

    @staticmethod
    async def detach_label(session: AsyncSession, card_id: str, label_id: str) -> bool:
        stmt = delete(CardLabelModel).where(CardLabelModel.card_id == str(card_id), CardLabelModel.label_id == str(label_id))
        res = await session.execute(stmt)
        await session.flush()
        return res.rowcount > 0

    # -------------------------------------------------------------
    # MEMBERS / ASSIGNEES
    # -------------------------------------------------------------

    @staticmethod
    async def assign_user(session: AsyncSession, card_id: str, user_id: str, role: str = "member") -> CardMemberModel:
        stmt = select(CardMemberModel).where(CardMemberModel.card_id == str(card_id), CardMemberModel.user_id == str(user_id))
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        cm = CardMemberModel(card_id=str(card_id), user_id=str(user_id), role=role, created_at=datetime.utcnow())
        session.add(cm)
        await session.flush()
        return cm

    @staticmethod
    async def unassign_user(session: AsyncSession, card_id: str, user_id: str) -> bool:
        stmt = delete(CardMemberModel).where(CardMemberModel.card_id == str(card_id), CardMemberModel.user_id == str(user_id))
        res = await session.execute(stmt)
        await session.flush()
        return res.rowcount > 0

    @staticmethod
    async def get_user_assigned_cards(session: AsyncSession, user_id: str) -> List[CardModel]:
        stmt = (
            select(CardModel)
            .join(CardMemberModel, CardMemberModel.card_id == CardModel.id)
            .where(
                CardMemberModel.user_id == str(user_id),
                CardModel.is_archived == False,
                CardModel.is_completed == False
            )
            .order_by(CardModel.due_date.asc().nulls_last())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    # -------------------------------------------------------------
    # CHECKLISTS & ITEMS
    # -------------------------------------------------------------

    @staticmethod
    async def create_checklist(session: AsyncSession, card_id: str, title: str = "Checklist") -> ChecklistModel:
        stmt = select(func.count(ChecklistModel.id)).where(ChecklistModel.card_id == str(card_id))
        res = await session.execute(stmt)
        count = res.scalar() or 0

        cl = ChecklistModel(card_id=str(card_id), title=title.strip() or "Checklist", position=count)
        session.add(cl)
        await session.flush()
        return cl

    @staticmethod
    async def delete_checklist(session: AsyncSession, checklist_id: str) -> bool:
        cl = await session.get(ChecklistModel, str(checklist_id))
        if not cl:
            return False
        await session.delete(cl)
        await session.flush()
        return True

    @staticmethod
    async def add_checklist_item(
        session: AsyncSession,
        checklist_id: str,
        title: str,
        due_date: Optional[datetime] = None
    ) -> ChecklistItemModel:
        stmt = select(func.count(ChecklistItemModel.id)).where(ChecklistItemModel.checklist_id == str(checklist_id))
        res = await session.execute(stmt)
        count = res.scalar() or 0

        item = ChecklistItemModel(
            checklist_id=str(checklist_id),
            title=title.strip(),
            is_done=False,
            position=count,
            due_date=due_date
        )
        session.add(item)
        await session.flush()
        return item

    @staticmethod
    async def toggle_checklist_item(session: AsyncSession, item_id: str) -> Optional[ChecklistItemModel]:
        item = await session.get(ChecklistItemModel, str(item_id))
        if not item:
            return None
        item.is_done = not item.is_done
        await session.flush()
        return item

    @staticmethod
    async def delete_checklist_item(session: AsyncSession, item_id: str) -> bool:
        item = await session.get(ChecklistItemModel, str(item_id))
        if not item:
            return False
        await session.delete(item)
        await session.flush()
        return True

    # -------------------------------------------------------------
    # COMMENTS
    # -------------------------------------------------------------

    @staticmethod
    async def add_comment(session: AsyncSession, card_id: str, user_id: str, content: str) -> CardCommentModel:
        comment = CardCommentModel(
            card_id=str(card_id),
            user_id=str(user_id),
            content=content.strip(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(comment)
        await session.flush()
        return comment

    @staticmethod
    async def delete_comment(session: AsyncSession, comment_id: str) -> bool:
        comment = await session.get(CardCommentModel, str(comment_id))
        if not comment:
            return False
        await session.delete(comment)
        await session.flush()
        return True

    # -------------------------------------------------------------
    # ACTIVITIES
    # -------------------------------------------------------------

    @staticmethod
    async def add_activity(
        session: AsyncSession,
        board_id: str,
        user_id: str,
        action_type: str,
        card_id: Optional[str] = None,
        details: Optional[str] = None
    ) -> ActivityModel:
        act = ActivityModel(
            board_id=str(board_id),
            card_id=str(card_id) if card_id else None,
            user_id=str(user_id),
            action_type=action_type,
            details=details,
            created_at=datetime.utcnow()
        )
        session.add(act)
        await session.flush()
        return act
