#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
SOURCE_SKILL="$REPO_ROOT/skills/video-script-studio"
E2E_ROOT="$SOURCE_SKILL/tests/e2e"
INITIAL_PROMPT="$E2E_ROOT/visual-essay-prompt.md"
GATE_SCHEMA="$E2E_ROOT/gate-result.schema.json"
REVIEW_SCHEMA="$E2E_ROOT/review-result.schema.json"
FINAL_SCHEMA="$E2E_ROOT/expected-result.schema.json"
SUCCESS_MARKER="video-script-studio-e2e ok"
PREFLIGHT_MARKER="video-script-studio-e2e preflight ok"

die() {
  printf '%s\n' "video-script-studio-e2e: $*" >&2
  exit 1
}

official_validator_path() {
  local original_home="${HOME:?HOME is required to locate Codex dependencies}"
  local original_codex_home="${CODEX_HOME:-$original_home/.codex}"
  printf '%s\n' "$original_codex_home/skills/.system/skill-creator/scripts/quick_validate.py"
}

validate_official_validator() {
  local validator=$1
  command -v python3 >/dev/null 2>&1 || die "required command is unavailable: python3"
  python3 - "$validator" <<'PY'
import os
import stat
import sys
from pathlib import Path

validator = Path(sys.argv[1])
try:
    metadata = validator.lstat()
except OSError:
    raise SystemExit("official validator is unavailable or unsafe")
if (validator.resolve() != validator or validator.is_symlink()
        or not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022 or not os.access(validator, os.R_OK)):
    raise SystemExit("official validator is unavailable or unsafe")
PY
}

execute_official_validator() {
  local validator=$1
  local skill=$2
  local uv_bin
  uv_bin="$(command -v uv)" || die "required command is unavailable: uv"
  python3 - "$validator" "$skill" "$uv_bin" <<'PY'
import os
import subprocess
import sys
import tempfile
from pathlib import Path

validator, skill, uv_bin = sys.argv[1:]
try:
    with tempfile.TemporaryDirectory(prefix="video-script-studio-preflight-") as directory:
        root = Path(directory)
        paths = {
            "HOME": root / "home",
            "CODEX_HOME": root / "codex-home",
            "XDG_CONFIG_HOME": root / "xdg-config",
            "XDG_DATA_HOME": root / "xdg-data",
            "XDG_CACHE_HOME": root / "xdg-cache",
            "TMPDIR": root / "tmp",
        }
        for path in paths.values():
            path.mkdir(mode=0o700)
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONDONTWRITEBYTECODE": "1",
            **{name: str(path) for name, path in paths.items()},
        }
        completed = subprocess.run(
            [uv_bin, "run", "--with", "pyyaml", "python", validator, skill],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
except (OSError, subprocess.SubprocessError):
    raise SystemExit("official validator execution failed")
if completed.returncode != 0 or completed.stdout != b"Skill is valid!\n":
    raise SystemExit("official validator execution failed")
PY
}

