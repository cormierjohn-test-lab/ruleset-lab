---
name: "Lab: Timezone Review"
description: "Lab port of the real timezone reviewer, to test the outstanding-findings re-review model end to end"

# A real reviewer, running the real shared prompt, so the re-review behaviour
# under test is the one that will ship -- not a mock of it.
#
# What is being tested:
#   1. a NEW defect gets an inline comment
#   2. on re-review, an UNFIXED defect is listed in the review body only, with
#      NO second inline comment
#   3. a FIXED defect disappears silently -- no "resolved" note
#   4. a run with only outstanding defects still submits REQUEST_CHANGES
#
# Trigger is review_requested plus synchronize so a push can drive the
# re-review without a human re-requesting.
on:
  pull_request:
    types: [review_requested, synchronize]
    branches: [main]
    paths:
      - '**/*.py'
    draft: false

imports:
  - shared/pr-review-common.md

permissions:
  contents: read
  pull-requests: read

engine:
  id: copilot

timeout-minutes: 15

cache:
  key: pr-prefetch-${{ github.event.pull_request.head.sha }}
  path: /tmp/gh-aw/agent
  restore-keys:
    - pr-prefetch-${{ github.event.pull_request.number }}-

safe-outputs:
  create-check-run:
    name: "Lab Timezone Review"
    max: 1

pre-agent-steps:
  - name: Find changed Python files
    id: candidates
    env:
      PR_NUMBER: ${{ github.event.pull_request.number }}
      EXPR_GITHUB_REPOSITORY: ${{ github.repository }}
      GH_TOKEN: ${{ github.token }}
    run: |
      set -euo pipefail
      mkdir -p /tmp/gh-aw/agent

      if ! CHANGED=$(gh pr view "$PR_NUMBER" --repo "$EXPR_GITHUB_REPOSITORY" \
                       --json files --jq '.files[].path'); then
        echo "::error::Could not list changed files for PR #${PR_NUMBER}."
        exit 1
      fi

      : > /tmp/gh-aw/agent/candidates.txt
      printf '%s\n' "$CHANGED" | grep -E '\.py$' >> /tmp/gh-aw/agent/candidates.txt || true

      COUNT=$(wc -l < /tmp/gh-aw/agent/candidates.txt | tr -d ' ')
      echo "count=${COUNT}" >> "$GITHUB_OUTPUT"
      echo "Python files changed: ${COUNT}"
      sed 's/^/  /' /tmp/gh-aw/agent/candidates.txt
---

# Timezone review

You check **one thing**: a timestamp that is not localized to the business
timezone. Ignore everything else in the file.

## What is a defect — `severity: defect`

A call that produces a timestamp or date in UTC where a business date is meant:

- `current_timestamp()`, `CURRENT_DATE()`, `now()` in SQL
- `datetime.now()` or `datetime.utcnow()` in Python with no timezone argument
- `F.current_timestamp()` / `F.current_date()` in PySpark

The cluster runs UTC. A report grouped by a UTC date puts late-evening business
activity on the following day, silently, and only in the hours that matter most.

## What is correct

An explicit timezone: `from_utc_timestamp(current_timestamp(), 'America/Chicago')`,
`datetime.now(ZoneInfo("America/Chicago"))`, or a `CONTEXT_TIMEZONE` variable
resolved from config.

## Not a finding

- A UTC timestamp written to an audit or logging column, where UTC is correct.
- A comment or docstring mentioning `now()`.
- A variable named `current_timestamp` that is not the function call.
