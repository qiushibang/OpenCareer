#!/bin/sh
# 容器启动前的一次性兜底：建数据目录、注册 career MCP、放好技能包，然后 exec Dockerfile 里的 CMD。
# 幂等：所有写入都是「不存在才写」，重启不会覆盖朋友们的数据。
set -eu

STATE_DIR="${COWORKER_STATE_DIR:-/data/state}"
CAREER_DIR="${CAREER_DATA_DIR:-/data/career}"
PRIVATE_DIR="${CAREER_PRIVATE_DIR:-/data/private}"
WORKSPACE="${OPENCAR_ALPHA_WORKSPACE:-/data/workspace}"
BUNDLED_SKILLS_DIR="${OPENCAR_BUNDLED_SKILLS_DIR:-/app/skills-bundled}"

mkdir -p "$STATE_DIR" "$CAREER_DIR" "$PRIVATE_DIR" "$WORKSPACE"

# career 工具链走全局 MCP 配置（$STATE_DIR/mcp.json）而不是 workspace 的 .coworker/mcp.json：
# 后者要求先「信任该 workspace」，服务模式下没人去点那个确认。
if [ ! -f "$STATE_DIR/mcp.json" ]; then
  cp /app/deploy/mcp.container.json "$STATE_DIR/mcp.json"
fi

# 镜像内置 Skill 属于受管运行时文件，每次启动同步；用户自行安装的其他 Skill 保留。
SKILLS_DIR="$STATE_DIR/skills"
SKILLS_MANIFEST="$STATE_DIR/.bundled-skills-manifest"
SKILLS_MANIFEST_TMP="$STATE_DIR/.bundled-skills-manifest.tmp"
if [ -d "$BUNDLED_SKILLS_DIR" ]; then
  mkdir -p "$SKILLS_DIR"
  : > "$SKILLS_MANIFEST_TMP"
  for source in "$BUNDLED_SKILLS_DIR"/*; do
    [ -f "$source/SKILL.md" ] || continue
    name="$(basename "$source")"
    printf '%s\n' "$name" >> "$SKILLS_MANIFEST_TMP"
  done

  if [ -f "$SKILLS_MANIFEST" ]; then
    while IFS= read -r name; do
      case "$name" in
        ""|"."|".."|*/*|*\\*)
          echo "[entrypoint] invalid bundled Skill manifest entry" >&2
          exit 1
          ;;
      esac
      if ! grep -Fxq "$name" "$SKILLS_MANIFEST_TMP"; then
        rm -rf "$SKILLS_DIR/$name"
      fi
    done < "$SKILLS_MANIFEST"
  else
    # Upgrade from deployments that copied bundled Skills without a manifest.
    rm -rf \
      "$SKILLS_DIR/career-application-packet" \
      "$SKILLS_DIR/career-tailored-resume"
  fi

  for source in "$BUNDLED_SKILLS_DIR"/*; do
    [ -f "$source/SKILL.md" ] || continue
    name="$(basename "$source")"
    rm -rf "$SKILLS_DIR/$name"
    cp -R "$source" "$SKILLS_DIR/$name"
  done
  mv "$SKILLS_MANIFEST_TMP" "$SKILLS_MANIFEST"
fi

# 可选：首次启动灌 3 条示例岗位，免得朋友打开是一片空白（OPENCAR_SEED_DEMO=1 才做）。
if [ "${OPENCAR_SEED_DEMO:-0}" = "1" ] && [ ! -f "$STATE_DIR/.demo-seeded" ]; then
  if python /app/scripts/seed_alpha_demo.py; then
    : > "$STATE_DIR/.demo-seeded"
  else
    echo "[entrypoint] demo seeding failed, continuing without it" >&2
  fi
fi

# 模型可以按人/按环境切换，但 CMD 保持固定形态，所以在这里追加参数。
if [ -n "${OPENCAR_MODEL:-}" ]; then
  set -- "$@" --model "$OPENCAR_MODEL"
fi

echo "[entrypoint] starting: $*"
exec "$@"
