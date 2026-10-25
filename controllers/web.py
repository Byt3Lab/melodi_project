import json
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.routing import Request, Response
from core.page_builder import Page, Component
from base.components import admin_layout

from ..services.board_service import BoardService
from ..services.list_service import ListService
from ..services.card_service import CardService
from ..repositories.board_repository import BoardRepository
from ..repositories.card_repository import CardRepository
from ..models.models import BoardVisibility, CardPriority


def _get_current_user(request: Request) -> dict:
    user_raw = request.get_session("user_payload")
    user = json.loads(user_raw) if isinstance(user_raw, str) else (user_raw or {})
    return user or {"user_id": "admin", "username": "admin"}


async def _fetch_system_users(session) -> list:
    users = []
    try:
        from base.models.user_model import UserModel
        stmt = select(UserModel).options(selectinload(UserModel.contact)).order_by(UserModel.username)
        res = await session.execute(stmt)
        for u in res.scalars().all():
            display_name = u.contact.name if (getattr(u, "contact", None) and u.contact.name) else u.username
            email = u.contact.email if (getattr(u, "contact", None) and u.contact.email) else ""
            users.append({
                "user_id": u.user_id,
                "username": u.username,
                "name": display_name,
                "email": email
            })
    except Exception as e:
        print(f"[melodi_project] Notice fetching system users: {e}")
        users = [{"user_id": "admin", "username": "admin", "name": "Administrateur", "email": ""}]
    return users


