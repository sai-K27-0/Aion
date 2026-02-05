import asyncio
import sys
import os
import pytest

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_service import get_ai_service
from app.services.vector_service import get_vector_service
from uuid import uuid4

@pytest.mark.asyncio
async def test_neural_memory():
    ai = get_ai_service()
    vector = get_vector_service()
    
    if not await ai.is_available() or not await vector.is_available():
        print("Error: AI or Vector service not available.")
        return

    print("--- Ensuring Collection ---")
    await vector.ensure_collection()

    print("--- Seeding Disparate Test Data ---")
    # We use two unrelated blocks that mention different parts of the same "hidden" context
    block1_id = str(uuid4())
    block2_id = str(uuid4())
    
    # Block 1: Secret Project Name
    await vector.index_block(
        block_id=block1_id,
        name="Internal Project Code: NOCTURNE",
        description="Priority Alpha project focused on deep sea exploration.",
    )
    
    # Block 2: Secret Technical Detail
    await vector.index_block(
        block_id=block2_id,
        name="NOCTURNE Battery Specs",
        description="The exploration drones use high-density thermal-salt batteries for 48-hour endurance.",
    )
    
    print("Memory seeded.")
    
    print("\n--- Testing Synthesis ---")
    query = "How long can the Project Nocturne drones stay underwater, and what powers them?"
    print(f"Query: {query}")
    
    print("\nThinking...")
    response = await ai.chat(query)
    
    print("-" * 30)
    print(f"AI Response: {response}")
    print("-" * 30)
    
    # Validation logic
    has_salt = "salt" in response.lower()
    has_48 = "48" in response
    has_nocturne = "nocturne" in response.lower()
    
    if has_salt and has_48:
        print("\n[SUCCESS] AI successfully synthesized memory from multiple blocks.")
    else:
        print("\n[FAILURE] AI missed critical details from memory.")

    # Cleanup
    print("\nCleaning up...")
    await vector.delete_block_vectors(block1_id)
    await vector.delete_block_vectors(block2_id)

if __name__ == "__main__":
    asyncio.run(test_neural_memory())
