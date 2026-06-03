#!/usr/bin/env bash
# HSAP 前端构建（已迁移至 platform/web/ Vite 独立项目）
# 本脚本保留作为向后兼容入口，实际构建委托给 build_web.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "[build] 使用新构建系统 platform/web/ (Vite)..."
exec bash "$ROOT/scripts/build_web.sh"
