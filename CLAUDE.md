# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A throwaway lab, not a product. It exists to measure GitHub merge-gate and
PR-review-automation mechanics for `dominos-pizza/dai-dbx-platform-modernization`
before they are applied there. Nothing here is "shipped"; every workflow is an
experiment that answers one question, and the `*.txt` files at the root are
just content changes used to trigger PR events.

Read `HANDOFF.md` first for the current state of the gh-aw agent work. It
records what is proven, what is still a hypothesis, and which mistakes have
already cost a CI cycle. Do not re-litigate the items it marks as proven.

## Two accounts, one org

- Org `cormierjohn-test-lab` (Free plan). Owner `cormierjohn` is on team
  `managers` and stands in for the real repo's manager group.
- `johncormier-lovelytics` is the "developer": org member, on no team.
- Both are logged in locally. Switch with `gh auth switch --user <name>`.
  Author PRs as the dev, review and merge as the manager, because a PR author
  cannot review their own PR.
- `main` is protected by ruleset `develop-shape` (PR required, `Notebook PR
  Review` status check, bypass for `managers`). Merge with
  `gh pr merge <N> --merge --admin` as `cormierjohn`.

## Workflows

Plain `GITHUB_TOKEN` workflows (`.github/workflows/*.yml`) each carry a header
comment stating the question they test. The pair to understand together is
`sync-gate-a-pending.yml` and `sync-gate-b-reviewed.yml`: both gate a
`synchronize` run, but A keys on `requested_reviewers` (proven useless, a bot
review never clears it) and B keys on "has the bot already reviewed" via an API
call in a step, since that fact is not in the event payload.

`agent-review-sim.yml` and `bot-review.yml` are `workflow_dispatch` helpers
that post a review as `github-actions[bot]` so the gates have something to
react to.

`gate-b-agentic.md` is the only gh-aw (GitHub Agentic Workflows) workflow.
`gate-b-agentic.lock.yml` is generated from it and must be committed alongside.

### gh-aw rules

- Compile by name: `gh aw compile gate-b-agentic`. Never run bare
  `gh aw compile`; it rewrites env values across every workflow.
- Workflow changes only take effect once merged to `main`.
- A workflow-file-only push does not fire `pull_request`. Touch a `*.txt`.
- A PR with `mergeable: CONFLICTING` fires no events at all. Check
  `gh pr view <N> --json mergeable,mergeStateStatus` before assuming Actions is
  broken.
- Editing a shared import invalidates every dependent lock file
  (`E009 CONFIG_HASH_MISMATCH` at activation).

## Reading a run

```bash
gh run list --repo cormierjohn-test-lab/ruleset-lab --workflow gate-b-agentic.lock.yml --limit 1
gh run view <id> --repo cormierjohn-test-lab/ruleset-lab --json jobs --jq '.jobs[] | "\(.conclusion) \(.name)"'
gh run view <id> --repo cormierjohn-test-lab/ruleset-lab --log-failed
gh run download <id> --repo cormierjohn-test-lab/ruleset-lab -D <dir>
```

The downloaded artifacts include `agent/sandbox/firewall/` (squid access log,
api-proxy otel spans, `awf-reflect.json`), which show the real upstream host
and HTTP status behind a proxy error. Those are more diagnostic than the
harness message in the job log.

## Python pre-flight

`.github/scripts/python_preflight.py` runs on changed `.py` files only and
checks two runtime-fatal things: the file parses, and module-level name
references resolve. It is deliberately not a linter. Run it locally with
`python .github/scripts/python_preflight.py <file>...`, or
`--changed origin/main` to mirror what CI checks. With no arguments it scans
every tracked `.py` file.
