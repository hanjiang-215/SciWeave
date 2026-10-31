#!/usr/bin/env sh
# Publish the packed suite zips as a Gitee release, via the Gitee OpenAPI.
#
# gitee-cli (0.7.x) has no `release` command — `gitee help --json` lists it under
# unsupported_command_groups — so this script talks to the REST API with curl.
#
# It does four things, in order, and stops at the first failure:
#   1. resolve owner/repo, version, and base ref; refuse to release if the two
#      suites' suite.yaml versions disagree, or if the tag does not match them;
#   2. pin a git tag <ver> to the base ref (default: develop) and push it — the
#      tag is cut from the base ref's commit, NOT the checked-out HEAD, so
#      unmerged feature work never leaks into a release (Gitee also requires the
#      tag a release points at; creating it here keeps tag and attachment in
#      lockstep);
#   3. create the release if one for <ver> does not already exist;
#   4. upload every zip in the dist dir as an attachment.
#
# Credentials: the token is read from $GITEE_TOKEN, else from gitee-cli's config
# (~/.config/gitee/config.toml). It is NEVER written to disk or echoed.
#
# Usage:
#   ./publish.sh v0.1.0              # tag+release from develop (default base)
#   RELEASE_REF=master ./publish.sh v0.1.0   # hotfix cut from another ref
#   DRY_RUN=1 ./publish.sh v0.1.0    # print the planned calls, change nothing
#   REPO=owner/repo ./publish.sh ... # override inferred repository
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
TOOLKITS_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="${DIST_DIR:-$SCRIPT_DIR/dist}"
API="https://gitee.com/api/v5"

REFUSE() { echo "refuse: $*" >&2; exit 1; }

# ---- 1. inputs -----------------------------------------------------------
VER="${1:-}"
[ -n "$VER" ] || REFUSE "usage: ./publish.sh <version>   e.g. ./publish.sh v0.1.0"
TAG="$VER"
BARE="${VER#v}"

# Both suites must share one version; a mismatch means one zip is stale.
po_v="$(sed -n 's/^version: *//p' "$TOOLKITS_DIR/project-owner-agent-toolkit/suite.yaml" | head -1)"
re_v="$(sed -n 's/^version: *//p' "$TOOLKITS_DIR/researcher-agent-toolkit/suite.yaml" | head -1)"
[ "$po_v" = "$re_v" ] || REFUSE "suite versions disagree: po=$po_v researcher=$re_v"
[ "$BARE" = "$po_v" ] || REFUSE "publish version $VER does not match suite.yaml ($po_v); run pack.sh with the same version"

# Base ref the release is cut from. Default is develop (integrated branch);
# override with RELEASE_REF for a hotfix off master. The tag is pinned to the
# commit this ref resolves to, not to the checked-out HEAD.
RELEASE_REF="${RELEASE_REF:-develop}"
REL_COMMIT="$(git -C "$TOOLKITS_DIR" rev-parse -q --verify "$RELEASE_REF^{commit}" 2>/dev/null || true)"
[ -n "$REL_COMMIT" ] || REFUSE "base ref '$RELEASE_REF' not found; fetch it first (git fetch origin $RELEASE_REF)"

# Repository: explicit REPO wins; else infer from the git origin.
if [ "${REPO:-}" != "" ]; then
  SLUG="$REPO"
else
  url="$(git -C "$TOOLKITS_DIR" remote get-url origin 2>/dev/null || true)"
  [ -n "$url" ] || REFUSE "no REPO given and no git origin to infer from"
  # git@gitee.com:owner/repo.git | https://gitee.com/owner/repo.git -> owner/repo
  SLUG="$(printf '%s' "$url" | sed -E 's#^(git@|https://)[^:/]*[:/]##; s#\.git$##')"
fi
[ -n "$SLUG" ] || REFUSE "could not resolve owner/repo"

# ---- credentials ---------------------------------------------------------
TOKEN="${GITEE_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f "$HOME/.config/gitee/config.toml" ]; then
  TOKEN="$(sed -n 's/^token *= *"\(.*\)"/\1/p' "$HOME/.config/gitee/config.toml" | head -1)"
fi
[ -n "$TOKEN" ] || REFUSE "no token: set GITEE_TOKEN or run 'gitee auth login'"

DRY_RUN="${DRY_RUN:-0}"
run() {
  if [ "$DRY_RUN" = "1" ]; then echo "[dry-run] $*"; else eval "$@"; fi
}

# ---- zips ----------------------------------------------------------------
# Attachments to upload: the two suite zips plus SHA256SUMS. install-suite.sh
# fetches SHA256SUMS from the same release to verify the zip it downloaded, so
# shipping it is part of the contract, not an extra.
ZIPS=""
for z in "$DIST_DIR"/sciweave-po-toolkit-"$BARE".zip "$DIST_DIR"/sciweave-researcher-toolkit-"$BARE".zip; do
  [ -f "$z" ] || REFUSE "missing $z — run pack.sh $VER first"
  ZIPS="$ZIPS $z"
done
[ -f "$DIST_DIR/SHA256SUMS" ] || REFUSE "missing $DIST_DIR/SHA256SUMS — run pack.sh $VER first"
ZIPS="$ZIPS $DIST_DIR/SHA256SUMS"

echo "repo:    $SLUG"
echo "tag:     $TAG"
echo "base:    $RELEASE_REF ($REL_COMMIT)"
echo "files:$ZIPS"
echo

