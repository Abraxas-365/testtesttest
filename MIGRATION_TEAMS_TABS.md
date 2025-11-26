# Migration Guide: Azure Bot Framework → Teams Tabs

This document explains the migration from Azure Bot Framework to Microsoft Teams Tabs for the GrupoDC Agent backend.

## 📋 Overview

### What Changed?

- **Before (Bot Framework):** Teams users interacted with a bot via messaging interface
- **After (Teams Tabs):** Teams users interact with a web application (React frontend) embedded as a tab

### Architecture Changes

| Component | Old (Bot) | New (Tabs) |
|-----------|-----------|------------|
| **Communication** | Activity-based messaging via Bot Framework | Direct REST API calls |
| **Authentication** | Bot Framework token | Teams SSO JWT tokens |
| **Endpoint** | `/api/v1/teams/message` | `/api/v1/tabs/invoke` |
| **Request Format** | Bot Activity objects | Simple JSON |
| **Response Format** | Activity with text/cards | JSON response |
| **User Context** | From Activity object | From JWT claims |

---

## 🔧 Backend Changes Implemented

### 1. New Dependencies

Added to `requirements.txt`:

```python
httpx==0.27.0          # Async HTTP client
PyJWT==2.8.0          # JWT token validation
cryptography==41.0.7   # Cryptographic functions
python-jose[cryptography]==3.3.0  # Additional JWT utilities
```

**Install with:**

```bash
pip install -r requirements.txt
```

### 2. New Middleware: Token Validation

**File:** `src/middleware/teams_auth.py`

**Purpose:** Validates Teams SSO JWT tokens using Microsoft's public keys.

**Key Functions:**

- `validate_teams_token()` - FastAPI dependency for token validation
- `get_user_from_token()` - Extract user info from decoded token
- `validate_teams_token_optional()` - Optional auth dependency

**Usage in routes:**

```python
from src.middleware.teams_auth import validate_teams_token, get_user_from_token

@router.post("/protected-endpoint")
async def protected(token_data: dict = Depends(validate_teams_token)):
    user_info = get_user_from_token(token_data)
    # user_info contains: user_id, name, email, tenant_id
```

### 3. New API Routes

**File:** `src/application/api/tabs_routes.py`

**Endpoints:**

1. **`POST /api/v1/tabs/invoke`** - Main endpoint for processing user messages
   - Requires Teams SSO token
   - Validates user authentication
   - Routes to appropriate agent
   - Returns JSON response

2. **`GET /api/v1/tabs/health`** - Health check for tabs integration

3. **`GET /api/v1/tabs/user/profile`** - Get authenticated user profile

4. **`POST /api/v1/tabs/config`** - Get tab configuration for user

**Request Example:**

```json
POST /api/v1/tabs/invoke
Authorization: Bearer <teams-sso-token>

{
  "prompt": "What is the company policy on remote work?",
  "agent_name": "search_assistant",
  "session_id": "optional-session-id",
  "mode": "auto",
  "source": "all"
}
```

**Response Example:**

```json
{
  "response": "According to our HR policies...",
  "agent_name": "search_assistant",
  "agent_area": "hr",
  "session_id": "session-123",
  "metadata": {
    "user_id": "azure-ad-object-id",
    "user_name": "John Doe",
    "user_email": "john.doe@grupodc.com",
    "mode": "auto",
    "source": "all"
  }
}
```

### 4. Updated CORS Configuration

**File:** `src/main.py`

Added Teams domains to CORS allowlist:

```python
allow_origins=[
    "https://teams.microsoft.com",
    "https://*.teams.microsoft.com",
    "https://*.teams.office.com",
    "https://outlook.office.com",
    "https://*.outlook.office.com",
    "http://localhost:5173",  # For local dev
    # ... your frontend URL
]
```

### 5. Updated Teams Manifest

**File:** `teams/manifest.json`

Added tabs configuration:

```json
{
  "staticTabs": [
    {
      "entityId": "grupodc-assistant-tab",
      "name": "Assistant",
      "contentUrl": "https://your-frontend-app-url.com?inTeams=true",
      "scopes": ["personal"]
    }
  ],
  "configurableTabs": [
    {
      "configurationUrl": "https://your-frontend-app-url.com/config?inTeams=true",
      "canUpdateConfiguration": true,
      "scopes": ["team", "groupchat"]
    }
  ]
}
```

**Note:** Bot configuration is still present for backward compatibility during migration.

---

## 🔐 Azure AD Configuration

### Required Environment Variables

Add these to your `.env` file (see `.env.example`):

```bash
# Azure AD Configuration (for Teams Tabs SSO)
AZURE_TENANT_ID=your-azure-tenant-id-guid
AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
AZURE_CLIENT_SECRET=your-azure-client-secret
```

### Azure AD App Registration Setup

1. **Go to Azure Portal** → App Registrations → Your App

2. **Authentication** → Add Platform → **Single-page application**
   - Add redirect URI: `https://your-frontend-app-url.com/auth-end`
   - Enable Access tokens and ID tokens

