"""Preserve per-request model pricing without rewriting historical accounting."""
from alembic import op
import sqlalchemy as sa

revision='0008'
down_revision='0007'
branch_labels=depends_on=None


def upgrade():
    op.add_column('organization_calls',sa.Column('price_snapshot',sa.JSON,nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM organization_calls WHERE price_snapshot IS NOT NULL')):
        raise RuntimeError('Restore a verified backup; request pricing must not be discarded.')
    op.drop_column('organization_calls','price_snapshot')
