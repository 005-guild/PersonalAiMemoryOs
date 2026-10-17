"""Versioned prompts, persistent batches, and ordered Knowledge sources.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("knowledge_sources",
        sa.Column("knowledge_id", sa.String(36), sa.ForeignKey("knowledge.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("knowledge_id", "position", name="uq_knowledge_source_position"),
        sa.CheckConstraint("position >= 0 AND position < 20", name="ck_knowledge_source_position"))
    op.execute(sa.text("INSERT INTO knowledge_sources (knowledge_id,source_id,position) SELECT id,source_id,0 FROM knowledge WHERE source_id IS NOT NULL"))
    for column in (sa.Column("source_snapshots", sa.JSON(), nullable=True),
                   sa.Column("prompt_snapshot", sa.JSON(), nullable=True),
                   sa.Column("generation_settings", sa.JSON(), nullable=True),
                   sa.Column("finish_reason", sa.String(100), nullable=True),
                   sa.Column("failure_stage", sa.String(100), nullable=True)):
        op.add_column("processing_runs", column)
    op.create_table("prompt_templates",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("output_schema_version", sa.Integer(), nullable=False), sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.String(40), nullable=True), sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("output_schema_version IN (1, 2)", name="ck_prompt_schema"))
    op.create_index("uq_prompt_default", "prompt_templates", ["is_default"], unique=True,
                    sqlite_where=sa.text("is_default = 1"))
    op.create_table("prompt_revisions",
        sa.Column("template_id", sa.String(36), sa.ForeignKey("prompt_templates.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("output_schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False))
    op.create_table("processing_batches",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(100), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("profile_id", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False), sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("prompt_snapshot", sa.JSON(), nullable=False), sa.Column("generation_settings", sa.JSON(), nullable=False),
        sa.Column("source_snapshots", sa.JSON(), nullable=False), sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True), sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False), sa.Column("finished_at", sa.String(40), nullable=True),
        sa.CheckConstraint("mode IN ('individual', 'merged')", name="ck_batch_mode"),
        sa.CheckConstraint("status IN ('pending','running','paused','completed','cancelling','cancelled')", name="ck_batch_status"))
    op.create_index("ix_processing_batches_status", "processing_batches", ["status"])
    op.create_table("processing_batch_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("processing_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("processing_runs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("run_ids", sa.JSON(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.UniqueConstraint("batch_id", "position", name="uq_batch_position"),
        sa.CheckConstraint("position >= 0", name="ck_batch_position"),
        sa.CheckConstraint("status IN ('pending','running','ready','failed','interrupted','cancelled')", name="ck_batch_item_status"))
    op.create_index("ix_processing_batch_items_batch_id", "processing_batch_items", ["batch_id"])


def downgrade():
    op.drop_table("processing_batch_items")
    op.drop_table("processing_batches")
    op.drop_table("prompt_revisions")
    op.drop_table("prompt_templates")
    for column in ("failure_stage", "finish_reason", "generation_settings", "prompt_snapshot", "source_snapshots"):
        op.drop_column("processing_runs", column)
    op.drop_table("knowledge_sources")
