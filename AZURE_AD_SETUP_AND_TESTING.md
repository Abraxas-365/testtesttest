# Azure AD Setup & Frontend Testing Guide

## Your Backend URL
```
https://grupodc-agent-backend-dev-118078450167.us-east4.run.app
```

---

## 📋 Part 1: Azure AD App Registration Configuration

### Step 1: Go to Azure Portal
1. Navigate to [Azure Portal](https://portal.azure.com)
2. Go to **Azure Active Directory** (or Microsoft Entra ID)
3. Click **App registrations** in the left menu
4. Find your app: **Client ID: `8f932a37-a7f6-4fe8-be5e-a72ab69758cf`**

### Step 2: Configure Redirect URIs

Go to **Authentication** → **Platform configurations** → **Add a platform** (if needed)

#### Add Web Platform Redirect URIs:
```
https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
http://localhost:8080/api/v1/auth/callback
```

#### Add Single-page application (SPA) Redirect URIs (for Teams Tab):
```
https://your-frontend-url.com/auth-end.html
http://localhost:5173/auth-end.html
http://localhost:3000/auth-end.html
```

**Important**:
- The `/api/v1/auth/callback` is a **Web** platform redirect (NOT SPA)
- The `/auth-end.html` is for **Teams Tab SSO** (can be SPA or Web)

### Step 3: Configure Implicit Grant (if needed for Teams)
Under **Authentication** → **Implicit grant and hybrid flows**:
- ☑️ Check **ID tokens** (used for implicit flow)
- ☑️ Check **Access tokens** (if needed)

### Step 4: API Permissions
Go to **API permissions** → Ensure these are granted:

**Microsoft Graph API**:
- `openid` (Delegated)
- `profile` (Delegated)
- `email` (Delegated)
- `User.Read` (Delegated)

Click **Grant admin consent for [Your Organization]** if you have admin rights.

### Step 5: Get Your Credentials

**From Overview page, note down**:
- **Application (client) ID**: `8f932a37-a7f6-4fe8-be5e-a72ab69758cf`
- **Directory (tenant) ID**: `<your-tenant-id>` (copy this!)

**Create Client Secret** (if you haven't):
1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Add description: "Backend OAuth2"
4. Expires: 24 months (or custom)
5. Click **Add**
6. **COPY THE SECRET VALUE IMMEDIATELY** (you can't see it again!)

### Step 6: Configure Supported Account Types
Under **Authentication** → **Supported account types**:
- Select based on your needs:
  - **Single tenant**: Only your organization
  - **Multitenant**: Any Azure AD organization
  - **Multitenant + Personal**: Any Azure AD + Microsoft accounts

---

## ⚙️ Part 2: Update Backend Environment Variables

Add these to your Cloud Run service:

```bash
# Azure AD Configuration
AZURE_TENANT_ID=<your-tenant-id-from-step-5>
AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
AZURE_CLIENT_SECRET=<your-client-secret-from-step-5>

# OAuth2 Callback Configuration
AZURE_REDIRECT_URI=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback

# Frontend URL (update when you deploy frontend)
FRONTEND_URL=http://localhost:5173
```

**To set in Cloud Run**:
```bash
gcloud run services update grupodc-agent-backend-dev \
  --region=us-east4 \
  --update-env-vars="AZURE_TENANT_ID=<your-tenant-id>,AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf,AZURE_CLIENT_SECRET=<your-secret>,AZURE_REDIRECT_URI=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback,FRONTEND_URL=http://localhost:5173"
```

**Or via Cloud Console**:
1. Go to Cloud Run → Your service
2. Click **EDIT & DEPLOY NEW REVISION**
3. Go to **Variables & Secrets** tab
4. Add each variable above
5. Click **DEPLOY**

---

## 🧪 Part 3: Testing with cURL

### Test 1: Health Check
```bash
curl -X GET "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/health"
```

**Expected Response**:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "mode": "multi (bot + tabs + web)",
  "authentication": {
    "teams_bot": true,
    "teams_sso": true,
    "web_oauth2": true
  },
  "endpoints": {
    "auth_login": "/api/v1/auth/login-url",
    "auth_callback": "/api/v1/auth/callback",
    "auth_me": "/api/v1/auth/me"
  }
}
```

---

### Test 2: Get OAuth2 Login URL

```bash
curl -X GET "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/login-url?redirect_uri=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback"
```

**Expected Response**:
```json
{
  "login_url": "https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/authorize?client_id=8f932a37...",
  "state": "random-csrf-token"
}
```

**What to do**: Copy the `login_url` and open it in a browser to test the login flow.

---

### Test 3: Check Authentication Status (Unauthenticated)

```bash
curl -X GET "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/status"
```

**Expected Response**:
```json
{
  "authenticated": false,
  "user": null
}
```

---

### Test 4: Full OAuth2 Login Flow (Browser-based)

**Step-by-step**:

1. **Get login URL**:
```bash
curl -X GET "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/login-url?redirect_uri=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback" | jq -r '.login_url'
```

2. **Open the URL in your browser** (copy from response)

3. **Login with Microsoft account** (must be in your Azure AD tenant)

4. **After successful login**, you'll be redirected to:
```
http://localhost:5173/auth/success
```
(and a `session_id` cookie will be set)

5. **Test authenticated endpoint** (in browser's console):
```javascript
fetch('https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/me', {
  credentials: 'include'
}).then(r => r.json()).then(console.log)
```

**Expected Response**:
```json
{
  "user_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "name": "Your Name",
  "email": "your.email@domain.com",
  "tenant_id": "your-tenant-id",
  "authenticated": true
}
```

---

### Test 5: Send Message (Teams SSO Token)

**If you have a Teams SSO token** (from Teams SDK):

```bash
curl -X POST "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/tabs/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TEAMS_SSO_TOKEN_HERE" \
  -d '{
    "prompt": "Hello, test message",
    "agent_name": "search_assistant",
    "session_id": "test-session-123"
  }'
```

**Expected Response**:
```json
{
  "response": "Agent response here...",
  "agent_name": "search_assistant",
  "agent_area": "general",
  "session_id": "test-session-123",
  "metadata": {
    "user_id": "xxx",
    "user_name": "Your Name",
    "user_email": "your.email@domain.com"
  }
}
```

---

### Test 6: Send Message (Web Session Cookie)

**After completing OAuth2 login flow** (with session cookie):

```bash
curl -X POST "https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/tabs/invoke" \
  -H "Content-Type: application/json" \
  -H "Cookie: session_id=YOUR_SESSION_ID_FROM_BROWSER" \
  -d '{
    "prompt": "Hello from web app",
    "agent_name": "search_assistant"
  }'
