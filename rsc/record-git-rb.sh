#!/usr/bin/env bash
# Regenerate from the repository root with asciinema 3 and agg:
# asciinema rec --overwrite --return --window-size 80x24 \
#   --output-format asciicast-v2 --title 'git rb: rebase, delete, conflict' \
#   --command 'bash rsc/record-git-rb.sh' rsc/git-rb.cast
# agg --font-size 16 --theme monokai rsc/git-rb.cast rsc/git-rb.gif
set -euo pipefail

script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
for executable in bash git python3; do
  command -v "$executable" >/dev/null
done
work_dir="$(mktemp -d)"
readonly work_dir
trap 'rm -rf -- "$work_dir"' EXIT

# Keep the demo independent of the user's Git configuration and repository.
env -i PATH="$PATH" HOME="$work_dir" LC_ALL=C TERM=xterm-256color \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_AUTHOR_DATE=2026-01-01T12:00:00Z GIT_COMMITTER_DATE=2026-01-01T12:00:00Z \
  bash --noprofile --norc -s -- "$script_dir/.." "$work_dir" <<'DEMO'
set -euo pipefail
export PATH="$1:$PATH"
cd -- "$2"
git init -q -b main
git config user.name 'Demo'
git config user.email 'demo@example.com'
git config color.ui always
git config core.pager cat
git config commit.gpgsign false
printf 'theme=light\n' > settings.txt
git add settings.txt
git commit -qm 'Initial project'

git switch -qc 1-conflict
printf 'theme=blue\n' > settings.txt
git commit -qam 'Use a blue theme'
git branch --set-upstream-to=main >/dev/null
conflict_tip="$(git rev-parse HEAD)"

git switch -qc 2-feature main
printf 'New feature\n' > feature.txt
git add feature.txt
git commit -qm 'Add a feature'
git branch --set-upstream-to=main >/dev/null
feature_tip="$(git rev-parse HEAD)"

git switch -qc 3-landed main
printf 'Documentation\n' > guide.txt
git add guide.txt
git commit -qm 'Add documentation'
git branch --set-upstream-to=main >/dev/null
landed_tip="$(git rev-parse HEAD)"

git switch -q main
git cherry-pick "$landed_tip" >/dev/null
printf 'theme=dark\n' > settings.txt
git commit -qam 'Use a dark theme on main'

prompt() {
  printf '\033[1;32m$\033[0m %s\n' "$1"
  sleep 0.8
}

printf '\033[2J\033[H\033[1mThree branches track main\033[0m\n\n'
printf '1-conflict  edits the same line as main\n'
printf '2-feature   has work to rebase\n'
printf '3-landed    is already merged into main\n\n'
prompt 'git log --graph --oneline --all --decorate'
git log --graph --oneline --all --decorate
sleep 5

printf '\033[2J\033[H'
prompt 'git rb'
rb_status=0
git rb || rb_status=$?
sleep 3
prompt 'echo $?'
printf '%s\n' "$rb_status"
printf '\n'
prompt 'git branch -vv'
git branch -vv
printf '\n'
prompt 'git status --short --branch'
git status --short --branch
printf '\nConflict aborted; 1-conflict is ready for manual resolution.\n'
sleep 5

# Verify the advertised outcomes without adding noise to the recording.
test "$rb_status" -eq 1
test "$(git branch --show-current)" = 1-conflict
test "$(git rev-parse 1-conflict)" = "$conflict_tip"
test "$(git rev-parse 2-feature)" != "$feature_tip"
git merge-base --is-ancestor main 2-feature
if git show-ref --verify --quiet refs/heads/3-landed; then
  printf 'Expected 3-landed to be deleted\n' >&2
  exit 1
fi
test -z "$(git status --porcelain)"
test ! -d .git/rebase-merge
test ! -d .git/rebase-apply
DEMO
