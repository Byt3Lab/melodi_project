import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import (
    BoardModel,
    CardModel,
    SprintModel,
    EpicModel,
    TaskDependencyModel,
    SprintDependencyModel,
    DependencyType,
    ListModel,
    SprintStatus,
    EpicStatus,
)
from .activity_service import ActivityService
from .epic_service import EpicService


def add_working_days(dt: datetime, days: float, work_week=(1, 2, 3, 4, 5)) -> datetime:
    """Ajoute un nombre de jours en respectant les jours ouvrés (1=Lundi, 7=Dimanche)."""
    curr = dt
    int_days = int(days)
    remainder = days - int_days

    step = 1 if int_days >= 0 else -1
    remaining = abs(int_days)

    while remaining > 0:
        curr += timedelta(days=step)
        if curr.isoweekday() in work_week:
            remaining -= 1

    if remainder > 0:
        curr += timedelta(hours=int(remainder * 24))

    return curr


def subtract_working_days(dt: datetime, days: float, work_week=(1, 2, 3, 4, 5)) -> datetime:
    return add_working_days(dt, -days, work_week)


class GanttService:

    @staticmethod
    async def get_gantt_dataset(session: AsyncSession, board_id: str) -> Dict[str, Any]:
        board = await session.get(BoardModel, str(board_id))
        if not board:
            raise ValueError("Tableau de projet introuvable.")

        # Récupérer les epics
        epics_stmt = select(EpicModel).where(EpicModel.board_id == str(board_id)).order_by(EpicModel.start_date.asc())
        epics_res = await session.execute(epics_stmt)
        epics = [e.to_dict() for e in epics_res.scalars().all()]

        # Récupérer les sprints
        sprints_stmt = select(SprintModel).where(SprintModel.board_id == str(board_id)).order_by(SprintModel.start_date.asc())
        sprints_res = await session.execute(sprints_stmt)
        sprints = [s.to_dict() for s in sprints_res.scalars().all()]

        # Récupérer les listes (colonnes) pour les libellés de statut
        lists_stmt = select(ListModel).where(ListModel.board_id == str(board_id)).order_by(ListModel.position.asc())
        lists_res = await session.execute(lists_stmt)
        list_map = {l.id: l.title for l in lists_res.scalars().all()}

        # Récupérer les cartes avec assignés
        cards_stmt = (
            select(CardModel)
            .where(CardModel.board_id == str(board_id), CardModel.is_archived == False)
            .options(
                selectinload(CardModel.assignees),
                selectinload(CardModel.list)
            )
            .order_by(CardModel.start_date.asc().nulls_last(), CardModel.position.asc())
        )
        cards_res = await session.execute(cards_stmt)
        cards = cards_res.scalars().all()

        tasks_data = []
        for c in cards:
            c_dict = c.to_dict()
            c_dict["status_column"] = list_map.get(c.list_id, "")
            # Définir des dates par défaut si non renseignées
            if not c.start_date:
                c_dict["start_date"] = (c.created_at or datetime.utcnow()).strftime("%Y-%m-%d")
            if not c.due_date:
                start_dt = c.start_date or c.created_at or datetime.utcnow()
                dur = float(c.duration_days) if c.duration_days else 1.0
                c_dict["due_date"] = add_working_days(start_dt, dur).strftime("%Y-%m-%d")
            tasks_data.append(c_dict)

        # Récupérer les dépendances entre tâches
        deps_stmt = select(TaskDependencyModel).where(TaskDependencyModel.board_id == str(board_id))
        deps_res = await session.execute(deps_stmt)
        deps = [d.to_dict() for d in deps_res.scalars().all()]

        # Récupérer les dépendances entre sprints
        sprint_deps_stmt = select(SprintDependencyModel).where(SprintDependencyModel.board_id == str(board_id))
        sprint_deps_res = await session.execute(sprint_deps_stmt)
        sprint_deps = [sd.to_dict() for sd in sprint_deps_res.scalars().all()]

        return {
            "project": board.to_dict(),
            "epics": epics,
            "sprints": sprints,
            "tasks": tasks_data,
            "dependencies": deps,
            "sprint_dependencies": sprint_deps,
        }

    @staticmethod
    async def has_path(session: AsyncSession, from_id: str, to_id: str, visited: Optional[Set[str]] = None) -> bool:
        """Détection de chemin orienté pour prévenir les cycles (BFS/DFS)."""
        if visited is None:
            visited = set()
        if from_id == to_id:
            return True
        visited.add(from_id)

        stmt = select(TaskDependencyModel.successor_id).where(TaskDependencyModel.predecessor_id == str(from_id))
        res = await session.execute(stmt)
        succs = res.scalars().all()

        for s_id in succs:
            if s_id not in visited:
                if await GanttService.has_path(session, s_id, to_id, visited):
                    return True
        return False

    @staticmethod
    async def create_dependency(
        session: AsyncSession,
        board_id: str,
        predecessor_id: str,
        successor_id: str,
        dependency_type: str = "FS",
        lag_days: float = 0.0,
        user_id: Optional[str] = None
    ) -> TaskDependencyModel:
        if str(predecessor_id) == str(successor_id):
            raise ValueError("Une tâche ne peut pas dépendre d'elle-même.")

        try:
            dep_type = DependencyType(dependency_type)
        except ValueError:
            dep_type = DependencyType.FS

        # Vérifier l'absence de lien déjà existant
        existing_stmt = select(TaskDependencyModel).where(
            TaskDependencyModel.predecessor_id == str(predecessor_id),
            TaskDependencyModel.successor_id == str(successor_id)
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            existing.dependency_type = dep_type
            existing.lag_days = lag_days
            await session.flush()
            return existing

        # Vérification anti-cycle : s'il existe déjà un chemin successor -> predecessor, ajouter predecessor -> successor créerait un cycle
        if await GanttService.has_path(session, str(successor_id), str(predecessor_id)):
            raise ValueError("Impossible de créer ce lien : il provoquerait une dépendance cyclique infinie.")

        dep = TaskDependencyModel(
            id=str(uuid.uuid4()),
            board_id=str(board_id),
            predecessor_id=str(predecessor_id),
            successor_id=str(successor_id),
            dependency_type=dep_type,
            lag_days=lag_days,
            created_at=datetime.utcnow()
        )
        session.add(dep)
        await session.flush()

        # Aligner automatiquement la tâche successeur si elle commence trop tôt
        await GanttService.reschedule_card(
            session=session,
            card_id=str(successor_id),
            start_date=None,
            auto_cascade=True
        )

        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            user_id=user_id or "system",
            action_type="dependency_created",
            details={
                "predecessor_id": predecessor_id,
                "successor_id": successor_id,
                "type": dep_type.value
            }
        )

        return dep

    @staticmethod
    async def delete_dependency(
        session: AsyncSession,
        dependency_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        dep = await session.get(TaskDependencyModel, str(dependency_id))
        if not dep:
            return False

        board_id = dep.board_id
        await session.delete(dep)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=board_id,
            user_id=user_id or "system",
            action_type="dependency_deleted",
            details={"dependency_id": dependency_id}
        )

        return True

    @staticmethod
    async def reschedule_card(
        session: AsyncSession,
        card_id: str,
        start_date: Optional[datetime] = None,
        due_date: Optional[datetime] = None,
        duration_days: Optional[float] = None,
        auto_cascade: bool = True
    ) -> List[Dict[str, Any]]:
        card = await session.get(CardModel, str(card_id))
        if not card:
            return []

        # Calcul des dates de la tâche
        if start_date is not None:
            card.start_date = start_date

        if duration_days is not None:
            card.duration_days = duration_days

        if due_date is not None:
            card.due_date = due_date
            if card.start_date and due_date >= card.start_date:
                # Recalculer duration
                diff_days = (card.due_date - card.start_date).total_seconds() / 86400.0
                card.duration_days = max(1.0, round(diff_days, 1))
        elif card.start_date and card.duration_days:
            card.due_date = add_working_days(card.start_date, float(card.duration_days))

        card.updated_at = datetime.utcnow()
        await session.flush()

        affected = [{
            "id": card.id,
            "start_date": card.start_date.isoformat() if card.start_date else None,
            "due_date": card.due_date.isoformat() if card.due_date else None,
            "duration_days": float(card.duration_days) if card.duration_days else 1.0,
            "progress_percent": card.progress_percent,
        }]

        # Ajuster l'Epic parent si nécessaire
        if card.epic_id:
            await EpicService.recalculate_epic_progress(session, card.epic_id)

        # Propagation en cascade sur les tâches dépendantes
        if auto_cascade:
            cascade_affected = await GanttService.propagate_dependency_cascade(session, card.id)
            affected.extend(cascade_affected)

        return affected

    @staticmethod
    async def propagate_dependency_cascade(
        session: AsyncSession,
        root_card_id: str,
        visited: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        if visited is None:
            visited = set()
        if root_card_id in visited:
            return []
        visited.add(root_card_id)

        root_card = await session.get(CardModel, str(root_card_id))
        if not root_card or not root_card.due_date:
            return []

        # Trouver tous les liens où root_card est le prédécesseur
        stmt = select(TaskDependencyModel).where(TaskDependencyModel.predecessor_id == str(root_card_id))
        links_res = await session.execute(stmt)
        links = links_res.scalars().all()

        affected = []

        for link in links:
            succ = await session.get(CardModel, link.successor_id)
            if not succ:
                continue

            old_start = succ.start_date
            old_due = succ.due_date
            duration = float(succ.duration_days) if succ.duration_days else 1.0
            lag = float(link.lag_days or 0.0)

            # Règle selon le type de lien
            if link.dependency_type == DependencyType.FS:
                earliest_start = add_working_days(root_card.due_date, lag)
                if not succ.start_date or succ.start_date < earliest_start:
                    succ.start_date = earliest_start
                    succ.due_date = add_working_days(succ.start_date, duration)

            elif link.dependency_type == DependencyType.SS:
                if root_card.start_date:
                    earliest_start = add_working_days(root_card.start_date, lag)
                    if not succ.start_date or succ.start_date < earliest_start:
                        succ.start_date = earliest_start
                        succ.due_date = add_working_days(succ.start_date, duration)

            elif link.dependency_type == DependencyType.FF:
                earliest_end = add_working_days(root_card.due_date, lag)
                if not succ.due_date or succ.due_date < earliest_end:
                    succ.due_date = earliest_end
                    succ.start_date = subtract_working_days(succ.due_date, duration)

            elif link.dependency_type == DependencyType.SF:
                if root_card.start_date:
                    earliest_end = add_working_days(root_card.start_date, lag)
                    if not succ.due_date or succ.due_date < earliest_end:
                        succ.due_date = earliest_end
                        succ.start_date = subtract_working_days(succ.due_date, duration)

            if succ.start_date != old_start or succ.due_date != old_due:
                succ.updated_at = datetime.utcnow()
                affected.append({
                    "id": succ.id,
                    "start_date": succ.start_date.isoformat() if succ.start_date else None,
                    "due_date": succ.due_date.isoformat() if succ.due_date else None,
                    "duration_days": duration,
                    "progress_percent": succ.progress_percent,
                })
                # Cascade récursive
                child_affected = await GanttService.propagate_dependency_cascade(session, succ.id, visited)
                affected.extend(child_affected)

        await session.flush()
        return affected

    @staticmethod
    async def create_sprint_dependency(
        session: AsyncSession,
        board_id: str,
        predecessor_sprint_id: str,
        successor_sprint_id: str,
        dependency_type: str = "FS",
        lag_days: float = 0.0,
        user_id: Optional[str] = None
    ) -> SprintDependencyModel:
        if str(predecessor_sprint_id) == str(successor_sprint_id):
            raise ValueError("Un sprint ne peut pas dépendre de lui-même.")

        try:
            dep_type = DependencyType(dependency_type)
        except ValueError:
            dep_type = DependencyType.FS

        # Vérifier l'absence de lien déjà existant
        existing_stmt = select(SprintDependencyModel).where(
            SprintDependencyModel.predecessor_sprint_id == str(predecessor_sprint_id),
            SprintDependencyModel.successor_sprint_id == str(successor_sprint_id)
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            existing.dependency_type = dep_type
            existing.lag_days = lag_days
            await session.flush()
            return existing

        dep = SprintDependencyModel(
            id=str(uuid.uuid4()),
            board_id=str(board_id),
            predecessor_sprint_id=str(predecessor_sprint_id),
            successor_sprint_id=str(successor_sprint_id),
            dependency_type=dep_type,
            lag_days=lag_days,
            created_at=datetime.utcnow()
        )
        session.add(dep)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            user_id=user_id or "system",
            action_type="sprint_dependency_created",
            details={
                "predecessor_sprint_id": predecessor_sprint_id,
                "successor_sprint_id": successor_sprint_id,
                "type": dep_type.value
            }
        )

        return dep

    @staticmethod
    async def delete_sprint_dependency(
        session: AsyncSession,
        dependency_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        dep = await session.get(SprintDependencyModel, str(dependency_id))
        if not dep:
            return False

        board_id = dep.board_id
        await session.delete(dep)
        await session.flush()

        await ActivityService.log_activity(
            session=session,
            board_id=board_id,
            user_id=user_id or "system",
            action_type="sprint_dependency_deleted",
            details={"dependency_id": dependency_id}
        )

        return True

    @staticmethod
    async def shift_sprint_and_cascade(
        session: AsyncSession,
        sprint_id: str,
        new_start: datetime,
        new_end: datetime
    ) -> List[Dict[str, Any]]:
        sprint = await session.get(SprintModel, str(sprint_id))
        if not sprint:
            return []

        old_end = sprint.end_date
        sprint.start_date = new_start
        sprint.end_date = new_end
        sprint.updated_at = datetime.utcnow()

        affected_sprints = [sprint.to_dict()]

        # Trouver tous les sprints successeurs liés par une dépendance FS
        succ_stmt = select(SprintDependencyModel).where(
            SprintDependencyModel.predecessor_sprint_id == str(sprint_id)
        )
        succ_res = await session.execute(succ_stmt)
        succ_links = succ_res.scalars().all()

        for link in succ_links:
            succ_sp = await session.get(SprintModel, link.successor_sprint_id)
            if succ_sp:
                dur_days = (succ_sp.end_date - succ_sp.start_date).total_seconds() / 86400.0
                earliest_start = add_working_days(new_end, float(link.lag_days or 1.0))
                if succ_sp.start_date < earliest_start:
                    succ_sp.start_date = earliest_start
                    succ_sp.end_date = add_working_days(succ_sp.start_date, dur_days)
                    succ_sp.updated_at = datetime.utcnow()
                    affected_sprints.append(succ_sp.to_dict())

        # Ré-ancrer les cartes du sprint si leurs dates dépassent les bornes du sprint
        cards_stmt = select(CardModel).where(CardModel.sprint_id == sprint.id)
        cards = (await session.execute(cards_stmt)).scalars().all()
        for c in cards:
            if c.due_date and c.due_date > new_end:
                c.due_date = new_end
            if c.start_date and c.start_date < new_start:
                c.start_date = new_start

        await session.flush()
        return affected_sprints

    @staticmethod
    async def recalculate_sprint_and_epic_progress(
        session: AsyncSession,
        card_id: str
    ) -> Dict[str, Any]:
        """
        Propagation ascendante en temps réel :
        Mise à jour du statut d'une carte Kanban -> Recalcul immédiat du Sprint -> Recalcul de l'Epic.
        """
        card = await session.get(CardModel, str(card_id))
        if not card:
            return {}

        result = {}

        # 1. Mise à jour du Sprint
        if card.sprint_id:
            sprint = await session.get(SprintModel, card.sprint_id)
            if sprint:
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
                result["sprint"] = sprint.to_dict()

        # 2. Mise à jour de l'Epic
        if card.epic_id:
            epic = await EpicService.recalculate_epic_progress(session, card.epic_id)
            if epic:
                result["epic"] = epic.to_dict()

        await session.flush()
        return result
