#!/usr/bin/env bash
# Offline, manifest-only installer. Does not register a ChatGPT plugin.
set -euo pipefail
NAME="income-opportunity-map"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SKILLS_DIR="${HOME:?HOME is not set}/.agents/skills"
CHECK_ONLY=0
STAGING=""
LOCK_DIR=""
MEMBERS=()
fail() { printf '错误：%s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'HELP'
收入可能性地图 — 本地文件安装
bash install.sh
bash install.sh --check
bash install.sh --skills-dir /absolute/path/to/.agents/skills
默认：~/.agents/skills/income-opportunity-map
--check 不写入；同名不同内容不覆盖。仅复制 SHA256SUMS 所列文件。
无需联网、API Key、Python 或 sudo；不改全局配置，不复制 .git。
HELP
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1; shift ;;
    --skills-dir)
      [[ $# -ge 2 && -n "$2" ]] || fail '--skills-dir 需要目录。'
      SKILLS_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "未知参数：$1" ;;
  esac
done
[[ "$SKILLS_DIR" = /* ]] || fail '安装目录必须是绝对路径。'
case "$SKILLS_DIR/" in *'/../'*|*'/./'*) fail '请使用不含 . 或 .. 的绝对路径。' ;; esac
# Resolve existing ancestors before mkdir, including macOS /var aliases.
resolve_destination() {
  local candidate="${1%/}" suffix="" part resolved
  [[ -n "$candidate" ]] || candidate='/'
  while [[ ! -d "$candidate" ]]; do
    [[ ! -e "$candidate" && ! -L "$candidate" ]] || return 1
    part="${candidate##*/}"
    suffix="/$part$suffix"
    candidate="${candidate%/*}"
    [[ -n "$candidate" ]] || candidate='/'
  done
  resolved="$(cd -- "$candidate" && pwd -P)" || return 1
  resolved="${resolved%/}$suffix"
  printf '%s\n' "${resolved:-/}"
}
SKILLS_DIR="$(resolve_destination "$SKILLS_DIR")" || fail '无法解析安装目录。'
case "${SKILLS_DIR%/}/" in "$SOURCE_DIR/"*) fail '安装位置不能位于安装源内部。' ;; esac
[[ -f "$SOURCE_DIR/SHA256SUMS" && ! -L "$SOURCE_DIR/SHA256SUMS" ]] || fail '缺少正常的 SHA256SUMS。'
[[ -f "$SOURCE_DIR/SKILL.md" ]] || fail '安装包不完整。'
if command -v shasum >/dev/null 2>&1; then HASH_TOOL=shasum
elif command -v sha256sum >/dev/null 2>&1; then HASH_TOOL=sha256sum
else fail '找不到 shasum 或 sha256sum。'; fi

# Strict paths also prevent checksum entries from reading outside the package.
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^([0-9a-f]{64})\ \ ([A-Za-z0-9._/-]+)$ ]] || fail '校验清单格式错误。'
  relative="${BASH_REMATCH[2]}"
  case "$relative" in /*|-*|SHA256SUMS) fail "不安全的清单路径：$relative" ;; esac
  case "/$relative/" in *'/../'*|*'/./'*|*'/.git/'*|*'//'*) fail "不安全的清单路径：$relative" ;; esac
  for previous in "${MEMBERS[@]+${MEMBERS[@]}}"; do
    [[ "$previous" != "$relative" ]] || fail "重复清单路径：$relative"
  done
  MEMBERS+=("$relative")
done < "$SOURCE_DIR/SHA256SUMS"
[[ ${#MEMBERS[@]} -gt 0 ]] || fail '校验清单为空。'
found_skill=0
for relative in "${MEMBERS[@]}"; do [[ "$relative" != SKILL.md ]] || found_skill=1; done
[[ "$found_skill" == 1 ]] || fail '清单没有包含 SKILL.md。'

safe_member() {
  local base="$1" relative="$2" part current="$1"
  local parts=()
  IFS='/' read -r -a parts <<< "$relative"
  for part in "${parts[@]}"; do
    current="$current/$part"
    [[ ! -L "$current" ]] || return 1
  done
  [[ -f "$current" ]]
}
verify() {
  local directory="$1" relative
  [[ -d "$directory" && ! -L "$directory" ]] || return 1
  [[ -f "$directory/SHA256SUMS" && ! -L "$directory/SHA256SUMS" ]] || return 1
  cmp -s "$SOURCE_DIR/SHA256SUMS" "$directory/SHA256SUMS" || return 1
  for relative in "${MEMBERS[@]}"; do safe_member "$directory" "$relative" || return 1; done
  if [[ "$HASH_TOOL" == shasum ]]; then
    (cd -- "$directory" && shasum -a 256 -c "$SOURCE_DIR/SHA256SUMS" >/dev/null 2>&1)
  else
    (cd -- "$directory" && sha256sum -c "$SOURCE_DIR/SHA256SUMS" >/dev/null 2>&1)
  fi
}
cleanup() {
  if [[ -n "$STAGING" && -d "$STAGING" ]]; then rm -rf -- "$STAGING"; fi
  if [[ -n "$LOCK_DIR" && -d "$LOCK_DIR" ]]; then rmdir -- "$LOCK_DIR" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM
verify "$SOURCE_DIR" || fail '安装源校验失败，未写入目标。'
TARGET="${SKILLS_DIR%/}/$NAME"
[[ ! -L "$TARGET" ]] || fail '目标是符号链接，已停止。'
if [[ "$CHECK_ONLY" == 1 ]]; then
  verify "$TARGET" || fail "目标不存在或受管理文件不同：$TARGET"
  printf '文件校验通过：%s\n' "$TARGET"
  printf '这不证明客户端已加载或模型行为已通过验收。\n'
  exit 0
fi
mkdir -p -- "$SKILLS_DIR"
SKILLS_DIR="$(cd -- "$SKILLS_DIR" && pwd -P)"
case "$SKILLS_DIR/" in "$SOURCE_DIR/"*) fail '安装位置不能位于安装源内部。' ;; esac
TARGET="$SKILLS_DIR/$NAME"
LOCK_DIR="$SKILLS_DIR/.$NAME-install-lock"
if ! mkdir -- "$LOCK_DIR" 2>/dev/null; then LOCK_DIR=''; fail '检测到安装锁，请先检查其他安装进程。'; fi
[[ ! -L "$TARGET" ]] || fail '目标是符号链接，已停止。'
if [[ -e "$TARGET" ]]; then
  if verify "$TARGET"; then printf '受管理文件一致，未覆盖：%s\n' "$TARGET"; exit 0; fi
  fail "同名目录已有不同内容，未覆盖。请先备份并移出：$TARGET"
fi
STAGING="$(mktemp -d "$SKILLS_DIR/.$NAME-install.XXXXXX")"
for relative in "${MEMBERS[@]}"; do
  mkdir -p -- "$(dirname -- "$STAGING/$relative")"
  cp -- "$SOURCE_DIR/$relative" "$STAGING/$relative"
done
cp -- "$SOURCE_DIR/SHA256SUMS" "$STAGING/SHA256SUMS"
verify "$STAGING" || fail '临时副本校验失败。'
[[ ! -e "$TARGET" && ! -L "$TARGET" ]] || fail '目标在安装过程中已出现，停止。'
mv -- "$STAGING" "$TARGET"
STAGING=''
printf '文件安装与完整性校验成功：%s\n' "$TARGET"
printf '未修改全局配置；未验证客户端加载或模型行为。\n'
