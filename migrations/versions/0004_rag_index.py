"""Durable RAG publication and restart-safe embedding intentions.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_index_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("collection", sa.String(100), nullable=False, unique=True),
        sa.Column("profile_id", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_rag_index_generations_status", "rag_index_generations", ["status"])
    op.create_table(
        "rag_note_index_states",
        sa.Column("generation_id", sa.String(36), primary_key=True),
        sa.Column("knowledge_id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("published_job_id", sa.String(36), nullable=True),
        sa.Column("pending_job_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["rag_index_generations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["knowledge_id"], ["knowledge.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_rag_note_index_states_status", "rag_note_index_states", ["status"])
    op.create_table(
        "rag_index_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("generation_id", sa.String(36), nullable=False),
        sa.Column("knowledge_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("chunks", sa.JSON(), nullable=False),
        sa.Column("vectors", sa.JSON(), nullable=True),
        sa.Column("intents", sa.JSON(), nullable=False),
        sa.Column("cleanup_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["generation_id"], ["rag_index_generations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["knowledge_id"], ["knowledge.id"], ondelete="RESTRICT"),
    )
    for field in ("generation_id", "knowledge_id", "status"):
        op.create_index(f"ix_rag_index_jobs_{field}", "rag_index_jobs", [field])


def downgrade():
    op.drop_table("rag_index_jobs")
    op.drop_table("rag_note_index_states")
    op.drop_table("rag_index_generations")