```

**To get your session_id**:
1. Open browser DevTools (F12)
2. Go to Application tab → Cookies
3. Find `session_id` cookie
4. Copy the value

---

## 🖥️ Part 4: Frontend Integration Code

### For Web Application (React/Vue/etc.)

#### 1. Login Flow
```javascript
// Get login URL from backend
async function loginWithMicrosoft() {
  const response = await fetch(
    'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/login-url' +
    '?redirect_uri=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback'
  );
  const { login_url } = await response.json();

  // Redirect to Microsoft login
  window.location.href = login_url;
}
```

#### 2. Check Auth Status
```javascript
async function checkAuthStatus() {
  const response = await fetch(
    'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/status',
    {
      credentials: 'include' // Important: send cookies
    }
  );
  const data = await response.json();

  if (data.authenticated) {
    console.log('User:', data.user);
    return data.user;
  } else {
    console.log('Not authenticated');
    return null;
  }
}
```

#### 3. Get Current User
```javascript
async function getCurrentUser() {
  const response = await fetch(
    'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/me',
    {
      credentials: 'include'
    }
  );

  if (response.ok) {
    return await response.json();
  } else {
    throw new Error('Not authenticated');
  }
}
```

#### 4. Send Message to Agent
```javascript
async function sendMessage(prompt, agentName = 'search_assistant') {
  const response = await fetch(
    'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/tabs/invoke',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include', // Send session cookie
      body: JSON.stringify({
        prompt: prompt,
        agent_name: agentName,
        mode: 'auto',
        source: 'all'
      })
    }
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }

  return await response.json();
}

// Usage:
const result = await sendMessage('What is the weather?');
console.log('Agent response:', result.response);
```

#### 5. Logout
```javascript
async function logout() {
  await fetch(
    'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/logout',
    {
      method: 'POST',
      credentials: 'include'
    }
  );

  // Redirect to home or login page
  window.location.href = '/';
}
```

---

### For Teams Tab (with Teams SDK)

#### 1. Initialize Teams SDK
```javascript
import * as microsoftTeams from "@microsoft/teams-js";

