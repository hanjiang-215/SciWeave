#!/usr/bin/env sh
# One-shot installer for a SciWeave Agent suite, straight from a Gitee release.
#
# It does exactly what a user would do by hand, without the guessing:
#   1. pick a version (latest release tag, or --version vX.Y.Z);
#   2. download that tag's suite zip and its SHA256SUMS from the release;
#   3. verify the checksum (refuse on mismatch — a tampered/incomplete download
#      must not be installed);
#   4. unpack into a temp dir and run the suite's own install.sh.
#
# The suite's install.sh remains the single source of truth for *how* a suite
# installs (where skills go, what services start). This script never duplicates
# that logic; it only fetches and hands off.
#
# Usage:
#   ./install-suite.sh po                  # latest PO suite
#   ./install-suite.sh researcher          # latest researcher suite
#   ./install-suite.sh po --version v0.1.0
#   REPO=owner/repo ./install-suite.sh po  # non-default repo
#
# Env passed through to the suite installer: SCIWEAVE_OWNER_SKILLS_HOME,
# SCIWEAVE_TASK_AGENT_HOME, SCIWEAVE_RESEARCHER_SKILLS_HOME, etc.
set -eu

REPO="${REPO:-qi-yueran/ai4science}"
API="https://gitee.com/api/v5"
TOKEN="${GITEE_TOKEN:-}"   # optional; needed only for a private repo

REFUSE() { echo "install-suite: $*" >&2; exit 1; }

SUITE="${1:-}"
[ -n "$SUITE" ] || REFUSE "usage: ./install-suite.sh <po|researcher> [--version vX.Y.Z]"
shift || true
WANT_VER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --version) WANT_VER="${2:-}"; shift 2;;
    --version=*) WANT_VER="${1#*=}"; shift;;
    *) REFUSE "unknown argument: $1";;
  esac
done

case "$SUITE" in
  po)         ZIP_PREFIX="sciweave-po-toolkit";        SUITE_DIR="project-owner-agent-toolkit";;
  researcher) ZIP_PREFIX="sciweave-researcher-toolkit"; SUITE_DIR="researcher-agent-toolkit";;
  *) REFUSE "unknown suite '$SUITE' (expected: po | researcher)";;
esac

need() { command -v "$1" >/dev/null 2>&1 || REFUSE "missing required tool: $1"; }
need curl; need unzip; need sha256sum

# A private repo serves release files only to an authenticated caller.
auth_q=""
[ -n "$TOKEN" ] && auth_q="?access_token=$TOKEN"
curl_auth() {
  if [ -n "$TOKEN" ]; then curl -sS -H "Authorization: token $TOKEN" "$@"; else curl -sS "$@"; fi
}

# ---- 1. resolve version --------------------------------------------------
if [ -n "$WANT_VER" ]; then
  VER="$WANT_VER"
else
  echo "resolving latest release ..."
  VER="$(curl_auth "$API/repos/$REPO/releases/latest$auth_q" \
    | python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("tag_name",""))
except Exception:
    print("")' 2>/dev/null || true)"
  [ -n "$VER" ] || REFUSE "no releases found for $REPO (or cannot read them)"
fi
BARE="${VER#v}"
echo "version: $VER  suite: $SUITE"

# ---- 2. locate attachments ----------------------------------------------
REL_JSON="$(curl_auth "$API/repos/$REPO/releases/tags/$VER$auth_q" || true)"
[ -n "$REL_JSON" ] || REFUSE "release $VER not found"

pick_url() {
  # $1 = exact attachment name; print its download_url (or "")
  NAME="$1" printf '%s' "$REL_JSON" | python3 -c 'import sys,json,os
name=os.environ["NAME"]
try:
    d=json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
for a in d.get("assets", d.get("attach_files", [])):
    if a.get("name")==name:
        print(a.get("browser_download_url") or a.get("download_url") or ""); break
else:
    print("")'
}

ZIP_NAME="${ZIP_PREFIX}-${BARE}.zip"
ZIP_URL="$(pick_url "$ZIP_NAME")"
SUM_URL="$(pick_url "SHA256SUMS")"
[ -n "$ZIP_URL" ] || REFUSE "release $VER has no asset named $ZIP_NAME"

# ---- 3. download + verify -----------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "downloading $ZIP_NAME ..."
curl_auth -L -o "$TMP/$ZIP_NAME" "$ZIP_URL"
[ -s "$TMP/$ZIP_NAME" ] || REFUSE "download produced an empty file"

if [ -n "$SUM_URL" ]; then
  curl_auth -L -o "$TMP/SHA256SUMS" "$SUM_URL"
  want="$(awk -v n="$ZIP_NAME" '$2==n{print $1}' "$TMP/SHA256SUMS")"
  got="$(sha256sum "$TMP/$ZIP_NAME" | awk '{print $1}')"
  [ -n "$want" ] || REFUSE "SHA256SUMS has no entry for $ZIP_NAME"
  [ "$want" = "$got" ] || REFUSE "checksum mismatch for $ZIP_NAME
  expected $want
  got      $got
refusing to install a corrupted or tampered archive"
  echo "checksum OK"
else
  echo "warning: release has no SHA256SUMS; skipping checksum verification" >&2
fi

# ---- 4. unpack + hand off -----------------------------------------------
unzip -q "$TMP/$ZIP_NAME" -d "$TMP/x"
SRC="$TMP/x/$SUITE_DIR"
[ -f "$SRC/install.sh" ] || REFUSE "archive did not contain $SUITE_DIR/install.sh"
echo "running $SUITE_DIR/install.sh ..."
echo
( cd "$SRC" && sh ./install.sh )
