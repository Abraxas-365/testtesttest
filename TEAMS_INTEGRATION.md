# Microsoft Teams Integration with Azure AD Group Routing

## Overview

This integration enables automatic routing of Microsoft Teams messages to appropriate GCP agents based on users' Azure AD group membership.

**Key Features:**
- ✅ **Database-Driven Configuration**: Group mappings stored in PostgreSQL, no code changes needed
- ✅ **Weight-Based Priority**: Flexible priority system for users in multiple groups
- ✅ **REST API Management**: Full CRUD operations for managing group mappings
- ✅ **Session Persistence**: Conversation memory across Teams interactions
- ✅ **Fallback Support**: Automatic routing to general agent when no match found

## How It Works

```
Teams User Message
    ↓
Microsoft Graph API (get user's AD groups)
    ↓
Azure AD Group Mapper (maps groups to area_type)
    ↓
Agent Router (finds agent with matching area_type)
    ↓
GCP Agent Service (invokes agent with conversation memory)
    ↓
Response to Teams User
```

## Architecture

### 1. Database Schema

The `area_type` column in the `agents` table now accepts any string value (constraint removed):

```sql
area_type VARCHAR(50) DEFAULT 'general'  -- No CHECK constraint
```

This allows `area_type` to match your Azure AD group names dynamically.

### 2. Group to Agent Mapping (Database-Driven)

Group mappings are now stored in the database table `azure_ad_group_mappings` with configurable weights:

```sql
CREATE TABLE azure_ad_group_mappings (
    mapping_id SERIAL PRIMARY KEY,
    group_name VARCHAR(255) NOT NULL UNIQUE,  -- Azure AD group display name
    area_type VARCHAR(50) NOT NULL,           -- Agent area_type to route to
    weight INTEGER NOT NULL DEFAULT 0,        -- Higher weight = higher priority
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE
);
```

**Default Mappings with Weights:**
- Admin-Users → admin (weight: 1000)
- Legal-Users → legal (weight: 900)
- Finance-Users → finance (weight: 900)
- HR-Users → hr (weight: 850)
- Developer-Users → developer (weight: 800)
- And more...

**Weight-Based Routing:**
When a user belongs to multiple Azure AD groups, the system uses the mapping with the **highest weight** to determine which agent to route to.

### 3. Agent Creation Examples

Create agents with `area_type` matching your groups:

```sql
-- Legal agent for Legal-Users group
INSERT INTO agents (agent_id, name, area_type, instruction, description, model_name)
VALUES (
    'agent-legal-001',
    'legal_assistant',
    'legal',  -- Matches GROUP_TO_AREA_MAP['Legal-Users']
    'You are a legal assistant specializing in contract law and compliance.',
    'Legal department AI assistant',
    'gemini-2.0-flash'
);

-- HR agent for HR-Users group
INSERT INTO agents (agent_id, name, area_type, instruction, description, model_name)
VALUES (
    'agent-hr-001',
    'hr_assistant',
    'hr',  -- Matches GROUP_TO_AREA_MAP['HR-Users']
    'You are an HR assistant helping with employee policies and benefits.',
    'Human Resources AI assistant',
    'gemini-2.0-flash'
);

-- General fallback agent
INSERT INTO agents (agent_id, name, area_type, instruction, description, model_name)
VALUES (
    'agent-general-001',
    'general_assistant',
    'general',  -- Default fallback
    'You are a general-purpose assistant.',
    'General AI assistant',
    'gemini-2.0-flash'
);
```

## Setup Instructions

### Step 1: Apply Database Migrations

```bash
# Run migration to remove area_type constraint
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f migrations/002_remove_area_type_constraint.sql

# Run migration to create group mappings table
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f migrations/003_azure_ad_group_mappings.sql
```

This will create the `azure_ad_group_mappings` table with default mappings pre-populated.

### Step 2: Configure Environment Variables

Add to your `.env` file:

```bash
# Microsoft Graph API credentials
GRAPH_TENANT_ID=your-azure-tenant-id
GRAPH_CLIENT_ID=your-teams-app-client-id
GRAPH_CLIENT_SECRET=your-app-secret
```

### Step 3: Create Agents with Matching area_type

Ensure you have agents in the database with `area_type` values that match your Azure AD groups.

### Step 4: Deploy to Cloud Run

```bash
# Commit changes
git add -A
git commit -m "Add Teams integration with Azure AD group routing"
git push

# Deploy will happen automatically via Cloud Build
```

