# Branching and pull requests

Moved out of `AGENTS.md` on 2026-11-14, unchanged, so that file stays short
enough to read every session. `AGENTS.md` keeps the rules; this has the
reasons and the detail.

**Every independent branch is cut from `main`.** Not from another feature
branch, and not from whatever happens to be checked out.

```bash
git checkout main && git pull --ff-only
git checkout -b <type>/<scope>-<subject>
```

### Stack only for a real dependency

Base a branch on another one only when it genuinely cannot build or be
reviewed without it — it edits the same functions, or relies on an API the
parent introduces. "It came next chronologically" is not a dependency.

When you do stack, say so in the PR body: name the parent, state the
dependency, and note the merge order.

Why this matters here: GitHub retargets a stacked PR only when its base branch
is **deleted** on merge. `delete_branch_on_merge` is enabled on this
repository, so that now happens automatically — but merging a stack out of
order still lands children in the wrong place, and a stack more than two deep
compounds every rebase. Independent branches have neither problem.

### Merging

- **Merge commits**, not squash and not rebase-and-merge. Commits are split
  deliberately (`fix:` separately from `docs:` and large mechanical churn) so
  they review independently, and squashing destroys that. Rebase rewrites the
  SHAs that verification notes refer to.
- Merge a stack **bottom-up**, so each child retargets before its own turn.
- If a branch falls behind `main`, rebase it — `git rebase origin/main` —
  rather than merging `main` into it.

### Before opening a PR

The full suite, the linter and the type checker must all pass:

```bash
pytest && ruff check . && mypy pyguara
```

When a branch carries several commits, each one should pass on its own, not
merely the tip.

### Once a PR is open, the branch is frozen

Do not push more commits to a branch after its PR is up for review. The PR
can merge at any moment — `delete_branch_on_merge` then removes the branch,
and a later `git push` to that name **recreates it** as a zombie: commits
that are not in `main`, sitting on a branch with no open PR, that nothing
will ever merge. This has happened repeatedly.

Anything that comes after — review feedback, an extra test, a tracker or docs
fix, the next phase of an audit — goes on a **new branch cut from `main`**
with its own PR (or a stacked branch if it is a genuine dependency, per
above). Before pushing to any pre-existing branch, confirm its PR is still
open:

```bash
gh pr view <branch> --json state,title   # MERGED / CLOSED -> new branch from main
```

On handoff, say which it is: "PR is final, nothing else coming" versus "still
adding X, do not merge yet" — so a fast merge is never a gamble.

### Cleaning up

After a PR merges, delete any local branch that tracked it
(`git fetch --prune` clears the remote-tracking ref; `git branch -d <branch>`
the local one). Periodically reconcile: `git branch -a` against
`gh pr list --state merged` — a branch with a merged PR and no follow-up work
is dead weight, remote (`git push origin --delete <branch>`) and local both.
