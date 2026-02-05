import asyncio
import sys
import os
import pytest

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import async_session_maker
from app.services.block_service import BlockService
from app.services.trigger_service import TriggerService
from app.schemas.block import BlockCreate
from app.models.trigger import Trigger
from sqlalchemy import delete

@pytest.mark.asyncio
async def test_trigger_flow():
    from app.db.base import Base # Ensure all models are loaded
    from app.db.session import engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session_maker() as session:
        trigger_service = TriggerService(session)
        block_service = BlockService(session, trigger_service)
        
        print("--- Setting up Trigger ---")
        # 1. Create a trigger: "When block name is 'TRIGGER_TEST', print 'Fired' (or similar)"
        # Note: We'll use a real action like 'open_url' but pointing to a placeholder
        trigger_data = {
            "name": "Test Automation",
            "event_type": "block_created",
            "condition": {"block_name": "TRIGGER_TEST"},
            "action_type": "open_url",
            "action_params": {"url": "https://example.com/automation_success"}
        }
        
        trigger = Trigger(**trigger_data)
        session.add(trigger)
        await session.commit()
        print(f"Trigger created: {trigger.id}")
        
        print("\n--- Creating Matching Block ---")
        # 2. Create matching block
        block_data = BlockCreate(
            name="TRIGGER_TEST",
            description="Testing the automation engine."
        )
        
        # This SHOULD fire the trigger
        print("Creating block now...")
        await block_service.create_block(block_data)
        await session.commit()
        print("Block created.")
        
        print("\n[SUCCESS] Trigger-Action flow executed check server logs for fulfillment.")
        
        # Cleanup
        print("\nCleaning up...")
        await session.execute(delete(Trigger).where(Trigger.id == trigger.id))
        # Note: We leave the block for now or clean it up if needed
        await session.commit()

if __name__ == "__main__":
    asyncio.run(test_trigger_flow())
