#!/bin/bash
# ============================================================================
# Teams Manifest Package Script
# ============================================================================
# This script creates a Teams app package (ZIP) from the manifest and icons.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}📦 Creating Teams App Package${NC}"
echo ""

# Change to script directory
cd "$(dirname "$0")"

# Check required files exist
echo "Checking required files..."
MISSING_FILES=0

if [ ! -f "manifest.json" ]; then
  echo -e "${RED}❌ manifest.json not found${NC}"
  MISSING_FILES=1
fi

if [ ! -f "color.png" ]; then
  echo -e "${YELLOW}⚠️  color.png not found (192x192 icon required)${NC}"
  MISSING_FILES=1
fi

if [ ! -f "outline.png" ]; then
  echo -e "${YELLOW}⚠️  outline.png not found (32x32 icon required)${NC}"
  MISSING_FILES=1
fi

if [ $MISSING_FILES -eq 1 ]; then
  echo ""
  echo -e "${RED}Cannot create package without required files${NC}"
  exit 1
fi

echo -e "${GREEN}✅ All files present${NC}"
echo ""

# Validate manifest.json
echo "Validating manifest.json..."
if ! jq empty manifest.json 2>/dev/null; then
  echo -e "${RED}❌ manifest.json is not valid JSON${NC}"
  exit 1
fi

# Check for placeholder URLs
echo "Checking for placeholder URLs..."
PLACEHOLDERS=$(grep -o "your-frontend-app-url.com" manifest.json | wc -l)
if [ "$PLACEHOLDERS" -gt 0 ]; then
  echo -e "${YELLOW}⚠️  Found $PLACEHOLDERS placeholder URL(s): 'your-frontend-app-url.com'${NC}"
  echo -e "${YELLOW}   Update manifest.json with your actual frontend URL before deploying to production${NC}"
else
  echo -e "${GREEN}✅ No placeholders found${NC}"
fi
echo ""

# Extract manifest info
APP_NAME=$(jq -r '.name.short' manifest.json)
APP_VERSION=$(jq -r '.version' manifest.json)
APP_ID=$(jq -r '.id' manifest.json)

echo "App Details:"
echo "  Name: $APP_NAME"
echo "  Version: $APP_VERSION"
echo "  ID: $APP_ID"
echo ""

# Create package
PACKAGE_NAME="grupodc-agent-teams-v${APP_VERSION}.zip"
echo "Creating package: $PACKAGE_NAME"

# Remove old package if exists
if [ -f "$PACKAGE_NAME" ]; then
  rm "$PACKAGE_NAME"
fi

# Create ZIP with specific file order (manifest first)
zip -q "$PACKAGE_NAME" manifest.json
zip -q "$PACKAGE_NAME" color.png outline.png

# Verify ZIP contents
echo ""
echo "Package contents:"
unzip -l "$PACKAGE_NAME"

echo ""
echo -e "${GREEN}✅ Package created successfully!${NC}"
echo ""
echo "📁 Package location: teams/$PACKAGE_NAME"
echo ""
echo "Next steps:"
echo "1. Go to Teams Admin Center: https://admin.teams.microsoft.com"
echo "2. Navigate to: Teams apps → Manage apps"
echo "3. Click: Upload new app"
echo "4. Upload: $PACKAGE_NAME"
echo ""
echo "Or for development/testing:"
echo "1. Open Microsoft Teams"
echo "2. Go to Apps → Manage your apps"
echo "3. Click: Upload a custom app"
echo "4. Select: $PACKAGE_NAME"
echo ""
echo "For more details, see: TEAMS_MANIFEST_GUIDE.md"