3. **Expose an API**
   - Application ID URI: `api://your-frontend-app-url.com/8f932a37-a7f6-4fe8-be5e-a72ab69758cf`
   - Add scope: `access_as_user`
   - Add authorized client applications (Teams clients)

4. **API Permissions**
   - Microsoft Graph: `User.Read` (delegated)
   - Your API: `access_as_user` (delegated)

5. **Certificates & Secrets**
   - Create a new client secret
   - Copy the value to `AZURE_CLIENT_SECRET`

---

## 🚀 Deployment

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AZURE_TENANT_ID=your-tenant-id
export AZURE_CLIENT_ID=your-client-id
export AZURE_CLIENT_SECRET=your-secret

# Run server
uvicorn src.main:app --reload --port 8080
```

### Testing Endpoints

```bash
# Health check (no auth required)
curl http://localhost:8080/api/v1/tabs/health

# With authentication (you need a real Teams token)
curl -X POST http://localhost:8080/api/v1/tabs/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TEAMS_SSO_TOKEN" \
  -d '{
    "prompt": "Hello",
    "agent_name": "search_assistant"
  }'
```

### Google Cloud Run Deployment

```bash
# Deploy with environment variables
gcloud run deploy grupodc-agent-backend \
  --source . \
  --region us-east4 \
  --allow-unauthenticated \
  --set-env-vars AZURE_TENANT_ID=xxx,AZURE_CLIENT_ID=xxx,AZURE_CLIENT_SECRET=xxx \
  --set-env-vars GOOGLE_CLOUD_PROJECT=xxx,GOOGLE_CLOUD_LOCATION=us-east4
```

---

## 🔄 Migration Strategy

### Phase 1: Dual Mode (Current)

- ✅ Both bot and tabs endpoints are active
- ✅ Bot endpoint: `/api/v1/teams/message` (legacy)
- ✅ Tabs endpoint: `/api/v1/tabs/invoke` (new)
- Users can use either interface during transition

### Phase 2: Tabs Primary

- Set tabs as default in Teams
- Monitor usage metrics
- Keep bot as fallback

### Phase 3: Bot Deprecation

- Remove bot from Teams manifest
- Remove `/api/v1/teams/message` endpoint
- Remove `src/application/api/teams_routes.py`
- Clean up bot-specific dependencies

---

## 🧪 Testing Checklist

- [ ] Install new dependencies
- [ ] Set Azure AD environment variables
- [ ] Test `/api/v1/tabs/health` endpoint
- [ ] Deploy backend to Cloud Run
- [ ] Update Teams manifest with backend URL
- [ ] Test with valid Teams SSO token
- [ ] Verify user authentication works
- [ ] Test agent routing and responses
- [ ] Check CORS headers for Teams domains
- [ ] Monitor logs for errors

---

## 🐛 Troubleshooting

### Error: "Azure AD configuration missing"

**Cause:** `AZURE_TENANT_ID` or `AZURE_CLIENT_ID` not set

**Solution:** Set environment variables in `.env` or deployment config

### Error: "Token expired" (401)

**Cause:** Teams SSO token has expired (1-hour lifetime)

**Solution:** Frontend should refresh token automatically. Check Teams SDK implementation.

### Error: "Invalid token audience" (401)

**Cause:** Token audience doesn't match `AZURE_CLIENT_ID`

**Solution:** Verify client ID in Azure AD matches environment variable

### Error: "CORS error" in browser

**Cause:** Frontend domain not in CORS allowlist

**Solution:** Add your frontend URL to `allow_origins` in `main.py`

### Error: "Failed to get signing key from JWT"

**Cause:** Cannot reach Microsoft JWKS endpoint or invalid token format

**Solution:** 
- Check internet connectivity to `login.microsoftonline.com`
- Verify token is in correct format: `Bearer <token>`
- Check token is actually a JWT (three base64 parts separated by dots)

---

## 📚 Additional Resources

- [Microsoft Teams Tabs Documentation](https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/what-are-tabs)
- [Teams SSO Authentication](https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-overview)
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [PyJWT Documentation](https://pyjwt.readthedocs.io/)

---

## 📝 Notes

1. **Frontend Required:** This backend migration requires a React frontend that:
   - Uses `@microsoft/teams-js` SDK
   - Implements Teams SSO authentication
   - Calls the `/api/v1/tabs/invoke` endpoint
   - See the original migration guide for frontend implementation details

2. **Session Management:** Sessions are now identified by Teams chat/channel ID instead of bot conversation ID

3. **File Uploads:** File upload support is not yet implemented for tabs (unlike the bot). This would require standard multipart/form-data handling.

4. **Typing Indicators:** Not available in tabs (only in bot). Use client-side loading states instead.

---

## ✅ Migration Completed

The following changes have been successfully implemented:

- ✅ JWT token validation middleware
- ✅ New tabs API routes
- ✅ Updated CORS configuration
- ✅ Updated Teams manifest
- ✅ Environment variable documentation
- ✅ Migration guide

**Next Steps:**

1. Deploy the backend with Azure AD environment variables
2. Implement the React frontend (see original guide)
3. Test end-to-end integration
4. Upload updated Teams manifest
5. Gradually migrate users from bot to tabs
