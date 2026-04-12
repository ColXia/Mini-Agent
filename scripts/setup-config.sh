#!/bin/bash
# Mini-Agent configuration bootstrap for local repo usage on Unix-like systems.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

copy_template_if_missing() {
    local source="$1"
    local destination="$2"
    local label="$3"

    if [ ! -f "$source" ]; then
        echo -e "${YELLOW}   [WARN] Missing template: ${label}${NC}"
        return
    fi

    if [ -f "$destination" ]; then
        echo -e "${YELLOW}   [SKIP] Exists: ${destination}${NC}"
        return
    fi

    cp "$source" "$destination"
    echo -e "${GREEN}   [OK] Created: ${destination}${NC}"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PACKAGE_CONFIG_DIR="${REPO_ROOT}/src/mini_agent/config"
USER_CONFIG_DIR="${HOME}/.mini-agent/config"
REPO_ENV_EXAMPLE="${REPO_ROOT}/.env.local.example"
REPO_ENV_LOCAL="${REPO_ROOT}/.env.local"

if [ ! -d "$PACKAGE_CONFIG_DIR" ]; then
    echo -e "${RED}[ERROR] Cannot find src/mini_agent/config under repo root.${NC}"
    exit 1
fi

echo -e "${CYAN}==================================================${NC}"
echo -e "${CYAN}   Mini-Agent Local Config Bootstrap${NC}"
echo -e "${CYAN}==================================================${NC}"
echo ""

echo -e "${BLUE}[1/2]${NC} Ensuring user config directory..."
mkdir -p "$USER_CONFIG_DIR"
echo -e "${GREEN}   [OK] Ready: ${USER_CONFIG_DIR}${NC}"
echo ""

echo -e "${BLUE}[2/2]${NC} Copying local templates if missing..."
copy_template_if_missing "${PACKAGE_CONFIG_DIR}/config-example.yaml" "${USER_CONFIG_DIR}/config.yaml" "config.yaml"
copy_template_if_missing "${PACKAGE_CONFIG_DIR}/mcp-example.json" "${USER_CONFIG_DIR}/mcp.json" "mcp.json"
copy_template_if_missing "${PACKAGE_CONFIG_DIR}/system_prompt.md" "${USER_CONFIG_DIR}/system_prompt.md" "system_prompt.md"
echo ""

echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}   Local Bootstrap Complete${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo "User config directory:"
echo -e "  ${CYAN}${USER_CONFIG_DIR}${NC}"
echo ""
echo "Preset provider keys:"
echo -e "  ${GREEN}OPENAI_API_KEY${NC}"
echo -e "  ${GREEN}ANTHROPIC_API_KEY${NC}"
echo -e "  ${GREEN}GEMINI_API_KEY${NC}"
echo -e "  ${GREEN}MINIMAX_API_KEY${NC}"
echo ""
echo "Current behavior:"
echo "  - Runtime checks system environment variables first."
echo "  - Repo-local fallback is .env.local."
echo "  - .env.local.example is a template only and is not loaded."
echo ""

if [ -f "$REPO_ENV_EXAMPLE" ] && [ ! -f "$REPO_ENV_LOCAL" ]; then
    echo "Optional repo-local secret file:"
    echo -e "  ${GREEN}cp \"${REPO_ENV_EXAMPLE}\" \"${REPO_ENV_LOCAL}\"${NC}"
    echo ""
fi

echo "Useful commands:"
echo -e "  ${GREEN}uv run mini${NC}"
echo -e "  ${GREEN}uv run mini tui${NC}"
echo -e "  ${GREEN}uv run mini qq${NC}"
echo -e "  ${GREEN}uv run mini-agent doctor${NC}"