static_preflight() {
  local validator
  validator="$(official_validator_path)"
  validate_official_validator "$validator"
  [[ -d "$SOURCE_SKILL/scripts" ]] || die "source skill is missing"
  [[ -f "$INITIAL_PROMPT" && -f "$GATE_SCHEMA" && -f "$REVIEW_SCHEMA" \
     && -f "$FINAL_SCHEMA" ]] \
    || die "E2E prompt or schema is missing"
  python3 - "$INITIAL_PROMPT" "$GATE_SCHEMA" "$REVIEW_SCHEMA" "$FINAL_SCHEMA" <<'PY'
import json
import sys
from pathlib import Path

prompt_path, gate_path, review_path, final_path = map(Path, sys.argv[1:])
prompt = prompt_path.read_text(encoding="utf-8")
required_prompt = (
    "$video-script-studio", "__PROJECT_ROOT__", "visual-essay", "骑行", "版画",
    "只创建并展示 brief.md", "不得批准 brief", "无外部事实主张",
)
if any(item not in prompt for item in required_prompt):
    raise SystemExit("initial prompt contract is incomplete")
for path in (gate_path, review_path, final_path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("type") != "object" or value.get("additionalProperties") is not False:
        raise SystemExit("result schema is not strict")
PY
  execute_official_validator "$validator" "$SOURCE_SKILL"
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
OFFICIAL_VALIDATOR="$ORIGINAL_CODEX_HOME/skills/.system/skill-creator/scripts/quick_validate.py"
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
BASELINE_ROOT="$RUN_ROOT/initializer-baseline"
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
  "$TMP_XDG_CACHE" "$TMP_TMPDIR" "$TMP_WORKSPACE" "$TMP_LOGS" "$PROJECT_ROOT" \
  "$BASELINE_ROOT"
"$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" TMPDIR="$TMP_TMPDIR" \
  GIT_CONFIG_NOSYSTEM=1 "$GIT_BIN" -c init.defaultBranch=main -C "$TMP_WORKSPACE" init -q
[[ ! -e "$TMP_WORKSPACE/AGENTS.md" && ! -e "$TMP_WORKSPACE/.codex" \
   && ! -e "$TMP_WORKSPACE/.agents" ]] || die "workspace isolation failed"

mkdir -m 700 "$TMP_CODEX_HOME/skills"
[[ ! -e "$TMP_CODEX_HOME/skills/video-script-studio" ]] \
  || die "target skill unexpectedly exists before installation"
INSTALLED_SKILL="$TMP_CODEX_HOME/skills/video-script-studio"
mkdir -m 700 "$INSTALLED_SKILL"
cp -R "$SOURCE_SKILL/." "$INSTALLED_SKILL/"
RUNTIME_INITIAL_PROMPT="$INSTALLED_SKILL/tests/e2e/visual-essay-prompt.md"
RUNTIME_GATE_SCHEMA="$INSTALLED_SKILL/tests/e2e/gate-result.schema.json"
RUNTIME_REVIEW_SCHEMA="$INSTALLED_SKILL/tests/e2e/review-result.schema.json"
RUNTIME_FINAL_SCHEMA="$INSTALLED_SKILL/tests/e2e/expected-result.schema.json"
RUNTIME_GATE_DIAGNOSTIC="$INSTALLED_SKILL/tests/e2e/gate_result_diagnostic.py"
RUNTIME_CODEX_FAILURE_DIAGNOSTIC="$INSTALLED_SKILL/tests/e2e/codex_failure_diagnostic.py"
RUNTIME_STATE_CONTRACT_DIAGNOSTIC="$INSTALLED_SKILL/tests/e2e/state_contract_diagnostic.py"
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
validate_official_validator "$OFFICIAL_VALIDATOR"
"$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" CODEX_HOME="$TMP_CODEX_HOME" \
  XDG_CONFIG_HOME="$TMP_XDG_CONFIG" XDG_DATA_HOME="$TMP_XDG_DATA" \
  XDG_CACHE_HOME="$TMP_XDG_CACHE" TMPDIR="$TMP_TMPDIR" \
  "$UV_BIN" run --with pyyaml python "$OFFICIAL_VALIDATOR" "$INSTALLED_SKILL" \
  >"$TMP_LOGS/official-validator.log" 2>&1 || die "official skill validation failed"
grep -Fxq "Skill is valid!" "$TMP_LOGS/official-validator.log" \
  || die "official validator success marker is missing"

BASELINE_PROJECT="$("$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" \
  CODEX_HOME="$TMP_CODEX_HOME" XDG_CONFIG_HOME="$TMP_XDG_CONFIG" \
  XDG_DATA_HOME="$TMP_XDG_DATA" XDG_CACHE_HOME="$TMP_XDG_CACHE" \
  TMPDIR="$TMP_TMPDIR" PYTHONDONTWRITEBYTECODE=1 \
  "$PYTHON_BIN" - "$INSTALLED_SKILL/scripts" "$BASELINE_ROOT" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from init_project import init_project

result = init_project(
    Path(sys.argv[2]),
    "双重轨迹：骑行与版画",
    "visual-essay",
    secondary_type="创作者纪录片",
    platform="YouTube 16:9",
)
print(result["path"])
PY
)"
[[ -d "$BASELINE_PROJECT" ]] || die "initializer baseline was not created"

# Authentication is deliberately untouched until all auth-free validation succeeds.
"$PYTHON_BIN" - "$ORIGINAL_AUTH" <<'PY'
import os
import stat
import sys
from pathlib import Path

auth = Path(sys.argv[1])
metadata = auth.lstat()
if (auth.is_symlink() or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077):
    raise SystemExit("authentication file is not a trusted regular file")
PY
AUTH_DIGEST_BEFORE="$($PYTHON_BIN - "$ORIGINAL_AUTH" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PY
)"
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

run_codex_turn() {
  local prompt_path=$1
  local schema_path=$2
  local result_path=$3
  local log_path=$4
  local exit_code=0
  if run_with_timeout "$TURN_TIMEOUT" "$log_path" "$prompt_path" \
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
    :
  else
    exit_code=$?
    local diagnostic
    diagnostic="$($PYTHON_BIN "$RUNTIME_CODEX_FAILURE_DIAGNOSTIC" "$exit_code" "$log_path")" \
      || die "codex_turn_diagnostic_failure"
    case "$diagnostic" in
      codex_turn_timeout|codex_turn_schema_error|codex_turn_structured_output_error|codex_turn_auth_error|codex_turn_rate_limit|codex_turn_network_error|codex_turn_nonzero)
        printf '%s\n' "$diagnostic" >&2
        ;;
      *)
        die "codex_turn_diagnostic_failure"
        ;;
    esac
    die "Codex turn failed; private log withheld"
  fi
  [[ -s "$result_path" ]] || die "Codex turn did not produce structured output"
  "$PYTHON_BIN" - "$result_path" <<'PY'
import json
import sys
json.loads(open(sys.argv[1], encoding="utf-8").read())
PY
}

