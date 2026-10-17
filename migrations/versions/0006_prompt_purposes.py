"""Separate analysis and cited-question prompt purposes without altering old revisions.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("prompt_templates", sa.Column("purpose", sa.String(20), nullable=False, server_default="knowledge"))
    op.add_column("prompt_revisions", sa.Column("purpose", sa.String(20), nullable=False, server_default="knowledge"))
    op.drop_index("uq_prompt_default", table_name="prompt_templates")
    op.create_index("uq_prompt_default", "prompt_templates", ["purpose"], unique=True,
                    sqlite_where=sa.text("is_default = 1"))
    # Triggers avoid SQLite table rebuilding (and retain all incoming FK rows).
    for table in ("prompt_templates", "prompt_revisions"):
        for action in ("INSERT", "UPDATE"):
            op.execute(sa.text(f"CREATE TRIGGER ck_{table}_purpose_{action.lower()} BEFORE {action} ON {table} "
                "WHEN NEW.purpose NOT IN ('knowledge','rag_qa') BEGIN SELECT RAISE(ABORT, 'invalid prompt purpose'); END"))


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM prompt_templates WHERE purpose != 'knowledge'")):
        raise RuntimeError("Restore a verified 0005 backup to downgrade after creating RAG templates; no template is deleted automatically.")
    for table in ("prompt_templates", "prompt_revisions"):
        for action in ("insert", "update"):
            op.execute(sa.text(f"DROP TRIGGER ck_{table}_purpose_{action}"))
    op.drop_index("uq_prompt_default", table_name="prompt_templates")
    op.create_index("uq_prompt_default", "prompt_templates", ["is_default"], unique=True,
                    sqlite_where=sa.text("is_default = 1"))
    op.drop_column("prompt_revisions", "purpose")
    op.drop_column("prompt_templates", "purpose")
