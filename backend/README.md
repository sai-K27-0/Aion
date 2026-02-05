# Aion Backend

A privacy-centric, AI-powered personal life management system backend.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Ollama (for local AI)

### 1. Clone and Setup

```bash
cd aion/backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
```

### 2. Start Services

```bash
# Start PostgreSQL, Qdrant, and Redis
docker-compose up -d

# Wait for services to be ready
docker-compose ps
```

### 3. Initialize Database

```bash
# Run migrations (once Alembic is set up)
alembic upgrade head
```

### 4. Start Ollama (For AI Features)

```bash
# Install Ollama from https://ollama.ai

# Pull required models
ollama pull llama3.2
ollama pull nomic-embed-text

# Ollama runs automatically as a service
```

### 5. Run the API

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 6. Access the API

- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📁 Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Settings management
│   ├── api/
│   │   ├── deps.py          # Dependencies
│   │   └── v1/
│   │       ├── router.py    # API router
│   │       └── endpoints/
│   │           └── blocks.py
│   ├── models/
│   │   └── block.py         # SQLAlchemy models
│   ├── schemas/
│   │   └── block.py         # Pydantic schemas
│   ├── services/
│   │   └── block_service.py # Business logic
│   └── db/
│       ├── base.py          # Base model
│       └── session.py       # Database session
├── alembic/                  # Migrations
├── tests/                    # Test suite
├── docker-compose.yml        # Local services
├── Dockerfile               # Production build
└── requirements.txt         # Dependencies
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_blocks.py -v
```

## 📊 API Endpoints

### Blocks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/blocks` | Create a block |
| GET | `/api/v1/blocks` | List blocks |
| GET | `/api/v1/blocks/tree` | Get block tree |
| GET | `/api/v1/blocks/{id}` | Get block by ID |
| PATCH | `/api/v1/blocks/{id}` | Update block |
| DELETE | `/api/v1/blocks/{id}` | Delete block |
| POST | `/api/v1/blocks/{id}/move` | Move block |
| GET | `/api/v1/blocks/{id}/ancestors` | Get ancestors |
| GET | `/api/v1/blocks/{id}/descendants` | Get descendants |
| POST | `/api/v1/blocks/{id}/fields` | Add field |
| GET | `/api/v1/blocks/{id}/fields` | Get fields |
| POST | `/api/v1/blocks/{id}/entries` | Create entry |
| GET | `/api/v1/blocks/{id}/entries` | Get entries |

## 🔒 Security

- All data is stored locally
- No external API calls (except to local Ollama)
- CORS configured for local clients only
- Environment-based configuration

## 📝 License

MIT License - See LICENSE file for details.
