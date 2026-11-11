#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

for d in .git/rebase-merge .git/rebase-apply .git/MERGE_HEAD .git/CHERRY_PICK_HEAD; do
  [ -e "$d" ] && exit 0
done

branch=$(git rev-parse --abbrev-ref HEAD)
[ "$branch" = "HEAD" ] && exit 0

backup="wip/backup-${branch//\//-}"

git add -A

git diff --cached --quiet && exit 0

if git diff --cached --name-only | grep -qE '(^|/)\.env(\.|$)|\.pem$|id_rsa'; then
  echo "bloqué: fichier sensible"
  git reset
  exit 1
fi

git commit -q -m "chore(wip): checkpoint $(date -u +%Y-%m-%dT%H:%M:%SZ) [$branch]"

git push -q origin "HEAD:refs/heads/$backup"

echo "poussé: $backup"
