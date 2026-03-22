"""add system_settings table

Revision ID: a1b2c3d4e5f6
Revises: d5ebee6cb992
Create Date: 2026-03-22 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd5ebee6cb992'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('registration_locked', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('setup_complete', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('tunnel_domain', sa.String(length=255), nullable=True),
        sa.Column('tunnel_type', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('system_settings')
