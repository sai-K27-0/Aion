import httpx
import asyncio

async def test_chat():
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("Testing AI Chat Endpoint...")
        try:
            response = await client.post(
                "http://localhost:8000/api/v1/ai/chat",
                json={"message": "Hello, what time is it?"}
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Response: {data.get('response', 'No response')[:200]}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