write_gate_schema() {
  local destination=$1
  local gate=$2
  local artifact=$3
  "$PYTHON_BIN" - "$RUNTIME_GATE_SCHEMA" "$destination" "$gate" "$artifact" <<'PY'
import json
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:3])
gate, artifact = sys.argv[3:]
schema = json.loads(source.read_text(encoding="utf-8"))
gate_values = schema["properties"]["awaiting_gate"].get("enum", [])
artifact_values = schema["properties"]["artifact"].get("enum", [])
if gate not in gate_values or artifact not in artifact_values:
    raise SystemExit("gate schema requested an unsupported stop point")
schema["properties"]["awaiting_gate"] = {"enum": [gate]}
schema["properties"]["artifact"] = {"enum": [artifact]}
destination.write_text(
    json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
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

write_production_prompt() {
  local destination=$1
  local project=$2
  local script_digest=$3
  local skill_dir=$4
  "$PYTHON_BIN" - "$destination" "$project" "$script_digest" "$skill_dir" <<'PY'
import shlex
import sys
from pathlib import Path

destination = Path(sys.argv[1])
project, digest, skill_dir = sys.argv[2:]
approve_command = f"cd {shlex.quote(skill_dir)} && python3 scripts/state_manager.py approve --project {shlex.quote(project)} --stage script"
status_command = f"cd {shlex.quote(skill_dir)} && python3 scripts/state_manager.py status --project {shlex.quote(project)}"
text = f"""使用 $video-script-studio 继续现有项目 `{project}`。这是第六个全新临时会话。必须先运行 status，以 project.yaml 和状态命令为准；不得修改已批准的 brief.md、research.md、sources.md、concepts.md 或 outline.md。

我已逐字审阅 `script.md`，其 SHA-256 为 `{digest}`。我现在明确批准这个精确脚本版本；任何字节变化都会使批准失效。请执行 script approve，然后完成 storyboard.md、assets.md、publish.md。

“批准”必须是实际状态机动作，不是口头确认：先逐字运行 `{approve_command}`，确认批准命令退出码为 0；若失败必须停止，不得伪造回执。完成三个制作文件后，再次运行 status：逐字运行 `{status_command}`，解析 JSON，必须确认 stage 为 script_approved，且 approvals 中 brief、research、concept、outline、script 全部为 approved；否则停止，不得输出成功 JSON。

必须兑现已批准的视觉随笔契约：使用稳定场景编号 S01—S05；轮胎纹理拓印的可见试做；油墨糊掉路径并撕裂纸面的失败；裂痕由失败痕迹变成路线；车轮空转、滚墨、撕纸等环境声；至少三处明确写“无旁白”，旁白只补不可见的意义转变。storyboard.md 必须使用三个独立二级标题 ## 可见行动、## 视觉母题、## 环境声，每个标题下至少写一句实质内容。不得复制 Gawx 的具体作品、标题或措辞，不得生成媒体或发布。

本轮只承担制作作者职责：只改写 storyboard.md、assets.md、publish.md，绝对不得改写 review.md，不得评分，不得运行 complete。把独立评审留给下一个全新会话。最终严格输出 JSON：project_path 为真实绝对路径，stage 为 independent-review；authored_artifacts 必须是对象，精确写成 {{"storyboard":"storyboard.md","assets":"assets.md","publish":"publish.md"}}，不得使用数组。
"""
destination.write_text(text, encoding="utf-8")
PY
}

write_independent_review_prompt() {
  local destination=$1
  local project=$2
  local reviewer_session=$3
  "$PYTHON_BIN" - "$destination" "$project" "$reviewer_session" <<'PY'
import sys
from pathlib import Path

destination = Path(sys.argv[1])
project, reviewer_session = sys.argv[2:]
text = f"""使用 $video-script-studio 审核现有项目 `{project}`。这是独立的第七会话，身份仅为 reviewer，不是 brief、research、concepts、outline、script、storyboard、assets 或 publish 的作者。必须先运行 status，并逐字读取十个 Markdown 文件；不得修改除 review.md 与完成状态 project.yaml 以外的任何项目文件。

在 review.md 正文写入 `## 独立评审来源`，并逐字记录 `第七会话 reviewer_session: {reviewer_session}`，说明这是新的独立评审上下文；另写 `## 逐项证据`，逐字列出六个英文核心维度名和七个英文 base gate 名，每一项引用 S01—S05 中的具体场景证据，不能自评分式空泛通过。按 visual-essay canonical weights 评审：全部七个 base gates 为 true，每个核心维度至少 7，总分至少 80，revision_count 不超过 2，否则停止且不得完成。

提取 sources.md 的 JSON manifest 并实际运行来源校验；实际运行完整 pack 校验，解析 JSON 并确认 valid=true；只有这样才能运行 complete。最终严格输出要求的 JSON，project_path 必须是真实绝对路径，primary_type 为 visual-essay，stage 为 complete，validation_valid 为 true，saved_artifacts 列出精确十个 Markdown 产物，unresolved_warnings 使用真实校验警告，next_action 同时说明进入人工拍摄验收。
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

file_sha256() {
  "$PYTHON_BIN" - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

snapshot_project() {
  local project=$1
  local destination=$2
  "$PYTHON_BIN" - "$project" "$destination" <<'PY'
import hashlib
import json
import stat
import sys
from pathlib import Path

project, destination = map(Path, sys.argv[1:])
snapshot = {}
for path in sorted(project.rglob("*")):
    relative = path.relative_to(project).as_posix()
    metadata = path.lstat()
    if path.is_symlink():
        raise SystemExit("project snapshot encountered a symbolic link")
    if stat.S_ISREG(metadata.st_mode):
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif stat.S_ISDIR(metadata.st_mode):
        snapshot[relative + "/"] = "directory"
    else:
        raise SystemExit("project snapshot encountered an unsafe entry")
destination.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
PY
}

assert_only_paths_changed() {
  local before=$1
  local after=$2
  shift 2
  "$PYTHON_BIN" - "$before" "$after" "$@" <<'PY'
import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
allowed = set(sys.argv[3:])
changed = {
    name for name in set(before) | set(after)
    if before.get(name) != after.get(name)
}
unexpected = sorted(
    name for name in changed
    if name.rstrip("/").split("/", 1)[0] not in allowed
)
if unexpected:
    raise SystemExit("turn changed paths outside its allowlist")
PY
}

assert_matches_initializer_baseline() {
  local project=$1
  shift
  "$PYTHON_BIN" - "$BASELINE_PROJECT" "$project" "$@" <<'PY'
import sys
from pathlib import Path

baseline, project = map(Path, sys.argv[1:3])
changed = set(sys.argv[3:])
artifacts = {
    "brief.md", "research.md", "concepts.md", "outline.md", "script.md",
    "storyboard.md", "assets.md", "publish.md", "sources.md", "review.md",
}
if not changed <= artifacts:
    raise SystemExit("baseline assertion received an unknown artifact")
expected_top = artifacts | {"project.yaml", "history", ".video-script-studio-state.lock"}
if {path.name for path in project.iterdir()} != expected_top:
    raise SystemExit("project topology differs from the initializer contract")
if any((project / "history").iterdir()):
    raise SystemExit("history changed without an explicit reopen")
for name in artifacts:
    baseline_bytes = (baseline / name).read_bytes()
    actual_bytes = (project / name).read_bytes()
    if name in changed:
        if actual_bytes == baseline_bytes or not actual_bytes.strip():
            raise SystemExit("expected stage artifact still matches its initializer skeleton")
    elif actual_bytes != baseline_bytes:
        raise SystemExit("a downstream artifact changed before its stage")
PY
}

assert_exact_approvals() {
  local project=$1
  local expected_stage=$2
  local approved_csv=$3
  local status_file=$4
  "$PYTHON_BIN" "$INSTALLED_SKILL/scripts/state_manager.py" status \
    --project "$project" >"$status_file"
  local pack_file=""
  if [[ "$expected_stage" == "complete" ]]; then
    pack_file="$status_file.pack.json"
    "$PYTHON_BIN" "$INSTALLED_SKILL/scripts/validate_pack.py" \
      --project "$project" >"$pack_file"
  fi
  local diagnostic
  diagnostic="$($PYTHON_BIN "$RUNTIME_STATE_CONTRACT_DIAGNOSTIC" \
    "$status_file" "$expected_stage" "$approved_csv" ${pack_file:+"$pack_file"})" \
    || die "state_contract_diagnostic_failure"
  if [[ -n "$diagnostic" ]]; then
    while IFS= read -r code; do
      case "$code" in
        state_stage_mismatch|state_approval_map_mismatch|pack_error_*|pack_diagnostic_invalid|state_contract_diagnostic_failure)
          printf '%s\n' "$code" >&2
          ;;
        *)
          die "state_contract_diagnostic_failure"
          ;;
      esac
    done <<<"$diagnostic"
    die "state or pack contract failed"
  fi
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
  local diagnostics code
  diagnostics="$("$PYTHON_BIN" "$RUNTIME_GATE_DIAGNOSTIC" \
    "$result" "$project" "$gate" "$artifact")" \
    || die "gate_result_diagnostic_failure"
  [[ -z "$diagnostics" ]] && return 0
  while IFS= read -r code; do
    case "$code" in
      gate_result_invalid_json|gate_result_invalid_shape|gate_result_project_path_mismatch|gate_result_awaiting_gate_mismatch|gate_result_artifact_mismatch)
        printf '%s\n' "$code" >&2
        ;;
      *)
        die "gate_result_diagnostic_failure"
        ;;
    esac
  done <<<"$diagnostics"
  die "gate result contract failed"
}

assert_review_result() {
  local result=$1
  local project=$2
  "$PYTHON_BIN" - "$result" "$project" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if Path(value.get("project_path", "")).resolve() != Path(sys.argv[2]).resolve():
    raise SystemExit("production result project path mismatch")
if value.get("stage") != "independent-review":
    raise SystemExit("production turn did not stop for independent review")
artifacts = value.get("authored_artifacts", [])
if artifacts != {
    "storyboard": "storyboard.md",
    "assets": "assets.md",
    "publish": "publish.md",
}:
    raise SystemExit("production turn reported the wrong author artifacts")
PY
}

TURN1_PROMPT="$RUN_ROOT/turn-1.md"
TURN1_RESULT="$RUN_ROOT/turn-1.json"
TURN1_SCHEMA="$RUN_ROOT/turn-1.schema.json"
write_initial_prompt "$TURN1_PROMPT"
write_gate_schema "$TURN1_SCHEMA" brief brief.md
run_codex_turn "$TURN1_PROMPT" "$TURN1_SCHEMA" "$TURN1_RESULT" "$TMP_LOGS/turn-1.log"

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
assert_exact_approvals "$PROJECT" brief_pending "" "$RUN_ROOT/status-1.json"
assert_matches_initializer_baseline "$PROJECT" brief.md
"$PYTHON_BIN" - "$PROJECT/brief.md" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
headings = re.findall(r"(?m)^##[ \t]+(.+?)[ \t]*$", text)
expected = ["创作命题", "受众与目标", "制作边界", "事实与权利边界", "视觉随笔硬约束"]
if headings != expected:
    raise SystemExit("brief does not have the exact deterministic section contract")
for phrase in ("骑行", "版画", "90", "visual-essay", "无外部事实", "权利"):
    if phrase not in text:
        raise SystemExit("brief omitted a deterministic premise or boundary")
PY
BRIEF_HASH="$(combined_sha256 "$PROJECT/brief.md")"
SNAPSHOT1="$RUN_ROOT/snapshot-1.json"
snapshot_project "$PROJECT" "$SNAPSHOT1"

TURN2_PROMPT="$RUN_ROOT/turn-2.md"
TURN2_RESULT="$RUN_ROOT/turn-2.json"
TURN2_SCHEMA="$RUN_ROOT/turn-2.schema.json"
write_resume_prompt "$TURN2_PROMPT" "$PROJECT" brief "brief.md" "$BRIEF_HASH" research research.md \
  '记录本项目不需要外部研究的明确理由；写 research.md 与严格 JSON frontmatter 的 sources.md。frontmatter 必须是合法 JSON 对象且字段只能有这五项：{"schema_version":1,"research_required":false,"decision_reason":"本项目只使用用户给定的创作命题，不引入外部事实主张。","sources":[],"claims":[]}；不得省略 schema_version，不得把数字 1 写成字符串。把项目状态中的 research 与 sources disposition 从 undecided 改为明确的 not-required。完成后停止。'
write_gate_schema "$TURN2_SCHEMA" research research.md
run_codex_turn "$TURN2_PROMPT" "$TURN2_SCHEMA" "$TURN2_RESULT" "$TMP_LOGS/turn-2.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_gate_result "$TURN2_RESULT" "$PROJECT" research research.md
assert_exact_approvals "$PROJECT" research_pending "brief" "$RUN_ROOT/status-2.json"
assert_matches_initializer_baseline "$PROJECT" brief.md research.md sources.md
"$PYTHON_BIN" - "$INSTALLED_SKILL/scripts" "$PROJECT/sources.md" <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from validate_sources import validate

parts = Path(sys.argv[2]).read_text(encoding="utf-8").split("---", 2)
try:
    manifest = json.loads(parts[1]) if len(parts) == 3 else None
except (TypeError, ValueError):
    manifest = None
expected_fields = {
    "schema_version", "research_required", "decision_reason", "sources", "claims",
}
valid_shape = (
    isinstance(manifest, dict)
    and set(manifest) == expected_fields
    and type(manifest.get("schema_version")) is int
    and manifest.get("schema_version") == 1
    and manifest.get("research_required") is False
    and isinstance(manifest.get("decision_reason"), str)
    and bool(manifest.get("decision_reason", "").strip())
    and manifest.get("sources") == []
    and manifest.get("claims") == []
)
result = validate(manifest, "") if isinstance(manifest, dict) else {"valid": False}
if not valid_shape or result.get("valid") is not True:
    raise SystemExit("research stage source manifest is invalid")
PY
SNAPSHOT2="$RUN_ROOT/snapshot-2.json"
snapshot_project "$PROJECT" "$SNAPSHOT2"
assert_only_paths_changed "$SNAPSHOT1" "$SNAPSHOT2" project.yaml research.md sources.md
RESEARCH_HASH="$(combined_sha256 "$PROJECT/research.md" "$PROJECT/sources.md")"

TURN3_PROMPT="$RUN_ROOT/turn-3.md"
TURN3_RESULT="$RUN_ROOT/turn-3.json"
TURN3_SCHEMA="$RUN_ROOT/turn-3.schema.json"
write_resume_prompt "$TURN3_PROMPT" "$PROJECT" research "research.md + sources.md" "$RESEARCH_HASH" concept concepts.md \
  "生成恰好三个实质不同且可拍的概念，只能使用三个二级标题：## 方案 A、## 方案 B、## 方案 C。A 必须是‘纹理档案’，B 必须是‘双重轨迹’并标记推荐但待用户选择，C 必须是‘声音地图’；逐项写观看理由、叙事引擎、转折、声音、难度和风险，不要替用户批准。完成后停止。"
write_gate_schema "$TURN3_SCHEMA" concept concepts.md
run_codex_turn "$TURN3_PROMPT" "$TURN3_SCHEMA" "$TURN3_RESULT" "$TMP_LOGS/turn-3.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_gate_result "$TURN3_RESULT" "$PROJECT" concept concepts.md
assert_exact_approvals "$PROJECT" concept_pending "brief,research" "$RUN_ROOT/status-3.json"
assert_matches_initializer_baseline "$PROJECT" brief.md research.md sources.md concepts.md
SNAPSHOT3="$RUN_ROOT/snapshot-3.json"
snapshot_project "$PROJECT" "$SNAPSHOT3"
assert_only_paths_changed "$SNAPSHOT2" "$SNAPSHOT3" project.yaml concepts.md
CONCEPT_HASH="$(combined_sha256 "$PROJECT/concepts.md")"

TURN4_PROMPT="$RUN_ROOT/turn-4.md"
TURN4_RESULT="$RUN_ROOT/turn-4.json"
TURN4_SCHEMA="$RUN_ROOT/turn-4.schema.json"
write_resume_prompt "$TURN4_PROMPT" "$PROJECT" concept "concepts.md（明确选择方案 B：双重轨迹）" "$CONCEPT_HASH" outline outline.md \
  "按已选择的方案 B：双重轨迹写 outline.md，必须逐字记录‘方案 B：双重轨迹’，必须有 ## 体验节点 标题和稳定节点 S01—S05；明确写可见试做、失败、调整、视觉母题变化、环境声和主题恢复，不要写长篇解释性旁白。完成后停止。"
write_gate_schema "$TURN4_SCHEMA" outline outline.md
run_codex_turn "$TURN4_PROMPT" "$TURN4_SCHEMA" "$TURN4_RESULT" "$TMP_LOGS/turn-4.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_gate_result "$TURN4_RESULT" "$PROJECT" outline outline.md
assert_exact_approvals "$PROJECT" outline_pending "brief,research,concept" "$RUN_ROOT/status-4.json"
assert_matches_initializer_baseline "$PROJECT" brief.md research.md sources.md concepts.md outline.md
SNAPSHOT4="$RUN_ROOT/snapshot-4.json"
snapshot_project "$PROJECT" "$SNAPSHOT4"
assert_only_paths_changed "$SNAPSHOT3" "$SNAPSHOT4" project.yaml outline.md
OUTLINE_HASH="$(combined_sha256 "$PROJECT/outline.md")"

DURATION_INPUT="$RUN_ROOT/duration-input.json"
DURATION_RESULT="$RUN_ROOT/duration-result.json"
"$PYTHON_BIN" - "$DURATION_INPUT" <<'PY'
import json
import sys
from pathlib import Path

payload = {
    "primary_type": "visual-essay",
    "segments": [
        {"id": scene, "duration_seconds": duration}
        for scene, duration in zip(("S01", "S02", "S03", "S04", "S05"), (18, 22, 20, 15, 15))
    ],
}
Path(sys.argv[1]).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
PY
"$ENV_BIN" -i PATH="$ISOLATED_PATH" HOME="$TMP_HOME" TMPDIR="$TMP_TMPDIR" \
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" "$INSTALLED_SKILL/scripts/estimate_duration.py" \
  --input "$DURATION_INPUT" >"$DURATION_RESULT"
"$PYTHON_BIN" - "$DURATION_RESULT" <<'PY'
import json
import sys
from pathlib import Path

expected = {
    "primary_type": "visual-essay",
    "estimated_seconds": 90,
    "estimated_minutes": 1.5,
    "diagnostics": [],
    "segment_count": 5,
}
if json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) != expected:
    raise SystemExit("copied estimator CLI returned an unexpected result")
PY
DURATION_INPUT_HASH="$(file_sha256 "$DURATION_INPUT")"
DURATION_RESULT_HASH="$(file_sha256 "$DURATION_RESULT")"

TURN5_PROMPT="$RUN_ROOT/turn-5.md"
TURN5_RESULT="$RUN_ROOT/turn-5.json"
TURN5_SCHEMA="$RUN_ROOT/turn-5.schema.json"
write_resume_prompt "$TURN5_PROMPT" "$PROJECT" outline "outline.md" "$OUTLINE_HASH" script script.md \
  "写同时包含干净表演稿与制作执行稿的 script.md。必须按顺序使用 ## 最终命题、## 目标、## 预计时长、## 干净表演稿、## 制作执行稿、## 待人工确认事项、## 可删段落、## 短版本切点、## 旁白克制；每个标题下至少写一句实质内容，没有待办时在待人工确认事项下写“无待办”，不得留空。读取 harness 已用复制版 estimator CLI 生成的 $DURATION_INPUT 和 ${DURATION_RESULT}；在 ## 预计时长 中逐字记录 duration_input_sha256: ${DURATION_INPUT_HASH}、duration_result_sha256: ${DURATION_RESULT_HASH}、estimated_seconds: 90、segment_count: 5，以及五行 S01 duration_seconds: 18、S02 duration_seconds: 22、S03 duration_seconds: 20、S04 duration_seconds: 15、S05 duration_seconds: 15。完成后停止。"
write_gate_schema "$TURN5_SCHEMA" script script.md
run_codex_turn "$TURN5_PROMPT" "$TURN5_SCHEMA" "$TURN5_RESULT" "$TMP_LOGS/turn-5.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_approved_unchanged "$OUTLINE_HASH" "$PROJECT/outline.md"
assert_gate_result "$TURN5_RESULT" "$PROJECT" script script.md
assert_exact_approvals "$PROJECT" script_pending "brief,research,concept,outline" "$RUN_ROOT/status-5.json"
assert_matches_initializer_baseline "$PROJECT" brief.md research.md sources.md concepts.md outline.md script.md
"$PYTHON_BIN" - "$INSTALLED_SKILL/scripts" "$PROJECT/script.md" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from validate_pack import SCRIPT_HEADINGS, _heading_sections, _meaningful

sections = _heading_sections(Path(sys.argv[2]).read_text(encoding="utf-8"))
for heading in (*SCRIPT_HEADINGS, "旁白克制"):
    values = sections.get(heading)
    if not values:
        raise SystemExit("script stage is missing a required section")
    if not any(_meaningful(value) for value in values):
        raise SystemExit("script stage contains an empty required section")
PY
SNAPSHOT5="$RUN_ROOT/snapshot-5.json"
snapshot_project "$PROJECT" "$SNAPSHOT5"
assert_only_paths_changed "$SNAPSHOT4" "$SNAPSHOT5" project.yaml script.md
SCRIPT_HASH="$(combined_sha256 "$PROJECT/script.md")"

TURN6_PROMPT="$RUN_ROOT/turn-6.md"
TURN6_RESULT="$RUN_ROOT/turn-6.json"
write_production_prompt "$TURN6_PROMPT" "$PROJECT" "$SCRIPT_HASH" "$INSTALLED_SKILL"
run_codex_turn "$TURN6_PROMPT" "$RUNTIME_REVIEW_SCHEMA" "$TURN6_RESULT" "$TMP_LOGS/turn-6.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_approved_unchanged "$OUTLINE_HASH" "$PROJECT/outline.md"
assert_approved_unchanged "$SCRIPT_HASH" "$PROJECT/script.md"
assert_review_result "$TURN6_RESULT" "$PROJECT"
assert_exact_approvals "$PROJECT" script_approved "brief,research,concept,outline,script" "$RUN_ROOT/status-6.json"
assert_matches_initializer_baseline "$PROJECT" brief.md research.md sources.md concepts.md outline.md script.md storyboard.md assets.md publish.md
"$PYTHON_BIN" - "$INSTALLED_SKILL/scripts" "$PROJECT/storyboard.md" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from validate_pack import ROUTE_ANCHORS, _heading_sections, _meaningful

sections = _heading_sections(Path(sys.argv[2]).read_text(encoding="utf-8"))
for heading in ROUTE_ANCHORS["visual-essay"]["storyboard.md"]:
    values = sections.get(heading)
    if not values or not any(_meaningful(value) for value in values):
        raise SystemExit("storyboard stage is missing a substantive route anchor")
PY
SNAPSHOT6="$RUN_ROOT/snapshot-6.json"
snapshot_project "$PROJECT" "$SNAPSHOT6"
assert_only_paths_changed "$SNAPSHOT5" "$SNAPSHOT6" project.yaml storyboard.md assets.md publish.md

REVIEWER_SESSION="turn-7-independent-$(combined_sha256 "$TURN6_RESULT")"
TURN7_PROMPT="$RUN_ROOT/turn-7.md"
TURN7_RESULT="$RUN_ROOT/turn-7.json"
write_independent_review_prompt "$TURN7_PROMPT" "$PROJECT" "$REVIEWER_SESSION"
run_codex_turn "$TURN7_PROMPT" "$RUNTIME_FINAL_SCHEMA" "$TURN7_RESULT" "$TMP_LOGS/turn-7.log"
assert_approved_unchanged "$BRIEF_HASH" "$PROJECT/brief.md"
assert_approved_unchanged "$RESEARCH_HASH" "$PROJECT/research.md" "$PROJECT/sources.md"
assert_approved_unchanged "$CONCEPT_HASH" "$PROJECT/concepts.md"
assert_approved_unchanged "$OUTLINE_HASH" "$PROJECT/outline.md"
assert_approved_unchanged "$SCRIPT_HASH" "$PROJECT/script.md"
SNAPSHOT7="$RUN_ROOT/snapshot-7.json"
snapshot_project "$PROJECT" "$SNAPSHOT7"
assert_only_paths_changed "$SNAPSHOT6" "$SNAPSHOT7" project.yaml review.md
assert_exact_approvals "$PROJECT" complete "brief,research,concept,outline,script" "$RUN_ROOT/status-7.json"
assert_matches_initializer_baseline "$PROJECT" brief.md research.md sources.md concepts.md outline.md script.md storyboard.md assets.md publish.md review.md

"$PYTHON_BIN" - "$INSTALLED_SKILL" "$PROJECT" "$TURN7_RESULT" "$DURATION_INPUT" \
  "$DURATION_RESULT" "$DURATION_INPUT_HASH" "$DURATION_RESULT_HASH" \
  "$REVIEWER_SESSION" <<'PY'
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
duration_input_path = Path(sys.argv[4])
duration_result_path = Path(sys.argv[5])
duration_input_hash, duration_result_hash, reviewer_session = sys.argv[6:9]
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
expected_project = {
    "title": "双重轨迹：骑行与版画",
    "primary_type": "visual-essay",
    "secondary_type": "创作者纪录片",
    "platform": "YouTube 16:9",
    "profile_id": None,
}
if any(state["project"].get(key) != value for key, value in expected_project.items()):
    raise SystemExit("project metadata differs from the diagnosed brief")
if state["research"]["disposition"] == "undecided" or state["sources"]["disposition"] == "undecided":
    raise SystemExit("research disposition was not recorded")
if not re.fullmatch(r"[0-9a-f]{64}", state["completion_digest"]):
    raise SystemExit("completion digest is invalid")

brief_text = (project / "brief.md").read_text(encoding="utf-8")
brief_headings = re.findall(r"(?m)^##[ \t]+(.+?)[ \t]*$", brief_text)
if brief_headings != ["创作命题", "受众与目标", "制作边界", "事实与权利边界", "视觉随笔硬约束"]:
    raise SystemExit("brief contract changed after its gate")

concepts_text = (project / "concepts.md").read_text(encoding="utf-8")
concept_headings = re.findall(r"(?m)^##[ \t]+(.+?)[ \t]*$", concepts_text)
if concept_headings != ["方案 A", "方案 B", "方案 C"]:
    raise SystemExit("concepts are not exactly A/B/C")
sections = re.split(r"(?m)^##[ \t]+方案 [ABC][ \t]*$", concepts_text)[1:]
required_fields = ("观看理由", "叙事引擎", "转折", "声音", "难度", "风险")
for section, unique_marker in zip(sections, ("纹理档案", "双重轨迹", "声音地图")):
    if unique_marker not in section or any(field not in section for field in required_fields):
        raise SystemExit("concepts are not materially distinct and fully specified")
if "推荐" not in sections[1] or "待用户选择" not in sections[1]:
    raise SystemExit("B is not the pending recommendation")

outline_text = (project / "outline.md").read_text(encoding="utf-8")
if not re.search(r"(?m)^##[ \t]+体验节点[ \t]*$", outline_text):
    raise SystemExit("outline is not organized by experience nodes")
for marker in ("方案 B：双重轨迹", "S01", "S02", "S03", "S04", "S05", "试做", "失败", "环境声", "恢复"):
    if marker not in outline_text:
        raise SystemExit("outline omitted a required visible experience beat")

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

def file_hash(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()

duration_input = json.loads(duration_input_path.read_text(encoding="utf-8"))
duration_result = json.loads(duration_result_path.read_text(encoding="utf-8"))
expected_duration_result = {
    "primary_type": "visual-essay", "estimated_seconds": 90,
    "estimated_minutes": 1.5, "diagnostics": [], "segment_count": 5,
}
if file_hash(duration_input_path) != duration_input_hash or file_hash(duration_result_path) != duration_result_hash:
    raise SystemExit("persisted duration evidence changed")
if estimate_duration.estimate(duration_input) != expected_duration_result or duration_result != expected_duration_result:
    raise SystemExit("persisted duration evidence does not come from the copied estimator")
for marker in (
    f"duration_input_sha256: {duration_input_hash}",
    f"duration_result_sha256: {duration_result_hash}",
    "estimated_seconds: 90", "segment_count: 5",
    "S01 duration_seconds: 18", "S02 duration_seconds: 22",
    "S03 duration_seconds: 20", "S04 duration_seconds: 15",
    "S05 duration_seconds: 15",
):
    if marker not in script_text:
        raise SystemExit("script timing is not tied to persisted estimator evidence")

review_text = (project / "review.md").read_text(encoding="utf-8")
review_parts = review_text.split("---", 2)
if len(review_parts) != 3:
    raise SystemExit("review frontmatter is missing")
review = json.loads(review_parts[1])
weights = {"visible_action": 20, "visual_storytelling": 20, "inner_outer_change": 15,
           "sound_design": 15, "voiceover_restraint": 15, "aesthetic_consistency": 15}
if not re.search(r"(?m)^##[ \t]+独立评审来源[ \t]*$", review_text):
    raise SystemExit("review provenance heading is missing")
if f"第七会话 reviewer_session: {reviewer_session}" not in review_text:
    raise SystemExit("review was not produced by the separate reviewer context")
review_body = review_parts[2]
if not re.search(r"(?m)^##[ \t]+逐项证据[ \t]*$", review_body):
    raise SystemExit("independent review evidence section is missing")
evidence_terms = set(weights) | set(validate_pack.BASE_GATES)
if any(term not in review_body for term in evidence_terms):
    raise SystemExit("independent review does not cite every scored dimension and gate")
if any(scene not in review_body for scene in ("S01", "S02", "S03", "S04", "S05")):
    raise SystemExit("independent review does not cite concrete scene evidence")
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
