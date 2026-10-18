from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import ListModel, ColumnType
from ..repositories.card_repository import CardRepository
from .activity_service import ActivityService


class ListService:

    @staticmethod
    async def normalize_board_column_positions(session: AsyncSession, board_id: str) -> None:
        """
        Régularise l'ordre et les positions de toutes les colonnes du tableau:
        1. Colonne de départ (ENTRY) toujours en 1ère position (1000.0)
        2. Colonnes étapes intermédiaires (IN_PROGRESS) ordonnées entre Début et Fin (2000.0, 3000.0...)
        3. Colonne de fin (DONE) immédiatement après la dernière étape intermédiaire
        4. Colonne d'abandon (CANCELLED) en toute fin de tableau
        """
        res = await session.execute(
            select(ListModel)
            .where(ListModel.board_id == str(board_id), ListModel.is_archived == False)
            .order_by(ListModel.position.asc())
        )
        all_lists = res.scalars().all()
        entry_lists = [l for l in all_lists if l.column_type == ColumnType.ENTRY]
        in_prog_lists = [l for l in all_lists if l.column_type == ColumnType.IN_PROGRESS]
        done_lists = [l for l in all_lists if l.column_type == ColumnType.DONE]
        cancelled_lists = [l for l in all_lists if l.column_type == ColumnType.CANCELLED]

        ordered = entry_lists + in_prog_lists + done_lists + cancelled_lists
        for idx, l in enumerate(ordered):
            l.position = (idx + 1) * 1000.0

    @staticmethod
    async def create_list(
        session: AsyncSession,
        board_id: str,
        title: str,
        color: Optional[str] = None,
        wip_limit: Optional[int] = None,
        position: Optional[float] = None,
        column_type: Optional[ColumnType] = None,
        user_id: str = "system"
    ) -> ListModel:
        # Default to IN_PROGRESS for newly added columns
        if column_type is None:
            t_lower = (title or "").lower()
            if any(k in t_lower for k in ("annul", "cancel")):
                column_type = ColumnType.CANCELLED
            elif any(k in t_lower for k in ("termin", "done", "fini", "closed")):
                column_type = ColumnType.DONE
            elif any(k in t_lower for k in ("début", "debut", "start", "à faire", "a faire", "todo")):
                column_type = ColumnType.ENTRY
            else:
                column_type = ColumnType.IN_PROGRESS

        # Règle stricte : interdiction des doublons pour Début, Fini et Annulé
        if column_type in (ColumnType.ENTRY, ColumnType.DONE, ColumnType.CANCELLED):
            existing = await session.execute(
                select(ListModel).where(
                    ListModel.board_id == str(board_id),
                    ListModel.column_type == column_type,
                    ListModel.is_archived == False
                )
            )
            if existing.scalars().first():
                type_labels = {
                    ColumnType.ENTRY: "Début",
                    ColumnType.DONE: "Fini",
                    ColumnType.CANCELLED: "Annulé"
                }
                lbl = type_labels.get(column_type, column_type.value)
                raise ValueError(
                    f"Une colonne de type '{lbl}' existe déjà sur ce projet. "
                    f"Les colonnes Début, Fini et Annulé sont uniques et ne peuvent pas être ajoutées en double."
                )

        lst = await CardRepository.create_list(
            session=session,
            board_id=str(board_id),
            title=title,
            color=color,
            wip_limit=wip_limit,
            position=position or 2500.0,
            column_type=column_type
        )

        # Normaliser pour placer automatiquement toute colonne progress entre Début et Fini
        await ListService.normalize_board_column_positions(session, str(board_id))

        await ActivityService.log_activity(
            session=session,
            board_id=str(board_id),
            user_id=user_id,
            action_type="list_created",
            details={"list_id": lst.id, "title": lst.title, "column_type": lst.column_type.value}
        )
        return lst

    @staticmethod
    async def update_list(
        session: AsyncSession,
        list_id: str,
        user_id: str = "system",
        **kwargs
    ) -> Optional[ListModel]:
        lst = await CardRepository.get_list_by_id(session, str(list_id))
        if not lst:
            return None

        if "column_type" in kwargs:
            new_type = kwargs["column_type"]
            if isinstance(new_type, str):
                new_type = ColumnType(new_type.lower())
            if lst.column_type in (ColumnType.ENTRY, ColumnType.DONE, ColumnType.CANCELLED) and new_type != lst.column_type:
                raise ValueError(f"Impossible de modifier le type de la colonne obligatoire '{lst.title}'.")
            if new_type in (ColumnType.ENTRY, ColumnType.DONE, ColumnType.CANCELLED) and new_type != lst.column_type:
                existing = await session.execute(
                    select(ListModel).where(
                        ListModel.board_id == lst.board_id,
                        ListModel.column_type == new_type,
                        ListModel.id != lst.id,
                        ListModel.is_archived == False
                    )
                )
                if existing.scalars().first():
                    raise ValueError(f"Une colonne de type '{new_type.value}' existe déjà sur ce projet.")

        updated = await CardRepository.update_list(session, str(list_id), **kwargs)
        if updated:
            if "column_type" in kwargs or "position" in kwargs:
                await ListService.normalize_board_column_positions(session, updated.board_id)

            await ActivityService.log_activity(
                session=session,
                board_id=updated.board_id,
                user_id=user_id,
                action_type="list_updated",
                details={"list_id": updated.id, **kwargs}
            )
        return updated

    @staticmethod
    async def delete_list(session: AsyncSession, list_id: str, user_id: str = "system") -> bool:
        lst = await CardRepository.get_list_by_id(session, str(list_id))
        if not lst:
            return False

        # Règle stricte : les colonnes obligatoires (Début, Fini, Annulé) ne peuvent JAMAIS être supprimées
        if lst.column_type in (ColumnType.ENTRY, ColumnType.DONE, ColumnType.CANCELLED):
            type_labels = {
                ColumnType.ENTRY: "Début",
                ColumnType.DONE: "Fini",
                ColumnType.CANCELLED: "Annulé"
            }
            lbl = type_labels.get(lst.column_type, lst.column_type.value)
            raise ValueError(
                f"Impossible de supprimer la colonne '{lst.title}'. "
                f"La colonne '{lbl}' est obligatoire pour le fonctionnement du projet et ne peut pas être supprimée."
            )

        board_id = lst.board_id
        list_title = lst.title
        success = await CardRepository.delete_list(session, str(list_id))
        if success:
            await ListService.normalize_board_column_positions(session, board_id)
            await ActivityService.log_activity(
                session=session,
                board_id=board_id,
                user_id=user_id,
                action_type="list_deleted",
                details={"list_id": str(list_id), "title": list_title}
            )
        return success

    @staticmethod
    async def reorder_lists(session: AsyncSession, board_id: str, ordered_list_ids: List[str]) -> bool:
        base_pos = 1000.0
        step = 1000.0
        for idx, lid in enumerate(ordered_list_ids):
            await CardRepository.update_list(session, str(lid), position=base_pos + (idx * step))
        await ListService.normalize_board_column_positions(session, board_id)
        return True
