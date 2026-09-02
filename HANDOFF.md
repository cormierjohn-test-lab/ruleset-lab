# Handoff — get a gh-aw agent actually running in this repo

**Goal:** get *any* gh-aw agentic workflow to execute an agent turn in
`cormierjohn-test-lab/ruleset-lab`.

## RESOLVED 2026-09-02

Run [33588186977](https://github.com/cormierjohn-test-lab/ruleset-lab/actions/runs/33588186977)
completed a full agent turn on `claude-sonnet-5`: every job green, `Gate B
Probe` check run published on the head SHA, comment posted, ~15 AI credits.
The Copilot Pro subscription on `cormierjohn` is sufficient. No org Copilot
billing was needed.

Two things were wrong, and both were assumptions in this doc:

1. **The PAT never had the Copilot Requests permission.** It had the
   *repository* permission "Copilot agent settings", which is unrelated.
   Copilot Requests is an *account* permission, only offered as **Read-only**
   (there is no read-and-write option). It also needs a second, undocumented
   account permission: **Models: Read-only**. Without Models, the proxy's
   `/models` fetch returns 401 and every run dies before inference. Editing the
   existing token's permissions keeps the same secret value, so
   `COPILOT_GITHUB_TOKEN` did not need to be re-set.
2. **`pull_request` runs use the workflow file from the PR branch**, merged with
   `main`. The probe branch still pinned `model: claude-sonnet-4.6` in both the
   `.md` and the `.lock.yml`, so a repo variable set on `main` was ignored, and
   4.6 is not in the integrator's model list. Fix was syncing the two workflow
   files on `probe/ghaw-gate-test` to `main`.

Model is now set by the repo variable `GH_AW_DEFAULT_MODEL_COPILOT=claude-sonnet-5`
(the compiled lock reads `vars.GH_AW_MODEL_AGENT_COPILOT ||
vars.GH_AW_DEFAULT_MODEL_COPILOT || 'auto'`), so changing model needs no
recompile or merge. Models the `agentic-workflows` integrator accepts include
`claude-sonnet-5`, `claude-opus-5`, `claude-fable-5.1`, `claude-haiku-4.5`,
`gpt-5.5`, `gpt-5.4`. `claude-sonnet-4.6` is **not** accepted.

Corrections to the earlier analysis, so nobody chases them again:
- The `model: auto` 400 run had **not** authenticated. Its `/models` fetch also
  returned 401; the pricing error was the proxy's local fallback for an empty
  model list.
- `claude-sonnet-5` was never an invalid model id. It 401'd for the same token
  reason as everything else.
- The proxy sends the raw PAT as `Authorization: Bearer` to
  `api.githubcopilot.com` with `Copilot-Integration-Id: agentic-workflows`. No
  token exchange. Individual plans work fine with this.

Local diagnostic that matches what CI does (Copilot CLI is installed via
`npm install -g @github/copilot`; CI pins 1.0.79):

```bash
 export COPILOT_GITHUB_TOKEN='github_pat_...'
copilot --prefer-version 1.0.79 -p "reply with the single word PONG"; unset COPILOT_GITHUB_TOKEN
```

**Still untested:** the `proceed=false` / `noop` path. The successful run took
`push_after_bot_review`, so whether `noop` leaves a green check run behind is
still the open question this probe was built for. It needs a `synchronize`
push on a PR the bot has never reviewed.

Everything below this line is the pre-resolution state, kept for the record.

---

## The blocker, precisely (historical)

Every run reaches the agent job and dies there:

```
Authentication failed with provider at http://172.30.0.30:10002 (HTTP 401).
  Check your COPILOT_PROVIDER_API_KEY or COPILOT_PROVIDER_BEARER_TOKEN.

[copilot-harness] attempt 2: Copilot authentication failed through the gh-aw
  API proxy (HTTP 401, model=claude-sonnet-4.6, stage=starting the Copilot CLI request)

[copilot-harness] awf-reflect: models fetch returned 401 for http://api-proxy:10002/models
```

**The most diagnostic line is the last one.** `models fetch returned 401` means
even *listing* available models fails — this happens before any model choice
matters, so it is not a bad model identifier.

Failing runs, newest first:

| Run | What was being tested | Outcome |
|---|---|---|
| [33584724207](https://github.com/cormierjohn-test-lab/ruleset-lab/actions/runs/33584724207) | `model: claude-sonnet-4.6` | 401 |
| [33583361351](https://github.com/cormierjohn-test-lab/ruleset-lab/actions/runs/33583361351) | model unpinned → `auto` | **400** — different error, see below |
| [33581639350](https://github.com/cormierjohn-test-lab/ruleset-lab/actions/runs/33581639350) | `model: claude-sonnet-5` | 401 |
| [33578096430](https://github.com/cormierjohn-test-lab/ruleset-lab/actions/runs/33578096430) | classic PAT | rejected at validation |

Job breakdown on a 401 run: `pre_activation ✅ → activation ✅ → agent ❌ →
detection ✅ → safe_outputs ✅ → conclusion ✅`.

### The leading hypothesis

**Copilot Pro probably does not grant API-inference entitlement to a PAT.**

Pro is an editor subscription. gh-aw needs *programmatic* inference through its
proxy, which is generally a Copilot **Business/Enterprise** feature. gh-aw's own
compile-time tip points the same way:

> set `permissions.copilot-requests: write` to use GitHub Actions token-based
> inference with the Copilot engine instead of a personal access token
> (`COPILOT_GITHUB_TOKEN`). This option requires that your organization has
> centralized Copilot billing enabled.

This is a hypothesis, not a proven fact. **It has not been tested by calling the
Copilot API directly with the token** — that is the single highest-value next
step, because it distinguishes "token/permission wrong" from "plan does not
include this" in one call instead of a 4-minute CI cycle.

---

## What is already proven (do not re-litigate)

Each of these cost a CI cycle. The error message *changed* at each step, which
is what makes them conclusions rather than guesses.

1. **gh-aw runs here.** It compiles, the workflow triggers, `pre_activation` and
   `activation` both pass. This was the first gh-aw workflow ever in this repo.
2. **Classic PATs (`ghp_`) are rejected outright** — hard error, "Classic PATs
   are not supported for GitHub Copilot".
3. **The token must be a fine-grained PAT** (`github_pat_`), **personal
   resource owner** (not the org). ~~with Copilot Requests: read and write~~
   **This was wrong.** The token had no account permissions at all; see the
   RESOLVED section. Copilot Requests only exists as read-only.
4. **`claude-sonnet-5` is not a valid gh-aw model id.** gh-aw's own workflows
   use `claude-sonnet-4.6`, `claude-haiku-4.5`, `claude-opus-4.8`.
5. **Leaving `model` unset resolves to `auto`, which fails differently:**
   `400 Model "auto" has no AI credits pricing and no default pricing is
   configured`. Worth noting: a 400 here means the request **authenticated** and
   reached the model layer. That is the closest this has come to working, and it
   may be a more productive thread than the 401.

---

## Setup

### Org — `cormierjohn-test-lab` (plan: **free**)

| | |
|---|---|
| Owner / "manager" | **`cormierjohn`** — has `admin:org` |
| "Developer" | **`johncormier-lovelytics`** |
| Team | **`managers`** — sole member `cormierjohn`; the dev is deliberately NOT in it |
| Copilot | No org seats. `cormierjohn` holds a personal **Copilot Pro** subscription |

Both accounts are authenticated locally; switch with
`gh auth switch --user <name>`. Two accounts exist so PR author and reviewer can
be different people — a PR author cannot review their own PR.

### Repo — `cormierjohn-test-lab/ruleset-lab` (**public**)

Public matters: **Actions minutes are unlimited**, so a stalled workflow is
never a quota problem.

- Actions: `enabled`, `allowed_actions: all`
- Org workflow policy: `default_workflow_permissions: write`,
  `can_approve_pull_request_reviews: true` (both were `read`/`false`, which
  greyed out the repo-level controls — org policy overrides repo)
- Ruleset `develop-shape` on `main`: requires a PR, requires the
  `Notebook PR Review` status check, `dismiss_stale_reviews_on_push: true`,
  bypass actor = the `managers` team
- Secret: **`COPILOT_GITHUB_TOKEN`** (set 2026-09-02T02:00:47Z; permissions
  corrected in place 2026-09-02, same value)
- Variable: **`GH_AW_DEFAULT_MODEL_COPILOT`** = `claude-sonnet-5`

To merge to `main`, use `cormierjohn` with `gh pr merge <N> --merge --admin`.

### Local

- Clone: `C:\Repositories\ruleset-lab`
- gh-aw CLI: **v0.86.2**
- gh-aw source (useful reference): `C:\Repositories\gh-aw`

---

## How to test

The existing probe is `.github/workflows/gate-b-agentic.md` (+ its `.lock.yml`).
It is deliberately trivial: read a file written by a pre-agent step, emit a check
run, then either `noop` or post one comment. It does not review code — it exists
only to prove an agent turn can happen.

```powershell
cd C:\Repositories\ruleset-lab

# compile BY NAME (never bare `gh aw compile` — see gotchas)
gh aw compile gate-b-agentic

# workflow changes must be on main to take effect
gh auth switch --user cormierjohn
git checkout -b <branch> origin/main
git add .github/workflows/gate-b-agentic.*
git commit -m "..."
git push -u origin <branch>
gh pr create --base main --head <branch> --title "..." --body "..."
gh pr merge <N> --merge --admin

# then trigger from the dev account on an open PR
gh auth switch --user johncormier-lovelytics
git checkout probe/ghaw-gate-test
"x" | Add-Content ghaw_test.txt      # must be a CONTENT change, not workflow-only
git commit -am "trigger" ; git push

# read the result
gh run list --repo cormierjohn-test-lab/ruleset-lab --workflow gate-b-agentic.lock.yml --limit 1
gh run view <id> --repo cormierjohn-test-lab/ruleset-lab --json jobs --jq '.jobs[] | "\(.conclusion) \(.name)"'
gh run view <id> --repo cormierjohn-test-lab/ruleset-lab --log-failed
```

PR **#42** (`probe/ghaw-gate-test`) is open and wired up for this.

**A `workflow_dispatch` trigger would be far easier to iterate on** than the
current `pull_request` setup — no PR state to keep healthy, no merge to main
before each attempt. Adding one is encouraged.

---

## Gotchas that already cost time

**A conflicted PR fires NO `pull_request` events.** Two pushes triggered
absolutely nothing — not even trivial non-gh-aw workflows. Everything looked
healthy: pushes succeeded, commits reached the remote, Actions enabled, all
workflows `active`, GitHub Status green. The cause was `mergeable: CONFLICTING`
after a workflow file was changed on both `main` and the branch. **Check this
first when workflows go silent:**

```powershell
gh pr view <N> --repo cormierjohn-test-lab/ruleset-lab --json mergeable,mergeStateStatus
```

**A workflow-file-only push does not trigger the workflow.** Change a content
file to trigger.

**Never run a bare `gh aw compile`.** It rewrites
`GH_AW_ACTION_FAILURE_ISSUE_EXPIRES_HOURS` across every workflow. Always compile
by name.

**gh-aw hashes the *merged* frontmatter.** Editing a shared import invalidates
the lock of every workflow that imports it, and a stale lock fails `activation`
with `E009 CONFIG_HASH_MISMATCH`.

**`gh pr edit --add-reviewer Copilot` fails** — gh lowercases the login. The
reviewer entry named "Copilot" in the UI is GitHub's own code review, a separate
product.

**`github-actions[bot]` cannot be requested as a reviewer.** The API returns
**200 with a PR object** and silently does nothing — a no-op, not an error.

---

## Suggested order of attack

1. **Call the Copilot API directly with the token.** One request settles whether
   this is a permission problem or a plan problem. Currently unproven and it
   gates everything else.
2. **Chase the `auto` / 400 pricing error instead.** That path authenticated
   successfully. If `apiProxy.defaultAiCreditsPricing` can be configured, it may
   be a shorter route to a working agent than fixing the 401.
3. **If Pro genuinely cannot do API inference,** the options are Copilot Business
   on the org (then use `copilot-requests: write` and drop the PAT entirely), or
   a different gh-aw engine that does not depend on Copilot.
4. **Add a `workflow_dispatch` trigger** regardless — the iteration loop is
   currently much slower than it needs to be.

---

## Background: why this lab exists

Testing PR-review automation for
`dominos-pizza/dai-dbx-platform-modernization`, where a suite of gh-aw reviewers
already runs. Two findings drove the work here, both measured in this repo:

- **`github-actions[bot]` cannot be re-requested as a reviewer**, so a developer
  has no way to ask the agents to look again after pushing fixes.
- **A bot review does not clear `requested_reviewers`.** The human stays pending
  forever, so "is someone pending?" is useless as a re-run condition — it is true
  on every subsequent push.

The fix under test is **Gate B**: on `synchronize`, run only if the bot has
already reviewed this PR ("re-check what I raised"), plus `concurrency` with
`cancel-in-progress` so a burst of commits collapses into one run.

**Gate B is already proven with plain `GITHUB_TOKEN` workflows** — see
`sync-gate-b-reviewed.yml`. Measured: skips before any review, fires on review
request, fires on push only after a bot review, and 3 rapid pushes collapsed to
1 run on the latest SHA.

The only untested piece is whether **`noop` still leaves a green check run**.
That ordering matters: `noop` is terminal, so a check run emitted *after* it
never publishes and the PR shows a missing check rather than a passing one —
a silent failure. That is what `gate-b-agentic.md` is meant to verify, and it
needs a working agent to do so.
