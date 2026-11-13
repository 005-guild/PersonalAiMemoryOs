"""Explicit collection organization and locally accounted generation budgets."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = depends_on = None


def upgrade():
    op.create_table('organization_control', sa.Column('id', sa.Integer, primary_key=True), sa.Column('value', sa.JSON, nullable=False))
    op.create_table('organization_items',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('identity', sa.String(160), nullable=False, unique=True),
        sa.Column('snapshot', sa.JSON, nullable=False), sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('source_id', sa.String(36), sa.ForeignKey('sources.id', ondelete='RESTRICT')),
        sa.Column('knowledge_id', sa.String(36), sa.ForeignKey('knowledge.id', ondelete='RESTRICT'), unique=True),
        sa.Column('status', sa.String(30), nullable=False), sa.Column('result', sa.JSON), sa.Column('error', sa.String(100)),
        sa.Column('export_path', sa.Text), sa.Column('export_hash', sa.String(64)),
        sa.Column('exported_version', sa.Integer, nullable=False), sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_organization_items_status', 'organization_items', ['status'])
    op.create_table('organization_jobs', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('mode', sa.String(20), nullable=False), sa.Column('status', sa.String(30), nullable=False),
        sa.Column('selection', sa.JSON, nullable=False), sa.Column('settings', sa.JSON, nullable=False),
        sa.Column('error', sa.String(100)), sa.Column('created_at', sa.String(40), nullable=False), sa.Column('finished_at', sa.String(40)))
    op.create_index('ix_organization_jobs_status', 'organization_jobs', ['status'])
    op.create_table('organization_calls', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False), sa.Column('attempt', sa.Integer, nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('organization_jobs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('item_id', sa.String(36), sa.ForeignKey('organization_items.id', ondelete='RESTRICT')),
        sa.Column('stage', sa.String(50), nullable=False), sa.Column('period', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('reserved_micros', sa.Integer, nullable=False),
        sa.Column('accounted_micros', sa.Integer, nullable=False), sa.Column('response', sa.Text),
        sa.Column('usage', sa.JSON), sa.Column('error', sa.String(100)), sa.Column('created_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('fingerprint', 'attempt', name='uq_organization_call_attempt'))
    op.create_index('ix_organization_calls_fingerprint', 'organization_calls', ['fingerprint'])
    op.create_index('ix_organization_calls_period', 'organization_calls', ['period'])
    op.execute("CREATE VIRTUAL TABLE organization_fts USING fts5(item_id UNINDEXED, title, summary, original, tags, tokenize='trigram')")


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM organization_items')) or op.get_bind().scalar(sa.text('SELECT count(*) FROM organization_calls')):
        raise RuntimeError('Restore a verified backup; organization history must not be discarded.')
    op.execute('DROP TABLE organization_fts')
    for name in ('organization_calls', 'organization_jobs', 'organization_items', 'organization_control'):
        op.drop_table(name)
