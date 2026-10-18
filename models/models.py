import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    DateTime as SADateTime,
    Text as SAText,
    Numeric as SANumeric,
    Index,
    UniqueConstraint,
)

from core.orm.model import (
    BaseModel,
    Mapped,
    mapped_column,
    relationship,
    Integer,
    String,
    Boolean,
    Numeric,
    Enum,
    ForeignKey,
)

from ..config import ProjectTables


def generate_uuid() -> str:
    return str(uuid.uuid4())


class BoardVisibility(str, enum.Enum):
    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


class CardPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class SprintStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EpicStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class DependencyType(str, enum.Enum):
    FS = "FS"  # Finish to Start (default)
    SS = "SS"  # Start to Start
    FF = "FF"  # Finish to Finish
    SF = "SF"  # Start to Finish


class ColumnType(str, enum.Enum):
    ENTRY = "entry"            # Colonne de départ / entrée (obligatoire)
    IN_PROGRESS = "in_progress" # Colonnes intermédiaires (autant qu'on veut)
    DONE = "done"              # Colonne de fin / complétion (obligatoire)
    CANCELLED = "cancelled"    # Colonne d'abandon / annulation (obligatoire)


class CardItemType(str, enum.Enum):
    TASK = "task"
    STORY = "story"
    BUG = "bug"
    MILESTONE = "milestone"


