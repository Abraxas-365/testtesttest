# Architecture Documentation

## Overview

This project implements a **Ports & Adapters (Hexagonal) Architecture** with **Dependency Injection** to build a maintainable, testable, and scalable ADK (Agent Development Kit) service.

## Architectural Patterns

### 1. Ports & Adapters (Hexagonal Architecture)

The application is structured in three main layers:

#### Domain Layer (Core/Hexagon)
- **Location**: `src/domain/`
- **Purpose**: Contains business logic, domain models, and port interfaces
- **Dependencies**: None (depends on nothing)
- **Components**:
  - `models/`: Domain entities (AgentConfig, ToolConfig, ModelConfig)
  - `ports/`: Interface definitions (AgentRepository)
  - `services/`: Business logic (AgentService)

#### Infrastructure Layer (Adapters)
- **Location**: `src/infrastructure/`
- **Purpose**: Implements ports with concrete technologies
- **Dependencies**: Domain layer
- **Components**:
  - `adapters/postgres/`: PostgreSQL implementation of AgentRepository
  - `tools/`: Tool registry and implementations

#### Application Layer
- **Location**: `src/application/`
- **Purpose**: Orchestrates the application, handles HTTP, DI
- **Dependencies**: Domain and Infrastructure layers
- **Components**:
  - `api/`: FastAPI routes and endpoints
  - `di/`: Dependency injection container

### 2. Dependency Injection

**Pattern**: Constructor Injection with Container

```python
# Port (interface)
class AgentRepository(ABC):
    @abstractmethod
    async def get_agent_by_id(self, agent_id: str): ...

# Adapter (implementation)
class PostgresAgentRepository(AgentRepository):
    async def get_agent_by_id(self, agent_id: str): ...

# Service (depends on port, not adapter)
class AgentService:
    def __init__(self, repository: AgentRepository):
        self.repository = repository  # Injected dependency

# Container (wires everything together)
class Container:
    async def get_agent_service(self) -> AgentService:
        repository = await self.init_repository()
        return AgentService(repository)
```

**Benefits**:
- Easy to test (inject mocks)
- Loose coupling
- Easy to swap implementations

### 3. Repository Pattern

**Purpose**: Abstract data access behind an interface

```python
# Domain defines what it needs (port)
class AgentRepository(ABC):
    @abstractmethod
    async def get_agent_by_id(self, agent_id: str): ...

# Infrastructure provides it (adapter)
class PostgresAgentRepository(AgentRepository):
    async def get_agent_by_id(self, agent_id: str):
        # PostgreSQL-specific implementation
        ...
```

**Benefits**:
- Domain doesn't know about PostgreSQL
- Easy to add other adapters (MongoDB, Redis, etc.)
- Testable with in-memory implementations

### 4. Registry Pattern

**Purpose**: Manage dynamic tool loading and registration

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        self._tools[name] = func

    def get_tool(self, config: ToolConfig):
        return self._tools.get(config.function_name)
```

**Benefits**:
- Dynamic tool loading
- Centralized tool management
- Easy to extend with new tools

## Data Flow

### Request Flow (Invoke Agent)

```
1. HTTP Request
   ↓
2. FastAPI Route (application/api/routes.py)
   ↓
3. Get Container
   ↓
4. Get Agent Service (via DI)
   ↓
5. Agent Service → Repository (port)
   ↓
6. PostgreSQL Adapter (implements port)
   ↓
7. Database Query
   ↓
8. AgentConfig returned
   ↓
9. Agent Service → Tool Registry
   ↓
10. Tool Registry returns tool functions
    ↓
11. Create ADK Agent with config + tools
    ↓
12. Invoke Agent with prompt
    ↓
13. Return Response
```

### Dependency Graph

```
main.py
  └─→ Container (DI)
       ├─→ AgentRepository (port)
       │    └─→ PostgresAgentRepository (adapter)
       │         └─→ asyncpg (database driver)
       │
       ├─→ ToolRegistry
       │    └─→ sample_tools (functions)
       │
       └─→ AgentService
            ├─→ AgentRepository (injected)
            └─→ ToolRegistry (injected)