## API Endpoints

### 1. Process Teams Message

**Endpoint:** `POST /api/v1/teams/message`

Routes a message to the appropriate agent based on user's Azure AD groups.

```bash
curl -X POST https://your-service.run.app/api/v1/teams/message \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "I need help with a contract review",
    "aad_user_id": "12345-67890-abcdef",
    "user_name": "John Doe",
    "session_id": "teams-session-123",
    "persist_session": true
  }'
```

**Response:**
```json
{
  "success": true,
  "response": "I'd be happy to help with your contract review...",
  "agent_name": "legal_assistant",
  "agent_area": "legal",
  "user_groups": ["Legal-Users", "All-Employees"],
  "session_id": "teams-session-123"
}
```

### 2. Get User's Agent Info

**Endpoint:** `GET /api/v1/teams/user/{aad_user_id}/agents`

Shows which agent(s) a user can access.

```bash
curl https://your-service.run.app/api/v1/teams/user/12345-67890-abcdef/agents
```

**Response:**
```json
{
  "user_groups": ["Legal-Users", "All-Employees"],
  "primary_agent": {
    "name": "legal_assistant",
    "description": "Legal department AI assistant",
    "area": "legal"
  },
  "accessible_agents": [
    {
      "name": "legal_assistant",
      "description": "Legal department AI assistant",
      "area": "legal"
    },
    {
      "name": "general_assistant",
      "description": "General AI assistant",
      "area": "general"
    }
  ]
}
```

### 3. Health Check

**Endpoint:** `GET /api/v1/teams/health`

```bash
curl https://your-service.run.app/api/v1/teams/health
```

### 4. Manage Group Mappings

#### List All Group Mappings

**Endpoint:** `GET /api/v1/groups/mappings`

```bash
curl https://your-service.run.app/api/v1/groups/mappings
```

#### Create New Mapping

**Endpoint:** `POST /api/v1/groups/mappings`

```bash
curl -X POST https://your-service.run.app/api/v1/groups/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "Engineering-Team",
    "area_type": "developer",
    "weight": 800,
    "description": "Engineering team members",
    "enabled": true
  }'
```

#### Update Existing Mapping

**Endpoint:** `PUT /api/v1/groups/mappings/{mapping_id}`

```bash
curl -X PUT https://your-service.run.app/api/v1/groups/mappings/5 \
  -H "Content-Type: application/json" \
  -d '{
    "weight": 950,
    "description": "Updated description"
  }'
```

#### Delete Mapping

**Endpoint:** `DELETE /api/v1/groups/mappings/{mapping_id}`

```bash
curl -X DELETE https://your-service.run.app/api/v1/groups/mappings/5
```

#### Get Mapping by Group Name

**Endpoint:** `GET /api/v1/groups/mappings/by-group/{group_name}`

```bash
curl https://your-service.run.app/api/v1/groups/mappings/by-group/Legal-Users
```

## Routing Logic

### Weight-Based Priority

If a user belongs to multiple groups, the router uses **weight-based selection**:

1. Query database for all group mappings matching user's groups
2. Sort mappings by weight (descending)
3. Select the mapping with the **highest weight**
4. Route to the agent with matching `area_type`

**Default Weights:**
- Admin-Users: **1000** (highest priority)
- Legal-Users: **900**
- Finance-Users: **900**
- HR-Users: **850**
- Developer-Users: **800**
- Operations-Users: **800**
- Data-Analysis-Users: **750**
- Sales-Users: **700**
- Marketing-Users: **700**
- Customer-Support-Users: **650**
- All-Employees: **100** (lowest priority)

### Fallback Behavior

- If no matching agent found for user's group → uses 'general' agent
- If no groups found for user → uses 'general' agent
- If 'general' agent doesn't exist → returns error

## Integration with Microsoft Teams Bot

### Teams Bot Implementation

Your Microsoft Teams bot (Azure Bot Service) should call this API:

```python
# In your Teams bot handler
async def on_message_activity(self, turn_context: TurnContext):
    # Get user info from Teams
    user_message = turn_context.activity.text
    aad_user_id = turn_context.activity.from_property.aad_object_id
    user_name = turn_context.activity.from_property.name
    conversation_id = turn_context.activity.conversation.id

    # Call your GCP API
    response = await call_teams_api(
        user_message=user_message,
        aad_user_id=aad_user_id,
        user_name=user_name,
        session_id=f"teams-{conversation_id}"
    )

    # Send response back to Teams
    await turn_context.send_activity(response['response'])
```

