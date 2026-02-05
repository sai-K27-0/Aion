import asyncio
import sys
import os
import pytest

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_service import get_vector_service

@pytest.mark.asyncio
async def test_graph_export():
    vector = get_vector_service()
    
    if not await vector.is_available():
        print("Error: Vector service not available.")
        return

    print("--- Testing Semantic Graph Export ---")
    graph = await vector.get_semantic_graph(limit=10)
    
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    
    print(f"Nodes found: {len(nodes)}")
    print(f"Links found: {len(links)}")
    
    if nodes:
        print("\nNode Preview:")
        for n in nodes[:3]:
            print(f" - {n['name']} ({n['id']})")
    
    if links:
        print("\nLink Preview:")
        for l in links[:3]:
            print(f" - {l['source']} --({l['value']:.2f})--> {l['target']}")
            
    if len(nodes) > 0:
        print("\n[SUCCESS] Neural graph data generated.")
    else:
        print("\n[WARNING] No blocks found in vector database. Seeding some data might be helpful for full testing.")

if __name__ == "__main__":
    asyncio.run(test_graph_export())
