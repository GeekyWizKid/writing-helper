#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
SOURCE_SKILL="$REPO_ROOT/skills/video-script-studio"
E2E_ROOT="$SOURCE_SKILL/tests/e2e"
INITIAL_PROMPT="$E2E_ROOT/visual-essay-prompt.md"
GATE_SCHEMA="$E2E_ROOT/gate-result.schema.json"
FINAL_SCHEMA="$E2E_ROOT/expected-result.schema.json"
SUCCESS_MARKER="video-script-studio-e2e ok"
PREFLIGHT_MARKER="video-script-studio-e2e preflight ok"

die() {
  printf '%s\n' "video-script-studio-e2e: $*" >&2
  exit 1
}

static_preflight() {
  [[ -d "$SOURCE_SKILL/scripts" ]] || die "source skill is missing"
  [[ -f "$INITIAL_PROMPT" && -f "$GATE_SCHEMA" && -f "$FINAL_SCHEMA" ]] \
    || die "E2E prompt or schema is missing"
  python3 - "$INITIAL_PROMPT" "$GATE_SCHEMA" "$FINAL_SCHEMA" <<'PY'
import json
import sys
from pathlib import Path

prompt_path, gate_path, final_path = map(Path, sys.argv[1:])
prompt = prompt_path.read_text(encoding="utf-8")
required_prompt = (
    "$video-script-studio", "__PROJECT_ROOT__", "visual-essay", "骑行", "版画",
    "只创建并展示 brief.md", "不得批准 brief", "无外部事实主张",
)
if any(item not in prompt for item in required_prompt):
    raise SystemExit("initial prompt contract is incomplete")
for path in (gate_path, final_path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("type") != "object" or value.get("additionalProperties") is not False:
        raise SystemExit("result schema is not strict")
PY
  printf '%s\n' "$PREFLIGHT_MARKER"
}

if [[ "${1:-}" == "--preflight" ]]; then
  [[ $# -eq 1 ]] || die "--preflight accepts no other arguments"
  static_preflight
  exit 0
fi
[[ $# -eq 0 ]] || die "unknown argument"

static_preflight >/dev/null

for command in python3 codex uv git install env; do
  command -v "$command" >/dev/null 2>&1 || die "required command is unavailable: $command"
done

PYTHON_BIN="$(command -v python3)"
CODEX_BIN="$(command -v codex)"
UV_BIN="$(command -v uv)"
GIT_BIN="$(command -v git)"
INSTALL_BIN="$(command -v install)"
ENV_BIN="$(command -v env)"
ISOLATED_PATH="$(dirname "$CODEX_BIN"):$(dirname "$PYTHON_BIN"):$(dirname "$UV_BIN"):/usr/bin:/bin:/usr/sbin:/sbin"
ORIGINAL_HOME="${HOME:?HOME is required to locate the existing Codex authentication file}"
ORIGINAL_CODEX_HOME="${CODEX_HOME:-$ORIGINAL_HOME/.codex}"
ORIGINAL_AUTH="$ORIGINAL_CODEX_HOME/auth.json"
OFFICIAL_VALIDATOR="${VIDEO_SCRIPT_STUDIO_OFFICIAL_VALIDATOR:-$ORIGINAL_CODEX_HOME/skills/.system/skill-creator/scripts/quick_validate.py}"
TURN_TIMEOUT="${VIDEO_SCRIPT_STUDIO_E2E_TIMEOUT_SECONDS:-900}"
[[ "$TURN_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || die "timeout must be a positive integer"

RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/video-script-studio-e2e.XXXXXX")"
TMP_HOME="$RUN_ROOT/home"
TMP_CODEX_HOME="$RUN_ROOT/codex-home"
TMP_XDG_CONFIG="$RUN_ROOT/xdg-config"
TMP_XDG_DATA="$RUN_ROOT/xdg-data"
TMP_XDG_CACHE="$RUN_ROOT/xdg-cache"
TMP_TMPDIR="$RUN_ROOT/tmp"
TMP_WORKSPACE="$RUN_ROOT/workspace"
TMP_LOGS="$RUN_ROOT/logs"
PROJECT_ROOT="$TMP_WORKSPACE/video-projects"
ACTIVE_PROCESS_GROUP=""
ACTIVE_PID_FILE="$RUN_ROOT/active-process-group"

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -f "$ACTIVE_PID_FILE" ]]; then
    ACTIVE_PROCESS_GROUP="$(<"$ACTIVE_PID_FILE")"
  fi
  if [[ "$ACTIVE_PROCESS_GROUP" =~ ^[1-9][0-9]*$ ]]; then
    kill -TERM -- "-$ACTIVE_PROCESS_GROUP" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$ACTIVE_PROCESS_GROUP" 2>/dev/null || true
  fi
  chmod -R u+rwX "$RUN_ROOT" 2>/dev/null || true
  "$PYTHON_BIN" - "$RUN_ROOT" <<'PY' 2>/dev/null || true
import shutil
import sys
shutil.rmtree(sys.argv[1], ignore_errors=True)
PY
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

mkdir -m 700 "$TMP_HOME" "$TMP_CODEX_HOME" "$TMP_XDG_CONFIG" "$TMP_XDG_DATA" \
  "$TMP_XDG_CACHE" "$TMP_TMPDIR" "$TMP_WORKSPACE" "$TMP_LOGS" "$PROJECT_ROOT"
"$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" TMPDIR="$TMP_TMPDIR" \
  GIT_CONFIG_NOSYSTEM=1 "$GIT_BIN" -c init.defaultBranch=main -C "$TMP_WORKSPACE" init -q
[[ ! -e "$TMP_WORKSPACE/AGENTS.md" && ! -e "$TMP_WORKSPACE/.codex" \
   && ! -e "$TMP_WORKSPACE/.agents" ]] || die "workspace isolation failed"

"$PYTHON_BIN" - "$ORIGINAL_AUTH" "$OFFICIAL_VALIDATOR" <<'PY'
import os
import stat
import sys
from pathlib import Path

auth, validator = map(Path, sys.argv[1:])
metadata = auth.lstat()
if auth.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
    raise SystemExit("authentication file is not a trusted regular file")
if not validator.is_file() or validator.is_symlink():
    raise SystemExit("official validator is unavailable or unsafe")
PY

mkdir -m 700 "$TMP_CODEX_HOME/skills"
[[ ! -e "$TMP_CODEX_HOME/skills/video-script-studio" ]] \
  || die "target skill unexpectedly exists before installation"
"$INSTALL_BIN" -m 600 "$ORIGINAL_AUTH" "$TMP_CODEX_HOME/auth.json"
"$PYTHON_BIN" - "$TMP_CODEX_HOME/auth.json" <<'PY'
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
metadata = path.lstat()
if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit("copied authentication file permissions are unsafe")
PY

INSTALLED_SKILL="$TMP_CODEX_HOME/skills/video-script-studio"
mkdir -m 700 "$INSTALLED_SKILL"
cp -R "$SOURCE_SKILL/." "$INSTALLED_SKILL/"
RUNTIME_INITIAL_PROMPT="$INSTALLED_SKILL/tests/e2e/visual-essay-prompt.md"
RUNTIME_GATE_SCHEMA="$INSTALLED_SKILL/tests/e2e/gate-result.schema.json"
RUNTIME_FINAL_SCHEMA="$INSTALLED_SKILL/tests/e2e/expected-result.schema.json"
"$PYTHON_BIN" - "$INSTALLED_SKILL" <<'PY'
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
for path in tuple(root.rglob("__pycache__")):
    shutil.rmtree(path)
for path in tuple(root.rglob("*.pyc")):
    path.unlink()
PY

tree_digest() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*")):
    relative = path.relative_to(root)
    if "__pycache__" in relative.parts or path.suffix == ".pyc":
        continue
    digest.update(relative.as_posix().encode("utf-8") + b"\0")
    if path.is_symlink():
        raise SystemExit("skill tree contains a symbolic link")
    if path.is_file():
        digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}

SOURCE_DIGEST_BEFORE="$(tree_digest "$SOURCE_SKILL")"
INSTALLED_DIGEST="$(tree_digest "$INSTALLED_SKILL")"
[[ "$SOURCE_DIGEST_BEFORE" == "$INSTALLED_DIGEST" ]] || die "installed skill differs from repository source"
AUTH_DIGEST_BEFORE="$($PYTHON_BIN - "$ORIGINAL_AUTH" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"

"$PYTHON_BIN" - "$TMP_CODEX_HOME/skills" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
entries = sorted(path.name for path in root.iterdir())
if entries != ["video-script-studio"]:
    raise SystemExit("temporary Codex home contains an unexpected skill")
PY

"$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" CODEX_HOME="$TMP_CODEX_HOME" \
  XDG_CONFIG_HOME="$TMP_XDG_CONFIG" XDG_DATA_HOME="$TMP_XDG_DATA" \
  XDG_CACHE_HOME="$TMP_XDG_CACHE" TMPDIR="$TMP_TMPDIR" \
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" -m unittest discover \
  -s "$INSTALLED_SKILL/tests" -v >"$TMP_LOGS/copied-tests.log" 2>&1 \
  || die "copied deterministic suite failed"
"$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" CODEX_HOME="$TMP_CODEX_HOME" \
  XDG_CONFIG_HOME="$TMP_XDG_CONFIG" XDG_DATA_HOME="$TMP_XDG_DATA" \
  XDG_CACHE_HOME="$TMP_XDG_CACHE" TMPDIR="$TMP_TMPDIR" \
  "$UV_BIN" run --with pyyaml python "$OFFICIAL_VALIDATOR" "$INSTALLED_SKILL" \
  >"$TMP_LOGS/official-validator.log" 2>&1 || die "official skill validation failed"
grep -Fxq "Skill is valid!" "$TMP_LOGS/official-validator.log" \
  || die "official validator success marker is missing"

run_with_timeout() {
  local timeout_seconds=$1
  local log_path=$2
  local prompt_path=$3
  shift 3
  "$PYTHON_BIN" - "$timeout_seconds" "$log_path" "$prompt_path" "$ACTIVE_PID_FILE" "$@" <<'PY'
import os
import signal
import subprocess
import sys

timeout = int(sys.argv[1])
log_path, prompt_path, pid_path = sys.argv[2:5]
command = sys.argv[5:]
with open(prompt_path, "rb") as prompt, open(log_path, "wb") as log:
    process = subprocess.Popen(
        command,
        stdin=prompt,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    with open(pid_path, "w", encoding="ascii") as pid_file:
        pid_file.write(str(process.pid))
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        returncode = 124
    finally:
        try:
            os.unlink(pid_path)
        except FileNotFoundError:
            pass
raise SystemExit(returncode)
PY
}

redacted_log_tail() {
  "$PYTHON_BIN" - "$1" "$RUN_ROOT" "$ORIGINAL_HOME" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
for secret_path in sys.argv[2:]:
    text = text.replace(secret_path, "<redacted-path>")
patterns = (
    r"(?i)(authorization\s*[:=]\s*)([^\s]+)",
    r"(?i)(bearer\s+)([^\s]+)",
    r"(?i)((?:api[_-]?key|token|secret)\s*[:=]\s*)([^\s]+)",
)
for pattern in patterns:
    text = re.sub(pattern, lambda match: match.group(1) + "<redacted>", text)
text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "<redacted>", text)
safe = [line for line in text.splitlines() if re.search(r"(?i)error|failed|invalid|timeout|warning", line)]
for line in safe[-20:]:
    print(line[:500], file=sys.stderr)
PY
}

run_codex_turn() {
  local prompt_path=$1
  local schema_path=$2
  local result_path=$3
  local log_path=$4
  if ! run_with_timeout "$TURN_TIMEOUT" "$log_path" "$prompt_path" \
    "$ENV_BIN" -i \
      PATH="$ISOLATED_PATH" HOME="$TMP_HOME" CODEX_HOME="$TMP_CODEX_HOME" \
      XDG_CONFIG_HOME="$TMP_XDG_CONFIG" XDG_DATA_HOME="$TMP_XDG_DATA" \
      XDG_CACHE_HOME="$TMP_XDG_CACHE" TMPDIR="$TMP_TMPDIR" \
      USER="${USER:-e2e}" LOGNAME="${LOGNAME:-e2e}" SHELL="${SHELL:-/bin/bash}" \
      LANG="${LANG:-C.UTF-8}" LC_ALL="${LC_ALL:-C.UTF-8}" \
      "$CODEX_BIN" exec --ephemeral --ignore-user-config --ignore-rules --strict-config \
      --skip-git-repo-check --sandbox workspace-write \
      -c 'approval_policy="never"' --output-schema "$schema_path" \
      -C "$TMP_WORKSPACE" -o "$result_path" -; then
    redacted_log_tail "$log_path"
    die "Codex turn failed or timed out"
  fi
  [[ -s "$result_path" ]] || die "Codex turn did not produce structured output"
  "$PYTHON_BIN" - "$result_path" <<'PY'
import json
import sys
json.loads(open(sys.argv[1], encoding="utf-8").read())
PY
}

write_initial_prompt() {
  "$PYTHON_BIN" - "$RUNTIME_INITIAL_PROMPT" "$1" "$PROJECT_ROOT" <<'PY'
import sys
from pathlib import Path

source, destination, project_root = map(Path, sys.argv[1:])
text = source.read_text(encoding="utf-8").replace("__PROJECT_ROOT__", str(project_root))
destination.write_text(text, encoding="utf-8")
PY
}

write_resume_prompt() {
  local destination=$1
  local project=$2
  local approved_stage=$3
  local approved_files=$4
  local approved_digest=$5
  local next_gate=$6
  local next_artifact=$7
  local instructions=$8
  "$PYTHON_BIN" - "$destination" "$project" "$approved_stage" "$approved_files" \
    "$approved_digest" "$next_gate" "$next_artifact" "$instructions" <<'PY'
import sys
from pathlib import Path

destination = Path(sys.argv[1])
project, approved_stage, approved_files, digest, next_gate, next_artifact, instructions = sys.argv[2:]
text = f"""使用 $video-script-studio 继续现有项目 `{project}`。这是新的独立会话，必须先运行 status，以 project.yaml 和状态命令为准；读取当前阶段需要的产物，不得改写已经批准的上游文件。

我已逐字审阅 `{approved_files}`，其组合 SHA-256 为 `{digest}`。我现在明确批准这一个精确版本的 `{approved_stage}` 阶段；任何字节变化都会使本批准失效。请先执行该阶段的 approve 命令，再继续。

{instructions}

本轮只推进到 `{next_gate}` 确认门：创建并展示 `{next_artifact}` 所需内容，但不得批准 `{next_gate}`，不得跨越后续确认门。最终严格输出 JSON：`project_path` 为真实绝对路径，`awaiting_gate` 为 `{next_gate}`，`artifact` 为 `{next_artifact}`。
"""
destination.write_text(text, encoding="utf-8")
PY
}

write_final_prompt() {
  local destination=$1
  local project=$2
  local script_digest=$3
  "$PYTHON_BIN" - "$destination" "$project" "$script_digest" <<'PY'
import sys
from pathlib import Path

destination = Path(sys.argv[1])
project, digest = sys.argv[2:]
text = f"""使用 $video-script-studio 继续现有项目 `{project}`。必须先运行 status，以 project.yaml 和状态命令为准；不得修改已批准的 brief.md、research.md、sources.md、concepts.md 或 outline.md。

我已逐字审阅 `script.md`，其 SHA-256 为 `{digest}`。我现在明确批准这个精确脚本版本；任何字节变化都会使批准失效。请执行 script approve，然后完成 storyboard.md、assets.md、publish.md 和独立 review.md。

必须兑现已批准的视觉随笔契约：使用稳定场景编号 S01—S05；轮胎纹理拓印的可见试做；油墨糊掉路径并撕裂纸面的失败；裂痕由失败痕迹变成路线；车轮空转、滚墨、撕纸等环境声；至少三处明确写“无旁白”，旁白只补不可见的意义转变。不得复制 Gawx 的具体作品、标题或措辞，不得生成媒体或发布。

按 visual-essay canonical weights 做独立评审：全部七个 base gates 为 true，每个核心维度至少 7，总分至少 80，revision_count 不超过 2。提取 sources.md 的 JSON manifest 并实际运行来源校验；实际运行完整 pack 校验，解析 JSON 并确认 valid=true；只有这样才能运行 complete。最终严格输出要求的 JSON，project_path 必须是真实绝对路径，primary_type 为 visual-essay，stage 为 complete，validation_valid 为 true，saved_artifacts 列出精确十个 Markdown 产物，unresolved_warnings 使用真实校验警告，next_action 说明可进入人工拍摄验收。
"""
destination.write_text(text, encoding="utf-8")
PY
}

combined_sha256() {
  "$PYTHON_BIN" - "$@" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
for raw in sys.argv[1:]:
    path = Path(raw)
    digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes())
print(digest.hexdigest())
PY
}

assert_approved_unchanged() {
  local expected=$1
  shift
  local actual
  actual="$(combined_sha256 "$@")"
  [[ "$actual" == "$expected" ]] || die "an approved artifact changed after approval"
}

assert_gate_result() {
  local result=$1
  local project=$2
  local gate=$3
  local artifact=$4
  "$PYTHON_BIN" - "$result" "$project" "$gate" "$artifact" <<'PY'
import json
import sys
from pathlib import Path

result_path, project_path, gate, artifact = sys.argv[1:]
value = json.loads(Path(result_path).read_text(encoding="utf-8"))
if set(value) != {"project_path", "awaiting_gate", "artifact"}:
    raise SystemExit("gate result has unexpected fields")
if Path(value["project_path"]).resolve() != Path(project_path).resolve():
    raise SystemExit("gate result project path mismatch")
if value["awaiting_gate"] != gate or value["artifact"] != artifact:
    raise SystemExit("gate result does not match the expected stop point")
PY
}

assert_status_stage() {
  local project=$1
  local expected=$2
  local status_file=$3
  "$PYTHON_BIN" "$INSTALLED_SKILL/scripts/state_manager.py" status --project "$project" >"$status_file"
  "$PYTHON_BIN" - "$status_file" "$expected" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("stage") != sys.argv[2]:
    raise SystemExit("project stopped at the wrong stage")
PY
}

TURN1_PROMPT="$RUN_ROOT/turn-1.md"
TURN1_RESULT="$RUN_ROOT/turn-1.json"
write_initial_prompt "$TURN1_PROMPT"
run_codex_turn "$TURN1_PROMPT" "$RUNTIME_GATE_SCHEMA" "$TURN1_RESULT" "$TMP_LOGS/turn-1.log"

PROJECT="$($PYTHON_BIN - "$TURN1_RESULT" "$PROJECT_ROOT" <<'PY'
import json
import sys
from pathlib import Path

value = json.load(open(sys.argv[1], encoding="utf-8"))
project_root = Path(sys.argv[2]).resolve()
project = Path(value["project_path"]).resolve()
if project.parent != project_root or not project.is_dir() or project.is_symlink():
    raise SystemExit("reported project path escapes the fresh project root")
projects = [path.resolve() for path in project_root.iterdir() if path.is_dir()]
if projects != [project]:
    raise SystemExit("expected exactly one freshly created project")
print(project)
PY
)"
assert_gate_result "$TURN1_RESULT" "$PROJECT" brief brief.md
assert_status_stage "$PROJECT" brief_pending "$RUN_ROOT/status-1.json"
[[ -s "$PROJECT/brief.md" ]] || die "brief artifact is empty"
BRIEF_HASH="$(combined_sha256 "$PROJECT/brief.md")"

TURN2_PROMPT="$RUN_ROOT/turn-2.md"
TURN2_RESULT="$RUN_ROOT/turn-2.json"
write_resume_prompt "$TURN2_PROMPT" "$PROJECT" brief "brief.md" "$BRIEF_HASH" research research.md \
  "记录本项目不需要外部研究的明确理由；写 research.md 与严格 JSON frontmatter 的 sources.md，sources/claims 均为空；把项目状态中的 research 与 sources disposition 从 undecided 改为明确的 not-required。完成后停止。"
run_codex_turn "$TURN2_PROMPT" "$RUNTIME_GATE_SCHEMA" "$TURN2_RESULT" "$TMP_LOGS/turn-2.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_gate_result "$TURN2_RESULT" "$PROJECT" research research.md
assert_status_stage "$PROJECT" research_pending "$RUN_ROOT/status-2.json"
RESEARCH_HASH="$(combined_sha256 "$PROJECT/research.md" "$PROJECT/sources.md")"

TURN3_PROMPT="$RUN_ROOT/turn-3.md"
TURN3_RESULT="$RUN_ROOT/turn-3.json"
write_resume_prompt "$TURN3_PROMPT" "$PROJECT" research "research.md + sources.md" "$RESEARCH_HASH" concept concepts.md \
  "生成 A/B/C 三个实质不同且可拍的概念，逐项写观看理由、叙事引擎、转折、声音、难度和风险；明确标记方案 B 为“双重轨迹”，但不要替用户批准。完成后停止。"
run_codex_turn "$TURN3_PROMPT" "$RUNTIME_GATE_SCHEMA" "$TURN3_RESULT" "$TMP_LOGS/turn-3.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_gate_result "$TURN3_RESULT" "$PROJECT" concept concepts.md
assert_status_stage "$PROJECT" concept_pending "$RUN_ROOT/status-3.json"
CONCEPT_HASH="$(combined_sha256 "$PROJECT/concepts.md")"

TURN4_PROMPT="$RUN_ROOT/turn-4.md"
TURN4_RESULT="$RUN_ROOT/turn-4.json"
write_resume_prompt "$TURN4_PROMPT" "$PROJECT" concept "concepts.md（明确选择方案 B：双重轨迹）" "$CONCEPT_HASH" outline outline.md \
  "按观众体验节点写 outline.md，至少五个场景，包含试做、失败、调整、视觉母题变化、环境声和恢复；不要写长篇解释性旁白。完成后停止。"
run_codex_turn "$TURN4_PROMPT" "$RUNTIME_GATE_SCHEMA" "$TURN4_RESULT" "$TMP_LOGS/turn-4.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_gate_result "$TURN4_RESULT" "$PROJECT" outline outline.md
assert_status_stage "$PROJECT" outline_pending "$RUN_ROOT/status-4.json"
OUTLINE_HASH="$(combined_sha256 "$PROJECT/outline.md")"

TURN5_PROMPT="$RUN_ROOT/turn-5.md"
TURN5_RESULT="$RUN_ROOT/turn-5.json"
write_resume_prompt "$TURN5_PROMPT" "$PROJECT" outline "outline.md" "$OUTLINE_HASH" script script.md \
  "写同时包含干净表演稿与制作执行稿的 script.md，并包含全部确定性必需标题及旁白克制段。用 visual-essay 五段 18/22/20/15/15 秒 payload 实际运行 estimate_duration.py，在预计时长段记录 90 秒结果。完成后停止。"
run_codex_turn "$TURN5_PROMPT" "$RUNTIME_GATE_SCHEMA" "$TURN5_RESULT" "$TMP_LOGS/turn-5.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_approved_unchanged "$OUTLINE_HASH" "$PROJECT/outline.md"
assert_gate_result "$TURN5_RESULT" "$PROJECT" script script.md
assert_status_stage "$PROJECT" script_pending "$RUN_ROOT/status-5.json"
SCRIPT_HASH="$(combined_sha256 "$PROJECT/script.md")"

TURN6_PROMPT="$RUN_ROOT/turn-6.md"
TURN6_RESULT="$RUN_ROOT/turn-6.json"
write_final_prompt "$TURN6_PROMPT" "$PROJECT" "$SCRIPT_HASH"
run_codex_turn "$TURN6_PROMPT" "$RUNTIME_FINAL_SCHEMA" "$TURN6_RESULT" "$TMP_LOGS/turn-6.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_approved_unchanged "$OUTLINE_HASH" "$PROJECT/outline.md"
assert_approved_unchanged "$SCRIPT_HASH" "$PROJECT/script.md"

"$PYTHON_BIN" - "$INSTALLED_SKILL" "$PROJECT" "$TURN6_RESULT" <<'PY'
import importlib
import json
import os
import re
import stat
import sys
from pathlib import Path

skill = Path(sys.argv[1])
project = Path(sys.argv[2]).resolve()
result = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
scripts = skill / "scripts"
sys.path.insert(0, str(scripts))
state_manager = importlib.import_module("state_manager")
validate_pack = importlib.import_module("validate_pack")
validate_sources = importlib.import_module("validate_sources")
estimate_duration = importlib.import_module("estimate_duration")

artifacts = {
    "brief.md", "research.md", "concepts.md", "outline.md", "script.md",
    "storyboard.md", "assets.md", "publish.md", "sources.md", "review.md",
}
expected_top = artifacts | {"project.yaml", "history", ".video-script-studio-state.lock"}
if {path.name for path in project.iterdir()} != expected_top:
    raise SystemExit("project topology is not exact")
for name in artifacts | {"project.yaml"}:
    path = project / name
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or not path.read_bytes().strip():
        raise SystemExit(f"unsafe or empty project file: {name}")
history = project / "history"
if history.is_symlink() or not history.is_dir():
    raise SystemExit("history topology is unsafe")

state = state_manager.load_state(project)
status = state_manager.status(project)
if status["stage"] != "complete" or state["stage"] != "complete":
    raise SystemExit("project did not complete")
if set(state["approvals"].values()) != {"approved"}:
    raise SystemExit("not every approval gate is approved")
if state["project"]["primary_type"] != "visual-essay" or state["project"]["profile_id"] is not None:
    raise SystemExit("project route or project-local profile contract is wrong")
if state["research"]["disposition"] == "undecided" or state["sources"]["disposition"] == "undecided":
    raise SystemExit("research disposition was not recorded")
if not re.fullmatch(r"[0-9a-f]{64}", state["completion_digest"]):
    raise SystemExit("completion digest is invalid")

sources_text = (project / "sources.md").read_text(encoding="utf-8")
parts = sources_text.split("---", 2)
if len(parts) != 3:
    raise SystemExit("sources frontmatter is missing")
manifest = json.loads(parts[1])
if manifest.get("research_required") is not False or manifest.get("sources") != [] or manifest.get("claims") != []:
    raise SystemExit("no-research source manifest is incorrect")
if not str(manifest.get("decision_reason", "")).strip():
    raise SystemExit("no-research reason is missing")
script_text = (project / "script.md").read_text(encoding="utf-8")
source_result = validate_sources.validate(manifest, script_text)
if not source_result["valid"] or re.search(r"\[C[0-9]+\]", script_text):
    raise SystemExit("source validation failed")

for heading in (
    "最终命题", "目标", "预计时长", "干净表演稿", "制作执行稿",
    "待人工确认事项", "可删段落", "短版本切点", "旁白克制",
):
    if not re.search(rf"(?m)^##[ \t]+{re.escape(heading)}[ \t]*$", script_text):
        raise SystemExit(f"script heading missing: {heading}")
if "90" not in script_text or "骑行" not in script_text or "版画" not in script_text:
    raise SystemExit("script does not preserve premise or duration")
storyboard = (project / "storyboard.md").read_text(encoding="utf-8")
for heading in ("可见行动", "视觉母题", "环境声"):
    if not re.search(rf"(?m)^##[ \t]+{re.escape(heading)}[ \t]*$", storyboard):
        raise SystemExit(f"storyboard heading missing: {heading}")
for phrase in ("轮胎", "拓印", "油墨", "撕裂", "裂痕", "车轮", "滚墨", "撕纸"):
    if phrase not in storyboard + script_text:
        raise SystemExit(f"visual essay beat missing: {phrase}")
if (storyboard + script_text).count("无旁白") < 3:
    raise SystemExit("voiceover is not demonstrably sparse")
scene_labels = set(re.findall(r"(?:场景|镜头|S)(?:[ \t#|:_-]*)(?:0?[1-9])", storyboard, re.I))
if len(scene_labels) < 5:
    raise SystemExit("fewer than five identifiable scenes were produced")

duration = estimate_duration.estimate({
    "primary_type": "visual-essay",
    "segments": [{"duration_seconds": value} for value in (18, 22, 20, 15, 15)],
})
if duration["estimated_seconds"] != 90 or duration["segment_count"] != 5:
    raise SystemExit("deterministic duration estimate is wrong")

review_text = (project / "review.md").read_text(encoding="utf-8")
review_parts = review_text.split("---", 2)
if len(review_parts) != 3:
    raise SystemExit("review frontmatter is missing")
review = json.loads(review_parts[1])
weights = {"visible_action": 20, "visual_storytelling": 20, "inner_outer_change": 15,
           "sound_design": 15, "voiceover_restraint": 15, "aesthetic_consistency": 15}
dimensions = review.get("core_dimensions", {})
if set(dimensions) != set(weights):
    raise SystemExit("review dimensions are wrong")
if any(value.get("weight") != weights[name] or value.get("score", -1) < 7
       for name, value in dimensions.items()):
    raise SystemExit("review weights or thresholds are wrong")
computed = sum(value["score"] * value["weight"] / 10 for value in dimensions.values())
if abs(computed - review.get("total_score", -1)) > 0.01 or computed < 80:
    raise SystemExit("review total is wrong")
if review.get("passed") is not True or not 0 <= review.get("revision_count", -1) <= 2:
    raise SystemExit("review completion fields are wrong")
if set(review.get("base_gates", {})) != set(validate_pack.BASE_GATES) or not all(review["base_gates"].values()):
    raise SystemExit("review base gates are wrong")

validation = validate_pack.validate_pack(project)
if not validation["valid"] or validation["checked_file_count"] != 11 or validation["source_count"] != 0 or validation["claim_count"] != 0:
    raise SystemExit("deterministic pack validation failed")
if validation["errors"]:
    raise SystemExit("deterministic pack validation returned errors")

if Path(result.get("project_path", "")).resolve() != project:
    raise SystemExit("final result path differs from real project")
if result.get("primary_type") != "visual-essay" or result.get("stage") != "complete" or result.get("validation_valid") is not True:
    raise SystemExit("final structured status is false")
saved_artifacts = result.get("saved_artifacts", [])
if len(saved_artifacts) != len(artifacts) or set(saved_artifacts) != artifacts:
    raise SystemExit("final artifact inventory is wrong")
if result.get("unresolved_warnings") != validation["warnings"]:
    raise SystemExit("final warnings differ from validator warnings")
if not all(marker in result.get("next_action", "") for marker in ("人工", "拍摄")):
    raise SystemExit("final next action is not an honest manual handoff")
PY

SOURCE_DIGEST_AFTER="$(tree_digest "$SOURCE_SKILL")"
AUTH_DIGEST_AFTER="$($PYTHON_BIN - "$ORIGINAL_AUTH" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
[[ "$SOURCE_DIGEST_BEFORE" == "$SOURCE_DIGEST_AFTER" ]] || die "repository skill changed during E2E"
[[ "$AUTH_DIGEST_BEFORE" == "$AUTH_DIGEST_AFTER" ]] || die "original authentication file changed during E2E"

printf '%s\n' "$SUCCESS_MARKER"