### Example Azure Bot Service Integration

```python
import aiohttp

async def call_teams_api(user_message, aad_user_id, user_name, session_id):
    """Call GCP Teams integration API."""

    async with aiohttp.ClientSession() as session:
        async with session.post(
            'https://your-service.run.app/api/v1/teams/message',
            json={
                'user_message': user_message,
                'aad_user_id': aad_user_id,
                'user_name': user_name,
                'session_id': session_id,
                'persist_session': True
            }
        ) as resp:
            return await resp.json()
```

## Testing

### 1. Test Group Mapping

```bash
# List all group mappings
curl http://localhost:8080/api/v1/groups/mappings

# Get specific group mapping
curl http://localhost:8080/api/v1/groups/mappings/by-group/Legal-Users
```

### 2. Test API Locally

```bash
# Start the service
python -m src.main

# Test the Teams endpoint
curl -X POST http://localhost:8080/api/v1/teams/message \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "Help me with a legal question",
    "aad_user_id": "test-user-123",
    "user_name": "Test User",
    "session_id": "test-session-1"
  }'
```

### 3. Test with Real Azure AD

Requires:
- Azure AD tenant configured
- App registration with Microsoft Graph permissions
- Users assigned to security groups

## Customization

### Add Custom Group Mappings

Use the API to add new group mappings:

```bash
curl -X POST http://localhost:8080/api/v1/groups/mappings \
  -H "Content-Type: application/json" \
  -d '{
    "group_name": "Engineering-Team",
    "area_type": "developer",
    "weight": 850,
    "description": "Software engineering team",
    "enabled": true
  }'
```

Or directly via SQL:

```sql
INSERT INTO azure_ad_group_mappings (group_name, area_type, weight, description)
VALUES ('Engineering-Team', 'developer', 850, 'Software engineering team');
```

### Change Priority Order

Update weights via API to change priority:

```bash
# Make Engineering-Team higher priority than Legal-Users
curl -X PUT http://localhost:8080/api/v1/groups/mappings/5 \
  -H "Content-Type: application/json" \
  -d '{"weight": 950}'
```

Or via SQL:

```sql
-- Higher weight = higher priority
UPDATE azure_ad_group_mappings
SET weight = 950
WHERE group_name = 'Engineering-Team';
```

### Multi-Agent Access

Users in multiple groups can access multiple agents:

```python
# Get all agents user can access
accessible_agents = await agent_router.get_available_agents_for_user(user_groups)
```

## Monitoring

### Logs to Monitor

```bash
# View routing decisions
gcloud run services logs read $SERVICE_NAME --region $REGION | grep "Routing user"

# View group mappings
gcloud run services logs read $SERVICE_NAME --region $REGION | grep "area_type"

# View errors
gcloud run services logs read $SERVICE_NAME --region $REGION | grep "ERROR"
```

### Key Metrics

- **Route Success Rate**: Percentage of messages successfully routed
- **Agent Distribution**: Which agents are being used most
- **Group Coverage**: Percentage of users with matching agents

## Troubleshooting

### Issue: User gets "No suitable agent found"

**Solution:** Create an agent with matching `area_type` or ensure 'general' agent exists.

### Issue: Microsoft Graph API errors

**Solution:** Check Graph API permissions and credentials:
- User.Read
- Directory.Read.All
- GroupMember.Read.All

### Issue: Wrong agent selected

**Solution:**
1. Check group mappings: `GET /api/v1/groups/mappings`
2. Verify user's groups are mapped correctly
3. Check weight values - higher weight = higher priority
4. Update weights if needed: `PUT /api/v1/groups/mappings/{id}`

## Security Considerations

1. **API Authentication**: Add authentication to Teams API endpoints
2. **Rate Limiting**: Implement rate limiting for production
3. **Input Validation**: Validate all user inputs
4. **Audit Logging**: Log all routing decisions for compliance

## Next Steps

1. ✅ Database migration applied
2. ✅ Environment variables configured
3. ✅ Agents created with matching area_types
4. ⬜ Azure Bot Service configured to call this API
5. ⬜ Teams app deployed to organization
6. ⬜ Users assigned to appropriate Azure AD groups
7. ⬜ Testing completed

---

**Questions?** Check the main README or open an issue.
