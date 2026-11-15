"""Separate topic results and member revisions from authoritative knowledge notes."""
from alembic import op
import sqlalchemy as sa

revision='0009'
down_revision='0008'
branch_labels=depends_on=None


def upgrade():
    op.create_table('topic_summaries',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('topic',sa.String(200),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('members',sa.JSON,nullable=False),
        sa.Column('result',sa.JSON,nullable=True),
        sa.Column('job_id',sa.String(36),sa.ForeignKey('organization_jobs.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('created_at',sa.String(40),nullable=False))
    op.create_index('ix_topic_summaries_topic','topic_summaries',['topic'])


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM topic_summaries')):
        raise RuntimeError('Restore a verified backup to retain topic generation history.')
    op.drop_table('topic_summaries')
