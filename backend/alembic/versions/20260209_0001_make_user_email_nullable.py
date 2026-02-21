"""Make user email nullable (username-first auth)

Revision ID: 20260209_0001
Revises: 20260205_0001
Create Date: 2026-02-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260209_0001"
down_revision: Union[str, None] = "20260205_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Email becomes optional. Postgres UNIQUE allows multiple NULLs.
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # Best-effort: if NULL emails exist, this will fail at runtime.
    op.alter_column("users", "email", existing_type=sa.String(length=255), nullable=False)

