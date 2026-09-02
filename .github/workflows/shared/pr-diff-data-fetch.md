---
# Shared pre-agent-steps for pre-fetching PR diff, metadata, and review comments.
# Works for both pull_request events and slash_command (issue) events on PRs.
#
# Outputs written to:
#   /tmp/gh-aw/agent/pr-diff.patch          — unified diff (up to 2000 lines)
#   /tmp/gh-aw/agent/pr-meta.json           — PR metadata (number, title, body, etc.)
#   /tmp/gh-aw/agent/pr-review-comments.json — existing inline review comments
#
# Skip-check: if all three files already exist and cache head SHA matches current PR head SHA, fetch is skipped.
#
# Usage:
#   cache:
#     key: pr-prefetch-${{ github.event.pull_request.head.sha }}
#     path: /tmp/gh-aw/agent
#     restore-keys:
#       - pr-prefetch-${{ github.event.pull_request.number }}-
#   imports:
#     - shared/pr-diff-data-fetch.md

pre-agent-steps:
  - name: Pre-fetch PR diff and review comments
    env:
      GH_TOKEN: ${{ github.token }}
      PR_NUMBER: ${{ github.event.pull_request.number }}
      PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}
      EXPR_GITHUB_REPOSITORY: ${{ github.repository }}
      PR_DIFF_MAX_LINES: "3000"
    run: |
      set -euo pipefail
      mkdir -p /tmp/gh-aw/agent
      CURRENT_HEAD_SHA="${PR_HEAD_SHA:-}"
      if [ -z "$CURRENT_HEAD_SHA" ]; then
        CURRENT_HEAD_SHA=$(gh pr view "$PR_NUMBER" --repo "$EXPR_GITHUB_REPOSITORY" --json headRefOid --jq '.headRefOid' 2>/dev/null || true)
      fi
      CACHE_HEAD_SHA=""
      if [ -f /tmp/gh-aw/agent/pr-data-head-sha.txt ]; then
        CACHE_HEAD_SHA="$(tr -d '\n' < /tmp/gh-aw/agent/pr-data-head-sha.txt)"
      fi
      # Skip fetch only when cache data matches current PR head commit.
      if [ -n "$CURRENT_HEAD_SHA" ] && [ "$CURRENT_HEAD_SHA" = "$CACHE_HEAD_SHA" ] && [ -f /tmp/gh-aw/agent/pr-diff.patch ] && [ -f /tmp/gh-aw/agent/pr-meta.json ] && [ -f /tmp/gh-aw/agent/pr-review-comments.json ]; then
        LINES=$(wc -l < /tmp/gh-aw/agent/pr-diff.patch)
        COMMENT_COUNT=$(jq 'length' /tmp/gh-aw/agent/pr-review-comments.json)
        echo "Cache hit: using pre-fetched PR data for head ${CURRENT_HEAD_SHA} (${LINES} diff lines, ${COMMENT_COUNT} review comments)"
      else
        { gh pr diff "$PR_NUMBER" --repo "$EXPR_GITHUB_REPOSITORY" \
            --exclude '**/*.lock.yml' \
            --exclude '**/generated/**' \
            --exclude '**/dist/**' \
            --exclude '**/build/**' \
            || true; } | head -n "${PR_DIFF_MAX_LINES}" > /tmp/gh-aw/agent/pr-diff.patch
        LINES=$(wc -l < /tmp/gh-aw/agent/pr-diff.patch)
        gh pr view "$PR_NUMBER" \
          --repo "$EXPR_GITHUB_REPOSITORY" \
          --json number,title,body,headRefName,headRefOid,additions,deletions,changedFiles,files \
          > /tmp/gh-aw/agent/pr-meta.json
        if [ -z "$CURRENT_HEAD_SHA" ]; then
          CURRENT_HEAD_SHA="$(jq -r '.headRefOid // empty' /tmp/gh-aw/agent/pr-meta.json)"
        fi
        gh api "repos/$EXPR_GITHUB_REPOSITORY/pulls/$PR_NUMBER/comments" \
          --paginate \
          --jq '.[] | {id, path, line: (.line // .original_line), body: .body[:200], user: .user.login}' \
          2>/dev/null | jq -s '.' > /tmp/gh-aw/agent/pr-review-comments.json \
          || echo '[]' > /tmp/gh-aw/agent/pr-review-comments.json
        if [ -n "$CURRENT_HEAD_SHA" ]; then
          printf '%s\n' "$CURRENT_HEAD_SHA" > /tmp/gh-aw/agent/pr-data-head-sha.txt
        else
          rm -f /tmp/gh-aw/agent/pr-data-head-sha.txt
        fi
        COMMENT_COUNT=$(jq 'length' /tmp/gh-aw/agent/pr-review-comments.json)
        echo "Pre-fetched PR diff (${LINES} lines), metadata, and ${COMMENT_COUNT} existing review comments for head ${CURRENT_HEAD_SHA:-unknown}"
      fi
---

<!--
## PR diff data fetch

Adapted from githubnext/gh-aw shared/pr-diff-data-fetch.md.

Pre-fetches what the reviewer needs before the agent starts, so turns are spent
analysing rather than paging through API calls.

Three reasons it earns its place here:

1. **The diff is fetched once, not once per sub-agent.** Every check needs the
   same diff.
2. **Existing review comments come along for free** -- exactly what the
   coordinator needs to suppress repeat findings on a `synchronize` run, so it
   pairs directly with comment-memory.
3. **The cache is keyed on head SHA**, so a re-run on an unchanged commit skips
   the fetch entirely.

`*.lock.yml` is excluded deliberately: the compiled agentic workflow is ~110 KB
and would otherwise consume the whole diff budget whenever the reviewer itself
is edited.
-->
