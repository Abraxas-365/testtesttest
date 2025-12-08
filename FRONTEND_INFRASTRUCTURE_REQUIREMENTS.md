# Frontend Infrastructure Requirements - GCP Deployment

## Overview
Deploy React frontend to GCP with Cloud Storage bucket, Load Balancer, and Cloud CDN for multi-mode authentication (Teams Tabs + Web OAuth2).

---

## 🏗️ GCP Services Required

### 1. Cloud Storage Bucket
- **Purpose**: Host static React build files
- **Configuration**:
  - Bucket name: `your-frontend-app` (or custom name)
  - Location: Multi-region (e.g., `US` or `EU`)
  - Storage class: Standard
  - Public access: **Enabled** (for web hosting)
  - Uniform bucket-level access: Enabled
  - Default storage class: Standard

### 2. Cloud Load Balancer (HTTPS)
- **Type**: External HTTP(S) Load Balancer
- **Purpose**: Serve frontend with SSL/TLS termination
- **Configuration**:
  - Protocol: HTTPS (port 443)
  - HTTP to HTTPS redirect: **Required**
  - Backend: Cloud Storage bucket
  - Frontend: Static IP address
  - SSL certificate: Google-managed or custom

### 3. Cloud CDN
- **Purpose**: Cache static assets globally
- **Configuration**:
  - Enable Cloud CDN on load balancer backend
  - Cache mode: `CACHE_ALL_STATIC` or `USE_ORIGIN_HEADERS`
  - Default TTL: 3600 seconds (1 hour)
  - Max TTL: 86400 seconds (24 hours)
  - Negative caching: Enabled
  - Cache invalidation: Enable for deployments

### 4. Cloud DNS (Optional but Recommended)
- **Purpose**: Custom domain management
- **Configuration**:
  - Create A record pointing to load balancer static IP
  - Example: `app.your-domain.com` → `34.98.76.54`

---

## 🌐 Domain & SSL Requirements

### Custom Domain (Recommended)
- **Frontend domain**: `https://app.your-domain.com` (or subdomain of your choice)
- **Backend domain**: `https://api.your-domain.com` (your Cloud Run service)

### SSL/TLS Certificate
- **Option 1 - Google-managed certificate** (Recommended):
  - Automatically provisioned and renewed
  - Requires domain ownership verification
  - Takes 15-60 minutes to provision

- **Option 2 - Custom certificate**:
  - Upload your own SSL certificate
  - You manage renewal

### DNS Configuration
```
Type    Name                    Value                       TTL
A       app.your-domain.com     <LOAD_BALANCER_IP>         300
A       api.your-domain.com     <CLOUD_RUN_IP>             300
```

---

## 🔐 CORS & Security Configuration

### Backend CORS (Already Configured in `src/main.py`)
The backend already allows these origins:
```python
allow_origins=[
    "https://teams.microsoft.com",
    "https://*.teams.microsoft.com",
    "https://*.teams.office.com",
    "https://outlook.office.com",
    "http://localhost:5173",
    "http://localhost:3000",
    # ADD YOUR FRONTEND DOMAIN HERE:
    # "https://app.your-domain.com",
]
```

**ACTION REQUIRED**: Add your frontend domain to CORS `allow_origins` in `src/main.py:78`

### Cloud Storage Bucket CORS
Configure CORS on the storage bucket:
```json
[
  {
    "origin": ["https://app.your-domain.com", "https://teams.microsoft.com"],
    "method": ["GET", "HEAD", "OPTIONS"],
    "responseHeader": ["Content-Type", "Authorization"],
    "maxAgeSeconds": 3600
  }
]
```

Apply with:
```bash
gsutil cors set cors-config.json gs://your-frontend-app
```

### Security Headers (Load Balancer)
Add these headers via Cloud Armor or backend bucket config:
```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self' https://app.your-domain.com https://login.microsoftonline.com
```

---

## ⚙️ Environment Variables for Frontend Build

The frontend React app needs these environment variables **at build time**:

### For Teams Tab Mode
```bash
# Backend API endpoint
VITE_API_URL=https://api.your-domain.com/api/v1
# or REACT_APP_API_URL if using Create React App

# Azure AD Client ID (same as backend)
VITE_AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf

# Azure Tenant ID
VITE_AZURE_TENANT_ID=your-tenant-id-guid
```

### For Web OAuth2 Mode
```bash
# Frontend URL (for redirects)
VITE_FRONTEND_URL=https://app.your-domain.com

# OAuth2 redirect URI (backend callback endpoint)
VITE_OAUTH_CALLBACK_URL=https://api.your-domain.com/api/v1/auth/callback
```

