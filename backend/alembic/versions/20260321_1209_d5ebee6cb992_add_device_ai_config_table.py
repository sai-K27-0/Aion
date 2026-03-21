"""add device AI config table

Revision ID: d5ebee6cb992
Revises: 6759dc4f4f3c
Create Date: 2026-03-21 12:09:28.812569

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5ebee6cb992'
down_revision: Union[str, None] = '6759dc4f4f3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('device_ai_configs',
    sa.Column('device_id', sa.String(length=36), nullable=False),
    sa.Column('ai_source', sa.String(length=30), nullable=False),
    sa.Column('ollama_url', sa.String(length=500), nullable=True),
    sa.Column('ollama_model', sa.String(length=100), nullable=True),
    sa.Column('ollama_embedding_model', sa.String(length=100), nullable=True),
    sa.Column('api_provider', sa.String(length=30), nullable=True),
    sa.Column('api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('api_model', sa.String(length=100), nullable=True),
    sa.Column('api_base_url', sa.String(length=500), nullable=True),
    sa.Column('fallback_source', sa.String(length=30), nullable=True),
    sa.Column('fallback_api_key_encrypted', sa.Text(), nullable=True),
    sa.Column('fallback_api_model', sa.String(length=100), nullable=True),
    sa.Column('auto_fallback', sa.Boolean(), nullable=False),
    sa.Column('device_ram_gb', sa.Float(), nullable=True),
    sa.Column('device_cpu_cores', sa.Integer(), nullable=True),
    sa.Column('device_gpu_name', sa.String(length=200), nullable=True),
    sa.Column('device_gpu_vram_gb', sa.Float(), nullable=True),
    sa.Column('device_free_disk_gb', sa.Float(), nullable=True),
    sa.Column('device_os', sa.String(length=100), nullable=True),
    sa.Column('ollama_installed', sa.Boolean(), nullable=True),
    sa.Column('ollama_version', sa.String(length=50), nullable=True),
    sa.Column('ollama_models_installed', sa.Text(), nullable=True),
    sa.Column('setup_completed', sa.Boolean(), nullable=False),
    sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_health_status', sa.String(length=20), nullable=True),
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_device_ai_configs_ai_source', 'device_ai_configs', ['ai_source'], unique=False)
    op.create_index(op.f('ix_device_ai_configs_device_id'), 'device_ai_configs', ['device_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_device_ai_configs_device_id'), table_name='device_ai_configs')
    op.drop_index('ix_device_ai_configs_ai_source', table_name='device_ai_configs')
    op.drop_table('device_ai_configs')
