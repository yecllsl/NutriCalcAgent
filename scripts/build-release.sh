#!/usr/bin/env bash
# ──────────────────────────────────────────
# NutriCalcAgent 发布产物构建脚本
#
# 用法：bash scripts/build-release.sh <version>
#   version: 不含 v 前缀的版本号，如 0.1.1
#
# 产物（输出到 dist/）：
#   NutriCalcAgent-v<version>.zip
#   NutriCalcAgent-v<version>.tar.gz
#
# 设计原则："folder as product"——解压即用，无需额外构建链。
# 排除项：.git / .venv / __pycache__ / 运行时数据 / IDE 缓存
# ──────────────────────────────────────────
set -euo pipefail

# 版本号参数校验
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    echo "::error::用法: bash scripts/build-release.sh <version>（如 0.1.1）"
    exit 1
fi

# 定位项目根目录（脚本位于 scripts/ 下）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 产物目录
PKG_NAME="NutriCalcAgent-v${VERSION}"
DIST_DIR="$PROJECT_ROOT/dist"
STAGE_DIR="$DIST_DIR/$PKG_NAME"

echo "==> 构建版本: $VERSION"
echo "==> 项目根: $PROJECT_ROOT"
echo "==> 产物目录: $DIST_DIR"

# 清理旧产物
rm -rf "$DIST_DIR"
mkdir -p "$STAGE_DIR"

# ──────────────────────────────────────────
# 复制项目文件（排除运行时/构建缓存/版本控制）
# 使用 rsync 以便精细控制排除规则
# ──────────────────────────────────────────
if ! command -v rsync >/dev/null 2>&1; then
    echo "::error::rsync 未安装"
    exit 1
fi

rsync -a \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='.vscode/' \
    --exclude='.idea/' \
    --exclude='.trae/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='.mypy_cache/' \
    --exclude='.venv/' \
    --exclude='dist/' \
    --exclude='node_modules/' \
    --exclude='coverage.xml' \
    --exclude='.coverage' \
    --exclude='test-results/' \
    --exclude='*.log' \
    --exclude='.DS_Store' \
    --exclude='Thumbs.db' \
    --exclude='nutricalc-mcp/data/food_logs/*.json' \
    --exclude='nutricalc-mcp/data/user_profile/*.json' \
    --exclude='nutricalc-mcp/data/food_images/*' \
    --exclude='nutricalc-mcp/data/analysis_reports/*.json' \
    --exclude='nutricalc-mcp/data/meal_plans/*.json' \
    ./ "$STAGE_DIR/"

# 保留 data/ 子目录的 .gitkeep（已被 rsync 包含，无需额外处理）

echo "==> 已暂存到: $STAGE_DIR"

# ──────────────────────────────────────────
# 打包 zip + tar.gz
# - zip: Windows 用户友好
# - tar.gz: Linux/macOS 用户友好，gzip 通用
# 不再生成 tar.zst：zstd 在某些老旧 macOS 上需手动安装，通用性不足
# ──────────────────────────────────────────
echo "==> 生成 zip 包..."
cd "$DIST_DIR"
zip -r -q "${PKG_NAME}.zip" "$PKG_NAME"

echo "==> 生成 tar.gz 包..."
tar -czf "${PKG_NAME}.tar.gz" "$PKG_NAME"

# ──────────────────────────────────────────
# 校验产物
# ──────────────────────────────────────────
echo "==> 校验产物..."
for f in "${PKG_NAME}.zip" "${PKG_NAME}.tar.gz"; do
    if [ ! -f "$DIST_DIR/$f" ]; then
        echo "::error::缺失: $f"
        exit 1
    fi
    size=$(du -h "$DIST_DIR/$f" | cut -f1)
    echo "  ✓ $f ($size)"
done

echo "==> 构建完成: $DIST_DIR"
