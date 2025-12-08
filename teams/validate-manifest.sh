#!/bin/bash
# ============================================================================
# Teams Manifest Validation Script
# ============================================================================
# Validates the Teams manifest configuration and checks Azure AD setup

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Teams Manifest Validation${NC}"
echo ""

# Change to script directory
cd "$(dirname "$0")"

# Check if manifest exists
if [ ! -f "manifest.json" ]; then
  echo -e "${RED}❌ manifest.json not found${NC}"
  exit 1
fi

# Validate JSON syntax
echo "1. Validating JSON syntax..."
if jq empty manifest.json 2>/dev/null; then
  echo -e "${GREEN}   ✅ Valid JSON${NC}"
else
  echo -e "${RED}   ❌ Invalid JSON syntax${NC}"
  exit 1
fi
echo ""

# Extract values
APP_ID=$(jq -r '.id' manifest.json)
BOT_ID=$(jq -r '.bots[0].botId' manifest.json)
WEB_APP_ID=$(jq -r '.webApplicationInfo.id' manifest.json)
WEB_APP_RESOURCE=$(jq -r '.webApplicationInfo.resource' manifest.json)
APP_NAME=$(jq -r '.name.short' manifest.json)
APP_VERSION=$(jq -r '.version' manifest.json)

echo "2. Checking App IDs consistency..."
ISSUES=0

if [ "$APP_ID" != "$BOT_ID" ]; then
  echo -e "${RED}   ❌ App ID ($APP_ID) doesn't match Bot ID ($BOT_ID)${NC}"
  ISSUES=$((ISSUES + 1))
else
  echo -e "${GREEN}   ✅ App ID matches Bot ID${NC}"
fi

if [ "$APP_ID" != "$WEB_APP_ID" ]; then
  echo -e "${RED}   ❌ App ID ($APP_ID) doesn't match Web App ID ($WEB_APP_ID)${NC}"
  ISSUES=$((ISSUES + 1))
else
  echo -e "${GREEN}   ✅ App ID matches Web App ID${NC}"
fi

echo ""

echo "3. Checking URLs and domains..."

# Check for placeholders
PLACEHOLDER_COUNT=$(grep -o "your-frontend-app-url.com" manifest.json | wc -l)
if [ "$PLACEHOLDER_COUNT" -gt 0 ]; then
  echo -e "${YELLOW}   ⚠️  Found $PLACEHOLDER_COUNT placeholder URL(s)${NC}"
  echo -e "${YELLOW}      Replace 'your-frontend-app-url.com' with your actual frontend URL${NC}"
  ISSUES=$((ISSUES + 1))
else
  echo -e "${GREEN}   ✅ No placeholder URLs found${NC}"
fi

# Extract URLs
STATIC_TAB_URL=$(jq -r '.staticTabs[0].contentUrl' manifest.json)
CONFIG_TAB_URL=$(jq -r '.configurableTabs[0].configurationUrl' manifest.json)
VALID_DOMAINS=$(jq -r '.validDomains[]' manifest.json | tr '\n' ' ')

echo "   Static Tab URL: $STATIC_TAB_URL"
echo "   Config Tab URL: $CONFIG_TAB_URL"
echo ""

echo "4. Checking Web Application Info resource..."
echo "   Resource: $WEB_APP_RESOURCE"