### Build Commands
```bash
# For Vite (recommended)
npm run build

# For Create React App
npm run build

# Output directory: dist/ or build/
```

---

## 🔑 Azure AD App Registration Configuration

### Required Redirect URIs
Add these redirect URIs to your Azure AD App Registration:

1. **Backend OAuth2 Callback** (for web login):
   ```
   https://api.your-domain.com/api/v1/auth/callback
   ```

2. **Teams Tab SSO** (for Teams authentication):
   ```
   https://app.your-domain.com/auth-end.html
   ```

3. **Local Development**:
   ```
   http://localhost:5173/auth-end.html
   http://localhost:8080/api/v1/auth/callback
   ```

### API Permissions
Ensure these permissions are granted:
- `openid` (delegated)
- `profile` (delegated)
- `email` (delegated)
- `User.Read` (delegated)

---

## 🚀 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Internet                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                 ┌─────────┴─────────┐
                 │   Cloud DNS       │
                 │  (your domain)    │
                 └─────────┬─────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼──────┐   ┌────▼─────┐   ┌─────▼──────┐
    │  Frontend  │   │ Backend  │   │   Teams    │
    │    LB      │   │Cloud Run │   │  microsoft │
    └─────┬──────┘   └──────────┘   └────────────┘
          │
    ┌─────▼──────┐
    │ Cloud CDN  │
    └─────┬──────┘
          │
    ┌─────▼──────┐
    │   Bucket   │
    │ (Frontend) │
    └────────────┘
```

---

## 📋 Step-by-Step Deployment Checklist

### Phase 1: Infrastructure Setup
- [ ] Create Cloud Storage bucket
- [ ] Configure bucket for web hosting (index.html, 404.html)
- [ ] Set bucket permissions (allUsers: Storage Object Viewer)
- [ ] Reserve static external IP address
- [ ] Create Cloud Load Balancer with HTTPS
- [ ] Configure backend bucket in load balancer
- [ ] Enable Cloud CDN on backend service
- [ ] Set up Cloud DNS (if using custom domain)

### Phase 2: SSL Certificate
- [ ] Create Google-managed SSL certificate for frontend domain
- [ ] Add certificate to HTTPS load balancer
- [ ] Wait for certificate provisioning (15-60 min)
- [ ] Verify HTTPS access works

### Phase 3: Backend Configuration
- [ ] Add frontend domain to backend CORS (`src/main.py:78`)
- [ ] Set Cloud Run environment variables:
  - `AZURE_REDIRECT_URI=https://api.your-domain.com/api/v1/auth/callback`
  - `FRONTEND_URL=https://app.your-domain.com`
- [ ] Deploy updated backend to Cloud Run
- [ ] Map custom domain to Cloud Run (api.your-domain.com)

### Phase 4: Azure AD Configuration
- [ ] Add redirect URIs to Azure AD App Registration
- [ ] Add `https://api.your-domain.com/api/v1/auth/callback`
- [ ] Add `https://app.your-domain.com/auth-end.html`
- [ ] Verify API permissions are granted

### Phase 5: Frontend Build & Deploy
- [ ] Set frontend environment variables (see above)
- [ ] Build React app (`npm run build`)
- [ ] Upload build files to Cloud Storage bucket
  ```bash
  gsutil -m rsync -r -d ./dist gs://your-frontend-app
  ```
- [ ] Set cache-control headers
  ```bash
  # Static assets (1 year cache)
  gsutil -m setmeta -h "Cache-Control:public, max-age=31536000, immutable" \
    gs://your-frontend-app/assets/**

  # HTML files (no cache)
  gsutil -m setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" \
    gs://your-frontend-app/*.html
  ```

### Phase 6: Testing
- [ ] Test frontend loads: `https://app.your-domain.com`
- [ ] Test Teams Tab with SSO token authentication
- [ ] Test web OAuth2 login flow:
  1. Visit app → Click Login
  2. Redirect to Microsoft
  3. Login with Microsoft account
  4. Redirect back to app with session
  5. Make authenticated API calls
- [ ] Test CORS with backend API calls
- [ ] Test CDN caching (check response headers)
- [ ] Test on different devices/browsers

---

## 🛠️ GCP Commands Reference

### Create Bucket
```bash
gsutil mb -l US -c STANDARD gs://your-frontend-app
```

### Configure Bucket for Web Hosting
```bash
gsutil web set -m index.html -e 404.html gs://your-frontend-app
```

### Make Bucket Public
```bash
gsutil iam ch allUsers:objectViewer gs://your-frontend-app
```

### Upload Frontend Build
```bash
# Upload all files
gsutil -m rsync -r -d ./dist gs://your-frontend-app

# Set cache headers
gsutil -m setmeta -h "Cache-Control:public, max-age=31536000" "gs://your-frontend-app/assets/**"
gsutil -m setmeta -h "Cache-Control:no-cache" "gs://your-frontend-app/*.html"
```

