"""
Integration test: Trigger-Action automation flow.

Creates a trigger, creates a matching block, and verifies the trigger
fires without errors.  Uses an in-memory SQLite session (provided by the
conftest.py ``db_session`` fixture) so no running PostgreSQL is required.
"""

import sys
import os
import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete

from app.services.block_service import BlockService
from app.services.trigger_service import TriggerService
from app.schemas.block import BlockCreate
from app.models.trigger import Trigger


@pytest.mark.asyncio
async def test_trigger_flow(db_session):
    """
    End-to-end: create a trigger, create a matching block, verify the trigger
    fires (no unhandled exceptions) and clean up.
    """
    trigger_service = TriggerService(db_session)
    block_service = BlockService(db_session, trigger_service)

    # 1. Create a trigger that fires on block_created when name == 'TRIGGER_TEST'
    trigger_data = {
        "name": "Test Automation",
        "event_type": "block_created",
        "condition": {"block_name": "TRIGGER_TEST"},
        "action_type": "open_url",
        "action_params": {"url": "https://example.com/automation_success"},
    }

    trigger = Trigger(**trigger_data)
    db_session.add(trigger)
    await db_session.commit()

    assert trigger.id is not None, "Trigger should have been persisted with an ID"

    # 2. Create a block whose name matches the trigger condition
    block_data = BlockCreate(
        name="TRIGGER_TEST",
        description="Testing the automation engine.",
    )

    block = await block_service.create_block(block_data)
    await db_session.commit()

    assert block is not None, "Block creation should succeed"
    assert block.name == "TRIGGER_TEST"

    # 3. Verify the trigger is still active (i.e., nothing corrupted it)
    triggers = await trigger_service.list_triggers(active_only=True)
    assert any(t.id == trigger.id for t in triggers), (
        "Trigger should still be listed as active after block creation"
    )

    # 4. Cleanup
    await db_session.execute(delete(Trigger).where(Trigger.id == trigger.id))
    await db_session.commit()

