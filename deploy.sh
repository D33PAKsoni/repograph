#!/usr/bin/env bash
# ==============================================================================
# Graphify-Repograph Agent: Automated Deployment Script
# Target: Cloudways by DigitalOcean
# Description: Automates token retrieval, Git push/pull deployment via Cloudways
# REST API v1, remote Docker orchestration, and live healthcheck verification.
# ==============================================================================

set -euo pipefail

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Print Banner
echo -e "${CYAN}==================================================================${NC}"
echo -e "${CYAN}    Graphify-Repograph Agent: Cloudways by DigitalOcean Deployer  ${NC}"
echo -e "${CYAN}    Hacktoberfest Hack Day Production Deployment Automation       ${NC}"
echo -e "${CYAN}==================================================================${NC}"

# Configuration / Environment Defaults
CLOUDWAYS_API_URL="https://api.cloudways.com/api/v1"
CLOUDWAYS_EMAIL="${CLOUDWAYS_EMAIL:-}"
CLOUDWAYS_API_KEY="${CLOUDWAYS_API_KEY:-}"
CLOUDWAYS_SERVER_ID="${CLOUDWAYS_SERVER_ID:-}"
CLOUDWAYS_APP_ID="${CLOUDWAYS_APP_ID:-}"
GIT_REPO_URL="${GIT_REPO_URL:-https://github.com/D33PAKsoni/repograph.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
APP_LIVE_URL="${APP_LIVE_URL:-}"
DEPLOY_MODE="${DEPLOY_MODE:-api}" # 'api' (Cloudways REST) or 'docker-ssh'

show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --email <email>         Cloudways account email (env: CLOUDWAYS_EMAIL)"
    echo "  --api-key <key>         Cloudways API key (env: CLOUDWAYS_API_KEY)"
    echo "  --server-id <id>        Cloudways Server ID (env: CLOUDWAYS_SERVER_ID)"
    echo "  --app-id <id>           Cloudways Application ID (env: CLOUDWAYS_APP_ID)"
    echo "  --repo <url>            Git repository URL (default: repo git)"
    echo "  --branch <branch>       Git branch to deploy (default: main)"
    echo "  --live-url <url>        Live URL to test healthcheck after deployment"
    echo "  --mode <api|docker-ssh> Deployment mode (default: api)"
    echo "  --help                  Show this help message"
    echo ""
}

# Parse command-line flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --email)
            CLOUDWAYS_EMAIL="$2"
            shift 2
            ;;
        --api-key)
            CLOUDWAYS_API_KEY="$2"
            shift 2
            ;;
        --server-id)
            CLOUDWAYS_SERVER_ID="$2"
            shift 2
            ;;
        --app-id)
            CLOUDWAYS_APP_ID="$2"
            shift 2
            ;;
        --repo)
            GIT_REPO_URL="$2"
            shift 2
            ;;
        --branch)
            GIT_BRANCH="$2"
            shift 2
            ;;
        --live-url)
            APP_LIVE_URL="$2"
            shift 2
            ;;
        --mode)
            DEPLOY_MODE="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Step 1: Pre-flight Verification
log_info "Step 1: Running pre-flight validation..."
if [ "$DEPLOY_MODE" = "api" ]; then
    if [ -z "$CLOUDWAYS_EMAIL" ] || [ -z "$CLOUDWAYS_API_KEY" ]; then
        log_warning "Cloudways API credentials not set (CLOUDWAYS_EMAIL / CLOUDWAYS_API_KEY)."
        log_info "To deploy live via Cloudways REST API, set credentials:"
        log_info "  export CLOUDWAYS_EMAIL='your-email@example.com'"
        log_info "  export CLOUDWAYS_API_KEY='your-cloudways-api-key'"
        log_info "  export CLOUDWAYS_SERVER_ID='123456'"
        log_info "  export CLOUDWAYS_APP_ID='654321'"
        log_info "Simulating local build and container readiness test..."
        DEPLOY_MODE="local-test"
    fi
fi

