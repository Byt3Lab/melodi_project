from core import get_prefix_table
from core.db.base_module_tables import BaseModuleTables

MODULE_NAME = "melodi_project"
PREFIX_TABLE = get_prefix_table(MODULE_NAME)


class ProjectTables(BaseModuleTables):
    BOARDS = f"{PREFIX_TABLE}boards"
    BOARD_MEMBERS = f"{PREFIX_TABLE}board_members"
    LISTS = f"{PREFIX_TABLE}lists"
    CARDS = f"{PREFIX_TABLE}cards"
    CARD_MEMBERS = f"{PREFIX_TABLE}card_members"
    LABELS = f"{PREFIX_TABLE}labels"
    CARD_LABELS = f"{PREFIX_TABLE}card_labels"
    CHECKLISTS = f"{PREFIX_TABLE}checklists"
    CHECKLIST_ITEMS = f"{PREFIX_TABLE}checklist_items"
    COMMENTS = f"{PREFIX_TABLE}comments"
    ACTIVITIES = f"{PREFIX_TABLE}activities"
    EPICS = f"{PREFIX_TABLE}epics"
    SPRINTS = f"{PREFIX_TABLE}sprints"
    TASK_DEPENDENCIES = f"{PREFIX_TABLE}task_dependencies"
    SPRINT_DEPENDENCIES = f"{PREFIX_TABLE}sprint_dependencies"
