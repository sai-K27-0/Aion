"""add auth_provider email_verified oauth_provider_id to user

Revision ID: 774198a3ed65
Revises: 20260304_0001
Create Date: 2026-03-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "774198a3ed65"
down_revision: Union[str, None] = "20260304_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Auth provider: "local", "google", "github"
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=20),
            server_default="local",
            nullable=False,
        ),
    )

    # Email verification flag
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    # OAuth provider user ID (for Google/GitHub)
    op.add_column(
        "users",
        sa.Column("oauth_provider_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "oauth_provider_id")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "auth_provider")
