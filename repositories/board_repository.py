from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, or_, and_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import (
    BoardModel,
    BoardMemberModel,
    ListModel,
    CardModel,
    LabelModel,
    ActivityModel,
    ChecklistModel,
    BoardVisibility,
)


class BoardRepository:

    @staticmethod
    async def get_board_by_id(session: AsyncSession, board_id: str) -> Optional[BoardModel]:
        stmt = (
            select(BoardModel)
            .where(BoardModel.id == str(board_id))
            .options(
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.card_labels).selectinload(CardModel.card_labels.property.mapper.class_.label),
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.assignees),
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.checklists).selectinload(ChecklistModel.items),
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.comments),
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.epic),
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.sprint),
                selectinload(BoardModel.labels),
                selectinload(BoardModel.activities),
                selectinload(BoardModel.sprints),
                selectinload(BoardModel.epics),
                selectinload(BoardModel.members),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_all_boards(
        session: AsyncSession,
        search: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        is_archived: bool = False,
        created_by: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[BoardModel]:
        stmt = (
            select(BoardModel)
            .where(BoardModel.is_archived == is_archived)
            .options(
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.epic),
                selectinload(BoardModel.lists).selectinload(ListModel.cards).selectinload(CardModel.sprint),
                selectinload(BoardModel.labels),
                selectinload(BoardModel.members),
            )
        )

        if is_favorite is not None:
            stmt = stmt.where(BoardModel.is_favorite == is_favorite)

        if created_by:
            stmt = stmt.where(BoardModel.created_by == str(created_by))

        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(BoardModel.title.ilike(pattern), BoardModel.description.ilike(pattern)))

        stmt = stmt.order_by(BoardModel.is_favorite.desc(), BoardModel.updated_at.desc()).limit(limit).offset(offset)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def count_boards(session: AsyncSession, is_archived: bool = False) -> int:
        stmt = select(func.count(BoardModel.id)).where(BoardModel.is_archived == is_archived)
        res = await session.execute(stmt)
        return res.scalar() or 0

    @staticmethod
    async def create_board(
        session: AsyncSession,
        title: str,
        description: Optional[str] = None,
        color: str = "#4F46E5",
        icon: str = "dashboard",
        visibility: BoardVisibility = BoardVisibility.TEAM,
        created_by: Optional[str] = None,
        is_favorite: bool = False,
        project_type: str = "hybrid",
        default_view: str = "kanban"
    ) -> BoardModel:
        board = BoardModel(
            title=title.strip(),
            description=description.strip() if description else None,
            color=color or "#4F46E5",
            icon=icon or "dashboard",
            visibility=visibility,
            created_by=created_by,
            is_favorite=is_favorite,
            is_archived=False,
            project_type=project_type or "hybrid",
            default_view=default_view or "kanban",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(board)
        await session.flush()
        return board

    @staticmethod
    async def update_board(
        session: AsyncSession,
        board_id: str,
        **kwargs
    ) -> Optional[BoardModel]:
        board = await session.get(BoardModel, str(board_id))
        if not board:
            return None

        for key, val in kwargs.items():
            if hasattr(board, key) and key not in ("id", "created_at"):
                setattr(board, key, val)

        board.updated_at = datetime.utcnow()
        await session.flush()
        return board

    @staticmethod
    async def toggle_favorite(session: AsyncSession, board_id: str) -> Optional[BoardModel]:
        board = await session.get(BoardModel, str(board_id))
        if not board:
            return None
        board.is_favorite = not board.is_favorite
        board.updated_at = datetime.utcnow()
        await session.flush()
        return board

    @staticmethod
    async def delete_board(session: AsyncSession, board_id: str) -> bool:
        board = await session.get(BoardModel, str(board_id))
        if not board:
            return False
        await session.delete(board)
        await session.flush()
        return True

    @staticmethod
    async def get_global_stats(session: AsyncSession) -> Dict[str, Any]:
        now = datetime.utcnow()

        total_boards_stmt = select(func.count(BoardModel.id)).where(BoardModel.is_archived == False)
        active_cards_stmt = select(func.count(CardModel.id)).where(
            CardModel.is_archived == False,
            CardModel.is_completed == False
        )
        overdue_cards_stmt = select(func.count(CardModel.id)).where(
            CardModel.is_archived == False,
            CardModel.is_completed == False,
            CardModel.due_date < now
        )
        completed_cards_stmt = select(func.count(CardModel.id)).where(
            CardModel.is_archived == False,
            CardModel.is_completed == True
        )

        res_b = await session.execute(total_boards_stmt)
        res_a = await session.execute(active_cards_stmt)
        res_o = await session.execute(overdue_cards_stmt)
        res_c = await session.execute(completed_cards_stmt)

        return {
            "total_boards": res_b.scalar() or 0,
            "active_cards": res_a.scalar() or 0,
            "overdue_cards": res_o.scalar() or 0,
            "completed_cards": res_c.scalar() or 0,
        }

    @staticmethod
    async def get_board_members(session: AsyncSession, board_id: str) -> List[BoardMemberModel]:
        stmt = (
            select(BoardMemberModel)
            .where(BoardMemberModel.board_id == str(board_id))
            .order_by(BoardMemberModel.created_at.asc())
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def add_board_member(
        session: AsyncSession,
        board_id: str,
        user_id: str,
        role: str = "member"
    ) -> BoardMemberModel:
        stmt = select(BoardMemberModel).where(
            BoardMemberModel.board_id == str(board_id),
            BoardMemberModel.user_id == str(user_id)
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            existing.role = role
            await session.flush()
            return existing

        member = BoardMemberModel(
            board_id=str(board_id),
            user_id=str(user_id),
            role=role,
            created_at=datetime.utcnow()
        )
        session.add(member)
        await session.flush()
        return member

    @staticmethod
    async def remove_board_member(session: AsyncSession, board_id: str, user_id: str) -> bool:
        stmt = delete(BoardMemberModel).where(
            BoardMemberModel.board_id == str(board_id),
            BoardMemberModel.user_id == str(user_id)
        )
        res = await session.execute(stmt)
        await session.flush()
        return res.rowcount > 0

    @staticmethod
    async def is_board_member(session: AsyncSession, board_id: str, user_id: str) -> bool:
        stmt = select(func.count(BoardMemberModel.id)).where(
            BoardMemberModel.board_id == str(board_id),
            BoardMemberModel.user_id == str(user_id)
        )
        res = await session.execute(stmt)
        count = res.scalar() or 0
        return count > 0
