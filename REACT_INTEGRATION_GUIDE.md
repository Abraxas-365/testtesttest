# React Integration Guide - JWT Authentication

This guide shows how to integrate the multi-mode authentication system (Teams Bot + Teams SSO + Web OAuth2) into your React frontend.

---

## Table of Contents

1. [Installation](#installation)
2. [Authentication Hook](#authentication-hook)
3. [Login Page Component](#login-page-component)
4. [Auth Callback Handler](#auth-callback-handler)
5. [Protected Routes](#protected-routes)
6. [Chat Component with JWT](#chat-component-with-jwt)
7. [Teams Tab Integration](#teams-tab-integration)
8. [Error Handling](#error-handling)

---

## Installation

```bash
npm install @microsoft/teams-js
```

---

## Authentication Hook

Create `src/hooks/useAuth.js`:

```javascript
import { useState, useEffect, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app';

export function useAuth() {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('auth_token'));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch user info on mount if token exists
  useEffect(() => {
    if (token) {
      fetchUserInfo();
    } else {
      setLoading(false);
    }
  }, [token]);

  const fetchUserInfo = async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
        setError(null);
      } else if (response.status === 401) {
        // Token expired or invalid
        logout();
      } else {
        throw new Error('Failed to fetch user info');
      }
    } catch (err) {
      setError(err.message);
      logout();
    } finally {
      setLoading(false);
    }
  };

  const login = async () => {
    try {
      const redirectUri = `${window.location.origin}/auth/callback`;
      const response = await fetch(`${API_URL}/api/v1/auth/login-url?redirect_uri=${encodeURIComponent(redirectUri)}`);

      if (!response.ok) {
        throw new Error('Failed to get login URL');
      }

      const { login_url, state } = await response.json();

      // Save state for validation in callback
      sessionStorage.setItem('oauth_state', state);

      // Redirect to Microsoft login
      window.location.href = login_url;
    } catch (err) {
      setError(err.message);
    }
  };

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
    setError(null);
  }, []);

  const saveToken = useCallback((newToken) => {
    localStorage.setItem('auth_token', newToken);
    setToken(newToken);
  }, []);

  return {
    user,
    token,
    loading,
    error,
    isAuthenticated: !!user,
    login,
    logout,
    saveToken,
    fetchUserInfo
  };
}
```

---

## Login Page Component

Create `src/pages/LoginPage.jsx`:

```javascript
import { useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

export function LoginPage() {
  const { isAuthenticated, login, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/chat');
    }
  }, [isAuthenticated, navigate]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md max-w-md w-full">
        <h1 className="text-3xl font-bold text-center mb-6">Welcome to GrupoDC Agent</h1>

        <p className="text-gray-600 text-center mb-8">
          Sign in with your Microsoft account to continue
        </p>

        <button
          onClick={login}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition"
        >
          <svg className="w-5 h-5" viewBox="0 0 23 23" fill="none">
            <path d="M0 0h11v11H0z" fill="#f25022"/>
            <path d="M12 0h11v11H12z" fill="#00a4ef"/>
            <path d="M0 12h11v11H0z" fill="#7fba00"/>
            <path d="M12 12h11v11H12z" fill="#ffb900"/>
          </svg>
          Sign in with Microsoft
        </button>

        <p className="text-xs text-gray-500 text-center mt-6">
          By signing in, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
}
```

---

## Auth Callback Handler

Create `src/pages/AuthCallback.jsx`:

```javascript
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export function AuthCallback() {
  const navigate = useNavigate();
  const { saveToken, fetchUserInfo } = useAuth();

  useEffect(() => {
    // Extract token from URL fragment (#token=xxx)
    const hash = window.location.hash;

    if (hash && hash.includes('token=')) {
      // Extract token
      const token = hash.split('token=')[1];

      if (token) {
        // Save token
        saveToken(token);

        // Clear the hash from URL (for security)
        window.history.replaceState(null, '', window.location.pathname);

        // Fetch user info and redirect
        fetchUserInfo().then(() => {
          navigate('/chat', { replace: true });
        });
      } else {
        console.error('No token found in URL fragment');
        navigate('/login', { replace: true });
      }
    } else {
      console.error('Invalid callback URL format');
      navigate('/login', { replace: true });
    }
  }, [navigate, saveToken, fetchUserInfo]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
        <p className="mt-4 text-gray-600">Completing sign in...</p>
      </div>
    </div>
  );
}
```

---

## Protected Routes

Create `src/components/ProtectedRoute.jsx`:

```javascript
import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
```

**Usage in `src/App.jsx`**:

```javascript
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LoginPage } from './pages/LoginPage';
import { AuthCallback } from './pages/AuthCallback';
import { ChatPage } from './pages/ChatPage';
import { ProtectedRoute } from './components/ProtectedRoute';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/auth/success" element={<AuthCallback />} />

        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />

        <Route path="/" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

---

## Chat Component with JWT

Create `src/pages/ChatPage.jsx`:

```javascript
import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

const API_URL = import.meta.env.VITE_API_URL || 'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app';

export function ChatPage() {
  const { user, token, logout } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const sendMessage = async (e) => {
    e.preventDefault();

    if (!input.trim() || loading) return;

    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/tabs/invoke`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          prompt: input,
          agent_name: 'search_assistant',
          mode: 'auto',
          source: 'all'
        })
      });

      if (response.status === 401) {
        // Token expired
        setError('Session expired. Please login again.');
        setTimeout(() => logout(), 2000);
        return;
      }

      if (!response.ok) {
        throw new Error(`Error: ${response.status}`);
      }

      const data = await response.json();

      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString(),
        metadata: data.metadata
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      console.error('Error sending message:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-6xl mx-auto">
          <h1 className="text-xl font-semibold">GrupoDC Agent</h1>

          <div className="flex items-center gap-4">
            <div className="text-sm text-gray-600">
              <span className="font-medium">{user?.name}</span>
              <span className="text-gray-400 ml-2">({user?.email})</span>
            </div>

            <button
              onClick={logout}
              className="text-sm text-red-600 hover:text-red-700 font-medium"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-8">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="text-center text-gray-500 mt-12">
              <p className="text-lg">Start a conversation!</p>
              <p className="text-sm mt-2">Ask me anything about your business.</p>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-2xl rounded-lg px-4 py-3 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-800 border border-gray-200'
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                <p className="text-xs mt-2 opacity-70">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                  <span className="text-gray-600">Thinking...</span>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-red-700">
              <p className="font-medium">Error</p>
              <p className="text-sm">{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="bg-white border-t border-gray-200 px-6 py-4">
        <form onSubmit={sendMessage} className="max-w-4xl mx-auto">
          <div className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              disabled={loading}
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition"
            >
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

---

## Teams Tab Integration

Create `src/pages/TeamsTab.jsx` for Microsoft Teams:

```javascript
import { useEffect, useState } from 'react';
import * as microsoftTeams from '@microsoft/teams-js';
import { ChatPage } from './ChatPage';

const API_URL = import.meta.env.VITE_API_URL || 'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app';

export function TeamsTab() {
  const [teamsToken, setTeamsToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [inTeams, setInTeams] = useState(false);

  useEffect(() => {
    // Initialize Teams SDK
    microsoftTeams.app.initialize().then(() => {
      setInTeams(true);

      // Get Teams SSO token
      microsoftTeams.authentication.getAuthToken()
        .then(token => {
          console.log('Got Teams SSO token');
          setTeamsToken(token);

          // Store token for API calls
          localStorage.setItem('auth_token', token);
          setLoading(false);
        })
        .catch(err => {
          console.error('Failed to get Teams token:', err);
          setError('Failed to authenticate with Teams. Please try again.');
          setLoading(false);
        });
    }).catch(err => {
      // Not in Teams context
      console.log('Not running in Teams context');
      setInTeams(false);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-gray-600">Authenticating with Teams...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <p className="text-red-700 font-medium">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!inTeams) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 max-w-md">
          <p className="text-yellow-700">
            This page should be opened in Microsoft Teams.
          </p>
          <p className="text-sm text-yellow-600 mt-2">
            Please go to <a href="/login" className="underline">login page</a> for web access.
          </p>
        </div>
      </div>
    );
  }

  // Render chat with Teams token
  return <ChatPage />;
}
```

**Update routing in `src/App.jsx`**:

```javascript
import { TeamsTab } from './pages/TeamsTab';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Web routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/auth/success" element={<AuthCallback />} />

        {/* Teams Tab route (uses Teams SSO) */}
        <Route path="/teams" element={<TeamsTab />} />

        {/* Protected web chat */}
        <Route
          path="/chat"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />

        <Route path="/" element={<Navigate to="/chat" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

---

## Error Handling

Create `src/utils/apiClient.js` for centralized API calls:

```javascript
const API_URL = import.meta.env.VITE_API_URL || 'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app';

class APIError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function fetchWithAuth(endpoint, options = {}) {
  const token = localStorage.getItem('auth_token');

  if (!token) {
    throw new APIError('No authentication token', 401, null);
  }

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    ...options.headers
  };

  try {
    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers
    });

    // Handle 401 Unauthorized
    if (response.status === 401) {
      // Clear token and redirect to login
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
      throw new APIError('Session expired', 401, null);
    }

    // Handle other errors
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new APIError(
        errorData?.detail || `Request failed with status ${response.status}`,
        response.status,
        errorData
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }
    throw new APIError(error.message, 0, null);
  }
}

export const api = {
  // Auth endpoints
  getLoginUrl: () => fetch(`${API_URL}/api/v1/auth/login-url`).then(r => r.json()),
  getMe: () => fetchWithAuth('/api/v1/auth/me'),
  logout: () => fetchWithAuth('/api/v1/auth/logout', { method: 'POST' }),

  // Chat endpoints
  sendMessage: (data) => fetchWithAuth('/api/v1/tabs/invoke', {
    method: 'POST',
    body: JSON.stringify(data)
  }),

  getProfile: () => fetchWithAuth('/api/v1/tabs/user/profile'),
  getConfig: () => fetchWithAuth('/api/v1/tabs/config', { method: 'POST' })
};

export { APIError };
```

**Usage example**:

```javascript
import { api, APIError } from '../utils/apiClient';

function MyComponent() {
  const sendMessage = async (prompt) => {
    try {
      const response = await api.sendMessage({
        prompt,
        agent_name: 'search_assistant'
      });
      console.log(response);
    } catch (error) {
      if (error instanceof APIError) {
        if (error.status === 401) {
          console.log('Session expired, redirecting to login...');
        } else {
          console.error(`API Error ${error.status}: ${error.message}`);
        }
      } else {
        console.error('Network error:', error);
      }
    }
  };
}
```

---

## Environment Variables

Create `.env.local`:

```bash
VITE_API_URL=https://grupodc-agent-backend-dev-118078450167.us-east4.run.app
```

For production, update with your actual backend URL.

---

## Complete Example: Simple React App

Here's a minimal working example:

**`src/App.jsx`**:

```javascript
import { useState, useEffect } from 'react';

const API_URL = 'https://grupodc-agent-backend-dev-118078450167.us-east4.run.app';

function App() {
  const [token, setToken] = useState(localStorage.getItem('auth_token'));
  const [user, setUser] = useState(null);
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');

  useEffect(() => {
    // Check for token in URL fragment (after OAuth callback)
    const hash = window.location.hash;
    if (hash && hash.includes('token=')) {
      const newToken = hash.split('token=')[1];
      localStorage.setItem('auth_token', newToken);
      setToken(newToken);
      window.history.replaceState(null, '', window.location.pathname);
    }

    // Fetch user info if token exists
    if (token) {
      fetch(`${API_URL}/api/v1/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(r => r.json())
        .then(setUser)
        .catch(console.error);
    }
  }, [token]);

  const login = async () => {
    const redirectUri = `${window.location.origin}/auth/success`;
    const res = await fetch(`${API_URL}/api/v1/auth/login-url?redirect_uri=${redirectUri}`);
    const { login_url } = await res.json();
    window.location.href = login_url;
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
  };

  const sendMessage = async () => {
    const res = await fetch(`${API_URL}/api/v1/tabs/invoke`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        prompt: message,
        agent_name: 'search_assistant'
      })
    });
    const data = await res.json();
    setResponse(data.response);
  };

  if (!token) {
    return (
      <div style={{ padding: '50px', textAlign: 'center' }}>
        <h1>GrupoDC Agent</h1>
        <button onClick={login}>Login with Microsoft</button>
      </div>
    );
  }

  return (
    <div style={{ padding: '20px' }}>
      <div style={{ marginBottom: '20px' }}>
        <strong>Logged in as:</strong> {user?.name} ({user?.email})
        <button onClick={logout} style={{ marginLeft: '20px' }}>Logout</button>
      </div>

      <div>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask me anything..."
          style={{ width: '300px', padding: '8px' }}
        />
        <button onClick={sendMessage} style={{ marginLeft: '10px', padding: '8px' }}>
          Send
        </button>
      </div>

      {response && (
        <div style={{ marginTop: '20px', padding: '15px', background: '#f0f0f0', borderRadius: '8px' }}>
          <strong>Response:</strong>
          <p>{response}</p>
        </div>
      )}
    </div>
  );
}

export default App;
```

---

## Testing

1. **Start your React app**:
   ```bash
   npm run dev
   ```

2. **Test login flow**:
   - Click "Login with Microsoft"
   - Complete Microsoft authentication
   - You should be redirected back with a JWT token
   - Token is automatically saved to localStorage

3. **Test authenticated requests**:
   - Send a message in the chat
   - Check browser DevTools → Network tab
   - Verify Authorization header is present

4. **Test token expiration**:
   - Wait 24 hours or manually delete token
   - Try to send a message
   - Should be redirected to login

---

## Tips

1. **Store token securely**: localStorage is fine for JWTs. Don't use cookies for cross-domain.

2. **Handle token refresh**: Current implementation doesn't support refresh tokens. Users must re-login after 24 hours.

3. **CORS**: Make sure your backend CORS settings allow your frontend domain.

4. **Teams context detection**: Use `@microsoft/teams-js` to detect if running in Teams and handle auth accordingly.

5. **Error boundaries**: Wrap your app in React Error Boundaries to catch auth errors gracefully.

---

## Troubleshooting

### Token not found in callback
- Check that redirect URI matches exactly (including trailing slash)
- Check browser console for errors
- Verify Azure AD app registration redirect URIs

### 401 Unauthorized errors
- Check token is being sent in Authorization header
- Verify token hasn't expired (decode JWT to check `exp` claim)
- Check backend logs for validation errors

### CORS errors
- Verify backend `FRONTEND_URL` environment variable
- Check `allow_origins` in FastAPI CORS middleware
- Ensure credentials are included in fetch requests

---

## Security Best Practices

1. **Never commit tokens**: Add `.env.local` to `.gitignore`
2. **Use HTTPS**: Always use HTTPS in production
3. **Validate tokens**: Backend validates all tokens on every request
4. **Clear tokens on logout**: Remove from localStorage completely
5. **Handle token expiration**: Implement proper error handling for expired tokens
6. **Use Content Security Policy**: Add CSP headers to prevent XSS
