# cURL Testing Guide - JWT Authentication

## Base URL
```bash
export API_URL="https://grupodc-agent-backend-dev-118078450167.us-east4.run.app"
```

---

## 1. Health Check (No Auth Required)

```bash
curl -X GET "$API_URL/health"
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
  }
}
```

---

## 2. Get OAuth2 Login URL

```bash
curl -X GET "$API_URL/api/v1/auth/login-url?redirect_uri=$API_URL/api/v1/auth/callback"
```

**Expected Response**:
```json
{
  "login_url": "https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/authorize?...",
  "state": "random-state-token"
}
```

**What to do**: Copy the `login_url` and open it in a browser. After login, you'll be redirected to:
```
http://localhost:5173/auth/success#token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Extract the token from the URL fragment.

---

## 3. Check Auth Status (No Auth)

```bash
curl -X GET "$API_URL/api/v1/auth/status"
```

**Expected Response (Not authenticated)**:
```json
{
  "authenticated": false,
  "user": null
}
```

---

## 4. Get Current User Info (With JWT Token)

```bash
# Set your JWT token
export JWT_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X GET "$API_URL/api/v1/auth/me" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Expected Response**:
```json
{
  "user_id": "12345678-1234-1234-1234-123456789012",
  "name": "John Doe",
  "email": "john.doe@example.com",
  "tenant_id": "tenant-id-here",
  "authenticated": true
}
```

---

## 5. Send Message to Agent (With JWT Token)

```bash
export JWT_TOKEN="your-jwt-token-here"

curl -X POST "$API_URL/api/v1/tabs/invoke" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is artificial intelligence?",
    "agent_name": "search_assistant",
    "mode": "auto",
    "source": "all"
  }'
```

**Expected Response**:
```json
{
  "response": "Artificial intelligence (AI) is...",
  "agent_name": "search_assistant",
  "agent_area": "general",
  "session_id": "tab-12345678-1234-1234-1234-123456789012",
  "metadata": {
    "user_id": "12345678-1234-1234-1234-123456789012",
    "user_name": "John Doe",
    "user_email": "john.doe@example.com",
    "mode": "auto",
    "source": "all"
  }
}
```

---

## 6. Get User Profile (With JWT Token)

```bash
curl -X GET "$API_URL/api/v1/tabs/user/profile" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Expected Response**:
```json
{
  "user_id": "12345678-1234-1234-1234-123456789012",
  "name": "John Doe",
  "email": "john.doe@example.com",
  "tenant_id": "tenant-id",
  "authenticated": true
}
```

---

## 7. Get Tab Config (With JWT Token)

```bash
curl -X POST "$API_URL/api/v1/tabs/config" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "user": {
    "user_id": "12345678-1234-1234-1234-123456789012",
    "name": "John Doe",
    "email": "john.doe@example.com",
    "tenant_id": "tenant-id"
  },
  "available_agents": [
    "search_assistant",
    "general_assistant"
  ],
  "features": {
    "file_upload": false,
    "voice_input": false,
    "history": true
  }
}
```

---

## 8. Logout

```bash
curl -X POST "$API_URL/api/v1/auth/logout"
```

**Expected Response**:
```json
{
  "message": "Logged out successfully",
  "note": "Please delete the JWT token from client storage"
}
```

**Note**: With JWT, logout is client-side. Just delete the token from localStorage.

---

## 9. Test with Invalid/Expired Token

```bash
curl -X GET "$API_URL/api/v1/auth/me" \
  -H "Authorization: Bearer invalid-token-here"
```

**Expected Response** (401 Unauthorized):
```json
{
  "detail": "Invalid token: ..."
}
```

---

## 10. Test Teams SSO Token (If you have one)

```bash
# Get Teams SSO token from Teams SDK
export TEAMS_TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIs..."

curl -X POST "$API_URL/api/v1/tabs/invoke" \
  -H "Authorization: Bearer $TEAMS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello from Teams",
    "agent_name": "search_assistant"
  }'
```

---

## Complete Test Flow

```bash
#!/bin/bash
# complete-test.sh

API_URL="https://grupodc-agent-backend-dev-118078450167.us-east4.run.app"

echo "=== 1. Health Check ==="
curl -s "$API_URL/health" | jq

echo -e "\n=== 2. Get Login URL ==="
LOGIN_RESPONSE=$(curl -s "$API_URL/api/v1/auth/login-url?redirect_uri=$API_URL/api/v1/auth/callback")
echo $LOGIN_RESPONSE | jq

LOGIN_URL=$(echo $LOGIN_RESPONSE | jq -r '.login_url')
echo -e "\n📌 Open this URL in browser to login:"
echo "$LOGIN_URL"

echo -e "\n⏸️  After login, copy the token from the URL fragment (#token=xxx)"
echo "Then run:"
echo "export JWT_TOKEN='your-token-here'"

# If you already have a token:
if [ ! -z "$JWT_TOKEN" ]; then
  echo -e "\n=== 3. Get User Info ==="
  curl -s "$API_URL/api/v1/auth/me" \
    -H "Authorization: Bearer $JWT_TOKEN" | jq

  echo -e "\n=== 4. Send Message ==="
  curl -s -X POST "$API_URL/api/v1/tabs/invoke" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "prompt": "What is the weather today?",
      "agent_name": "search_assistant"
    }' | jq
fi
```

---

## Error Responses

### 401 Unauthorized (Invalid/Expired Token)
```json
{
  "detail": "Token expired"
}
```

### 401 Unauthorized (No Token)
```json
{
  "detail": "Authentication required. Please provide a valid JWT token in Authorization header."
}
```

### 500 Internal Server Error
```json
{
  "detail": "Error processing message: ..."
}
```

---

## Tips

1. **Extract token from browser**:
   - Open DevTools (F12)
   - Go to Console
   - After login redirect, run:
     ```javascript
     window.location.hash.split('token=')[1]
     ```

2. **Decode JWT to see contents** (for debugging):
   ```bash
   echo "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." | cut -d. -f2 | base64 -d | jq
   ```

3. **Check token expiration**:
   ```bash
   # Decode payload
   PAYLOAD=$(echo "$JWT_TOKEN" | cut -d. -f2)
   # Add padding if needed
   PAYLOAD=$(echo "$PAYLOAD" | sed 's/-/+/g; s/_/\//g')
   # Decode and check exp
   echo "$PAYLOAD" | base64 -d 2>/dev/null | jq .exp
   ```

4. **Token lifetime**: 24 hours (86400 seconds)
