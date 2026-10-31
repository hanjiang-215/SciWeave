#!/usr/bin/env sh
# Install the researcher suite on the researcher's own machine.
#
# Two halves, and they go to different places on purpose:
#
#   * the kit (runtime, service templates, libs, agent definitions, systemd
#     units) goes to ${SCIWEAVE_TASK_AGENT_HOME}, via deploy-task-agent/install.sh;
#   * the skills go to ${SCIWEAVE_RESEARCHER_SKILLS_HOME}, where the researcher's
#     *personal* Agent (Codex, WorkBuddy, whatever harness) reads them.
#
# The second half is deliberately NOT installed into the kit directory. The
# worker's own model loop loads skills from SCIWEAVE_SKILLS_PATH, and a worker
# that can read "how to deploy and reconfigure this kit" is a worker that can
# redeploy itself out of the definition the researcher gave it. Keeping the two
# directories apart is the whole point (runtime/src/work_agent_runtime/skills.py).
#
# Idempotent: re-running replaces code and skills in place and never touches an
# existing .env, WORKER_HOME or SQLite file.
set -eu

SOURCE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
KIT_HOME="${SCIWEAVE_TASK_AGENT_HOME:-$HOME/.sciweave/task-agent}"
SKILLS_HOME="${SCIWEAVE_RESEARCHER_SKILLS_HOME:-$HOME/.sciweave/researcher-skills}"

if [ ! -d "$SOURCE/deploy-task-agent" ]; then
  echo "deploy-task-agent/ is missing: this zip is incomplete" >&2
  exit 65
fi

# 1. The kit.
sh "$SOURCE/deploy-task-agent/install.sh"

# 2. The researcher's skills, flat: <skills-home>/<skill>/SKILL.md.
#    fast-agent's registry only descends one level, so a nested layout loads
#    zero skills and reports nothing (SkillRegistry._load_directory).
mkdir -p "$SKILLS_HOME"
for skill in install-suite upgrade-suite register-instance audit-buffer \
             use-research-map use-research-wiki promote-draft push-task-agent-to-rework; do
  if [ ! -f "$SOURCE/$skill/SKILL.md" ]; then
    echo "missing $skill/SKILL.md: this zip is incomplete" >&2
    exit 65
  fi
  rm -rf "${SKILLS_HOME:?}/$skill"
  cp -R "$SOURCE/$skill" "$SKILLS_HOME/$skill"
done

# The deployment skills travel with the kit they describe, and stay there.
# They are pointed at separately below rather than copied here, so the two
# audiences stay distinguishable in the harness configuration.

echo
echo "kit installed at      $KIT_HOME"
echo "researcher skills at  $SKILLS_HOME"
echo
echo "next:"
echo "  1. fill $KIT_HOME/.env (see .env.example; it was copied for you if absent)"
echo "  2. point your own harness at both skill directories, e.g. in the harness config:"
echo "       $SKILLS_HOME"
echo "       $SOURCE/deploy-task-agent/deploy-task-agent-skills"
if command -v systemctl >/dev/null 2>&1; then
  echo "  3. systemctl --user enable --now sciweave-task-agent-subscriber.service"
else
  echo "  3. (no systemd) start the gateway roles by hand: $KIT_HOME/bin/start-mcp and $KIT_HOME/bin/start-subscriber"
fi
echo "  4. ask your Agent to run the 'register-instance' skill before expecting a handoff"
echo
echo "Do NOT add either directory to SCIWEAVE_SKILLS_PATH: that is the worker's own"
echo "skill list, and the worker must not be able to redeploy itself."