# Step 2: Deployment Orchestration
if [ "$DEPLOY_MODE" = "api" ]; then
    log_info "Step 2: Authenticating with Cloudways API..."
    
    AUTH_RESPONSE=$(curl -s -X POST "${CLOUDWAYS_API_URL}/oauth/access_token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "email=${CLOUDWAYS_EMAIL}&api_key=${CLOUDWAYS_API_KEY}")

    ACCESS_TOKEN=$(echo "$AUTH_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4 || true)

    if [ -z "$ACCESS_TOKEN" ]; then
        log_error "Cloudways authentication failed. Response: ${AUTH_RESPONSE}"
        exit 1
    fi
    log_success "Obtained Cloudways OAuth Bearer token."

    log_info "Step 3: Triggering Git pull deployment on Server ${CLOUDWAYS_SERVER_ID}, App ${CLOUDWAYS_APP_ID}..."
    PULL_RESPONSE=$(curl -s -X POST "${CLOUDWAYS_API_URL}/git/pull" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "server_id=${CLOUDWAYS_SERVER_ID}&app_id=${CLOUDWAYS_APP_ID}&git_url=${GIT_REPO_URL}&branch_name=${GIT_BRANCH}")

    OPERATION_ID=$(echo "$PULL_RESPONSE" | grep -o '"operation_id":[^,}]*' | cut -d':' -f2 | tr -d ' ' || true)

    if [ -z "$OPERATION_ID" ]; then
        log_error "Git pull trigger failed. Response: ${PULL_RESPONSE}"
        exit 1
    fi
    log_success "Deployment operation registered. Operation ID: ${OPERATION_ID}"

    log_info "Step 4: Monitoring Cloudways deployment operation status..."
    MAX_ATTEMPTS=30
    ATTEMPT=1
    while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
        STATUS_RESP=$(curl -s -X GET "${CLOUDWAYS_API_URL}/operation/${OPERATION_ID}" \
            -H "Authorization: Bearer ${ACCESS_TOKEN}")
        
        OP_STATUS=$(echo "$STATUS_RESP" | grep -o '"status":[^,}]*' | head -n1 | cut -d':' -f2 | tr -d ' "' || true)
        log_info "Attempt ${ATTEMPT}/${MAX_ATTEMPTS}: Status is '${OP_STATUS}'..."

        if [ "$OP_STATUS" = "completed" ] || [ "$OP_STATUS" = "1" ]; then
            log_success "Cloudways Git deployment completed successfully!"
            break
        elif [ "$OP_STATUS" = "failed" ] || [ "$OP_STATUS" = "0" ]; then
            log_error "Cloudways operation failed: ${STATUS_RESP}"
            exit 1
        fi

        sleep 5
        ATTEMPT=$((ATTEMPT + 1))
    done

elif [ "$DEPLOY_MODE" = "docker-ssh" ]; then
    log_info "Deploying via Docker over SSH to Cloudways Flexible Server..."
    CLOUDWAYS_SSH_HOST="${CLOUDWAYS_SSH_HOST:-master.cloudways.com}"
    CLOUDWAYS_SSH_USER="${CLOUDWAYS_SSH_USER:-master_user}"

    ssh -o StrictHostKeyChecking=no "${CLOUDWAYS_SSH_USER}@${CLOUDWAYS_SSH_HOST}" << 'EOF'
        cd /home/master/applications/repograph/public_html
        git pull origin main
        docker build -t graphify-repograph:latest .
        docker stop graphify-repograph || true
        docker rm graphify-repograph || true
        docker run -d --name graphify-repograph \
            -p 8000:8000 \
            -e GEMINI_API_KEY="${GEMINI_API_KEY}" \
            --restart always \
            graphify-repograph:latest
EOF
    log_success "Container restarted on Cloudways server."

else
    log_info "Testing local container build and service integrity..."
    if command -v docker >/dev/null 2>&1; then
        log_info "Building local Docker image to verify container packaging..."
        docker build -t graphify-repograph:test .
        log_success "Local Docker image built successfully."
    else
        log_info "Docker CLI not detected locally. Validating Python application syntax..."
        python3 -m py_compile parser.py bridge.py ai_agent.py server.py
        log_success "All Python source files passed compilation checks."
    fi
fi

# Step 5: Post-Deployment Verification & Healthcheck
if [ -n "$APP_LIVE_URL" ]; then
    log_info "Step 5: Verifying live healthcheck on ${APP_LIVE_URL}/health..."
    HEALTH_RESP=$(curl -s -f "${APP_LIVE_URL}/health" || true)
    if [ -n "$HEALTH_RESP" ]; then
        log_success "Live healthcheck passed! Response:"
        echo "$HEALTH_RESP"
    else
        log_warning "Healthcheck did not respond immediately. Check server logs on Cloudways console."
    fi
else
    log_info "Tip: Provide --live-url https://your-app.cloudwaysapps.com to execute automated post-deploy healthchecks."
fi

log_success "Deployment pipeline execution complete! 🎉"