// Initialize Teams SDK
microsoftTeams.app.initialize().then(() => {
  console.log('Teams SDK initialized');
});
```

#### 2. Get SSO Token
```javascript
async function getTeamsToken() {
  try {
    const token = await microsoftTeams.authentication.getAuthToken();
    return token;
  } catch (error) {
    console.error('Failed to get Teams SSO token:', error);
    // Fall back to popup authentication
    return await getTokenViaPopup();
  }
}

async function getTokenViaPopup() {
  return new Promise((resolve, reject) => {
    microsoftTeams.authentication.authenticate({
      url: window.location.origin + '/auth-start.html',
      width: 600,
      height: 535,
      successCallback: (result) => resolve(result),
      failureCallback: (reason) => reject(reason)
    });
  });
}
```

#### 3. Send Message with SSO Token
```javascript
async function sendMessageFromTeams(prompt) {
  const token = await getTeamsToken();

  const response = await fetch(
    'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/tabs/invoke',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}` // SSO token
      },
      body: JSON.stringify({
        prompt: prompt,
        agent_name: 'search_assistant'
      })
    }
  );

  return await response.json();
}
```

---

## 🔧 Part 5: CORS Update Required

**IMPORTANT**: You need to add your frontend domain to CORS!

### Update `src/main.py` Line 78

Add your frontend URL to the `allow_origins` list:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Teams domains
        "https://teams.microsoft.com",
        "https://*.teams.microsoft.com",
        "https://*.teams.office.com",
        "https://outlook.office.com",
        "https://*.outlook.office.com",
        # Local development
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        # ADD YOUR FRONTEND URL HERE:
        "https://your-frontend-bucket-url.storage.googleapis.com",  # If using bucket direct URL
        "https://app.your-domain.com",  # If using custom domain
        # For development (remove in production)
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**After updating, commit and redeploy**:
```bash
git add src/main.py
git commit -m "Add frontend URL to CORS"
git push
# Redeploy to Cloud Run
```

---

## 📊 Part 6: Testing Checklist

- [ ] Health check returns 200 OK
- [ ] `/auth/login-url` returns valid Microsoft login URL
- [ ] Can open login URL in browser and login with Microsoft account
- [ ] After login, redirected to `http://localhost:5173/auth/success`
- [ ] Session cookie is set (check in DevTools)
- [ ] `/auth/me` returns user info with session cookie
- [ ] `/auth/status` shows `authenticated: true`
- [ ] Can send message via `/tabs/invoke` with session cookie
- [ ] Can logout via `/auth/logout`
- [ ] CORS allows requests from frontend domain

---

## 🚨 Common Issues & Solutions

### Issue: "AZURE_TENANT_ID or AZURE_CLIENT_ID not set"
**Solution**: Environment variables not set in Cloud Run. Set them via console or gcloud CLI.

### Issue: "Invalid token audience"
**Solution**: The `AZURE_CLIENT_ID` in your environment doesn't match your Azure AD app.

### Issue: "CORS error" from frontend
**Solution**: Add your frontend URL to `allow_origins` in `src/main.py:78` and redeploy.

### Issue: "Redirect URI mismatch"
**Solution**: The `redirect_uri` parameter must EXACTLY match what's configured in Azure AD App Registration.

### Issue: OAuth callback redirects but no session cookie
**Solution**:
1. Check that cookies are enabled in browser
2. Verify `FRONTEND_URL` is set correctly in Cloud Run
3. Check browser console for cookie errors

### Issue: "Token validation failed"
**Solution**:
1. Token might be expired (get new one)
2. Wrong audience or issuer configuration
3. Check `AZURE_TENANT_ID` is correct

---

## 📝 Quick Reference

**Backend URL**:
```
https://grupodc-agent-backend-dev-118078450167.us-east4.run.app
```

**Key Endpoints**:
```
GET  /health
GET  /api/v1/auth/login-url?redirect_uri=<uri>
GET  /api/v1/auth/callback?code=<code>&state=<state>
POST /api/v1/auth/logout
GET  /api/v1/auth/me
GET  /api/v1/auth/status
POST /api/v1/tabs/invoke
GET  /api/v1/tabs/health
```

**Required Azure AD Redirect URIs**:
```
https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
http://localhost:8080/api/v1/auth/callback
<your-frontend-url>/auth-end.html
```

**Required Cloud Run Environment Variables**:
```
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
AZURE_CLIENT_SECRET=<your-secret>
AZURE_REDIRECT_URI=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback
FRONTEND_URL=http://localhost:5173
```
