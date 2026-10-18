from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import CardModel, CardPriority
from ..repositories.card_repository import CardRepository
from .activity_service import ActivityService
from .project_event_publisher import ProjectEventPublisher


class CardService:

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
        item_type: Optional[Any] = None,
        module_instance: Any = None
    ) -> CardModel:
        card = await CardRepository.create_card(
            session=session,
            board_id=str(board_id),
            list_id=str(list_id),
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
            color_cover=color_cover,
            created_by=created_by,
            position=position,
            sprint_id=sprint_id,
            epic_id=epic_id,
            start_date=start_date,
            duration_days=duration_days,
            progress_percent=progress_percent,
            is_milestone=is_milestone,
            story_points=story_points,
            backlog_position=backlog_position,
            item_type=item_type
        )

        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            card_id=card.id,
            user_id=created_by or "system",
            action_type="card_created",
            details={"title": card.title, "list_id": str(list_id)}
        )

        if module_instance:
            await ProjectEventPublisher.publish_event(
                module_instance,
                "card_created",
                {
                    "card_id": card.id,
                    "board_id": str(board_id),
                    "list_id": str(list_id),
                    "title": card.title,
                    "created_by": created_by
                }
            )

        return card

    @staticmethod
    async def get_card(session: AsyncSession, card_id: str) -> Optional[CardModel]:
        return await CardRepository.get_card_by_id(session, str(card_id))

    @staticmethod
    async def update_card(
        session: AsyncSession,
        card_id: str,
        user_id: str = "system",
        **kwargs
    ) -> Optional[CardModel]:
        card = await CardRepository.update_card(session, str(card_id), **kwargs)
        if card:
            # Si l'état de complétion change, synchroniser le progrès
            if "is_completed" in kwargs:
                if kwargs["is_completed"]:
                    card.progress_percent = 100
                    card.completed_at = datetime.utcnow()
                else:
                    if card.progress_percent == 100:
                        card.progress_percent = 0
                    card.completed_at = None
                await session.flush()

            from .gantt_service import GanttService
            await GanttService.recalculate_sprint_and_epic_progress(session, card.id)

            await ActivityService.log_activity(
                session=session,
                board_id=card.board_id,
                card_id=card.id,
                user_id=user_id,
                action_type="card_updated",
                details=kwargs
            )
        return card

    @staticmethod
    async def move_card(
        session: AsyncSession,
        card_id: str,
        target_list_id: str,
        new_position: float,
        user_id: str = "system",
        module_instance: Any = None
    ) -> Optional[CardModel]:
        current_card = await CardRepository.get_card_by_id(session, str(card_id))
        if not current_card:
            return None

        old_list_id = current_card.list_id
        is_list_changed = str(old_list_id) != str(target_list_id)

        # Update card position and list
        card = await CardRepository.move_card(session, str(card_id), str(target_list_id), new_position)
        if not card:
            return None

        # Synchronisation Bidirectionnelle Kanban -> Gantt
        if is_list_changed:
            from ..models.models import ListModel, ColumnType
            from sqlalchemy import select

            target_list = await session.get(ListModel, str(target_list_id))
            if target_list:
                col_type = getattr(target_list, "column_type", ColumnType.IN_PROGRESS)

                if col_type == ColumnType.DONE:
                    # 1. COLONNE DE TYPE TERMINÉ (Succès / Fin = 100%)
                    card.progress_percent = 100
                    card.is_completed = True
                    card.completed_at = datetime.utcnow()
                elif col_type == ColumnType.ENTRY:
                    # 2. COLONNE DE TYPE ENTRÉE (Départ / À faire = 0%)
                    card.progress_percent = 0
                    card.is_completed = False
                    card.completed_at = None
                elif col_type == ColumnType.CANCELLED:
                    # 3. COLONNE DE TYPE ANNULÉ (Abandonné = 0%)
                    card.progress_percent = 0
                    card.is_completed = False
                    card.completed_at = None
                else:
                    # 4. COLONNES DE TYPE EN COURS (Progression échelonnée selon l'étape)
                    res = await session.execute(
                        select(ListModel)
                        .where(
                            ListModel.board_id == target_list.board_id,
                            ListModel.column_type == ColumnType.IN_PROGRESS,
                            ListModel.is_archived == False
                        )
                        .order_by(ListModel.position.asc())
                    )
                    in_progress_lists = res.scalars().all()
                    if in_progress_lists:
                        try:
                            idx = [l.id for l in in_progress_lists].index(target_list.id) + 1
                            total = len(in_progress_lists) + 1
                            card.progress_percent = int(round((idx / total) * 100))
                        except ValueError:
                            card.progress_percent = 50
                    else:
                        card.progress_percent = 50

                    card.is_completed = False
                    card.completed_at = None

                await session.flush()

                from .gantt_service import GanttService
                await GanttService.recalculate_sprint_and_epic_progress(session, card.id)

        await ActivityService.log_activity(
            session=session,
            board_id=card.board_id,
            card_id=card.id,
            user_id=user_id,
            action_type="card_moved",
            details={
                "from_list": old_list_id,
                "to_list": target_list_id,
                "position": new_position,
                "progress_percent": card.progress_percent
            }
        )

        if module_instance and is_list_changed:
            await ProjectEventPublisher.publish_event(
                module_instance,
                "card_moved",
                {
                    "card_id": card.id,
                    "board_id": card.board_id,
                    "from_list_id": old_list_id,
                    "to_list_id": target_list_id,
                    "moved_by": user_id
                }
            )

        return card

    @staticmethod
    async def assign_sprint(
        session: AsyncSession,
        card_id: str,
        sprint_id: Optional[str],
        user_id: str = "system"
    ) -> Optional[CardModel]:
        card = await session.get(CardModel, str(card_id))
        if not card:
            return None

        old_sprint_id = card.sprint_id
        card.sprint_id = str(sprint_id) if sprint_id else None

        if sprint_id:
            from ..models.models import SprintModel
            sprint = await session.get(SprintModel, str(sprint_id))
            if sprint:
                # Aligner les dates de la carte si elles sont non définies ou hors du sprint
                if not card.start_date or card.start_date < sprint.start_date or card.start_date > sprint.end_date:
                    card.start_date = sprint.start_date
                if not card.due_date or card.due_date > sprint.end_date or card.due_date < card.start_date:
                    card.due_date = sprint.end_date

        card.updated_at = datetime.utcnow()
        await session.flush()

        from .gantt_service import GanttService
        await GanttService.recalculate_sprint_and_epic_progress(session, card.id)
        if old_sprint_id and old_sprint_id != card.sprint_id:
            from .sprint_service import SprintService
            await SprintService.recalculate_sprint_progress(session, old_sprint_id)

        await ActivityService.log_activity(
            session=session,
            board_id=card.board_id,
            card_id=card.id,
            user_id=user_id,
            action_type="card_sprint_assigned",
            details={"sprint_id": sprint_id}
        )
        return card

    @staticmethod
    async def reorder_backlog(
        session: AsyncSession,
        board_id: str,
        ordered_card_ids: List[str]
    ) -> None:
        for index, c_id in enumerate(ordered_card_ids):
            card = await session.get(CardModel, str(c_id))
            if card:
                card.backlog_position = (index + 1) * 1000.0
                card.sprint_id = None  # S'assurer que le backlog a sprint_id = None
        await session.flush()

    @staticmethod
    async def toggle_completed(
        session: AsyncSession,
        card_id: str,
        user_id: str = "system",
        module_instance: Any = None
    ) -> Optional[CardModel]:
        card = await CardRepository.toggle_completed(session, card_id)
        if not card:
            return None

        from .gantt_service import GanttService
        await GanttService.recalculate_sprint_and_epic_progress(session, card.id)

        action = "card_completed" if card.is_completed else "card_reopened"
        await ActivityService.log_activity(
            session=session,
            board_id=card.board_id,
            card_id=card.id,
            user_id=user_id,
            action_type=action,
            details={"is_completed": card.is_completed}
        )

        if module_instance and card.is_completed:
            await ProjectEventPublisher.publish_event(
                module_instance,
                "card_completed",
                {"card_id": card.id, "board_id": card.board_id, "completed_by": user_id}
            )

        return card

    @staticmethod
    async def delete_card(session: AsyncSession, card_id: str, user_id: str = "system") -> bool:
        card = await CardRepository.get_card_by_id(session, str(card_id))
        if not card:
            return False
        board_id = card.board_id
        title = card.title
        success = await CardRepository.delete_card(session, str(card_id))
        if success:
            await ActivityService.log_activity(
                session=session,
                board_id=board_id,
                user_id=user_id,
                action_type="card_deleted",
                details={"card_id": str(card_id), "title": title}
            )
        return success

    @staticmethod
    async def assign_user(
        session: AsyncSession,
        card_id: str,
        user_id: str,
        role: str = "member",
        assigned_by: str = "system",
        module_instance: Any = None
    ) -> Any:
        card = await CardRepository.get_card_by_id(session, str(card_id))
        if not card:
            return None

        # Vérification stricte : l'utilisateur doit obligatoirement être membre du projet
        from ..repositories.board_repository import BoardRepository
        is_member = await BoardRepository.is_board_member(session, card.board_id, user_id)
        if not is_member:
            raise ValueError("L'utilisateur n'est pas membre de ce projet. Ajoutez-le d'abord au projet avant de lui assigner des tâches.")

        member = await CardRepository.assign_user(session, str(card_id), user_id, role)
        await ActivityService.log_activity(
            session=session,
            board_id=card.board_id,
            card_id=str(card_id),
            user_id=assigned_by,
            action_type="member_assigned",
            details={"assigned_user": user_id, "role": role}
        )

        if module_instance:
            await ProjectEventPublisher.publish_event(
                module_instance,
                "member_assigned",
                {"card_id": str(card_id), "user_id": user_id, "board_id": card.board_id}
            )

        return member

    @staticmethod
    async def unassign_user(
        session: AsyncSession,
        card_id: str,
        user_id: str,
        unassigned_by: str = "system"
    ) -> bool:
        card = await CardRepository.get_card_by_id(session, str(card_id))
        if not card:
            return False

        success = await CardRepository.unassign_user(session, str(card_id), user_id)
        if success:
            await ActivityService.log_activity(
                session=session,
                board_id=card.board_id,
                card_id=str(card_id),
                user_id=unassigned_by,
                action_type="member_unassigned",
                details={"unassigned_user": user_id}
            )
        return success

    @staticmethod
    async def attach_label(session: AsyncSession, card_id: str, label_id: str) -> Any:
        return await CardRepository.attach_label(session, str(card_id), str(label_id))

    @staticmethod
    async def detach_label(session: AsyncSession, card_id: str, label_id: str) -> bool:
        return await CardRepository.detach_label(session, str(card_id), str(label_id))

    @staticmethod
    async def add_comment(session: AsyncSession, card_id: str, user_id: str, content: str) -> Any:
        card = await CardRepository.get_card_by_id(session, str(card_id))
        if not card:
            return None

        comment = await CardRepository.add_comment(session, str(card_id), user_id, content)
        await ActivityService.log_activity(
            session=session,
            board_id=card.board_id,
            card_id=str(card_id),
            user_id=user_id,
            action_type="comment_added",
            details={"comment_id": comment.id}
        )
        return comment
