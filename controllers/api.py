import json
from datetime import datetime
from core.routing import Request, Response

from ..services.board_service import BoardService
from ..services.list_service import ListService
from ..services.card_service import CardService
from ..services.checklist_service import ChecklistService
from ..services.sprint_service import SprintService
from ..services.epic_service import EpicService
from ..services.gantt_service import GanttService
from ..repositories.card_repository import CardRepository
from ..models.models import BoardVisibility, CardPriority, SprintStatus, EpicStatus, DependencyType


def _get_current_user_id(request: Request) -> str:
    try:
        user_raw = request.get_session("user_payload")
    except Exception:
        user_raw = None
    user = json.loads(user_raw) if isinstance(user_raw, str) else (user_raw or {})
    return user.get("user_id") or "admin"


class ProjectAPIController:

    # -------------------------------------------------------------
    # BOARDS
    # -------------------------------------------------------------

    @staticmethod
    async def list_boards(request: Request, response: Response):
        search = request.query.get("q")
        fav = request.query.get("favorite")
        is_fav = (fav.lower() in ("true", "1")) if fav is not None else None
        arch = request.query.get("archived")
        is_arch = (arch.lower() in ("true", "1")) if arch is not None else False

        async with request.module.app.db.get_session() as session:
            boards = await BoardService.list_boards(
                session=session,
                search=search,
                is_favorite=is_fav,
                is_archived=is_arch
            )
            data = [b.to_dict() for b in boards]
            return response.render_json({"success": True, "data": data, "count": len(data)})

    @staticmethod
    async def create_board(request: Request, response: Response):
        data = request.json or {}
        title = data.get("title")
        if not title:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "Le titre du tableau est obligatoire."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        color = data.get("color") or "#4F46E5"
        icon = data.get("icon") or "dashboard"
        description = data.get("description")
        vis_str = data.get("visibility", "team")
        visibility = BoardVisibility(vis_str) if vis_str in ("private", "team", "public") else BoardVisibility.TEAM
        is_favorite = bool(data.get("is_favorite", False))
        create_defaults = bool(data.get("create_default_lists", True))

        async with request.module.app.db.get_session() as session:
            try:
                board = await BoardService.create_board(
                    session=session,
                    title=title,
                    description=description,
                    color=color,
                    icon=icon,
                    visibility=visibility,
                    created_by=user_id,
                    is_favorite=is_favorite,
                    create_default_lists=create_defaults,
                    module_instance=request.module
                )
                await session.commit()
                return response.render_json({"success": True, "data": board.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def get_board_detail(request: Request, response: Response):
        board_id_str = request.query.get("id") or request.params.get("id")
        if not board_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "Identifiant du tableau manquant."}
            }, status_code=400)

        board_id = str(board_id_str).strip()

        async with request.module.app.db.get_session() as session:
            board = await BoardService.get_board(session, board_id)
            if not board:
                return response.render_json({
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Tableau introuvable."}
                }, status_code=404)

            # Build full Kanban payload
            board_dict = board.to_dict()
            board_dict["lists"] = []
            for lst in board.lists:
                lst_dict = lst.to_dict()
                lst_dict["cards"] = [c.to_dict() for c in lst.cards if not c.is_archived]
                board_dict["lists"].append(lst_dict)

            board_dict["labels"] = [l.to_dict() for l in board.labels]
            board_dict["activities"] = [a.to_dict() for a in board.activities[:30]]

            return response.render_json({"success": True, "data": board_dict})

    @staticmethod
    async def update_board(request: Request, response: Response):
        board_id_str = request.query.get("id") or request.params.get("id")
        if not board_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "Identifiant du tableau manquant."}
            }, status_code=400)

        data = request.json or {}
        user_id = _get_current_user_id(request)

        async with request.module.app.db.get_session() as session:
            try:
                board = await BoardService.update_board(
                    session=session,
                    board_id=str(board_id_str).strip(),
                    user_id=user_id,
                    **data
                )
                if not board:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Tableau introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": board.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def delete_board(request: Request, response: Response):
        board_id_str = request.query.get("id") or request.params.get("id")
        if not board_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "Identifiant manquant."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            try:
                success = await BoardService.delete_board(session, str(board_id_str).strip())
                if not success:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Tableau introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "message": "Tableau supprimé avec succès."})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def toggle_favorite(request: Request, response: Response):
        board_id_str = request.query.get("id") or (request.json or {}).get("board_id")
        if not board_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "Identifiant manquant."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            board = await BoardService.toggle_favorite(session, str(board_id_str).strip())
            if not board:
                return response.render_json({
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Tableau introuvable."}
                }, status_code=404)
            await session.commit()
            return response.render_json({"success": True, "is_favorite": board.is_favorite})

    # -------------------------------------------------------------
    # PROJECT / BOARD MEMBERS
    # -------------------------------------------------------------

    @staticmethod
    async def list_board_members(request: Request, response: Response):
        board_id = request.query.get("board_id") or request.query.get("id")
        if not board_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "board_id requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            members = await BoardService.list_board_members(session, str(board_id).strip())
            data = [m.to_dict() for m in members]
            return response.render_json({"success": True, "data": data, "count": len(data)})

    @staticmethod
    async def add_board_member(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        user_id = data.get("user_id")
        role = data.get("role", "member")
        if not board_id or not user_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id et user_id requis."}
            }, status_code=400)

        current_user = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                member = await BoardService.add_board_member(
                    session=session,
                    board_id=str(board_id).strip(),
                    user_id=str(user_id).strip(),
                    role=str(role).strip(),
                    added_by=current_user,
                    module_instance=request.module
                )
                if not member:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Tableau introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": member.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def remove_board_member(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id") or request.query.get("board_id")
        user_id = data.get("user_id") or request.query.get("user_id")
        if not board_id or not user_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id et user_id requis."}
            }, status_code=400)

        current_user = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                success = await BoardService.remove_board_member(
                    session=session,
                    board_id=str(board_id).strip(),
                    user_id=str(user_id).strip(),
                    removed_by=current_user,
                    module_instance=request.module
                )
                if not success:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Membre ou tableau introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True})
            except ValueError as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "CANNOT_REMOVE", "message": str(e)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    # -------------------------------------------------------------
    # LISTS / COLUMNS
    # -------------------------------------------------------------

    @staticmethod
    async def create_list(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        title = data.get("title")
        if not board_id or not title:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id et title requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        color = data.get("color")
        wip_limit = int(data.get("wip_limit")) if data.get("wip_limit") else None
        col_type_str = data.get("column_type")
        col_type = None
        if col_type_str:
            try:
                from ..models.models import ColumnType
                col_type = ColumnType(col_type_str.lower())
            except ValueError:
                col_type = ColumnType.IN_PROGRESS

        async with request.module.app.db.get_session() as session:
            try:
                lst = await ListService.create_list(
                    session=session,
                    board_id=str(board_id).strip(),
                    title=title,
                    color=color,
                    wip_limit=wip_limit,
                    column_type=col_type,
                    user_id=user_id
                )
                await session.commit()
                return response.render_json({"success": True, "data": lst.to_dict()})
            except ValueError as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "FORBIDDEN_ACTION", "message": str(e)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def update_list(request: Request, response: Response):
        list_id_str = request.query.get("id") or (request.json or {}).get("list_id")
        if not list_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "list_id manquant."}
            }, status_code=400)

        data = request.json or {}
        user_id = _get_current_user_id(request)

        async with request.module.app.db.get_session() as session:
            try:
                lst = await ListService.update_list(
                    session=session,
                    list_id=str(list_id_str).strip(),
                    user_id=user_id,
                    **data
                )
                if not lst:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Colonne introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": lst.to_dict()})
            except ValueError as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "FORBIDDEN_ACTION", "message": str(e)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def delete_list(request: Request, response: Response):
        list_id_str = request.query.get("id") or (request.json or {}).get("list_id")
        if not list_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "list_id manquant."}
            }, status_code=400)

        user_id = _get_current_user_id(request)

        async with request.module.app.db.get_session() as session:
            try:
                success = await ListService.delete_list(session, str(list_id_str).strip(), user_id=user_id)
                if not success:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Colonne introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "message": "Colonne supprimée."})
            except ValueError as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "MANDATORY_COLUMN", "message": str(e)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def reorder_lists(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        ordered_ids = data.get("ordered_ids") or []
        if not board_id or not ordered_ids:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id et ordered_ids requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            await ListService.reorder_lists(session, str(board_id).strip(), [str(i).strip() for i in ordered_ids])
            await session.commit()
            return response.render_json({"success": True})

    # -------------------------------------------------------------
    # CARDS & DRAG AND DROP
    # -------------------------------------------------------------

    @staticmethod
    async def create_card(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        list_id = data.get("list_id")
        title = data.get("title")

        if not board_id or not list_id or not title:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id, list_id et title requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        desc = data.get("description")
        pri_str = data.get("priority", "medium")
        priority = CardPriority(pri_str) if pri_str in ("low", "medium", "high", "urgent") else CardPriority.MEDIUM
        due_date = datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None
        start_date = datetime.fromisoformat(data["start_date"]) if data.get("start_date") else None
        color_cover = data.get("color_cover")
        sprint_id = data.get("sprint_id")
        epic_id = data.get("epic_id")
        duration_days = float(data.get("duration_days", 1.0)) if data.get("duration_days") is not None else 1.0
        progress_percent = int(data.get("progress_percent", 0)) if data.get("progress_percent") is not None else 0
        is_milestone = bool(data.get("is_milestone", False))
        story_points = int(data.get("story_points")) if data.get("story_points") is not None else None
        item_type = data.get("item_type", "task")

        async with request.module.app.db.get_session() as session:
            try:
                card = await CardService.create_card(
                    session=session,
                    board_id=str(board_id).strip(),
                    list_id=str(list_id).strip(),
                    title=title,
                    description=desc,
                    priority=priority,
                    due_date=due_date,
                    color_cover=color_cover,
                    created_by=user_id,
                    sprint_id=str(sprint_id).strip() if sprint_id else None,
                    epic_id=str(epic_id).strip() if epic_id else None,
                    start_date=start_date,
                    duration_days=duration_days,
                    progress_percent=progress_percent,
                    is_milestone=is_milestone,
                    story_points=story_points,
                    item_type=item_type,
                    module_instance=request.module
                )
                await session.commit()
                return response.render_json({"success": True, "data": card.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def get_card_detail(request: Request, response: Response):
        card_id_str = request.query.get("id") or request.params.get("id")
        if not card_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "Identifiant de la carte manquant."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            card = await CardService.get_card(session, str(card_id_str).strip())
            if not card:
                return response.render_json({
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Carte introuvable."}
                }, status_code=404)

            card_dict = card.to_dict()
            card_dict["comments"] = [c.to_dict() for c in card.comments]
            card_dict["activities"] = [a.to_dict() for a in card.activities[:20]]
            return response.render_json({"success": True, "data": card_dict})

    @staticmethod
    async def update_card(request: Request, response: Response):
        card_id_str = request.query.get("id") or (request.json or {}).get("card_id")
        if not card_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "card_id manquant."}
            }, status_code=400)

        data = dict(request.json or {})
        user_id = _get_current_user_id(request)

        if "due_date" in data:
            data["due_date"] = datetime.fromisoformat(data["due_date"]) if data["due_date"] else None
        if "start_date" in data:
            data["start_date"] = datetime.fromisoformat(data["start_date"]) if data["start_date"] else None
        if "priority" in data and isinstance(data["priority"], str):
            data["priority"] = CardPriority(data["priority"])
        if "duration_days" in data and data["duration_days"] is not None:
            data["duration_days"] = float(data["duration_days"])
        if "progress_percent" in data and data["progress_percent"] is not None:
            data["progress_percent"] = max(0, min(100, int(data["progress_percent"])))
        if "story_points" in data:
            data["story_points"] = int(data["story_points"]) if data["story_points"] is not None else None
        if "sprint_id" in data and not data["sprint_id"]:
            data["sprint_id"] = None
        if "epic_id" in data and not data["epic_id"]:
            data["epic_id"] = None

        async with request.module.app.db.get_session() as session:
            try:
                card = await CardService.update_card(
                    session=session,
                    card_id=str(card_id_str).strip(),
                    user_id=user_id,
                    **data
                )
                if not card:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Carte introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": card.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def move_card(request: Request, response: Response):
        """
        Endpoint central du glisser-déposer (Drag & Drop) Kanban.
        Reçoit card_id, target_list_id et new_position.
        """
        data = request.json or {}
        card_id = data.get("card_id")
        target_list_id = data.get("target_list_id")
        new_pos = data.get("new_position")

        if card_id is None or target_list_id is None or new_pos is None:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "card_id, target_list_id et new_position requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)

        async with request.module.app.db.get_session() as session:
            try:
                card = await CardService.move_card(
                    session=session,
                    card_id=str(card_id).strip(),
                    target_list_id=str(target_list_id).strip(),
                    new_position=float(new_pos),
                    user_id=user_id,
                    module_instance=request.module
                )
                if not card:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Carte introuvable."}
                    }, status_code=404)

                await session.commit()
                return response.render_json({
                    "success": True,
                    "data": {
                        "card_id": card.id,
                        "list_id": card.list_id,
                        "position": float(card.position),
                        "is_completed": card.is_completed,
                        "progress_percent": card.progress_percent
                    }
                })
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def toggle_completed(request: Request, response: Response):
        card_id_str = request.query.get("id") or (request.json or {}).get("card_id")
        if not card_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "card_id manquant."}
            }, status_code=400)

        user_id = _get_current_user_id(request)

        async with request.module.app.db.get_session() as session:
            try:
                card = await CardService.toggle_completed(
                    session=session,
                    card_id=str(card_id_str).strip(),
                    user_id=user_id,
                    module_instance=request.module
                )
                if not card:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Carte introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({
                    "success": True,
                    "is_completed": card.is_completed,
                    "completed_at": card.completed_at.isoformat() if card.completed_at else None
                })
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def delete_card(request: Request, response: Response):
        card_id_str = request.query.get("id") or (request.json or {}).get("card_id")
        if not card_id_str:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "card_id manquant."}
            }, status_code=400)

        user_id = _get_current_user_id(request)

        async with request.module.app.db.get_session() as session:
            try:
                success = await CardService.delete_card(session, str(card_id_str).strip(), user_id=user_id)
                if not success:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Carte introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "message": "Carte supprimée."})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    # -------------------------------------------------------------
    # ASSIGNEES & LABELS
    # -------------------------------------------------------------

    @staticmethod
    async def assign_member(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id")
        user_id = data.get("user_id")
        if not card_id or not user_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "card_id et user_id requis."}
            }, status_code=400)

        current_user = _get_current_user_id(request)
        try:
            async with request.module.app.db.get_session() as session:
                member = await CardService.assign_user(
                    session=session,
                    card_id=str(card_id).strip(),
                    user_id=str(user_id).strip(),
                    assigned_by=current_user,
                    module_instance=request.module
                )
                if not member:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Tâche introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": member.to_dict()})
        except ValueError as e:
            return response.render_json({
                "success": False,
                "error": {"code": "NOT_PROJECT_MEMBER", "message": str(e)}
            }, status_code=400)

    @staticmethod
    async def unassign_member(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id")
        user_id = data.get("user_id")
        if not card_id or not user_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "card_id et user_id requis."}
            }, status_code=400)

        current_user = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            success = await CardService.unassign_user(session, str(card_id).strip(), str(user_id).strip(), unassigned_by=current_user)
            await session.commit()
            return response.render_json({"success": success})

    @staticmethod
    async def attach_label(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id")
        label_id = data.get("label_id")
        if not card_id or not label_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "card_id et label_id requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            cl = await CardService.attach_label(session, str(card_id).strip(), str(label_id).strip())
            await session.commit()
            return response.render_json({"success": True, "data": cl.to_dict()})

    @staticmethod
    async def detach_label(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id") or request.query.get("card_id")
        label_id = data.get("label_id") or request.query.get("label_id")
        if not card_id or not label_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "card_id et label_id requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            success = await CardService.detach_label(session, str(card_id).strip(), str(label_id).strip())
            await session.commit()
            return response.render_json({"success": success})

    @staticmethod
    async def list_labels(request: Request, response: Response):
        board_id = request.query.get("board_id")
        if not board_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "board_id requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            labels = await CardRepository.get_labels_by_board(session, str(board_id).strip())
            return response.render_json({"success": True, "data": [l.to_dict() for l in labels]})

    @staticmethod
    async def create_label(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        name = data.get("name")
        color = data.get("color") or "#3B82F6"
        if not board_id or not name:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id et name requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            label = await CardRepository.create_label(session, str(board_id).strip(), name, color)
            await session.commit()
            return response.render_json({"success": True, "data": label.to_dict()})

    # -------------------------------------------------------------
    # CHECKLISTS & ITEMS
    # -------------------------------------------------------------

    @staticmethod
    async def create_checklist(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id")
        title = data.get("title") or "Checklist"
        if not card_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "card_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            cl = await ChecklistService.create_checklist(session, str(card_id).strip(), title, user_id=user_id)
            await session.commit()
            return response.render_json({"success": True, "data": cl.to_dict()})

    @staticmethod
    async def delete_checklist(request: Request, response: Response):
        cl_id = request.query.get("id") or (request.json or {}).get("checklist_id")
        if not cl_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "checklist_id manquant."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            success = await ChecklistService.delete_checklist(session, str(cl_id).strip(), user_id=user_id)
            await session.commit()
            return response.render_json({"success": success})

    @staticmethod
    async def add_checklist_item(request: Request, response: Response):
        data = request.json or {}
        checklist_id = data.get("checklist_id")
        title = data.get("title")
        if not checklist_id or not title:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "checklist_id et title requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            item = await ChecklistService.add_item(session, str(checklist_id).strip(), title, user_id=user_id)
            await session.commit()
            return response.render_json({"success": True, "data": item.to_dict()})

    @staticmethod
    async def toggle_checklist_item(request: Request, response: Response):
        data = request.json or {}
        item_id = data.get("item_id") or request.query.get("id")
        if not item_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "item_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            item = await ChecklistService.toggle_item(session, str(item_id).strip(), user_id=user_id)
            if not item:
                return response.render_json({
                    "success": False,
                    "error": {"code": "NOT_FOUND", "message": "Élément introuvable."}
                }, status_code=404)
            await session.commit()
            return response.render_json({"success": True, "data": item.to_dict()})

    @staticmethod
    async def delete_checklist_item(request: Request, response: Response):
        item_id = request.query.get("id") or (request.json or {}).get("item_id")
        if not item_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "item_id manquant."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            success = await ChecklistService.delete_item(session, str(item_id).strip(), user_id=user_id)
            await session.commit()
            return response.render_json({"success": success})

    # -------------------------------------------------------------
    # COMMENTS
    # -------------------------------------------------------------

    @staticmethod
    async def add_comment(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id")
        content = data.get("content")
        if not card_id or not content:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "card_id et content requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            comment = await CardService.add_comment(session, str(card_id).strip(), user_id, content)
            await session.commit()
            return response.render_json({"success": True, "data": comment.to_dict()})

    # -------------------------------------------------------------
    # GANTT CHART
    # -------------------------------------------------------------

    @staticmethod
    async def get_gantt_data(request: Request, response: Response):
        board_id = request.query.get("board_id") or request.query.get("id")
        if not board_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "board_id requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            try:
                data = await GanttService.get_gantt_dataset(session, str(board_id).strip())
                return response.render_json({"success": True, "data": data})
            except Exception as e:
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def reschedule_card(request: Request, response: Response):
        data = request.json or {}
        item_type = data.get("item_type", "task")
        start_date_raw = data.get("start_date") or data.get("new_start_date")
        due_date_raw = data.get("due_date") or data.get("new_end_date") or data.get("end_date")

        start_date = datetime.fromisoformat(str(start_date_raw).replace("Z", "")) if start_date_raw else None
        due_date = datetime.fromisoformat(str(due_date_raw).replace("Z", "")) if due_date_raw else None

        if item_type == "sprint" or "sprint_id" in data:
            sprint_id = data.get("sprint_id") or data.get("item_id")
            if not sprint_id or not start_date or not due_date:
                return response.render_json({
                    "success": False,
                    "error": {"code": "MISSING_PARAM", "message": "sprint_id, start_date et due_date requis."}
                }, status_code=400)

            async with request.module.app.db.get_session() as session:
                try:
                    affected = await GanttService.shift_sprint_and_cascade(
                        session=session,
                        sprint_id=str(sprint_id).strip(),
                        new_start_date=start_date,
                        new_end_date=due_date
                    )
                    await session.commit()
                    return response.render_json({"success": True, "data": affected})
                except ValueError as ve:
                    await session.rollback()
                    return response.render_json({
                        "success": False,
                        "error": {"code": "OVERLAP_ERROR", "message": str(ve)}
                    }, status_code=400)
                except Exception as e:
                    await session.rollback()
                    return response.render_json({
                        "success": False,
                        "error": {"code": "SERVER_ERROR", "message": str(e)}
                    }, status_code=500)

        card_id = data.get("card_id") or data.get("item_id")
        if not card_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "card_id requis."}
            }, status_code=400)

        duration_days = float(data.get("duration_days")) if data.get("duration_days") is not None else None
        auto_cascade = bool(data.get("auto_cascade", True))

        async with request.module.app.db.get_session() as session:
            try:
                affected = await GanttService.reschedule_card(
                    session=session,
                    card_id=str(card_id).strip(),
                    start_date=start_date,
                    due_date=due_date,
                    duration_days=duration_days,
                    auto_cascade=auto_cascade
                )
                await session.commit()
                return response.render_json({"success": True, "data": affected})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def create_dependency(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        predecessor_id = data.get("predecessor_id")
        successor_id = data.get("successor_id")
        dep_type = data.get("dependency_type", "FS")
        lag_days = float(data.get("lag_days", 0.0))

        if not board_id or not predecessor_id or not successor_id:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id, predecessor_id et successor_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                dep = await GanttService.create_dependency(
                    session=session,
                    board_id=str(board_id).strip(),
                    predecessor_id=str(predecessor_id).strip(),
                    successor_id=str(successor_id).strip(),
                    dependency_type=dep_type,
                    lag_days=lag_days,
                    user_id=user_id
                )
                await session.commit()
                return response.render_json({"success": True, "data": dep.to_dict()})
            except ValueError as ve:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "VALIDATION_FAILED", "message": str(ve)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def delete_dependency(request: Request, response: Response):
        dep_id = request.query.get("id") or (request.json or {}).get("dependency_id")
        if not dep_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "id de la dépendance requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                success = await GanttService.delete_dependency(session, str(dep_id).strip(), user_id=user_id)
                await session.commit()
                return response.render_json({"success": success})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    # -------------------------------------------------------------
    # SCRUM - SPRINTS & PLANNING
    # -------------------------------------------------------------

    @staticmethod
    async def list_sprints(request: Request, response: Response):
        board_id = request.query.get("board_id")
        if not board_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "board_id requis."}
            }, status_code=400)

        status = request.query.get("status")
        async with request.module.app.db.get_session() as session:
            sprints = await SprintService.list_sprints(session, str(board_id).strip(), status)
            return response.render_json({"success": True, "data": [s.to_dict() for s in sprints]})

    @staticmethod
    async def create_sprint(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        name = data.get("name")
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")

        if not board_id or not name or not start_date_str or not end_date_str:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id, name, start_date et end_date requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
        goal = data.get("goal")

        async with request.module.app.db.get_session() as session:
            try:
                sprint = await SprintService.create_sprint(
                    session=session,
                    board_id=str(board_id).strip(),
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    goal=goal,
                    user_id=user_id
                )
                await session.commit()
                return response.render_json({"success": True, "data": sprint.to_dict()})
            except ValueError as ve:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "VALIDATION_FAILED", "message": str(ve)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def update_sprint(request: Request, response: Response):
        sprint_id = request.query.get("id") or (request.json or {}).get("sprint_id")
        if not sprint_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "sprint_id requis."}
            }, status_code=400)

        data = dict(request.json or {})
        if "start_date" in data and data["start_date"]:
            data["start_date"] = datetime.fromisoformat(data["start_date"])
        if "end_date" in data and data["end_date"]:
            data["end_date"] = datetime.fromisoformat(data["end_date"])

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                sprint = await SprintService.update_sprint(session, str(sprint_id).strip(), user_id=user_id, **data)
                if not sprint:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Sprint introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": sprint.to_dict()})
            except ValueError as ve:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "VALIDATION_FAILED", "message": str(ve)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def delete_sprint(request: Request, response: Response):
        sprint_id = request.query.get("id") or (request.json or {}).get("sprint_id")
        if not sprint_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "sprint_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                success = await SprintService.delete_sprint(session, str(sprint_id).strip(), user_id=user_id)
                await session.commit()
                return response.render_json({"success": success})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def start_sprint(request: Request, response: Response):
        data = request.json or {}
        sprint_id = data.get("sprint_id") or request.query.get("id")
        if not sprint_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "sprint_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                sprint = await SprintService.start_sprint(session, str(sprint_id).strip(), user_id=user_id)
                await session.commit()
                return response.render_json({"success": True, "data": sprint.to_dict()})
            except ValueError as ve:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "VALIDATION_FAILED", "message": str(ve)}
                }, status_code=400)
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def complete_sprint(request: Request, response: Response):
        data = request.json or {}
        sprint_id = data.get("sprint_id") or request.query.get("id")
        move_incomplete_to = data.get("move_incomplete_to", "backlog")
        if not sprint_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "sprint_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                sprint = await SprintService.complete_sprint(
                    session=session,
                    sprint_id=str(sprint_id).strip(),
                    user_id=user_id,
                    move_incomplete_to=move_incomplete_to
                )
                await session.commit()
                return response.render_json({"success": True, "data": sprint.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def assign_card_sprint(request: Request, response: Response):
        data = request.json or {}
        card_id = data.get("card_id")
        sprint_id = data.get("sprint_id")  # None means move to backlog

        if not card_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "card_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                card = await CardService.assign_sprint(
                    session=session,
                    card_id=str(card_id).strip(),
                    sprint_id=str(sprint_id).strip() if sprint_id else None,
                    user_id=user_id
                )
                if not card:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Carte introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": card.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def reorder_backlog(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        ordered_ids = data.get("ordered_ids") or []
        if not board_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "board_id requis."}
            }, status_code=400)

        async with request.module.app.db.get_session() as session:
            try:
                await CardService.reorder_backlog(session, str(board_id).strip(), [str(i) for i in ordered_ids])
                await session.commit()
                return response.render_json({"success": True})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    # -------------------------------------------------------------
    # SCRUM - EPICS
    # -------------------------------------------------------------

    @staticmethod
    async def list_epics(request: Request, response: Response):
        board_id = request.query.get("board_id")
        if not board_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "board_id requis."}
            }, status_code=400)

        status = request.query.get("status")
        async with request.module.app.db.get_session() as session:
            epics = await EpicService.list_epics(session, str(board_id).strip(), status)
            return response.render_json({"success": True, "data": [e.to_dict() for e in epics]})

    @staticmethod
    async def create_epic(request: Request, response: Response):
        data = request.json or {}
        board_id = data.get("board_id")
        title = data.get("title")

        if not board_id or not title:
            return response.render_json({
                "success": False,
                "error": {"code": "VALIDATION_FAILED", "message": "board_id et title requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        desc = data.get("description")
        color = data.get("color") or "#8B5CF6"
        start_date = datetime.fromisoformat(data["start_date"]) if data.get("start_date") else None
        end_date = datetime.fromisoformat(data["end_date"]) if data.get("end_date") else None

        async with request.module.app.db.get_session() as session:
            try:
                epic = await EpicService.create_epic(
                    session=session,
                    board_id=str(board_id).strip(),
                    title=title,
                    description=desc,
                    color=color,
                    start_date=start_date,
                    end_date=end_date,
                    user_id=user_id
                )
                await session.commit()
                return response.render_json({"success": True, "data": epic.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def update_epic(request: Request, response: Response):
        epic_id = request.query.get("id") or (request.json or {}).get("epic_id")
        if not epic_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "epic_id requis."}
            }, status_code=400)

        data = dict(request.json or {})
        if "start_date" in data and data["start_date"]:
            data["start_date"] = datetime.fromisoformat(data["start_date"])
        if "end_date" in data and data["end_date"]:
            data["end_date"] = datetime.fromisoformat(data["end_date"])

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                epic = await EpicService.update_epic(session, str(epic_id).strip(), user_id=user_id, **data)
                if not epic:
                    return response.render_json({
                        "success": False,
                        "error": {"code": "NOT_FOUND", "message": "Epic introuvable."}
                    }, status_code=404)
                await session.commit()
                return response.render_json({"success": True, "data": epic.to_dict()})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

    @staticmethod
    async def delete_epic(request: Request, response: Response):
        epic_id = request.query.get("id") or (request.json or {}).get("epic_id")
        if not epic_id:
            return response.render_json({
                "success": False,
                "error": {"code": "MISSING_PARAM", "message": "epic_id requis."}
            }, status_code=400)

        user_id = _get_current_user_id(request)
        async with request.module.app.db.get_session() as session:
            try:
                success = await EpicService.delete_epic(session, str(epic_id).strip(), user_id=user_id)
                await session.commit()
                return response.render_json({"success": success})
            except Exception as e:
                await session.rollback()
                return response.render_json({
                    "success": False,
                    "error": {"code": "SERVER_ERROR", "message": str(e)}
                }, status_code=500)

