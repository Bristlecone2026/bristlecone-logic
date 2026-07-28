import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Table, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class DendroRole(str, enum.Enum):
    SEEDLING = "seedling"       # Intake
    SAPLING = "sapling"         # Decomposition
    CAMBIUM = "cambium"         # Execution
    RESIN = "resin"             # Security/Treasury
    HEARTWOOD = "heartwood"     # Commit/Sync


class GateType(str, enum.Enum):
    PRE_EXECUTION = "pre_execution"
    POST_EXECUTION = "post_execution"


class ValidationStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    FLAGGED = "flagged"


# Association table for DAG lineages (Many-to-Many for merging agent states)
commit_edges = Table(
    "commit_edges",
    Base.metadata,
    Column("parent_id", UUID(as_uuid=True), ForeignKey("commit_nodes.id", ondelete="CASCADE"), primary_key=True),
    Column("child_id", UUID(as_uuid=True), ForeignKey("commit_nodes.id", ondelete="CASCADE"), primary_key=True),
)


class CommitNode(Base):
    __tablename__ = "commit_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Taxonomic Role
    agent_role = Column(Enum(DendroRole, name="dendro_role_enum"), nullable=False)

    # Deterministic Execution Proofs
    state_hash = Column(String, nullable=False, index=True)  # Merkle root or SHA256 of payload
    payload = Column(JSONB, nullable=True)                  # Prompt/tool diffs

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # DAG Relationship (Self-referential)
    parents = relationship(
        "CommitNode",
        secondary=commit_edges,
        primaryjoin=id == commit_edges.c.child_id,
        secondaryjoin=id == commit_edges.c.parent_id,
        backref="children",
    )

    # Invigilator Link
    validations = relationship("InvigilatorLog", back_populates="commit_node", cascade="all, delete-orphan")


class InvigilatorLog(Base):
    __tablename__ = "invigilator_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commit_node_id = Column(UUID(as_uuid=True), ForeignKey("commit_nodes.id", ondelete="CASCADE"), nullable=False)

    gate_type = Column(Enum(GateType, name="gate_type_enum"), nullable=False)
    status = Column(Enum(ValidationStatus, name="validation_status_enum"), nullable=False)

    # Audit trail details
    metrics = Column(JSONB, nullable=True)          # Token usage, latency, policy scores
    failure_reason = Column(String, nullable=True)  # Populated if status is FAIL or FLAGGED

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    commit_node = relationship("CommitNode", back_populates="validations")
