"""Add device approval columns for one-time device verification

Revision ID: 20260304_0001
Revises: 20260209_0001
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260304_0001"
down_revision: Union[str, None] = "20260209_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add approval_status: pending, approved, rejected
    op.add_column(
        "devices",
        sa.Column(
            "approval_status",
            sa.String(20),
            nullable=False,
            server_default="approved",  # Existing devices are grandfathered in
        ),
    )

    # 6-character approval code for device verification
    op.add_column(
        "devices",
        sa.Column("approval_code", sa.String(10), nullable=True),
    )

    # Which device approved this one
    op.add_column(
        "devices",
        sa.Column("approved_by_device_id", sa.String(36), nullable=True),
    )

    # When was the device approved
    op.add_column(
        "devices",
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Index for looking up pending devices quickly
    op.create_index(
        "ix_devices_approval_status",
        "devices",
        ["approval_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_devices_approval_status", table_name="devices")
    op.drop_column("devices", "approved_at")
    op.drop_column("devices", "approved_by_device_id")
    op.drop_column("devices", "approval_code")
    op.drop_column("devices", "approval_status")
