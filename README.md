# git subcommands by @maruel

Two Python scripts that simplify common git workflows:

## Scripts

| command | description |
| ------- | ----------- |
| `git squash` | Squashes all commits on the current branch into a single commit. Combines all commits since the upstream branch into one, merging their commit messages. Requires an upstream branch to be configured. |
| `git rb` | Rebases all local branches onto their upstreams in topological order, then removes empty branches (branches whose content is identical to their parent). Automatically handles conflicts with mergetool. |
| `git mt` | git mergetool that auto-resolve binary files during rebase tree conflicts. ||

## Usage

Configures git to a "rebase linearized history flow" where "one PR/CL equals one commit".
This is in Chromium, Go and other projects that aims towards a linear commit history.

Basic Usage:

```bash
git checkout -b my-branch origin/main
# (do work)
git commit -am.
# (do work)
git commit -am.
# (do work)
git commit -am.
# (when done)
git squash
git commit --amend  (set the actual commit message)
git push
```


Multiple chained changes:
```bash
git checkout -b 1_work_A origin/main
# (do work)
git commit -a -m "First commit"
git checkout -b 2_work_B 1_work_A
# (do different work)
git commit -a -m "Second commit"
```

When going back to update based on origin/main:
```bash
git checkout 1_work_A
git squash
git pull
git checkout 2_work_B
git pull
```

Pro-tip:
- Before a `git pull`, always `git squash` first! This means you will only have to do a merge conflict
  resolution once.