# Expected format: api://<backend-domain>/<app-id>
if [[ $WEB_APP_RESOURCE == api://*.run.app/* ]]; then
  echo -e "${GREEN}   ✅ Resource format looks correct${NC}"
elif [[ $WEB_APP_RESOURCE == api://your-frontend-app-url.com/* ]]; then
  echo -e "${YELLOW}   ⚠️  Resource still uses placeholder URL${NC}"
  ISSUES=$((ISSUES + 1))
else
  echo -e "${YELLOW}   ⚠️  Check resource format: should be api://<domain>/<app-id>${NC}"
fi

# Extract domain from resource
RESOURCE_DOMAIN=$(echo "$WEB_APP_RESOURCE" | sed 's/api:\/\///' | sed 's/\/.*//')
RESOURCE_APP_ID=$(echo "$WEB_APP_RESOURCE" | sed 's/.*\///')

if [ "$RESOURCE_APP_ID" != "$APP_ID" ]; then
  echo -e "${RED}   ❌ App ID in resource ($RESOURCE_APP_ID) doesn't match manifest ID ($APP_ID)${NC}"
  ISSUES=$((ISSUES + 1))
fi

echo ""

echo "5. Checking required valid domains..."
REQUIRED_DOMAINS=(
  "token.botframework.com"
  "login.microsoftonline.com"
  "grupodc-agent-backend-dev-118078450167.us-east4.run.app"
)

for domain in "${REQUIRED_DOMAINS[@]}"; do
  if echo "$VALID_DOMAINS" | grep -q "$domain"; then
    echo -e "${GREEN}   ✅ $domain${NC}"
  else
    echo -e "${RED}   ❌ Missing: $domain${NC}"
    ISSUES=$((ISSUES + 1))
  fi
done

echo ""

echo "6. Checking permissions..."
PERMISSIONS=$(jq -r '.permissions[]' manifest.json | tr '\n' ' ')
echo "   Permissions: $PERMISSIONS"

if echo "$PERMISSIONS" | grep -q "identity"; then
  echo -e "${GREEN}   ✅ 'identity' permission present (required for SSO)${NC}"
else
  echo -e "${RED}   ❌ Missing 'identity' permission (required for SSO)${NC}"
  ISSUES=$((ISSUES + 1))
fi

echo ""

echo "7. Checking bot configuration..."
SUPPORTS_FILES=$(jq -r '.bots[0].supportsFiles' manifest.json)
BOT_SCOPES=$(jq -r '.bots[0].scopes[]' manifest.json | tr '\n' ' ')

echo "   Bot ID: $BOT_ID"
echo "   Supports Files: $SUPPORTS_FILES"
echo "   Scopes: $BOT_SCOPES"

if [ "$SUPPORTS_FILES" = "true" ]; then
  echo -e "${GREEN}   ✅ File upload support enabled${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $ISSUES -eq 0 ]; then
  echo -e "${GREEN}✅ Validation PASSED - No issues found${NC}"
  echo ""
  echo "App Details:"
  echo "  Name: $APP_NAME"
  echo "  Version: $APP_VERSION"
  echo "  ID: $APP_ID"
  echo ""
  echo "You can now package the app with: ./package.sh"
else
  echo -e "${YELLOW}⚠️  Validation completed with $ISSUES issue(s)${NC}"
  echo ""
  echo "Please fix the issues above before deploying to production."
  echo "For testing purposes, you can still package the app, but it may not work correctly."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Azure AD Configuration Check
echo -e "${BLUE}🔐 Azure AD Configuration Checklist${NC}"
echo ""
echo "Make sure you have configured the following in Azure Portal:"
echo "https://portal.azure.com → Azure AD → App Registrations → $APP_NAME"
echo ""
echo "1. API Permissions:"
echo "   - Microsoft Graph: User.Read, email, openid, profile"
echo "   - Grant admin consent ✓"
echo ""
echo "2. Expose an API:"
echo "   - Application ID URI: $WEB_APP_RESOURCE"
echo "   - Scope: access_as_user"
echo "   - Authorized clients:"
echo "     * 1fec8e78-bce4-4aaf-ab1b-5451cc387264 (Teams mobile/desktop)"
echo "     * 5e3ce6c0-2b1f-4285-8d4b-75ee78787346 (Teams web)"
echo ""
echo "3. Authentication:"
echo "   - Platform: Web"
echo "   - Redirect URIs:"
echo "     * https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/api/v1/auth/callback"
echo "     * https://your-frontend-app.com/auth/callback"
echo "     * https://your-frontend-app.com/auth/success"
echo "   - Tokens: Access tokens ✓, ID tokens ✓"
echo ""
echo "4. Bot Service Configuration:"
echo "   - Messaging endpoint:"
echo "     https://grupodc-agent-backend-dev-118078450167.us-east4.run.app/bot/messages"
echo ""
echo "For detailed instructions, see: TEAMS_MANIFEST_GUIDE.md"
echo ""
