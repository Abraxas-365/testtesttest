# Teams Manifest Configuration Guide

Complete guide for configuring your Microsoft Teams app manifest with multi-mode authentication (Azure Bot + Teams SSO + Web OAuth2).

---

## 📋 Overview

This guide covers the updated Teams manifest (`teams/manifest.json`) that supports:

- **Azure Bot Framework** - Legacy bot messaging endpoint
- **Teams Tabs with SSO** - Single Sign-On using Teams SDK
- **Web OAuth2** - JWT-based authentication for standalone web access

---

## 🔧 Configuration Steps

### 1. Update Frontend URL

After deploying your frontend, replace `your-frontend-app-url.com` with your actual frontend domain in these locations:

**In `teams/manifest.json`:**

```json
{
  "staticTabs": [
    {
      "contentUrl": "https://your-frontend-app.com/teams?inTeams=true",
      "websiteUrl": "https://your-frontend-app.com"
    }
  ],
  "configurableTabs": [
    {
      "configurationUrl": "https://your-frontend-app.com/config?inTeams=true"
    }
  ],
  "validDomains": [
    "your-frontend-app.com"
  ]
}
```

**Example with actual domain:**

```json
{
  "staticTabs": [
    {
      "contentUrl": "https://grupodc-agent-frontend.web.app/teams?inTeams=true",
      "websiteUrl": "https://grupodc-agent-frontend.web.app"
    }
  ],
  "configurableTabs": [
    {
      "configurationUrl": "https://grupodc-agent-frontend.web.app/config?inTeams=true"
    }
  ],
  "validDomains": [
    "grupodc-agent-frontend.web.app"
  ]
}
```

### 2. Verify Backend URL

The backend URL is already configured:

```json
{
  "developer": {
    "websiteUrl": "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app"
  },
  "validDomains": [
    "grupodc-agent-backend-dev-118078450167.us-east4.run.app"
  ],
  "webApplicationInfo": {
    "resource": "api://grupodc-agent-backend-dev-118078450167.us-east4.run.app/8f932a37-a7f6-4fe8-be5e-a72ab69758cf"
  }
}
```

### 3. Verify App Registration IDs

Make sure these IDs match your Azure AD App Registration:

```json
{
  "id": "8f932a37-a7f6-4fe8-be5e-a72ab69758cf",
  "bots": [
    {
      "botId": "8f932a37-a7f6-4fe8-be5e-a72ab69758cf"
    }
  ],
  "webApplicationInfo": {
    "id": "8f932a37-a7f6-4fe8-be5e-a72ab69758cf"
  }
}
```

All three should use the same **Application (client) ID** from Azure AD.

---

## 🔐 Azure AD Configuration

### Required API Permissions

In Azure Portal → App Registrations → API permissions:

1. **Microsoft Graph**:
   - `User.Read` (Delegated)
   - `email` (Delegated)
   - `openid` (Delegated)
   - `profile` (Delegated)

2. **Azure Bot Service** (if using bot):
   - `BotFramework.All` (Delegated)

### Expose an API

In Azure Portal → App Registrations → Expose an API:

1. **Application ID URI**:
   ```
   api://grupodc-agent-backend-dev-118078450167.us-east4.run.app/8f932a37-a7f6-4fe8-be5e-a72ab69758cf
   ```

2. **Scopes**: Add a scope named `access_as_user`:
   - **Scope name**: `access_as_user`
   - **Who can consent**: Admins and users
   - **Display name**: Access GrupoDC Agent as the user
   - **Description**: Allows Teams to call the app's web APIs as the current user

3. **Authorized client applications**: Add Microsoft Teams:
   ```
   1fec8e78-bce4-4aaf-ab1b-5451cc387264  (Teams mobile/desktop)
   5e3ce6c0-2b1f-4285-8d4b-75ee78787346  (Teams web)
   ```

### Redirect URIs

In Azure Portal → App Registrations → Authentication:

Add these redirect URIs as **Web** platform:

```
https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
https://your-frontend-app.com/auth/callback
https://your-frontend-app.com/auth/success
```

**Token configuration:**
- ✅ Access tokens (used for implicit flows)
- ✅ ID tokens (used for implicit and hybrid flows)

---

## 📦 Package and Upload to Teams

### 1. Prepare the Package

Your `teams/` folder should contain:

```
teams/
├── manifest.json          # Updated manifest
├── color.png             # 192x192 app icon
└── outline.png           # 32x32 outline icon
```

### 2. Create ZIP Package

```bash
cd teams
zip -r grupodc-agent-teams.zip manifest.json color.png outline.png
```

Or use the helper script:

```bash
# Create teams/package.sh
cat > teams/package.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
zip -r grupodc-agent-teams.zip manifest.json color.png outline.png
echo "✅ Package created: grupodc-agent-teams.zip"
EOF

chmod +x teams/package.sh
./teams/package.sh
```

### 3. Upload to Teams Admin Center

**Option A: Teams Admin Center (for organization)**