class ProjectWebController:

    @staticmethod
    async def admin_dashboard(request: Request, response: Response):
        current_user = _get_current_user(request)
        search = request.query.get("q")
        filter_type = request.query.get("filter") or "all"
        is_fav = True if filter_type == "favorites" else None
        is_arch = True if filter_type == "archived" else False

        if request.method == "POST":
            form = request.form
            action_type = form.get("action_type")
            async with request.module.app.db.get_session() as session:
                try:
                    if action_type == "create_board":
                        title = form.get("title")
                        desc = form.get("description")
                        color = form.get("color") or "#4F46E5"
                        icon = form.get("icon") or "dashboard"
                        vis_str = form.get("visibility", "team")
                        vis = BoardVisibility(vis_str) if vis_str in ("private", "team", "public") else BoardVisibility.TEAM
                        is_favorite = form.get("is_favorite") == "on"
                        project_type = form.get("project_type") or "hybrid"
                        default_view = form.get("default_view") or "kanban"

                        if title:
                            await BoardService.create_board(
                                session=session,
                                title=title,
                                description=desc,
                                color=color,
                                icon=icon,
                                visibility=vis,
                                created_by=current_user.get("user_id"),
                                is_favorite=is_favorite,
                                create_default_lists=True,
                                project_type=project_type,
                                default_view=default_view,
                                module_instance=request.module
                            )
                            await session.commit()
                    elif action_type == "toggle_favorite":
                        board_id = str(form.get("board_id"))
                        await BoardService.toggle_favorite(session, board_id)
                        await session.commit()
                    elif action_type == "archive_board":
                        board_id = str(form.get("board_id"))
                        await BoardService.archive_board(session, board_id, user_id=current_user.get("user_id"))
                        await session.commit()
                    elif action_type == "unarchive_board":
                        board_id = str(form.get("board_id"))
                        await BoardService.unarchive_board(session, board_id, user_id=current_user.get("user_id"))
                        await session.commit()
                    elif action_type == "delete_board":
                        board_id = str(form.get("board_id"))
                        await BoardService.delete_board(session, board_id)
                        await session.commit()
                except Exception as e:
                    await session.rollback()
                    print(f"[melodi_project] Erreur formulaire dashboard: {e}")

        async with request.module.app.db.get_session() as session:
            boards = await BoardService.list_boards(
                session=session,
                search=search,
                is_favorite=is_fav,
                is_archived=is_arch
            )
            stats = await BoardRepository.get_global_stats(session)

            # Enrich boards with summaries
            board_cards = []
            for b in boards:
                summary = await BoardService.get_board_summary(session, b.id)
                board_cards.append({
                    "board": b,
                    "summary": summary
                })

        content = Component(module_name="melodi_project", name="admin_boards", context={
            "boards": board_cards,
            "stats": stats,
            "filter_type": filter_type,
            "search_query": search or "",
            "current_user": current_user,
        })
        content.require_css("/static/melodi_project/css/kanban.css", priority=20)
        content.require_css("/static/melodi_project/css/project.css", priority=30)
        page = Page("Gestion de Projets & Tableaux", admin_layout(content))
        return await response.render_page(page)

    @staticmethod
    async def admin_board_kanban(request: Request, response: Response):
        board_id = request.query.get("id")
        if not board_id:
            return response.redirect("/admin/melodi_project")

        sprint_id = request.query.get("sprint_id")
        current_user = _get_current_user(request)

        async with request.module.app.db.get_session() as session:
            board = await BoardService.get_board(session, board_id)
            if not board:
                return response.redirect("/admin/melodi_project")

            from ..services.sprint_service import SprintService
            sprints = await SprintService.list_sprints(session, board_id)
            selected_sprint = next((s for s in sprints if s.id == sprint_id), None) if sprint_id else None

            users = await _fetch_system_users(session)
            users_map = {u["user_id"]: u for u in users}
            labels = await CardRepository.get_labels_by_board(session, board_id)

            # Attach user info to project members
            project_members = []
            for m in (board.members or []):
                m.user_info = users_map.get(m.user_id, {"name": m.user_id, "username": m.user_id})
                project_members.append(m)

            # Attach user info to card assignees & filter by sprint if requested
            for lst in board.lists:
                if sprint_id:
                    lst.cards = [c for c in lst.cards if str(c.sprint_id) == str(sprint_id)]
                for card in lst.cards:
                    for a in card.assignees:
                        a.user_info = users_map.get(a.user_id, {"name": a.user_id, "username": a.user_id})

        content = Component(module_name="melodi_project", name="admin_board_kanban", context={
            "board": board,
            "project_members": project_members,
            "users": users,
            "users_map": users_map,
            "labels": labels,
            "sprints": sprints,
            "selected_sprint_id": sprint_id,
            "selected_sprint": selected_sprint,
            "current_user": current_user,
        })
        content.require_css("/static/melodi_project/css/kanban.css", priority=20)
        content.require_css("/static/melodi_project/css/project.css", priority=30)
        page = Page(f"{board.title} - Tableau Kanban", admin_layout(content))
        return await response.render_page(page)

    @staticmethod
    async def admin_board_table(request: Request, response: Response):
        board_id = request.query.get("id")
        if not board_id:
            return response.redirect("/admin/melodi_project")

        current_user = _get_current_user(request)

        async with request.module.app.db.get_session() as session:
            board = await BoardService.get_board(session, board_id)
            if not board:
                return response.redirect("/admin/melodi_project")

            users = await _fetch_system_users(session)
            users_map = {u["user_id"]: u for u in users}

            project_members = []
            for m in (board.members or []):
                m.user_info = users_map.get(m.user_id, {"name": m.user_id, "username": m.user_id})
                project_members.append(m)

            cards = await CardRepository.get_cards_by_board(session, board_id)

            for c in cards:
                for a in c.assignees:
                    a.user_info = users_map.get(a.user_id, {"name": a.user_id, "username": a.user_id})

        content = Component(module_name="melodi_project", name="admin_board_table", context={
            "board": board,
            "project_members": project_members,
            "cards": cards,
            "users": users,
            "users_map": users_map,
            "current_user": current_user,
        })
        content.require_css("/static/melodi_project/css/kanban.css", priority=20)
        content.require_css("/static/melodi_project/css/project.css", priority=30)
        page = Page(f"{board.title} - Vue Liste & Synthèse", admin_layout(content))
        return await response.render_page(page)

    @staticmethod
    async def admin_board_scrum(request: Request, response: Response):
        board_id = request.query.get("id")
        if not board_id:
            return response.redirect("/admin/melodi_project")

        current_user = _get_current_user(request)

        async with request.module.app.db.get_session() as session:
            board = await BoardService.get_board(session, board_id)
            if not board:
                return response.redirect("/admin/melodi_project")

            from ..services.sprint_service import SprintService
            from ..services.epic_service import EpicService
            from ..models.models import CardModel

            users = await _fetch_system_users(session)
            users_map = {u["user_id"]: u for u in users}

            project_members = []
            for m in (board.members or []):
                m.user_info = users_map.get(m.user_id, {"name": m.user_id, "username": m.user_id})
                project_members.append(m)

            sprints = await SprintService.list_sprints(session, board_id)
            active_sprint = await SprintService.get_active_sprint(session, board_id)
            epics = await EpicService.list_epics(session, board_id)

            # Cartes du backlog (sprint_id IS NULL)
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            backlog_stmt = (
                select(CardModel)
                .where(
                    CardModel.board_id == str(board_id),
                    CardModel.sprint_id.is_(None),
                    CardModel.is_archived == False
                )
                .options(
                    selectinload(CardModel.assignees),
                    selectinload(CardModel.epic),
                    selectinload(CardModel.card_labels),
                )
                .order_by(CardModel.backlog_position.asc(), CardModel.position.asc())
            )
            res_bl = await session.execute(backlog_stmt)
            backlog_cards = list(res_bl.scalars().all())

            # Calculer la vélocité et les story points totaux du backlog
            backlog_sp = sum(c.story_points or 0 for c in backlog_cards)

        content = Component(module_name="melodi_project", name="admin_board_scrum", context={
            "board": board,
            "project_members": project_members,
            "sprints": sprints,
            "active_sprint": active_sprint,
            "epics": epics,
            "backlog_cards": backlog_cards,
            "backlog_sp": backlog_sp,
            "users": users,
            "users_map": users_map,
            "current_user": current_user,
        })
        content.require_css("/static/melodi_project/css/kanban.css", priority=20)
        content.require_css("/static/melodi_project/css/project.css", priority=30)
        page = Page(f"{board.title} - Scrum & Sprints", admin_layout(content))
        return await response.render_page(page)

    @staticmethod
    async def admin_board_gantt(request: Request, response: Response):
        board_id = request.query.get("id")
        if not board_id:
            return response.redirect("/admin/melodi_project")

        current_user = _get_current_user(request)

        async with request.module.app.db.get_session() as session:
            board = await BoardService.get_board(session, board_id)
            if not board:
                return response.redirect("/admin/melodi_project")

            from ..services.gantt_service import GanttService
            gantt_data = await GanttService.get_gantt_dataset(session, board_id)
            users = await _fetch_system_users(session)
            users_map = {u["user_id"]: u for u in users}

            project_members = []
            for m in (board.members or []):
                m.user_info = users_map.get(m.user_id, {"name": m.user_id, "username": m.user_id})
                project_members.append(m)

        content = Component(module_name="melodi_project", name="admin_board_gantt", context={
            "board": board,
            "project_members": project_members,
            "gantt_data": gantt_data,
            "users": users,
            "users_map": users_map,
            "current_user": current_user,
        })
        content.require_css("/static/melodi_project/css/kanban.css", priority=20)
        content.require_css("/static/melodi_project/css/gantt.css", priority=25)
        content.require_css("/static/melodi_project/css/project.css", priority=30)
        page = Page(f"{board.title} - Diagramme de Gantt", admin_layout(content))
        return await response.render_page(page)

