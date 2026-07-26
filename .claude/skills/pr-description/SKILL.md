---
name: pr-description
description: Draft (and optionally open) a pull request description comparing the current branch against a base branch. Use when the user asks to write/help with a PR description, "compare with dev/main/master", or wants to open a PR for the current branch.
---

# PR Description

Generate an accurate, well-structured PR description by reading the actual
diff and commit history between the current branch and a base branch — not
by guessing from memory or from what you think you changed. Commit messages
in this repo are sometimes terse or bundle unrelated work together; the diff
is the source of truth.

## Args

`args` may name the base branch (e.g. `dev`, `main`, `master`). If omitted,
infer it: check for a branch named `dev`, then `main`, then `master` (in that
order) among local/remote branches. If more than one plausibly-relevant base
exists and it's not obvious which the user wants, ask — don't guess silently
for a PR description, since the diff and commit list change substantially
depending on the base.

## Steps

1. **Gather state in parallel** (independent, batch these):
   - `git branch --show-current` — current branch.
   - `git status -sb` — confirm working tree is clean-ish and see tracking/ahead-behind info.
   - `git log <base>..HEAD --oneline` — commits that will be in the PR.
   - `git diff <base>...HEAD --stat` — files changed, at a glance.
   - `git log <current-branch>..origin/<current-branch> --oneline` and the reverse — confirm the branch is actually pushed and in sync with its remote before offering to open a PR. If it's ahead of its remote, say so and ask whether to push first (never push without asking).

2. **Read enough of the actual diff to describe it accurately**, not just the stat. For any file whose change isn't self-explanatory from its name/commit message, look at the real diff (`git diff <base>...HEAD -- <path>`) before writing a claim about what changed. Do not invent behavior from commit message text alone — commit messages in this repo can bundle multiple unrelated changes into one line (e.g. "enhance X; update Y for improved Z"), and the real content is what matters for reviewers.

3. **Check for `gh` availability** (`which gh`). If present and the branch is pushed:
   - Offer to open the PR directly via `gh pr create --title "..." --body "$(cat <<'EOF' ... EOF)"`, base `<base>`, head `<current-branch>`.
   - If absent, or the user hasn't asked you to actually open it, just produce the description as text for them to paste in manually — say so explicitly, don't silently skip opening it.
   - Never push commits or open the PR without the user's go-ahead first; drafting the description doesn't imply consent to publish it.

4. **Draft the description**:
   - **Title**: under 70 characters, describes the change not the mechanism ("Add X" not "Update files for X").
   - **Summary**: bullet points grouped by theme/subsystem, not one bullet per commit. Group related commits together even if they landed as separate commits.
   - **Notable fixes/bugs** (only if applicable): if the branch's history shows real bugs found and fixed along the way (not just planned feature work), call them out separately with enough detail that a reviewer understands the failure mode that was fixed, not just that "a bug was fixed."
   - **Test plan**: a checklist of concrete, runnable verification steps specific to what changed — not generic boilerplate ("test the changes"). Base it on how the change was actually verified during development if that's known (e.g. specific commands run, specific endpoints hit), or on what a reviewer could realistically run.

5. Return the title + body as markdown, or the PR URL if actually opened via `gh`.

## What to avoid

- Don't pad the summary with restatements of the diff stat ("added 5 files, changed 3 files") — say what changed and why it matters.
- Don't write a test plan reviewers can't act on ("ensure everything works").
- Don't claim test coverage or verification that didn't actually happen.
