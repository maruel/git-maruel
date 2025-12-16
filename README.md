# git subcommands by @maruel

Two Python scripts that simplify common git workflows:

## Scripts

| command | description |
| ------- | ----------- |
| `git squash` | Squashes all commits on the current branch into a single commit. Combines all commits since the upstream branch into one, merging their commit messages. Requires an upstream branch to be configured. |
| `git rb` | Rebases all local branches onto their upstreams in topological order, then removes empty branches (branches whose content is identical to their parent). Automatically handles conflicts with mergetool. |
