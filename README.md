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

The agent itself is NOT installed here - this org has no Copilot
billing. Check runs are created directly via the API to test gating.