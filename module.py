from core.module import ApplicationModule, Permission
from .controllers.web import ProjectWebController
from .controllers.api import ProjectAPIController
from .services.board_service import BoardService
from .services.card_service import CardService
from .repositories.card_repository import CardRepository
from .models.models import (
    BoardModel,
    ListModel,
    CardModel,
    CardMemberModel,
    BoardMemberModel,
    LabelModel,
    CardLabelModel,
    ChecklistModel,
    ChecklistItemModel,
    CardCommentModel,
    ActivityModel,
    EpicModel,
    SprintModel,
    TaskDependencyModel,
    SprintDependencyModel,
)


class MelodiProjectModule(ApplicationModule):

    def _get_permissions(self):
        return [
            Permission(self, "project:read", "Consulter les projets, tableaux et tâches"),
            Permission(self, "project:write", "Créer et modifier des tableaux et des tâches"),
            Permission(self, "project:move", "Déplacer les cartes (Drag & Drop) et organiser les colonnes"),
            Permission(self, "project:comment", "Ajouter des commentaires aux tâches"),
            Permission(self, "project:delete", "Supprimer ou archiver des projets et des cartes"),
            Permission(self, "project:admin", "Administration complète du module de projets"),
        ]

    async def run_dev_migrations(self):
        """Création automatique et mise à niveau des tables SQL du module de gestion de projets."""
        # 1. Création des nouvelles tables si elles n'existent pas
        await self.app.db.create_all([
            BoardModel,
            BoardMemberModel,
            ListModel,
            EpicModel,
            SprintModel,
            CardModel,
            CardMemberModel,
            LabelModel,
            CardLabelModel,
            ChecklistModel,
            ChecklistItemModel,
            CardCommentModel,
            ActivityModel,
            TaskDependencyModel,
            SprintDependencyModel,
        ])

        # 2. Migration ascendante non-destructive pour les tables existantes
        from core.orm.model import text
        from .config import ProjectTables

        alter_statements = [
            f"ALTER TABLE {ProjectTables.BOARDS} ADD COLUMN IF NOT EXISTS project_type VARCHAR(20) DEFAULT 'hybrid';",
            f"ALTER TABLE {ProjectTables.BOARDS} ADD COLUMN IF NOT EXISTS default_view VARCHAR(20) DEFAULT 'kanban';",
            f"ALTER TABLE {ProjectTables.BOARDS} ADD COLUMN IF NOT EXISTS sprint_duration_weeks INT DEFAULT 2;",
            f"ALTER TABLE {ProjectTables.SPRINTS} ADD COLUMN IF NOT EXISTS progress_percent INT DEFAULT 0;",
            f"ALTER TABLE {ProjectTables.BOARDS} ADD COLUMN IF NOT EXISTS default_view VARCHAR(20) DEFAULT 'kanban';",
            f"ALTER TABLE {ProjectTables.BOARDS} ADD COLUMN IF NOT EXISTS sprint_duration_weeks INT DEFAULT 2;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS sprint_id VARCHAR(64) REFERENCES {ProjectTables.SPRINTS}(id) ON DELETE SET NULL;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS epic_id VARCHAR(64) REFERENCES {ProjectTables.EPICS}(id) ON DELETE SET NULL;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS start_date TIMESTAMP WITHOUT TIME ZONE;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS duration_days NUMERIC(6, 2) DEFAULT 1.0;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS progress_percent INT DEFAULT 0;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS is_milestone BOOLEAN DEFAULT FALSE;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS story_points INT DEFAULT NULL;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS backlog_position NUMERIC(10, 4) DEFAULT 0.0;",
            f"ALTER TABLE {ProjectTables.CARDS} ADD COLUMN IF NOT EXISTS item_type VARCHAR(20) DEFAULT 'task';",
        ]

        async with self.app.db.get_session() as session:
            for stmt in alter_statements:
                try:
                    await session.execute(text(stmt))
                except Exception as ex:
                    # Ignore if column or constraint already exists
                    pass
            await session.commit()

    async def load(self):
        """Initialisation et enregistrement du module MELODI Project."""
        self.permissions = self._get_permissions()

        # Exécution des migrations dev
        try:
            await self.run_dev_migrations()
        except Exception as e:
            print(f"[MELODI Project] Notice lors de la migration des tables: {e}")

        # -------------------------------------------------------------
        # Routes Web d'administration
        # -------------------------------------------------------------
        self.admin_router.add_route("", ProjectWebController.admin_dashboard, methods=["GET", "POST"])
        self.admin_router.add_route("/", ProjectWebController.admin_dashboard, methods=["GET", "POST"])
        self.admin_router.add_route("/board", ProjectWebController.admin_board_kanban, methods=["GET", "POST"])
        self.admin_router.add_route("/board/table", ProjectWebController.admin_board_table, methods=["GET"])
        self.admin_router.add_route("/board/scrum", ProjectWebController.admin_board_scrum, methods=["GET"])
        self.admin_router.add_route("/board/gantt", ProjectWebController.admin_board_gantt, methods=["GET"])

        # -------------------------------------------------------------
        # Routes API REST (Multi-Client & Drag and Drop)
        # -------------------------------------------------------------
        for router in (self.api_admin_router, self.api_router):
            # Boards
            router.add_route("/boards", ProjectAPIController.list_boards, methods=["GET"])
            router.add_route("/boards", ProjectAPIController.create_board, methods=["POST"])
            router.add_route("/boards/detail", ProjectAPIController.get_board_detail, methods=["GET"])
            router.add_route("/boards/detail", ProjectAPIController.update_board, methods=["PUT", "POST"])
            router.add_route("/boards/detail", ProjectAPIController.delete_board, methods=["DELETE"])
            router.add_route("/boards/favorite", ProjectAPIController.toggle_favorite, methods=["POST"])
            router.add_route("/boards/members", ProjectAPIController.list_board_members, methods=["GET"])
            router.add_route("/boards/members", ProjectAPIController.add_board_member, methods=["POST"])
            router.add_route("/boards/members", ProjectAPIController.remove_board_member, methods=["DELETE"])

            # Lists / Columns
            router.add_route("/lists", ProjectAPIController.create_list, methods=["POST"])
            router.add_route("/lists/detail", ProjectAPIController.update_list, methods=["PUT", "POST"])
            router.add_route("/lists/detail", ProjectAPIController.delete_list, methods=["DELETE"])
            router.add_route("/lists/reorder", ProjectAPIController.reorder_lists, methods=["POST"])

            # Cards & Drag & Drop
            router.add_route("/cards", ProjectAPIController.create_card, methods=["POST"])
            router.add_route("/cards/detail", ProjectAPIController.get_card_detail, methods=["GET"])
            router.add_route("/cards/detail", ProjectAPIController.update_card, methods=["PUT", "POST"])
            router.add_route("/cards/detail", ProjectAPIController.delete_card, methods=["DELETE"])
            router.add_route("/cards/move", ProjectAPIController.move_card, methods=["POST"])
            router.add_route("/cards/toggle-completed", ProjectAPIController.toggle_completed, methods=["POST"])

            # Members & Labels
            router.add_route("/cards/assign", ProjectAPIController.assign_member, methods=["POST"])
            router.add_route("/cards/unassign", ProjectAPIController.unassign_member, methods=["POST"])
            router.add_route("/cards/labels", ProjectAPIController.attach_label, methods=["POST"])
            router.add_route("/cards/labels", ProjectAPIController.detach_label, methods=["DELETE"])
            router.add_route("/labels", ProjectAPIController.list_labels, methods=["GET"])
            router.add_route("/labels", ProjectAPIController.create_label, methods=["POST"])

            # Checklists & Items
            router.add_route("/cards/checklists", ProjectAPIController.create_checklist, methods=["POST"])
            router.add_route("/cards/checklists", ProjectAPIController.delete_checklist, methods=["DELETE"])
            router.add_route("/cards/checklist-items", ProjectAPIController.add_checklist_item, methods=["POST"])
            router.add_route("/cards/checklist-items/toggle", ProjectAPIController.toggle_checklist_item, methods=["POST"])
            router.add_route("/cards/checklist-items", ProjectAPIController.delete_checklist_item, methods=["DELETE"])

            # Comments
            router.add_route("/cards/comments", ProjectAPIController.add_comment, methods=["POST"])

            # Gantt Chart & Dependencies
            router.add_route("/gantt/data", ProjectAPIController.get_gantt_data, methods=["GET"])
            router.add_route("/gantt/reschedule", ProjectAPIController.reschedule_card, methods=["POST"])
            router.add_route("/gantt/dependencies", ProjectAPIController.create_dependency, methods=["POST"])
            router.add_route("/gantt/dependencies", ProjectAPIController.delete_dependency, methods=["DELETE"])

            # Scrum - Sprints & Planning
            router.add_route("/scrum/sprints", ProjectAPIController.list_sprints, methods=["GET"])
            router.add_route("/scrum/sprints", ProjectAPIController.create_sprint, methods=["POST"])
            router.add_route("/scrum/sprints/detail", ProjectAPIController.update_sprint, methods=["PUT", "POST"])
            router.add_route("/scrum/sprints/detail", ProjectAPIController.delete_sprint, methods=["DELETE"])
            router.add_route("/scrum/sprints/start", ProjectAPIController.start_sprint, methods=["POST"])
            router.add_route("/scrum/sprints/complete", ProjectAPIController.complete_sprint, methods=["POST"])
            router.add_route("/scrum/cards/sprint", ProjectAPIController.assign_card_sprint, methods=["POST"])
            router.add_route("/scrum/backlog/reorder", ProjectAPIController.reorder_backlog, methods=["POST"])

            # Scrum - Epics
            router.add_route("/scrum/epics", ProjectAPIController.list_epics, methods=["GET"])
            router.add_route("/scrum/epics", ProjectAPIController.create_epic, methods=["POST"])
            router.add_route("/scrum/epics/detail", ProjectAPIController.update_epic, methods=["PUT", "POST"])
            router.add_route("/scrum/epics/detail", ProjectAPIController.delete_epic, methods=["DELETE"])

        # -------------------------------------------------------------
        # Actions inter-modules (Hook System)
        # -------------------------------------------------------------
        self._register_actions()

        # -------------------------------------------------------------
        # Navigation Menu Admin
        # -------------------------------------------------------------
        self.register_navigation(
            id="project_root",
            label="Projets & Kanban",
            icon="name=view_kanban&fill=white",
            url="/admin/melodi_project",
            priority=60,
            children=[
                {"label": "Tableaux Kanban", "icon": "name=dashboard&fill=white", "url": "/admin/melodi_project"},
            ]
        )

    def _register_actions(self):
        """Expose des actions réutilisables par les autres modules MELODI."""
        self.add_action("create_board", self.action_create_board)
        self.add_action("create_card", self.action_create_card)
        self.add_action("move_card", self.action_move_card)
        self.add_action("get_board_summary", self.action_get_board_summary)
        self.add_action("get_user_assigned_cards", self.action_get_user_assigned_cards)

    async def action_create_board(self, payload: dict) -> dict:
        title = payload.get("title")
        description = payload.get("description")
        color = payload.get("color") or "#4F46E5"
        created_by = payload.get("created_by") or "system"

        async with self.app.db.get_session() as session:
            board = await BoardService.create_board(
                session=session,
                title=title,
                description=description,
                color=color,
                created_by=created_by,
                module_instance=self
            )
            await session.commit()
            return board.to_dict()

    async def action_create_card(self, payload: dict) -> dict:
        board_id = payload.get("board_id")
        list_id = payload.get("list_id")
        title = payload.get("title")
        description = payload.get("description")
        created_by = payload.get("created_by") or "system"

        async with self.app.db.get_session() as session:
            # If list_id not provided, pick the first list of the board
            if not list_id and board_id:
                lists = await CardRepository.get_lists_by_board(session, board_id)
                if lists:
                    list_id = lists[0].id

            if not board_id or not list_id or not title:
                return {"error": "board_id, list_id, and title are required"}

            card = await CardService.create_card(
                session=session,
                board_id=board_id,
                list_id=list_id,
                title=title,
                description=description,
                created_by=created_by,
                module_instance=self
            )
            await session.commit()
            return card.to_dict()

    async def action_move_card(self, payload: dict) -> dict:
        card_id = payload.get("card_id")
        target_list_id = payload.get("target_list_id")
        new_position = payload.get("new_position", 1000.0)

        async with self.app.db.get_session() as session:
            card = await CardService.move_card(
                session=session,
                card_id=card_id,
                target_list_id=target_list_id,
                new_position=float(new_position),
                module_instance=self
            )
            await session.commit()
            return card.to_dict() if card else {}

    async def action_get_board_summary(self, payload: dict) -> dict:
        board_id = payload.get("board_id")
        async with self.app.db.get_session() as session:
            return await BoardService.get_board_summary(session, board_id)

    async def action_get_user_assigned_cards(self, payload: dict) -> list:
        user_id = payload.get("user_id")
        async with self.app.db.get_session() as session:
            cards = await CardRepository.get_user_assigned_cards(session, user_id)
            return [c.to_dict() for c in cards]


module = MelodiProjectModule(
    name="melodi_project",
    router_name="melodi_project"
)
