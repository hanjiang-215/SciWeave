#!/usr/bin/env sh
# One-command release: cut a suite release from the LOCAL develop branch.
#
# "From local develop" is literal: the tag and the release are pinned to whatever
# local `develop` points at right now. But a stale local develop would silently
# ship old code, so this script first syncs local develop with origin/develop
# (fast-forward only) and refuses to continue if they have diverged. Then it
# packs the two suites and hands off to publish.sh.
#
# Steps:
#   1. verify we are on a clean-enough tree and local develop exists;
#   2. fetch origin/develop and fast-forward local develop to it
#      (SKIP_SYNC=1 to skip, e.g. when you deliberately release an unpushed
#      develop);
#   3. pack the two suites at the given version (or suite.yaml's version);
#   4. run publish.sh against local develop, pushing the tag over origin (HTTPS).
#
# Usage:
#   ./release.sh                 # version from suite.yaml; sync, pack, publish
#   ./release.sh v0.2.0          # explicit version
#   DRY_RUN=1 ./release.sh       # print planned actions, change nothing
#   SKIP_SYNC=1 ./release.sh     # do not touch local develop before releasing
#
# Credentials for the tag push: HTTPS origin must be able to write. For the
# release API: $GITEE_TOKEN or gitee-cli's config (see publish.sh).
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TOOLKITS_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$TOOLKITS_DIR/../.." && pwd)"
DRY_RUN="${DRY_RUN:-0}"

REFUSE() { echo "release: $*" >&2; exit 1; }
run() {
  if [ "$DRY_RUN" = "1" ]; then echo "[dry-run] $*"; else eval "$@"; fi
}

VER="${1:-}"

# ---- 1. preconditions ----------------------------------------------------
git -C "$REPO_ROOT" rev-parse -q --verify "refs/heads/develop" >/dev/null 2>&1 \
  || REFUSE "local branch 'develop' does not exist"
if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]; then
  REFUSE "working tree has uncommitted changes; commit or stash before releasing
$(git -C "$REPO_ROOT" status --short --untracked-files=no)"
fi

# ---- 2. sync local develop with origin/develop (fast-forward only) --------
if [ "${SKIP_SYNC:-0}" = "1" ]; then
  echo "SKIP_SYNC=1: not syncing local develop"
else
  echo "fetching origin/develop ..."
  run "git -C '$REPO_ROOT' fetch origin develop"
  if git -C "$REPO_ROOT" rev-parse -q --verify origin/develop >/dev/null 2>&1; then
    local_tip="$(git -C "$REPO_ROOT" rev-parse develop)"
    remote_tip="$(git -C "$REPO_ROOT" rev-parse origin/develop)"
    if [ "$local_tip" = "$remote_tip" ]; then
      echo "local develop already up to date ($local_tip)"
    elif git -C "$REPO_ROOT" merge-base --is-ancestor "$local_tip" "$remote_tip"; then
      echo "fast-forwarding local develop $local_tip -> $remote_tip"
      run "git -C '$REPO_ROOT' branch -f develop '$remote_tip'"
    elif git -C "$REPO_ROOT" merge-base --is-ancestor "$remote_tip" "$local_tip"; then
      echo "local develop is ahead of origin/develop (${local_tip}); releasing local commits"
    else
      REFUSE "local develop and origin/develop have diverged; resolve manually
  local:  $local_tip
  remote: $remote_tip"
    fi
  fi
fi
REL_TIP="$(git -C "$REPO_ROOT" rev-parse develop)"
echo "releasing from local develop @ $REL_TIP"
echo

# ---- 3. pack -------------------------------------------------------------
if [ -n "$VER" ]; then
  run "'$SCRIPT_DIR/pack.sh' '$VER'"
else
  run "'$SCRIPT_DIR/pack.sh'"
fi
# pack.sh resolves the version identically; read it back for publish.
if [ -n "$VER" ]; then
  PV="$VER"
else
  PV="$(sed -n 's/^version: *//p' "$TOOLKITS_DIR/researcher-agent-toolkit/suite.yaml" | head -1)"
  PV="v$PV"
fi
echo

# ---- 4. publish ----------------------------------------------------------
# publish.sh cuts the tag from local develop (RELEASE_REF=develop) and pushes it
# over origin (PUSH_REMOTE=origin), matching "release from local develop".
run "RELEASE_REF=develop PUSH_REMOTE=origin DRY_RUN='$DRY_RUN' '$SCRIPT_DIR/publish.sh' '$PV'"
