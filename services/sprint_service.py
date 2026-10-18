import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import SprintModel, SprintStatus, CardModel
from .activity_service import ActivityService


class SprintService:

    @staticmethod
    async def list_sprints(
        session: AsyncSession,
        board_id: str,
        status: Optional[str] = None
    ) -> List[SprintModel]:
        stmt = (
            select(SprintModel)
            .where(SprintModel.board_id == str(board_id))
            .options(
                selectinload(SprintModel.cards).selectinload(CardModel.epic),
                selectinload(SprintModel.cards).selectinload(CardModel.assignees),
                selectinload(SprintModel.cards).selectinload(CardModel.card_labels),
            )
            .order_by(SprintModel.start_date.asc())
        )
        if status:
            try:
                st = SprintStatus(status)
                stmt = stmt.where(SprintModel.status == st)
            except ValueError:
                pass

        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_sprint(session: AsyncSession, sprint_id: str) -> Optional[SprintModel]:
        stmt = (
            select(SprintModel)
            .where(SprintModel.id == str(sprint_id))
            .options(
                selectinload(SprintModel.cards).selectinload(CardModel.epic),
                selectinload(SprintModel.cards).selectinload(CardModel.assignees),
                selectinload(SprintModel.cards).selectinload(CardModel.card_labels),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_active_sprint(session: AsyncSession, board_id: str) -> Optional[SprintModel]:
        stmt = (
            select(SprintModel)
            .where(
                SprintModel.board_id == str(board_id),
                SprintModel.status == SprintStatus.ACTIVE
            )
            .options(
                selectinload(SprintModel.cards).selectinload(CardModel.epic),
                selectinload(SprintModel.cards).selectinload(CardModel.assignees),
                selectinload(SprintModel.cards).selectinload(CardModel.card_labels),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def check_sprint_overlap(
        session: AsyncSession,
        board_id: str,
        start_date: datetime,
        end_date: datetime,
        exclude_sprint_id: Optional[str] = None
    ) -> Optional[SprintModel]:
        """
        Vérifie qu'aucun autre sprint planifié ou actif du même tableau ne chevauche l'intervalle [start_date, end_date].
        """
        stmt = select(SprintModel).where(
            SprintModel.board_id == str(board_id),
            SprintModel.status.in_([SprintStatus.PLANNED, SprintStatus.ACTIVE]),
            or_(
                # Début du nouveau sprint inclus dans un sprint existant
                and_(SprintModel.start_date <= start_date, SprintModel.end_date >= start_date),
                # Fin du nouveau sprint incluse dans un sprint existant
                and_(SprintModel.start_date <= end_date, SprintModel.end_date >= end_date),
                # Nouveau sprint englobe entièrement un sprint existant
                and_(SprintModel.start_date >= start_date, SprintModel.end_date <= end_date),
            )
        )
        if exclude_sprint_id:
            stmt = stmt.where(SprintModel.id != str(exclude_sprint_id))

        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def create_sprint(
        session: AsyncSession,
        board_id: str,
        name: str,
        start_date: datetime,
        end_date: datetime,
        goal: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> SprintModel:
        if end_date <= start_date:
            raise ValueError("La date de fin du sprint doit être strictement postérieure à la date de début.")

        overlap = await SprintService.check_sprint_overlap(session, board_id, start_date, end_date)
        if overlap:
            raise ValueError(f"Le sprint chevauche la période du sprint existant '{overlap.name}' ({overlap.start_date.strftime('%Y-%m-%d')} au {overlap.end_date.strftime('%Y-%m-%d')}).")

        sprint = SprintModel(
            id=str(uuid.uuid4()),
            board_id=str(board_id),
            name=name.strip(),
            goal=goal.strip() if goal else None,
            start_date=start_date,
            end_date=end_date,
            status=SprintStatus.PLANNED,
            created_by=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(sprint)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            user_id=user_id or "system",
            action_type="sprint_created",
            details={"sprint_id": sprint.id, "name": sprint.name}
        )

        return sprint

    @staticmethod
    async def update_sprint(
        session: AsyncSession,
        sprint_id: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Optional[SprintModel]:
        sprint = await session.get(SprintModel, str(sprint_id))
        if not sprint:
            return None

        new_start = kwargs.get("start_date", sprint.start_date)
        new_end = kwargs.get("end_date", sprint.end_date)

        if new_end <= new_start:
            raise ValueError("La date de fin du sprint doit être strictement postérieure à la date de début.")

        if "start_date" in kwargs or "end_date" in kwargs:
            overlap = await SprintService.check_sprint_overlap(
                session, sprint.board_id, new_start, new_end, exclude_sprint_id=sprint.id
            )
            if overlap:
                raise ValueError(f"Le sprint chevauche la période du sprint existant '{overlap.name}'.")

        for k, v in kwargs.items():
            if hasattr(sprint, k) and k not in ("id", "board_id", "created_at"):
                setattr(sprint, k, v)

        sprint.updated_at = datetime.utcnow()
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=sprint.board_id,
            user_id=user_id or "system",
            action_type="sprint_updated",
            details=kwargs
        )

        return sprint

    @staticmethod
    async def start_sprint(
        session: AsyncSession,
        sprint_id: str,
        user_id: Optional[str] = None
    ) -> SprintModel:
        sprint = await session.get(SprintModel, str(sprint_id))
        if not sprint:
            raise ValueError("Sprint introuvable.")

        # Vérifier qu'aucun autre sprint n'est déjà actif sur ce tableau
        active_sprint = await SprintService.get_active_sprint(session, sprint.board_id)
        if active_sprint and active_sprint.id != sprint.id:
            raise ValueError(f"Le sprint '{active_sprint.name}' est déjà en cours. Veuillez le terminer avant d'en démarrer un autre.")

        sprint.status = SprintStatus.ACTIVE
        sprint.updated_at = datetime.utcnow()
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=sprint.board_id,
            user_id=user_id or "system",
            action_type="sprint_started",
            details={"sprint_id": sprint.id, "name": sprint.name}
        )

        return sprint

    @staticmethod
    async def recalculate_sprint_progress(session: AsyncSession, sprint_id: str) -> Optional[SprintModel]:
        """
        Recalcule les story points et le pourcentage d'avancement du sprint en agrégeant ses cartes.
        """
        sprint = await session.get(SprintModel, str(sprint_id))
        if not sprint:
            return None

        cards_stmt = select(CardModel).where(
            CardModel.sprint_id == sprint.id,
            CardModel.is_archived == False
        )
        sp_cards = (await session.execute(cards_stmt)).scalars().all()

        total_sp = sum(c.story_points or 1 for c in sp_cards)
        done_sp = sum((c.story_points or 1) * ((c.progress_percent or (100 if c.is_completed else 0)) / 100.0) for c in sp_cards)

        sprint.total_story_points = sum(c.story_points or 0 for c in sp_cards)
        sprint.velocity_achieved = sum(c.story_points or 0 for c in sp_cards if c.is_completed)
        sprint.progress_percent = int((done_sp / total_sp) * 100) if total_sp > 0 else 0
        sprint.updated_at = datetime.utcnow()
        await session.flush()
        return sprint

    @staticmethod
    async def complete_sprint(
        session: AsyncSession,
        sprint_id: str,
        user_id: Optional[str] = None,
        move_incomplete_to: str = "backlog"
    ) -> SprintModel:
        sprint = await SprintService.get_sprint(session, str(sprint_id))
        if not sprint:
            raise ValueError("Sprint introuvable.")

        cards = sprint.cards or []
        velocity = 0
        incomplete_cards: List[CardModel] = []

        for card in cards:
            sp = card.story_points or 0
            if card.is_completed:
                velocity += sp
            else:
                incomplete_cards.append(card)

        sprint.velocity_achieved = velocity
        sprint.status = SprintStatus.COMPLETED
        sprint.updated_at = datetime.utcnow()

        # Gestion des cartes incomplètes
        target_sprint_id = None
        if move_incomplete_to == "next_sprint":
            # Trouver le prochain sprint planifié
            stmt = (
                select(SprintModel)
                .where(
                    SprintModel.board_id == sprint.board_id,
                    SprintModel.status == SprintStatus.PLANNED,
                    SprintModel.start_date >= sprint.end_date
                )
                .order_by(SprintModel.start_date.asc())
            )
            res = await session.execute(stmt)
            next_sprint = res.scalars().first()
            if next_sprint:
                target_sprint_id = next_sprint.id

        for c in incomplete_cards:
            c.sprint_id = target_sprint_id
            c.updated_at = datetime.utcnow()

        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=sprint.board_id,
            user_id=user_id or "system",
            action_type="sprint_completed",
            details={
                "sprint_id": sprint.id,
                "velocity_achieved": velocity,
                "incomplete_moved": len(incomplete_cards),
                "target_sprint_id": target_sprint_id
            }
        )

        return sprint

    @staticmethod
    async def delete_sprint(
        session: AsyncSession,
        sprint_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        sprint = await SprintService.get_sprint(session, str(sprint_id))
        if not sprint:
            return False

        # Remettre les cartes dans le backlog
        for c in sprint.cards:
            c.sprint_id = None

        board_id = sprint.board_id
        await session.delete(sprint)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=board_id,
            user_id=user_id or "system",
            action_type="sprint_deleted",
            details={"sprint_id": sprint_id}
        )

        return True
