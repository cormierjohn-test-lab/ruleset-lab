# ruleset-lab

Throwaway lab proving the merge-gate mechanics for
`dominos-pizza/dai-dbx-platform-modernization`.

## Identity mapping

| Lab | Real repo |
|---|---|
| `cormierjohn` (team `managers`) | `dai-databricks-all-managers` |
| `johncormier-lovelytics` (no team) | luisjaime-data, juandiaz-hub, mkuric9 |

## Requirements under test

1. No review auto-raised when a PR opens
2. No CODEOWNERS/manager-wide notification on review request
3. Agent fires on FIRST review request; blockers -> REQUEST_CHANGES
4. Agent skips subsequent re-requests (no endless loop)
5. `required_approving_review_count: 1`, approver limited to managers
6. Merge gated on the agent having RUN (not on it finding nothing)

Suspected conflicts: 2 vs 5 (CODEOWNERS auto-requests), and 4 vs 6
(a check run is bound to a SHA, so skipping may leave a new head
unchecked).

## Agent status

A gh-aw agent (`gate-b-agentic.md`) runs here on `claude-sonnet-5`, billed
to `cormierjohn`'s personal Copilot Pro via `COPILOT_GITHUB_TOKEN`. The org
has no Copilot seats and does not need any. Both Gate B paths are proven:

| PR | Path | Result |
|---|---|---|
| #42 | bot already reviewed, push again | agent runs, check run + comment |
| #50 | bot never reviewed, push | gate declines, `noop`, green check run, no comment |

The earlier plain-`GITHUB_TOKEN` workflows (`sync-gate-*.yml`,
`agent-review-sim.yml`, `bot-review.yml`) remain as the cheaper way to
probe event mechanics without spending AI credits.

`HANDOFF.md` has the full account of getting the agent running, including
the PAT permissions it needs. `CLAUDE.md` is the orientation for Claude Code.