### Invalidate CDN Cache (after deployment)
```bash
gcloud compute url-maps invalidate-cdn-cache LOAD_BALANCER_NAME \
  --path "/*" \
  --async
```

### Reserve Static IP
```bash
gcloud compute addresses create frontend-ip --global
gcloud compute addresses describe frontend-ip --global
```

---

## 📊 Monitoring & Logging

### Cloud Monitoring
- Monitor load balancer request count, latency, errors
- Set up alerting for 5xx errors
- Monitor CDN cache hit ratio (aim for >80%)

### Cloud Logging
- Enable request logs on load balancer
- Filter logs by status code, URL path
- Monitor CORS errors

### Recommended Alerts
1. **High 5xx Error Rate**: >1% of requests
2. **Low CDN Hit Ratio**: <70%
3. **SSL Certificate Expiry**: 30 days before expiration
4. **High Latency**: P95 latency >2 seconds

---

## 💰 Cost Estimation

### Monthly Costs (approximate)
- **Cloud Storage**: $0.02/GB stored + $0.12/GB data transfer
- **Cloud Load Balancer**: $18/month base + $0.008/GB processed
- **Cloud CDN**: $0.02-0.08/GB (varies by region)
- **Cloud DNS**: $0.20/zone + $0.40/million queries

**Example for 10GB storage, 100GB/month traffic**:
- Storage: $0.20
- Load Balancer: $18 + $0.80 = $18.80
- CDN: $2-8
- DNS: $0.20
- **Total: ~$21-27/month**

---

## 🔒 Security Best Practices

1. **Enable HTTPS only**: Redirect HTTP → HTTPS
2. **Use Google-managed certificates**: Auto-renewal
3. **Enable Cloud Armor**: DDoS protection (optional, extra cost)
4. **Restrict bucket access**: Only load balancer should access bucket
5. **Set security headers**: CSP, X-Frame-Options, etc.
6. **Enable Cloud CDN**: Reduces origin load
7. **Monitor access logs**: Detect anomalies
8. **Use least privilege IAM**: Separate dev/prod permissions

---

## 📞 Support Information

### Backend API Health Check
```
GET https://api.your-domain.com/health

Response:
{
  "status": "healthy",
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

### Required Environment Variables Summary

**Backend (Cloud Run)**:
```bash
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
AZURE_CLIENT_SECRET=your-client-secret
AZURE_REDIRECT_URI=https://api.your-domain.com/api/v1/auth/callback
FRONTEND_URL=https://app.your-domain.com
```

**Frontend (Build-time)**:
```bash
VITE_API_URL=https://api.your-domain.com/api/v1
VITE_AZURE_CLIENT_ID=8f932a37-a7f6-4fe8-be5e-a72ab69758cf
VITE_AZURE_TENANT_ID=your-tenant-id
VITE_FRONTEND_URL=https://app.your-domain.com
```

---

## 🚨 Common Issues & Troubleshooting

### Issue: CORS Errors
**Solution**: Verify frontend domain is in backend `allow_origins` list

### Issue: OAuth2 Redirect Loop
**Solution**: Check `AZURE_REDIRECT_URI` matches Azure AD App Registration exactly

### Issue: CDN Serving Stale Files
**Solution**: Invalidate CDN cache after deployment

### Issue: SSL Certificate Provisioning Failed
**Solution**: Verify domain ownership, check DNS propagation (can take 24-48h)

### Issue: 403 Forbidden on Bucket
**Solution**: Verify bucket is public: `gsutil iam ch allUsers:objectViewer gs://bucket`

---

## ✅ Final Verification

After deployment, verify:
1. [ ] Frontend loads over HTTPS
2. [ ] Backend API calls work from frontend
3. [ ] OAuth2 login flow completes successfully
4. [ ] Teams Tab authentication works (if applicable)
5. [ ] CDN cache headers are correct
6. [ ] SSL certificate is valid and trusted
7. [ ] CORS allows backend communication
8. [ ] No console errors in browser
9. [ ] Analytics/monitoring is working
10. [ ] DNS propagation is complete

---

## 📄 Additional Notes

- **SPA Routing**: Configure load balancer to serve `index.html` for all routes (404 → index.html)
- **Environment-specific builds**: Use different configs for dev/staging/prod
- **CI/CD**: Consider Cloud Build for automated deployments
- **Rollback strategy**: Keep previous build in separate bucket for quick rollback

---

**Document Version**: 1.0
**Last Updated**: 2025-11-28
**Contact**: Backend Team
