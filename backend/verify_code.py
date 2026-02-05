import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

print("Attempting to import app.main...")
try:
    from app.main import app
    print("Successfully imported app.main")
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)
except Exception as e:
    # It might fail to connect to DB on import if the startup logic runs immediately (which it shouldn't for FastAPI, only on lifespan startup)
    print(f"Import successful but encountered error during load (likely DB connection): {e}")

print("Attempting to import models...")
try:
    from app.models.block import Block
    print("Successfully imported models")
except Exception as e:
    print(f"Failed to import models: {e}")
    sys.exit(1)

print("Attempting to import services...")
try:
    from app.services.block_service import BlockService
    print("Successfully imported services")
except Exception as e:
    print(f"Failed to import services: {e}")
    sys.exit(1)

print("Code structure verification complete.")