class BoardModel(BaseModel):
    __tablename__ = ProjectTables.BOARDS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(SAText, nullable=True)
    color: Mapped[str] = mapped_column(String(50), default="#4F46E5", nullable=False)
    icon: Mapped[str] = mapped_column(String(50), default="dashboard", nullable=False)
    visibility: Mapped[BoardVisibility] = mapped_column(
        Enum(BoardVisibility, native_enum=False),
        default=BoardVisibility.TEAM,
        nullable=False,
        index=True
    )
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    project_type: Mapped[str] = mapped_column(String(20), default="hybrid", nullable=False)  # kanban, scrum, hybrid
    default_view: Mapped[str] = mapped_column(String(20), default="kanban", nullable=False)  # kanban, scrum, gantt, table
    sprint_duration_weeks: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    lists: Mapped[List["ListModel"]] = relationship(
        "ListModel",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="ListModel.position",
        lazy="selectin"
    )
    labels: Mapped[List["LabelModel"]] = relationship(
        "LabelModel",
        back_populates="board",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    activities: Mapped[List["ActivityModel"]] = relationship(
        "ActivityModel",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="ActivityModel.created_at.desc()",
        lazy="selectin"
    )
    epics: Mapped[List["EpicModel"]] = relationship(
        "EpicModel",
        back_populates="board",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    sprints: Mapped[List["SprintModel"]] = relationship(
        "SprintModel",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="SprintModel.start_date",
        lazy="selectin"
    )
    members: Mapped[List["BoardMemberModel"]] = relationship(
        "BoardMemberModel",
        back_populates="board",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description or "",
            "color": self.color,
            "icon": self.icon,
            "visibility": self.visibility.value if hasattr(self.visibility, "value") else str(self.visibility),
            "is_favorite": self.is_favorite,
            "is_archived": self.is_archived,
            "project_type": self.project_type,
            "default_view": self.default_view,
            "sprint_duration_weeks": self.sprint_duration_weeks,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "lists_count": len(self.lists) if hasattr(self, "__dict__") and "lists" in self.__dict__ and self.lists else 0,
            "sprints_count": len(self.sprints) if hasattr(self, "__dict__") and "sprints" in self.__dict__ and self.sprints else 0,
            "epics_count": len(self.epics) if hasattr(self, "__dict__") and "epics" in self.__dict__ and self.epics else 0,
            "members": [m.to_dict() for m in self.members] if (hasattr(self, "__dict__") and "members" in self.__dict__ and self.members) else [],
            "members_count": len(self.members) if (hasattr(self, "__dict__") and "members" in self.__dict__ and self.members) else 0,
        }


class BoardMemberModel(BaseModel):
    __tablename__ = ProjectTables.BOARD_MEMBERS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)  # owner, manager, member, viewer
    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel", back_populates="members")

    __table_args__ = (
        UniqueConstraint("board_id", "user_id", name="uq_melodi_project_board_member"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "user_id": self.user_id,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ListModel(BaseModel):
    __tablename__ = ProjectTables.LISTS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[float] = mapped_column(SANumeric(10, 4), default=0.0, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    wip_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    column_type: Mapped[ColumnType] = mapped_column(
        Enum(ColumnType, values_callable=lambda obj: [e.value for e in obj], native_enum=False),
        default=ColumnType.IN_PROGRESS,
        nullable=False,
        index=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel", back_populates="lists")
    cards: Mapped[List["CardModel"]] = relationship(
        "CardModel",
        back_populates="list",
        cascade="all, delete-orphan",
        order_by="CardModel.position",
        lazy="selectin"
    )

    def to_dict(self) -> dict:
        col_type_val = self.column_type.value if hasattr(self.column_type, "value") else str(self.column_type)
        return {
            "id": self.id,
            "board_id": self.board_id,
            "title": self.title,
            "position": float(self.position) if self.position is not None else 0.0,
            "color": self.color,
            "wip_limit": self.wip_limit,
            "column_type": col_type_val,
            "is_archived": self.is_archived,
            "cards_count": len(self.cards) if hasattr(self, "__dict__") and "cards" in self.__dict__ and self.cards else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EpicModel(BaseModel):
    __tablename__ = ProjectTables.EPICS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(SAText, nullable=True)
    color: Mapped[str] = mapped_column(String(30), default="#8B5CF6", nullable=False)
    start_date: Mapped[Optional[datetime]] = mapped_column(SADateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(SADateTime, nullable=True)
    status: Mapped[EpicStatus] = mapped_column(
        Enum(EpicStatus, native_enum=False),
        default=EpicStatus.PLANNED,
        nullable=False,
        index=True
    )
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel", back_populates="epics")
    cards: Mapped[List["CardModel"]] = relationship("CardModel", back_populates="epic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "title": self.title,
            "description": self.description or "",
            "color": self.color,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "progress_percent": self.progress_percent,
            "cards_count": len(self.cards) if hasattr(self, "__dict__") and "cards" in self.__dict__ and self.cards else 0,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SprintModel(BaseModel):
    __tablename__ = ProjectTables.SPRINTS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(SAText, nullable=True)
    start_date: Mapped[datetime] = mapped_column(SADateTime, nullable=False, index=True)
    end_date: Mapped[datetime] = mapped_column(SADateTime, nullable=False, index=True)
    status: Mapped[SprintStatus] = mapped_column(
        Enum(SprintStatus, native_enum=False),
        default=SprintStatus.PLANNED,
        nullable=False,
        index=True
    )
    velocity_achieved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_story_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel", back_populates="sprints")
    cards: Mapped[List["CardModel"]] = relationship("CardModel", back_populates="sprint")

    def to_dict(self) -> dict:
        total_sp = 0
        done_sp = 0
        card_items = self.cards if hasattr(self, "__dict__") and "cards" in self.__dict__ and self.cards else []
        for c in card_items:
            sp = c.story_points or 0
            total_sp += sp
            if c.is_completed:
                done_sp += sp

        calculated_pct = int((done_sp / total_sp * 100)) if total_sp > 0 else (100 if self.status == SprintStatus.COMPLETED else 0)
        return {
            "id": self.id,
            "board_id": self.board_id,
            "name": self.name,
            "goal": self.goal or "",
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "progress_percent": self.progress_percent if (self.progress_percent and self.progress_percent > 0) else calculated_pct,
            "velocity_achieved": self.velocity_achieved or done_sp,
            "total_story_points": self.total_story_points or total_sp,
            "completed_story_points": done_sp,
            "cards_count": len(card_items),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CardModel(BaseModel):
    __tablename__ = ProjectTables.CARDS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    list_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.LISTS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sprint_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.SPRINTS}.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    epic_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.EPICS}.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(SAText, nullable=True)
    position: Mapped[float] = mapped_column(SANumeric(10, 4), default=0.0, nullable=False)
    backlog_position: Mapped[float] = mapped_column(SANumeric(10, 4), default=0.0, nullable=False)
    priority: Mapped[CardPriority] = mapped_column(
        Enum(CardPriority, native_enum=False),
        default=CardPriority.MEDIUM,
        nullable=False,
        index=True
    )
    item_type: Mapped[CardItemType] = mapped_column(
        Enum(CardItemType, values_callable=lambda obj: [e.value for e in obj], native_enum=False),
        default=CardItemType.TASK,
        nullable=False,
        index=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(SADateTime, nullable=True, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(SADateTime, nullable=True, index=True)
    duration_days: Mapped[float] = mapped_column(SANumeric(6, 2), default=1.0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    color_cover: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    estimated_hours: Mapped[Optional[float]] = mapped_column(SANumeric(8, 2), nullable=True)
    spent_hours: Mapped[Optional[float]] = mapped_column(SANumeric(8, 2), nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(SADateTime, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel")
    list: Mapped["ListModel"] = relationship("ListModel", back_populates="cards")
    sprint: Mapped[Optional["SprintModel"]] = relationship("SprintModel", back_populates="cards")
    epic: Mapped[Optional["EpicModel"]] = relationship("EpicModel", back_populates="cards")
    assignees: Mapped[List["CardMemberModel"]] = relationship(
        "CardMemberModel",
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    card_labels: Mapped[List["CardLabelModel"]] = relationship(
        "CardLabelModel",
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    checklists: Mapped[List["ChecklistModel"]] = relationship(
        "ChecklistModel",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="ChecklistModel.position",
        lazy="selectin"
    )
    comments: Mapped[List["CardCommentModel"]] = relationship(
        "CardCommentModel",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="CardCommentModel.created_at.desc()",
        lazy="selectin"
    )
    activities: Mapped[List["ActivityModel"]] = relationship(
        "ActivityModel",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="ActivityModel.created_at.desc()",
        lazy="selectin"
    )
    predecessor_links: Mapped[List["TaskDependencyModel"]] = relationship(
        "TaskDependencyModel",
        primaryjoin="TaskDependencyModel.successor_id == CardModel.id",
        foreign_keys="[TaskDependencyModel.successor_id]",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    successor_links: Mapped[List["TaskDependencyModel"]] = relationship(
        "TaskDependencyModel",
        primaryjoin="TaskDependencyModel.predecessor_id == CardModel.id",
        foreign_keys="[TaskDependencyModel.predecessor_id]",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    __table_args__ = (
        Index("idx_card_board_list", "board_id", "list_id"),
        Index("idx_card_due_date", "due_date"),
        Index("idx_card_sprint", "sprint_id"),
        Index("idx_card_epic", "epic_id"),
    )

    @property
    def checklist_summary(self) -> dict:
        total = 0
        done = 0
        if hasattr(self, "__dict__") and "checklists" in self.__dict__ and self.checklists:
            for cl in self.checklists:
                if hasattr(cl, "__dict__") and "items" in cl.__dict__ and cl.items:
                    total += len(cl.items)
                    done += sum(1 for item in cl.items if item.is_done)
        percent = int((done / total * 100)) if total > 0 else 0
        return {"total": total, "done": done, "percent": percent}

    def to_dict(self) -> dict:
        cl_stats = self.checklist_summary
        return {
            "id": self.id,
            "board_id": self.board_id,
            "list_id": self.list_id,
            "sprint_id": self.sprint_id,
            "epic_id": self.epic_id,
            "title": self.title,
            "description": self.description or "",
            "position": float(self.position) if self.position is not None else 0.0,
            "backlog_position": float(self.backlog_position) if self.backlog_position is not None else 0.0,
            "priority": self.priority.value if hasattr(self.priority, "value") else str(self.priority),
            "item_type": self.item_type.value if hasattr(self.item_type, "value") else str(self.item_type),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "duration_days": float(self.duration_days) if self.duration_days is not None else 1.0,
            "progress_percent": self.progress_percent if self.progress_percent is not None else 0,
            "is_milestone": self.is_milestone,
            "story_points": self.story_points,
            "color_cover": self.color_cover,
            "estimated_hours": float(self.estimated_hours) if self.estimated_hours is not None else None,
            "spent_hours": float(self.spent_hours) if self.spent_hours is not None else None,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_archived": self.is_archived,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "assignees": [a.to_dict() for a in self.assignees] if hasattr(self, "__dict__") and "assignees" in self.__dict__ and self.assignees else [],
            "labels": [cl.label.to_dict() for cl in self.card_labels if cl.label] if hasattr(self, "__dict__") and "card_labels" in self.__dict__ and self.card_labels else [],
            "checklists": [c.to_dict() for c in self.checklists] if hasattr(self, "__dict__") and "checklists" in self.__dict__ and self.checklists else [],
            "comments_count": len(self.comments) if hasattr(self, "__dict__") and "comments" in self.__dict__ and self.comments else 0,
            "checklist_stats": cl_stats,
            "epic": self.epic.to_dict() if hasattr(self, "__dict__") and "epic" in self.__dict__ and self.epic else None,
            "sprint": self.sprint.to_dict() if hasattr(self, "__dict__") and "sprint" in self.__dict__ and self.sprint else None,
        }


class TaskDependencyModel(BaseModel):
    __tablename__ = ProjectTables.TASK_DEPENDENCIES

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    predecessor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    successor_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, native_enum=False),
        default=DependencyType.FS,
        nullable=False
    )
    lag_days: Mapped[float] = mapped_column(SANumeric(6, 2), default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)

    predecessor: Mapped["CardModel"] = relationship("CardModel", foreign_keys=[predecessor_id], back_populates="successor_links")
    successor: Mapped["CardModel"] = relationship("CardModel", foreign_keys=[successor_id], back_populates="predecessor_links")

    __table_args__ = (
        Index("idx_dep_pred_succ", "predecessor_id", "successor_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "predecessor_id": self.predecessor_id,
            "successor_id": self.successor_id,
            "dependency_type": self.dependency_type.value if hasattr(self.dependency_type, "value") else str(self.dependency_type),
            "lag_days": float(self.lag_days) if self.lag_days is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SprintDependencyModel(BaseModel):
    __tablename__ = ProjectTables.SPRINT_DEPENDENCIES

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    predecessor_sprint_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.SPRINTS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    successor_sprint_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.SPRINTS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, native_enum=False),
        default=DependencyType.FS,
        nullable=False
    )
    lag_days: Mapped[float] = mapped_column(SANumeric(6, 2), default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)

    predecessor_sprint: Mapped["SprintModel"] = relationship("SprintModel", foreign_keys=[predecessor_sprint_id])
    successor_sprint: Mapped["SprintModel"] = relationship("SprintModel", foreign_keys=[successor_sprint_id])

    __table_args__ = (
        Index("idx_sprint_dep_pred_succ", "predecessor_sprint_id", "successor_sprint_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "predecessor_sprint_id": self.predecessor_sprint_id,
            "successor_sprint_id": self.successor_sprint_id,
            "dependency_type": self.dependency_type.value if hasattr(self.dependency_type, "value") else str(self.dependency_type),
            "lag_days": float(self.lag_days) if self.lag_days is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CardMemberModel(BaseModel):
    __tablename__ = ProjectTables.CARD_MEMBERS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    card_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)

    card: Mapped["CardModel"] = relationship("CardModel", back_populates="assignees")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "card_id": self.card_id,
            "user_id": self.user_id,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LabelModel(BaseModel):
    __tablename__ = ProjectTables.LABELS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(30), default="#3B82F6", nullable=False)
    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel", back_populates="labels")
    card_labels: Mapped[List["CardLabelModel"]] = relationship(
        "CardLabelModel",
        back_populates="label",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "name": self.name,
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CardLabelModel(BaseModel):
    __tablename__ = ProjectTables.CARD_LABELS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    card_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    label_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.LABELS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    card: Mapped["CardModel"] = relationship("CardModel", back_populates="card_labels")
    label: Mapped["LabelModel"] = relationship("LabelModel", back_populates="card_labels", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "card_id": self.card_id,
            "label_id": self.label_id,
            "label": self.label.to_dict() if self.label else None,
        }


class ChecklistModel(BaseModel):
    __tablename__ = ProjectTables.CHECKLISTS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    card_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(150), default="Checklist", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    card: Mapped["CardModel"] = relationship("CardModel", back_populates="checklists")
    items: Mapped[List["ChecklistItemModel"]] = relationship(
        "ChecklistItemModel",
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="ChecklistItemModel.position",
        lazy="selectin"
    )

    def to_dict(self) -> dict:
        total = len(self.items) if self.items else 0
        done = sum(1 for it in self.items if it.is_done) if self.items else 0
        return {
            "id": self.id,
            "card_id": self.card_id,
            "title": self.title,
            "position": self.position,
            "total_items": total,
            "done_items": done,
            "percent": int((done / total * 100)) if total > 0 else 0,
            "items": [it.to_dict() for it in self.items] if self.items else [],
        }


class ChecklistItemModel(BaseModel):
    __tablename__ = ProjectTables.CHECKLIST_ITEMS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    checklist_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CHECKLISTS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(SADateTime, nullable=True)

    checklist: Mapped["ChecklistModel"] = relationship("ChecklistModel", back_populates="items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "checklist_id": self.checklist_id,
            "title": self.title,
            "is_done": self.is_done,
            "position": self.position,
            "due_date": self.due_date.isoformat() if self.due_date else None,
        }


class CardCommentModel(BaseModel):
    __tablename__ = ProjectTables.COMMENTS

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    card_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content: Mapped[str] = mapped_column(SAText, nullable=False)

    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    card: Mapped["CardModel"] = relationship("CardModel", back_populates="comments")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "card_id": self.card_id,
            "user_id": self.user_id,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ActivityModel(BaseModel):
    __tablename__ = ProjectTables.ACTIVITIES

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_uuid)
    board_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.BOARDS}.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    card_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey(f"{ProjectTables.CARDS}.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(SAText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(SADateTime, default=datetime.utcnow, nullable=False)

    board: Mapped["BoardModel"] = relationship("BoardModel", back_populates="activities")
    card: Mapped[Optional["CardModel"]] = relationship("CardModel", back_populates="activities")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "board_id": self.board_id,
            "card_id": self.card_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