1. Go to [Teams Admin Center](https://admin.teams.microsoft.com)
2. Navigate to **Teams apps** → **Manage apps**
3. Click **Upload new app**
4. Upload `grupodc-agent-teams.zip`
5. Review and approve the app

**Option B: Teams App Studio (for development)**

1. Open Microsoft Teams
2. Go to **Apps** → Search for "App Studio" or "Developer Portal"
3. Open **Developer Portal for Teams**
4. Click **Apps** → **Import app**
5. Upload `grupodc-agent-teams.zip`
6. Install to your personal scope or team

**Option C: Direct Sideload (for testing)**

1. Go to **Teams** → **Apps**
2. Click **Manage your apps** (bottom left)
3. Click **Upload an app** → **Upload a custom app**
4. Select `grupodc-agent-teams.zip`

---

## 🧪 Testing

### Test Azure Bot (Legacy)

Send a message to your bot in Teams:

```
Hello bot!
```

Backend endpoint: `/bot/messages` (handled automatically by Bot Framework)

### Test Teams Tab with SSO

1. Open the **Assistant** tab in Teams (personal app)
2. Teams SDK will automatically get SSO token
3. Token is sent to backend as `Authorization: Bearer <token>`
4. Backend validates RS256 JWT from Microsoft

**Frontend code (React)**:

```javascript
import * as microsoftTeams from '@microsoft/teams-js';

microsoftTeams.app.initialize().then(() => {
  microsoftTeams.authentication.getAuthToken()
    .then(token => {
      // Use token for API calls
      fetch('https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/tabs/invoke', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          prompt: 'Hello from Teams!',
          agent_name: 'search_assistant'
        })
      });
    });
});
```

### Test Web OAuth2

1. Go to `https://your-frontend-app.com/login`
2. Click "Login with Microsoft"
3. Complete OAuth2 flow
4. Receive JWT token in URL: `#token=eyJhbG...`
5. Frontend stores token and uses for API calls

---

## 🔍 Manifest Key Changes

### Version Bump

```json
{
  "version": "3.0.0"  // Updated from 2.0.0
}
```

### Static Tab Route

```json
{
  "contentUrl": "https://your-frontend-app.com/teams?inTeams=true"  // Changed from root to /teams
}
```

This allows different routing for Teams vs Web:
- `/teams` - Teams Tab with Teams SSO
- `/chat` - Web chat with OAuth2 login

### Valid Domains

```json
{
  "validDomains": [
    "token.botframework.com",
    "*.botframework.com",
    "*.blob.core.windows.net",
    "smba.trafficmanager.net",
    "grupodc-agent-backend-dev-118078450167.us-east4.run.app",
    "login.microsoftonline.com",  // Added for OAuth2
    "your-frontend-app.com"
  ]
}
```

Added `login.microsoftonline.com` for OAuth2 redirects.

### Web Application Info

```json
{
  "webApplicationInfo": {
    "id": "8f932a37-a7f6-4fe8-be5e-a72ab69758cf",
    "resource": "api://grupodc-agent-backend-dev-118078450167.us-east4.run.app/8f932a37-a7f6-4fe8-be5e-a72ab69758cf"
  }
}
```

Changed resource from frontend URL to backend URL since backend handles authentication.

---

## 📝 Environment Variables

Update your `deploy-config.sh` with correct values:

```bash
# Azure AD Configuration
export AZURE_TENANT_ID="your-tenant-id-guid"
export AZURE_CLIENT_ID="8f932a37-a7f6-4fe8-be5e-a72ab69758cf"
export AZURE_CLIENT_SECRET="your-secret-from-azure-portal"

# OAuth2 Redirect URI (Backend)
export AZURE_REDIRECT_URI="https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback"

# Frontend URL
export FRONTEND_URL="https://your-frontend-app.com"

# JWT Secret Key
export JWT_SECRET_KEY="$(openssl rand -base64 32)"
```

---

## 🚀 Deployment Checklist

- [ ] Update `teams/manifest.json` with your frontend URL
- [ ] Verify all IDs match your Azure AD App Registration
- [ ] Configure Azure AD API permissions
- [ ] Expose API with correct Application ID URI
- [ ] Add authorized client applications (Teams mobile + web)
- [ ] Add redirect URIs in Azure AD Authentication
- [ ] Create and upload Teams app package (ZIP)
- [ ] Test bot messaging
- [ ] Test Teams Tab SSO
- [ ] Test Web OAuth2 login
- [ ] Update CORS in backend to allow frontend domain

---

## 🔧 Troubleshooting

### "Application ID URI is not valid"

**Problem**: Resource URL in manifest doesn't match Azure AD

**Solution**: In Azure AD → Expose an API, set:
```
api://grupodc-agent-backend-dev-118078450167.us-east4.run.app/8f932a37-a7f6-4fe8-be5e-a72ab69758cf
```

### Teams SSO fails with "Consent required"

**Problem**: User hasn't consented to permissions

**Solution**:
1. Admin must grant consent in Azure AD
2. Or user must consent on first use
3. Check API permissions are not admin-restricted

### Web OAuth2 redirects but no token

**Problem**: Token in URL fragment not being extracted

**Solution**: Check frontend code:
```javascript
const hash = window.location.hash;
const token = hash.split('token=')[1];
```

### CORS error from frontend

**Problem**: Backend doesn't allow frontend domain

**Solution**: Update `src/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-frontend-app.com",
        "http://localhost:5173"  # For development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Bot not receiving messages

**Problem**: Messaging endpoint not configured in Azure Bot

**Solution**: In Azure Portal → Bot Service → Configuration:
```
Messaging endpoint: https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/bot/messages
```

---

## 📚 Additional Resources

- [Teams Manifest Schema](https://learn.microsoft.com/en-us/microsoftteams/platform/resources/schema/manifest-schema)
- [Teams SSO Documentation](https://learn.microsoft.com/en-us/microsoftteams/platform/tabs/how-to/authentication/tab-sso-overview)
- [Azure AD App Registration](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [Bot Framework Documentation](https://learn.microsoft.com/en-us/azure/bot-service/)

---

## 🆘 Support

For issues or questions:
1. Check backend logs: `gcloud run logs read grupodc-agent-backend-dev --project=your-project-id`
2. Check browser console for frontend errors
3. Verify Azure AD configuration matches this guide
4. Test with cURL using `CURL_TESTING_GUIDE.md`
5. Review React integration in `REACT_INTEGRATION_GUIDE.md`
