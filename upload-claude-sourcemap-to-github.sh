#!/usr/bin/env bash
# 一键：解压 ZIP → 新建 GitHub 仓库 → 推送（需已安装 gh 并已 gh auth login）
set -euo pipefail

ZIP="${1:-$HOME/Desktop/AI项目站/claude-code-sourcemap-main.zip}"
WORK="${2:-$HOME/Desktop/AI项目站/claude-code-sourcemap-main}"
REPO_NAME="${3:-claude-code-sourcemap-main}"

echo "ZIP:  $ZIP"
echo "目录: $WORK"
echo "仓库: $REPO_NAME"
echo ""

if ! command -v git >/dev/null; then echo "请先安装 Git"; exit 1; fi
if ! command -v gh >/dev/null; then echo "请先安装 GitHub CLI: brew install gh"; exit 1; fi
if [ ! -f "$ZIP" ]; then echo "找不到压缩包: $ZIP"; exit 1; fi

rm -rf "$WORK"
mkdir -p "$WORK"
unzip -q -o "$ZIP" -d "$WORK"

# 若只有一层子文件夹，摊平
D="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
F="$(find "$WORK" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d ' ')"
if [ "$D" -eq 1 ] && [ "$F" -eq 0 ]; then
  INNER="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d | head -1)"
  shopt -s dotglob
  mv "$INNER"/* "$WORK/"
  rmdir "$INNER" 2>/dev/null || true
fi

cd "$WORK"
rm -rf .git
git init
git branch -M main
git add .
git commit -m "Initial import: claude-code-sourcemap"

echo ""
echo "正在创建 GitHub 仓库并推送（浏览器可能会让你点一次确认）..."
gh repo create "$REPO_NAME" --public --description "Claude Code sourcemap" --source=. --remote=origin --push

echo ""
echo "完成。在浏览器打开你的 GitHub 主页即可看到新仓库。"
