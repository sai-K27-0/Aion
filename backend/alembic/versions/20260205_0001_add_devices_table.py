"""Add devices table for persistent device registration

Revision ID: 20260205_0001
Revises: 20260201_0002
Create Date: 2026-02-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260205_0001'
down_revision: Union[str, None] = '20260201_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('device_name', sa.String(255), nullable=False),
        sa.Column('device_type', sa.String(50), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('last_sync', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_version', sa.Integer(), nullable=False, default=0),
        sa.Column('device_token', sa.String(512), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('app_version', sa.String(50), nullable=True),
        sa.Column('os_version', sa.String(100), nullable=True),
        sa.Column('push_token', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create indexes
    op.create_index('ix_devices_user_id', 'devices', ['user_id'])
    op.create_index('ix_devices_is_active', 'devices', ['is_active'])
    op.create_index('ix_devices_platform', 'devices', ['platform'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_devices_platform', table_name='devices')
    op.drop_index('ix_devices_is_active', table_name='devices')
    op.drop_index('ix_devices_user_id', table_name='devices')
    
    # Drop table
    op.drop_table('devices')