```

## Design Principles

### SOLID Principles

#### Single Responsibility Principle (SRP)
- Each class has one reason to change
- `AgentService`: Manages agents
- `PostgresAgentRepository`: Handles database operations
- `ToolRegistry`: Manages tools

#### Open/Closed Principle (OCP)
- Open for extension, closed for modification
- Add new adapters without changing domain code
- Add new tools without changing ToolRegistry core

#### Liskov Substitution Principle (LSP)
- Subtypes must be substitutable for base types
- Any `AgentRepository` implementation can replace another
- `PostgresAgentRepository` can be swapped with `MongoAgentRepository`

#### Interface Segregation Principle (ISP)
- Clients shouldn't depend on interfaces they don't use
- `AgentRepository` only defines methods needed by `AgentService`

#### Dependency Inversion Principle (DIP)
- Depend on abstractions, not concretions
- `AgentService` depends on `AgentRepository` (interface)
- Not on `PostgresAgentRepository` (concrete class)

### Other Design Principles

#### Domain-Driven Design (DDD)
- Domain models represent business concepts
- Rich domain models with validation
- Domain services for business logic

#### Separation of Concerns
- HTTP concerns in API layer
- Business logic in domain layer
- Data access in infrastructure layer

#### Fail Fast
- Validate at domain model creation
- Use immutable domain objects (frozen dataclasses)
- Type hints for compile-time checks

## Testing Strategy

### Unit Tests

```python
# Test domain service with mock repository
def test_agent_service():
    mock_repo = Mock(spec=AgentRepository)
    mock_repo.get_agent_by_id.return_value = mock_config

    service = AgentService(mock_repo, mock_registry)
    agent = await service.get_agent("agent-001")

    assert agent is not None
    mock_repo.get_agent_by_id.assert_called_once()
```

### Integration Tests

```python
# Test with real PostgreSQL
@pytest.fixture
async def postgres_repo():
    repo = await PostgresAgentRepository.create(...)
    yield repo
    await repo.close()

async def test_postgres_repository(postgres_repo):
    agent = await postgres_repo.get_agent_by_id("agent-001")
    assert agent.name == "search_assistant"
```

### End-to-End Tests

```python
# Test complete flow
async def test_invoke_agent_endpoint(client):
    response = await client.post("/api/v1/invoke", json={
        "agent_id": "agent-001",
        "prompt": "Hello"
    })
    assert response.status_code == 200
```

## Extension Points

### Adding a New Adapter

To add a new repository adapter (e.g., MongoDB):

1. **Create adapter**:
```python
class MongoAgentRepository(AgentRepository):
    async def get_agent_by_id(self, agent_id: str):
        # MongoDB implementation
        ...
```

2. **Update container**:
```python
class Container:
    async def init_repository(self):
        if os.getenv("REPO_TYPE") == "mongo":
            return await MongoAgentRepository.create(...)
        return await PostgresAgentRepository.create(...)
```

### Adding a New Tool

1. **Create tool function**:
```python
def my_tool(param: str) -> dict:
    """Tool description."""
    return {"status": "success", "result": param}
```

2. **Add to database**:
```sql
INSERT INTO tools (tool_id, tool_name, tool_type, function_name)
VALUES ('tool-xyz', 'my_tool', 'function', 'my_tool');
```

3. **Tool registry auto-discovers it**

### Adding a New Endpoint

1. **Add route**:
```python
@router.post("/api/v1/custom")
async def custom_endpoint():
    service = await get_container().get_agent_service()
    # Use service...
```

## Cloud Run Considerations

### Stateless Design
- No local state (except caching)
- All configuration in database
- Container can scale horizontally

### Connection Pooling
- AsyncPG connection pool
- Shared across requests
- Configured in Container

### Graceful Shutdown
- FastAPI lifespan events
- Close database connections on shutdown

### Health Checks
- `/health` endpoint
- Kubernetes-style readiness

## Security Considerations

### Credentials Management
- Environment variables for config
- Secrets for sensitive data (passwords)
- Google Cloud Secret Manager integration

### Database Security
- Parameterized queries (SQL injection protection)
- Connection encryption (SSL/TLS)
- Least privilege database user

### API Security
- CORS configuration
- Rate limiting (add middleware)
- Authentication (add auth middleware)

## Performance Considerations

### Caching
- Agent cache in `AgentService`
- Avoid recreating agents on every request
- Cache invalidation via reload endpoint

### Connection Pooling
- AsyncPG pool (min=10, max=20)
- Reuse connections across requests

### Async/Await
- Non-blocking I/O
- FastAPI async endpoints
- AsyncPG for database

## Monitoring & Observability

### Logging
- Structured logging
- Log levels (INFO, ERROR)
- Request/response logging

### Metrics (to add)
- Request count
- Response time
- Database query time
- Agent invocation count

### Tracing (to add)
- OpenTelemetry
- Trace requests across services

## Future Enhancements

1. **Caching Layer**: Add Redis for agent caching
2. **Event Sourcing**: Track agent configuration changes
3. **Multi-tenancy**: Support multiple organizations
4. **Authentication**: Add OAuth2/JWT
5. **Rate Limiting**: Prevent abuse
6. **Metrics**: Prometheus/Cloud Monitoring
7. **A/B Testing**: Support multiple agent versions
8. **Versioning**: Version agent configurations

## References

- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [Dependency Injection](https://en.wikipedia.org/wiki/Dependency_injection)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