# ---- 2. tag --------------------------------------------------------------
# The tag must point at the base ref (develop by default), NOT whatever branch
# happens to be checked out — otherwise unmerged feature commits leak into the
# release. Resolve the ref to a commit SHA first so tag and release agree even
# if the branch moves between tag-push and release creation.
if git -C "$TOOLKITS_DIR" rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "tag $TAG already exists locally"
  existing_commit="$(git -C "$TOOLKITS_DIR" rev-list -n1 "$TAG")"
  [ "$existing_commit" = "$REL_COMMIT" ] || REFUSE "existing tag $TAG points at $existing_commit, not $RELEASE_REF ($REL_COMMIT)"
  TAG_ALREADY_LOCAL=1
else
  echo "creating tag $TAG at $RELEASE_REF"
  run "git -C '$TOOLKITS_DIR' tag -a '$TAG' '$REL_COMMIT' -m 'sci-weave suites $TAG'"
  TAG_ALREADY_LOCAL=0
fi

# Push the tag only if the remote does not already carry it at the same commit.
# A tag already on the remote pointing at our commit is exactly what we want
# (e.g. a maintainer pre-created it); do not fail, just move on.
PUSH_REMOTE="${PUSH_REMOTE:-origin}"
remote_tag="$(git -C "$TOOLKITS_DIR" ls-remote --tags "$PUSH_REMOTE" "refs/tags/$TAG^{}" 2>/dev/null | awk '{print $1}')"
[ -n "$remote_tag" ] || remote_tag="$(git -C "$TOOLKITS_DIR" ls-remote --tags "$PUSH_REMOTE" "refs/tags/$TAG" 2>/dev/null | awk '{print $1}')"
if [ -n "$remote_tag" ]; then
  [ "$remote_tag" = "$REL_COMMIT" ] || REFUSE "remote tag $TAG exists at $remote_tag, not $RELEASE_REF ($REL_COMMIT)"
  echo "tag $TAG already on $PUSH_REMOTE at $remote_tag; skipping push"
else
  echo "pushing tag $TAG to $PUSH_REMOTE"
  run "git -C '$TOOLKITS_DIR' push '$PUSH_REMOTE' 'refs/tags/$TAG'"
fi
echo

# ---- 3. release ----------------------------------------------------------
# Look for an existing release for this tag so re-runs are idempotent.
existing_id="$(curl -sS "$API/repos/$SLUG/releases/tags/$TAG?access_token=$TOKEN" 2>/dev/null \
  | (python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print(d.get("id",""))
except Exception:
    print("")') || true)"

if [ -n "$existing_id" ]; then
  REL_ID="$existing_id"
  echo "release for $TAG already exists (id=$REL_ID); will attach files to it"
elif [ "$DRY_RUN" = "1" ]; then
  REL_ID="DRY_RUN"
  echo "[dry-run] POST $API/repos/$SLUG/releases  (tag_name=$TAG, target_commitish=$REL_COMMIT)"
else
  echo "creating release $TAG"
  BODY="SciWeave Agent 套件 ${TAG}。下载后解压并运行对应的 install.sh：
- sciweave-po-toolkit-${BARE}.zip：项目负责人套件（装在本机 harness）
- sciweave-researcher-toolkit-${BARE}.zip：研究员套件（本机个人 Agent + Task Agent）
校验：同目录 SHA256SUMS。"
  REL_ID="$(curl -sS -X POST "$API/repos/$SLUG/releases" \
    --data-urlencode "access_token=$TOKEN" \
    --data-urlencode "tag_name=$TAG" \
    --data-urlencode "name=$TAG" \
    --data-urlencode "body=$BODY" \
    --data-urlencode "target_commitish=$REL_COMMIT" \
    | python3 -c 'import sys,json
d=json.load(sys.stdin); print(d.get("id",""))')"
  [ -n "$REL_ID" ] || REFUSE "failed to create release (see API response above)"
  echo "created release id=$REL_ID"
fi
echo

# ---- 4. attach -----------------------------------------------------------
# Attaching the same file name twice creates duplicates on Gitee; check first.
if [ "$DRY_RUN" = "1" ] || [ "$REL_ID" = "DRY_RUN" ]; then
  have=""
else
  have="$(curl -sS "$API/repos/$SLUG/releases/$REL_ID/attach_files?access_token=$TOKEN" 2>/dev/null \
    | python3 -c 'import sys,json
try:
    print(" ".join(a.get("name","") for a in json.load(sys.stdin)))
except Exception:
    print("")' || true)"
fi

for z in $ZIPS; do
  name="$(basename "$z")"
  case " $have " in
    *" $name "*) echo "already attached: $name"; continue;;
  esac
  echo "uploading $name"
  if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] curl -F file=@$z $API/repos/$SLUG/releases/$REL_ID/attach_files"
  else
    resp="$(curl -sS -X POST "$API/repos/$SLUG/releases/$REL_ID/attach_files" \
      -F "access_token=$TOKEN" \
      -F "file=@$z")"
    echo "$resp" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print("  ->", d.get("download_url") or d.get("browser_download_url") or d)' || {
      echo "upload response was not what we expected: $resp" >&2; exit 1; }
  fi
done

echo
echo "done. release: https://gitee.com/$SLUG/releases/tag/$TAG"
