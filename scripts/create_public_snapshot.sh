#!/usr/bin/env bash
# Create a clean public snapshot of the working tree.
#
# Usage:
#   bash scripts/create_public_snapshot.sh ../cognidq-public
#
# Result:
#   <out_dir>/   a fresh Git repo with one commit:
#                "Initial commit — CogniDQ v0.1.0-alpha"
#                and one tag: v0.1.0-alpha
set -euo pipefail

OUT_DIR="${1:-}"
RELEASE_TAG="${RELEASE_TAG:-v0.1.0-alpha}"
COMMIT_MSG="${COMMIT_MSG:-Initial commit — CogniDQ v0.1.0-alpha}"

if [[ -z "$OUT_DIR" ]]; then
    echo "usage: $0 <output_dir> [release_tag]" >&2
    echo "example: $0 ../cognidq-public" >&2
    exit 2
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: not inside a Git working tree. Run from the source repo root." >&2
    exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree is not clean. Commit or stash changes first." >&2
    git status --porcelain
    exit 1
fi

SRC_ROOT="$(pwd)"
if [[ "$OUT_DIR" != /* ]]; then
    OUT_DIR="$SRC_ROOT/$OUT_DIR"
fi
OUT_DIR="$(cd "$(dirname "$OUT_DIR")" && pwd)/$(basename "$OUT_DIR")"

if [[ -e "$OUT_DIR" ]]; then
    echo "ERROR: output directory already exists: $OUT_DIR" >&2
    exit 1
fi

echo "Source: $SRC_ROOT"
echo "Target: $OUT_DIR"
echo

echo "[1/5] Enumerating tracked files..."
FILE_COUNT=$(git ls-files | wc -l)
echo "       $FILE_COUNT files"

echo "[2/5] Extracting files via git archive (respects .gitattributes)..."
mkdir -p "$OUT_DIR"
git archive --worktree-attributes --format=tar HEAD | tar -x -C "$OUT_DIR"
COPIED=$(find "$OUT_DIR" -type f | wc -l)
echo "       extracted $COPIED files"

echo "[3/5] Initialising fresh Git repo..."
cd "$OUT_DIR"
git init --initial-branch=main >/dev/null
git config user.email "release-bot@cognidq.local"
git config user.name "CogniDQ Release"

echo "[4/5] Creating initial commit..."
git add -A
git -c commit.gpgsign=false commit -m "$COMMIT_MSG" >/dev/null

echo "[5/5] Tagging $RELEASE_TAG..."
git tag -a "$RELEASE_TAG" -m "CogniDQ $RELEASE_TAG" >/dev/null

echo
echo "DONE."
echo
echo "Snapshot at: $OUT_DIR"
echo
echo "Next steps:"
echo "  cd $OUT_DIR"
echo "  git remote add origin git@github.com:<your-org>/cognidq.git"
echo "  git push -u origin main"
echo "  git push origin $RELEASE_TAG"
