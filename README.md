# ADK Agent Service with PostgreSQL Configuration

A production-ready Cloud Run application using Google's Agent Development Kit (ADK) with PostgreSQL-based configuration management. Built with ports & adapters (hexagonal) architecture and dependency injection for maintainability and testability.

## Features

- **Google ADK Integration**: Build and deploy AI agents using Google's latest Agent Development Kit
- **PostgreSQL Configuration**: Store agent configurations, tools, and models in PostgreSQL
- **Ports & Adapters Architecture**: Clean separation between domain logic and infrastructure
- **Dependency Injection**: Modular, testable design with clean dependency management
- **Dynamic Tool Loading**: Load and register tools from configuration
- **Multi-Agent Support**: Support for hierarchical agent systems with sub-agents
- **Cloud Run Ready**: Optimized for Google Cloud Run deployment
- **RESTful API**: FastAPI-based REST endpoints for agent interaction

## Architecture

```
src/
├── domain/                 # Core business logic (ports)
│   ├── models/            # Domain models
│   │   └── agent_config.py
│   ├── ports/             # Repository interfaces
│   │   └── agent_repository.py
│   └── services/          # Business services
│       └── agent_service.py
├── infrastructure/        # Adapters
│   ├── adapters/
│   │   └── postgres/      # PostgreSQL adapter
│   │       ├── postgres_agent_repository.py
│   │       └── schema.sql
│   └── tools/             # ADK tool implementations
│       ├── sample_tools.py
│       └── tool_registry.py
├── application/           # Application layer
│   ├── api/               # API endpoints
│   │   └── routes.py
│   └── di/                # Dependency injection
│       └── container.py
└── main.py                # Entry point
```

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Docker (for containerized deployment)
- Google Cloud account (for Cloud Run deployment)
- Google Cloud SDK (`gcloud` CLI)

## Installation

### Local Development

1. **Clone the repository**

```bash
git clone <repository-url>
cd testtesttest
```

2. **Create virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Set up environment variables**

```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Set up PostgreSQL database**

```bash
# Create database
createdb agents_db

# Run schema
psql agents_db < src/infrastructure/adapters/postgres/schema.sql
```

6. **Run the application**

```bash
python -m src.main
```

### Docker Development

1. **Start services with Docker Compose**

```bash
docker-compose up -d
```

This will start:
- PostgreSQL database on port 5432
- Agent service on port 8080

2. **View logs**

```bash
docker-compose logs -f agent-service
```

3. **Stop services**

```bash
docker-compose down
```

## Usage

### API Endpoints

#### Health Check

```bash
curl http://localhost:8080/health
```

#### List Agents

```bash
curl http://localhost:8080/api/v1/agents
```

#### Get Agent Details

```bash
curl http://localhost:8080/api/v1/agents/agent-001
```

#### Invoke Agent by ID

```bash
curl -X POST http://localhost:8080/api/v1/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-001",
    "prompt": "What is the weather in San Francisco?"
  }'
```

#### Invoke Agent by Name

```bash
curl -X POST http://localhost:8080/api/v1/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "search_assistant",
    "prompt": "Search for information about AI agents"
  }'
```

#### Reload Agent Configuration

```bash
curl -X POST http://localhost:8080/api/v1/agents/agent-001/reload
```

### Interactive API Documentation

Visit http://localhost:8080/docs for Swagger UI documentation.

## Database Schema

The application uses the following tables:

- **agents**: Stores agent configurations (name, instruction, model, etc.)
- **tools**: Stores tool definitions
- **agent_tools**: Many-to-many relationship between agents and tools
- **agent_sub_agents**: Hierarchical relationships between agents

See `src/infrastructure/adapters/postgres/schema.sql` for the complete schema.

## Adding Custom Tools

1. **Create a tool function** in `src/infrastructure/tools/sample_tools.py`:

```python
def my_custom_tool(param: str) -> dict:
    """
    Description of what the tool does.

    Args:
        param: Parameter description

    Returns:
        A dictionary with the result
    """
    return {
        "status": "success",
        "result": f"Processed: {param}"
    }
```

2. **Add tool to database**:

```sql
INSERT INTO tools (tool_id, tool_name, tool_type, function_name, description)
VALUES ('tool-004', 'my_custom_tool', 'function', 'my_custom_tool', 'My custom tool');

-- Associate with an agent
INSERT INTO agent_tools (agent_id, tool_id)
VALUES ('agent-001', 'tool-004');
```

3. **Reload the agent** to pick up the new tool.

## Cloud Run Deployment

### Prerequisites

```bash
# Set your project ID
export PROJECT_ID=your-project-id
export REGION=us-central1
export SERVICE_NAME=adk-agent-service

# Authenticate
gcloud auth login
gcloud config set project $PROJECT_ID
```

### Deploy to Cloud Run

```bash
# Build and push container
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars "DB_HOST=your-postgres-host" \
  --set-env-vars "DB_NAME=agents_db" \
  --set-env-vars "DB_USER=postgres" \
  --set-secrets "DB_PASSWORD=db-password-secret:latest" \
  --set-secrets "GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp-credentials" \
  --memory 1Gi \
  --cpu 1 \
  --max-instances 10
```

### Using Cloud SQL

For production, use Cloud SQL for PostgreSQL:

```bash
# Create Cloud SQL instance
gcloud sql instances create agents-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=$REGION

# Create database
gcloud sql databases create agents_db --instance=agents-db

# Deploy with Cloud SQL connection
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --add-cloudsql-instances $PROJECT_ID:$REGION:agents-db \
  --set-env-vars "DB_HOST=/cloudsql/$PROJECT_ID:$REGION:agents-db" \
  ...
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | 8080 |
| `HOST` | Server host | 0.0.0.0 |
| `ENVIRONMENT` | Environment (development/production) | development |
| `DB_HOST` | PostgreSQL host | localhost |
| `DB_PORT` | PostgreSQL port | 5432 |
| `DB_NAME` | Database name | agents_db |
| `DB_USER` | Database user | postgres |
| `DB_PASSWORD` | Database password | postgres |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | - |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP credentials | - |

## Development

### Project Structure

- **Domain Layer**: Contains business logic and defines interfaces (ports)
- **Infrastructure Layer**: Implements ports with concrete adapters (PostgreSQL, tools)
- **Application Layer**: Handles HTTP requests, dependency injection

### Design Principles

1. **Ports & Adapters**: Domain logic is independent of infrastructure
2. **Dependency Injection**: Dependencies are injected via the container
3. **Separation of Concerns**: Each layer has a specific responsibility
4. **SOLID Principles**: Single responsibility, Open/closed, etc.

### Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run tests
pytest

# Run with coverage
pytest --cov=src tests/
```

## Troubleshooting

### Connection Issues

- Ensure PostgreSQL is running and accessible
- Check environment variables are set correctly
- Verify network connectivity

### Agent Not Found

- Check if agent exists in database
- Verify agent is enabled
- Try reloading agent configuration

### Tool Errors

- Ensure tool function exists in tool registry
- Check tool is enabled in database
- Verify tool parameters are correct

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License

## Resources

- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Ports & Adapters Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
