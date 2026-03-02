#!/bin/bash
#
# Quick start script for OpenCode WhatsApp Integration
# This script sets up and starts the complete integration
#

set -e

echo "=================================================="
echo "OpenCode WhatsApp Integration - Quick Start"
echo "=================================================="
echo ""

# Check for required tools
echo "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "✗ Docker is not installed. Please install Docker first."
    exit 1
fi
echo "✓ Docker found"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "✗ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
echo "✓ Docker Compose found"

# Check for .env file
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file from template..."
    cat > .env << EOF
# Admin API Key for WhatsApp API
ADMIN_API_KEY=$(openssl rand -hex 32)

# WhatsApp Tenant API Key (will be generated)
WHATSAPP_API_KEY=

# External webhook URL (update this for your server)
WEBHOOK_EXTERNAL_URL=http://localhost:5556

# Optional: Logging level
LOG_LEVEL=INFO

# Optional: OpenCode timeout
OPENCODE_TIMEOUT=120
EOF
    echo "✓ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and set WEBHOOK_EXTERNAL_URL to your server's public URL"
    echo ""
else
    echo "✓ Found existing .env file"
fi

# Create data directory
echo ""
echo "Creating data directories..."
mkdir -p data
echo "✓ Created data directory"

# Build and start services
echo ""
echo "Building and starting services..."
echo ""

if docker compose version &> /dev/null; then
    docker compose -f docker-compose.webhook.yml up -d --build
else
    docker-compose -f docker-compose.webhook.yml up -d --build
fi

echo ""
echo "=================================================="
echo "Services Started Successfully!"
echo "=================================================="
echo ""
echo "Services running:"
echo "  - WhatsApp API: http://localhost:8080"
echo "  - OpenCode Webhook: http://localhost:5556"
echo ""
echo "Next steps:"
echo ""
echo "1. Create a WhatsApp tenant:"
echo "   curl -X POST 'http://localhost:8080/admin/tenants?name=my_bot' \\"
echo "     -H 'X-API-Key: \$(grep ADMIN_API_KEY .env | cut -d= -f2)'"
echo ""
echo "2. Update .env with the returned API key:"
echo "   WHATSAPP_API_KEY=wa_returned_key_here"
echo ""
echo "3. Restart the webhook service:"
echo "   docker compose -f docker-compose.webhook.yml restart opencode-webhook"
echo ""
echo "4. Register the webhook:"
echo "   curl -X POST http://localhost:8080/api/webhooks \\"
echo "     -H 'X-API-Key: \$WHATSAPP_API_KEY' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"url\": \"http://opencode-webhook:5556/webhook\"}'"
echo ""
echo "5. Login to WhatsApp:"
echo "   curl -X POST http://localhost:8080/api/login \\"
echo "     -H 'X-API-Key: \$WHATSAPP_API_KEY'"
echo ""
echo "6. Scan the QR code with your WhatsApp app"
echo ""
echo "7. Send a test message to your WhatsApp number!"
echo ""
echo "For detailed documentation, see:"
echo "  docs/opencode-integration.md"
echo ""
echo "To view logs:"
echo "  docker compose -f docker-compose.webhook.yml logs -f"
echo ""
