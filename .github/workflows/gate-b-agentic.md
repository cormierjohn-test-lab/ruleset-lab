---
name: "Gate B Agentic Probe"
description: "Tests whether the Gate B re-review condition works inside gh-aw, including the noop path"

# The question this answers: Gate B needs to know whether the bot has already
# reviewed this PR, and that fact is NOT in the pull_request payload -- it needs
# an API call. A frontmatter `if:` can only see payload fields, so the gate has
# to live in a pre-agent step and end the run via `noop`.
#
# What is unproven and being measured here:
#   1. does gh-aw run in this repo at all (never tested before)
#   2. does a pre-agent step's output reach the agent
#   3. does `noop` end the run cleanly AND still leave a green check run
#
# Point 3 is the one that matters. In the dai-dbx workflows the check run must
# be emitted BEFORE noop, because noop is terminal -- it ends the run
# immediately. If that ordering is wrong the check never publishes and the PR
# shows a missing check rather than a passing one.
on:
  pull_request:
    types: [review_requested, synchronize]
    branches: [main]
    draft: false

permissions:
  contents: read
  pull-requests: read

engine:
  id: copilot

model: claude-sonnet-5

timeout-minutes: 10

safe-outputs:
  create-check-run:
    name: "Gate B Probe"
    max: 1
  add-comment:
    max: 1
    target: triggering
  noop:
    report-as-issue: false

pre-agent-steps:
  # The Gate B decision. Cheap: one API call, no agent time spent when it
  # declines. A push to a PR the bot has never reviewed should not wake it.
  - name: Decide whether this run should proceed
    id: gate
    env:
      PR_NUMBER: ${{ github.event.pull_request.number }}
      EXPR_GITHUB_REPOSITORY: ${{ github.repository }}
      EVENT_ACTION: ${{ github.event.action }}
      GH_TOKEN: ${{ github.token }}
    run: |
      set -euo pipefail
      mkdir -p /tmp/gh-aw/agent

      if [ "$EVENT_ACTION" = "review_requested" ]; then
        echo "proceed=true" > /tmp/gh-aw/agent/gate.txt
        echo "reason=review_requested" >> /tmp/gh-aw/agent/gate.txt
        echo "GATE: review_requested -- proceed"
        exit 0
      fi

      # synchronize: only re-run if this bot has already reviewed, so we are
      # re-checking findings we actually raised rather than reviewing a PR
      # nobody asked us about.
      COUNT=$(gh api "repos/${EXPR_GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/reviews" \
                --jq '[.[] | select(.user.login == "github-actions[bot]")] | length' \
              || echo 0)

      if [ "${COUNT:-0}" -gt 0 ]; then
        echo "proceed=true" > /tmp/gh-aw/agent/gate.txt
        echo "reason=push_after_bot_review" >> /tmp/gh-aw/agent/gate.txt
        echo "GATE: push, bot has ${COUNT} prior review(s) -- proceed"
      else
        echo "proceed=false" > /tmp/gh-aw/agent/gate.txt
        echo "reason=push_without_prior_bot_review" >> /tmp/gh-aw/agent/gate.txt
        echo "GATE: push, no prior bot review -- decline"
      fi
---

# Gate B Agentic Probe

You are testing a trigger condition, not reviewing code. Keep this short.

## Step 1 — Read the gate decision

Read `/tmp/gh-aw/agent/gate.txt`. It contains `proceed=true` or `proceed=false`
and a `reason=`.

## Step 2 — Publish the check run FIRST

Emit `create_check_run` named `Gate B Probe` with `conclusion: success`.

**Do this before anything else.** `noop` is terminal — it ends the run the
moment it is emitted — so a check run emitted after it never publishes, and the
PR shows a missing check instead of a passing one. That failure mode is silent,
which is exactly why the ordering is being tested here.

## Step 3 — Act on the decision

**If `proceed=false`:** call `noop` with a one-line explanation quoting the
`reason`. Post no comment. This is the path that must leave a green check run
behind.

**If `proceed=true`:** post one short comment via `add_comment` stating that the
gate allowed the run, quoting the `reason` and the head SHA. Then stop.

Do not review any files. Do not post inline comments. The only thing under test
is whether the gate, the check run, and `noop` behave as expected.
