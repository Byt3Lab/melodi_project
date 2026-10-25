from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import BoardModel, BoardVisibility, ColumnType
from ..repositories.board_repository import BoardRepository
from ..repositories.card_repository import CardRepository
from .activity_service import ActivityService
from .project_event_publisher import ProjectEventPublisher


class BoardService:

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
        create_default_lists: bool = True,
        project_type: str = "hybrid",
        default_view: str = "kanban",
        module_instance: Any = None
    ) -> BoardModel:
        board = await BoardRepository.create_board(
            session=session,
            title=title,
            description=description,
            color=color,
            icon=icon,
            visibility=visibility,
            created_by=created_by,
            is_favorite=is_favorite,
            project_type=project_type,
            default_view=default_view
        )

        # Automatically add creator as owner member of the project
        creator_id = created_by or "admin"
        await BoardRepository.add_board_member(
            session=session,
            board_id=board.id,
            user_id=creator_id,
            role="owner"
        )

        if create_default_lists:
            # Création automatique et obligatoire des 3 colonnes de base : Début, Fini, Annulé
            default_lists = [
                ("Début", "#64748B", 1000.0, ColumnType.ENTRY),
                ("Fini", "#10B981", 2000.0, ColumnType.DONE),
                ("Annulé", "#EF4444", 3000.0, ColumnType.CANCELLED),
            ]
            for l_title, l_color, l_pos, l_type in default_lists:
                await CardRepository.create_list(
                    session=session,
                    board_id=board.id,
                    title=l_title,
                    color=l_color,
                    position=l_pos,
                    column_type=l_type
                )

            # Création des étiquettes de base
            default_labels = [
                ("Bug", "#EF4444"),
                ("Feature", "#3B82F6"),
                ("Amélioration", "#10B981"),
                ("Design", "#8B5CF6"),
                ("Urgent", "#F97316"),
            ]
            for lbl_name, lbl_color in default_labels:
                await CardRepository.create_label(
                    session=session,
                    board_id=board.id,
                    name=lbl_name,
                    color=lbl_color
                )

        # Audit activity
        await ActivityService.log_activity(
            session=session,
            board_id=board.id,
            user_id=created_by or "system",
            action_type="board_created",
            details={"title": board.title}
        )

        if module_instance:
            await ProjectEventPublisher.publish_event(
                module_instance,
                "board_created",
                {"board_id": board.id, "title": board.title, "created_by": created_by}
            )

        return board

    @staticmethod
    async def get_board(session: AsyncSession, board_id: str) -> Optional[BoardModel]:
        return await BoardRepository.get_board_by_id(session, str(board_id))

    @staticmethod
    async def list_boards(
        session: AsyncSession,
        search: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        is_archived: bool = False,
        created_by: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[BoardModel]:
        return await BoardRepository.get_all_boards(
            session=session,
            search=search,
            is_favorite=is_favorite,
            is_archived=is_archived,
            created_by=created_by,
            limit=limit,
            offset=offset
        )

    @staticmethod
    async def update_board(
        session: AsyncSession,
        board_id: str,
        user_id: str = "system",
        **kwargs
    ) -> Optional[BoardModel]:
        board = await BoardRepository.update_board(session, str(board_id), **kwargs)
        if board:
            await ActivityService.log_activity(
                session=session,
                board_id=board.id,
                user_id=user_id,
                action_type="board_updated",
                details=kwargs
            )
        return board

    @staticmethod
    async def toggle_favorite(session: AsyncSession, board_id: str) -> Optional[BoardModel]:
        return await BoardRepository.toggle_favorite(session, str(board_id))

    @staticmethod
    async def archive_board(session: AsyncSession, board_id: str, user_id: str = "system") -> Optional[BoardModel]:
        board = await BoardRepository.update_board(session, str(board_id), is_archived=True)
        if board:
            await ActivityService.log_activity(
                session=session,
                board_id=board.id,
                user_id=user_id,
                action_type="board_archived"
            )
        return board

    @staticmethod
    async def unarchive_board(session: AsyncSession, board_id: str, user_id: str = "system") -> Optional[BoardModel]:
        board = await BoardRepository.update_board(session, str(board_id), is_archived=False)
        if board:
            await ActivityService.log_activity(
                session=session,
                board_id=board.id,
                user_id=user_id,
                action_type="board_unarchived"
            )
        return board

    @staticmethod
    async def delete_board(session: AsyncSession, board_id: str) -> bool:
        return await BoardRepository.delete_board(session, str(board_id))

    @staticmethod
    async def get_board_summary(session: AsyncSession, board_id: str) -> Dict[str, Any]:
        board = await BoardRepository.get_board_by_id(session, str(board_id))
        if not board:
            return {}

        total_cards = 0
        completed_cards = 0
        assignees_set = set()

        if board.lists:
            for lst in board.lists:
                if lst.cards:
                    for card in lst.cards:
                        total_cards += 1
                        if card.is_completed:
                            completed_cards += 1
                        if card.assignees:
                            for a in card.assignees:
                                assignees_set.add(a.user_id)

        percent = int((completed_cards / total_cards * 100)) if total_cards > 0 else 0
        active_sprint = next((s for s in board.sprints if getattr(s.status, "value", s.status) == "active"), None) if hasattr(board, "__dict__") and "sprints" in board.__dict__ and board.sprints else None

        members = await BoardRepository.get_board_members(session, str(board_id))
        member_ids = [m.user_id for m in members] if members else list(assignees_set)
        members_count = len(members) if members else len(assignees_set)

        return {
            "id": board.id,
            "title": board.title,
            "color": board.color,
            "total_lists": len(board.lists) if hasattr(board, "__dict__") and "lists" in board.__dict__ and board.lists else 0,
            "total_cards": total_cards,
            "completed_cards": completed_cards,
            "progress_percent": percent,
            "members_count": members_count,
            "members": member_ids[:5],
            "total_sprints": len(board.sprints) if hasattr(board, "__dict__") and "sprints" in board.__dict__ and board.sprints else 0,
            "active_sprint": active_sprint.to_dict() if active_sprint else None,
            "total_epics": len(board.epics) if hasattr(board, "__dict__") and "epics" in board.__dict__ and board.epics else 0,
        }

    @staticmethod
    async def list_board_members(session: AsyncSession, board_id: str) -> List[Any]:
        return await BoardRepository.get_board_members(session, str(board_id))

    @staticmethod
    async def add_board_member(
        session: AsyncSession,
        board_id: str,
        user_id: str,
        role: str = "member",
        added_by: str = "system",
        module_instance: Any = None
    ) -> Any:
        board = await BoardRepository.get_board_by_id(session, str(board_id))
        if not board:
            return None

        member = await BoardRepository.add_board_member(session, str(board_id), user_id, role)
        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            user_id=added_by,
            action_type="project_member_added",
            details={"user_id": user_id, "role": role}
        )
        if module_instance:
            await ProjectEventPublisher.publish_event(
                module_instance,
                "project_member_added",
                {"board_id": str(board_id), "user_id": user_id, "role": role}
            )
        return member

    @staticmethod
    async def remove_board_member(
        session: AsyncSession,
        board_id: str,
        user_id: str,
        removed_by: str = "system",
        module_instance: Any = None
    ) -> bool:
        board = await BoardRepository.get_board_by_id(session, str(board_id))
        if not board:
            return False

        members = await BoardRepository.get_board_members(session, str(board_id))
        if len(members) <= 1:
            raise ValueError("Impossible de retirer le dernier membre du projet.")

        success = await BoardRepository.remove_board_member(session, str(board_id), user_id)
        if success:
            await ActivityService.log_activity(
                session=session,
                board_id=str(board_id),
                user_id=removed_by,
                action_type="project_member_removed",
                details={"user_id": user_id}
            )
            if module_instance:
                await ProjectEventPublisher.publish_event(
                    module_instance,
                    "project_member_removed",
                    {"board_id": str(board_id), "user_id": user_id}
                )
        return success

