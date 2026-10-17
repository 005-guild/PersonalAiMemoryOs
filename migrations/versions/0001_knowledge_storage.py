"""Sources, knowledge, and recoverable Markdown synchronization.

Revision ID: 0001
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("deleted_at", sa.String(40), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "sources",
        *record_columns(),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index("ix_sources_deleted_at", "sources", ["deleted_at"])
    op.create_table(
        "knowledge",
        *record_columns(),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(200), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("concepts", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_knowledge_deleted_at", "knowledge", ["deleted_at"])
    op.create_index("ix_knowledge_source_id", "knowledge", ["source_id"])
    op.create_table(
        "sync_vault",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(36), nullable=False),
        sa.Column("initialized", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_sync_vault_singleton"),
    )
    op.create_table(
        "sync_states",
        sa.Column("knowledge_id", sa.String(36), primary_key=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("base", sa.JSON(), nullable=True),
        sa.Column("base_hash", sa.String(64), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("missing_since", sa.Float(), nullable=True),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["knowledge_id"], ["knowledge.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sync_states_status", "sync_states", ["status"])
    op.create_table(
        "sync_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("knowledge_id", sa.String(36), nullable=False),
        sa.Column("base", sa.JSON(), nullable=True),
        sa.Column("db_snapshot", sa.JSON(), nullable=False),
        sa.Column("file_snapshot", sa.JSON(), nullable=True),
        sa.Column("file_content", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("db_version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("resolved_at", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["knowledge_id"], ["knowledge.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sync_conflicts_knowledge_id", "sync_conflicts", ["knowledge_id"])
    op.create_index("ix_sync_conflicts_status", "sync_conflicts", ["status"])
    op.create_table(
        "sync_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("knowledge_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("expected_hash", sa.String(64), nullable=True),
        sa.Column("target_hash", sa.String(64), nullable=True),
        sa.Column("target_content", sa.Text(), nullable=True),
        sa.Column("previous_content", sa.Text(), nullable=True),
        sa.Column("target_snapshot", sa.JSON(), nullable=True),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40), nullable=True),
        sa.ForeignKeyConstraint(["knowledge_id"], ["knowledge.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sync_operations_knowledge_id", "sync_operations", ["knowledge_id"])
    op.create_index("ix_sync_operations_status", "sync_operations", ["status"])


def downgrade() -> None:
    for table in ("sync_operations", "sync_conflicts", "sync_states", "sync_vault", "knowledge", "sources"):
        op.drop_table(table)
