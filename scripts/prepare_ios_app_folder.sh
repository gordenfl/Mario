#!/usr/bin/env bash
# 生成「干净」的 iOS 应用目录：只含 main.py + client + client_kivy，不含 .venv / .git 等。
# 模拟器/真机安装若打入 .venv，会因 python3 等符号链接报错：invalid symlink。
#
# 用法：在仓库根执行 ./scripts/prepare_ios_app_folder.sh
# 然后用「本脚本打印的绝对路径」执行 toolchain create（或确保已有 mario-ios 指向该路径）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/build/ios_app"

echo $OUT
echo "==================="
mkdir -p "$OUT"

# 注意：exclude 模式相对于本次 rsync 的「源根」。不要用 '*.py'。
RSYNC_EX=(
  --exclude ".venv/"
  --exclude "venv/"
  --exclude "__pycache__/"
  --exclude ".git/"
  --exclude ".DS_Store"
  --exclude "*.pyc"
  --exclude "*.pyo"
)

echo "Syncing into $OUT ..."

# 源目录带尾部 / ：同步目录「内容」到目标目录
rsync -a "${RSYNC_EX[@]}" "$ROOT/main.py" "$OUT/"
mkdir -p "$OUT/client" "$OUT/client_kivy"
rsync -a --delete "${RSYNC_EX[@]}" "$ROOT/client/" "$OUT/client/"
rsync -a --delete "${RSYNC_EX[@]}" "$ROOT/client_kivy/" "$OUT/client_kivy/"

PY_COUNT="$(find "$OUT" -name "*.py" | wc -l | tr -d ' ')"
if [ "${PY_COUNT:-0}" -lt 1 ]; then
  echo "ERROR: no .py files under $OUT — rsync may have failed." >&2
  exit 1
fi

echo "OK: $PY_COUNT Python files under $OUT (sanity check)."
echo ""
echo "Next (kivy-ios venv): use this path with toolchain create — must match what Xcode syncs from:"
echo "  toolchain create mario \"$OUT\""
echo ""
echo "If Xcode YourApp still has no .py: delete old mario-ios folder and run toolchain create again"
echo "with the path above; do not point create at the whole repo (that may pull .venv)."
