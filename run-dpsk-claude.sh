#!/bin/bash
# claude-deepseek.sh - 完整参数支持版

set -e

# 颜色输出（仅在终端交互时）
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi

# 查找 .env 文件
find_env_file() {
    [ -f "$PWD/.env" ] && echo "$PWD/.env" && return 0
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [ -f "$SCRIPT_DIR/.env" ] && echo "$SCRIPT_DIR/.env" && return 0
    [ -f "$HOME/.config/claude-deepseek/.env" ] && echo "$HOME/.config/claude-deepseek/.env" && return 0
    [ -f "$HOME/.claude-deepseek.env" ] && echo "$HOME/.claude-deepseek.env" && return 0
    return 1
}

# 加载环境变量
ENV_FILE=$(find_env_file)
if [ -z "$ENV_FILE" ]; then
    echo -e "${RED}❌ 未找到 .env 文件${NC}" >&2
    exit 1
fi

# 提取 API Key
DEEPSEEK_API_KEY=$(grep -E "^DEEPSEEK_API_KEY=" "$ENV_FILE" | head -n1 | cut -d '=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/^["\x27]//;s/["\x27]$//')

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo -e "${RED}❌ .env 中未找到 DEEPSEEK_API_KEY${NC}" >&2
    exit 1
fi

# 设置环境变量
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
export ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash"

# 显示模式（仅当有终端且非静默模式时）
if [ -t 1 ] && [[ ! "$*" =~ --quiet ]]; then
    echo -e "${GREEN}✓ DeepSeek 模式已启用${NC}" >&2
fi

# 执行 Claude Code，透传所有参数
exec claude "$@"
