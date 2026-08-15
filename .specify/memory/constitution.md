<!--
Sync Impact Report
- Version change: (unratified template) → 1.0.0
- Rationale: Initial ratification. The prior file on disk was the raw, unfilled
  constitution-template scaffold (all placeholder tokens present, no adopted values) — this is
  therefore an initial adoption, not an amendment, hence MAJOR version 1.0.0.
- Modified principles: none (first defined set)
- Added sections:
  - I. Code Quality & Maintainability
  - II. Test-First & Testing Standards
  - III. Secure Credential & API Token Handling (NON-NEGOTIABLE)
  - Security Requirements (Section 2)
  - Development Workflow & Quality Gates (Section 3)
  - Governance
- Removed sections: none
- Deferred placeholders: none — all bracketed tokens from the template have been resolved.
- Templates checked for alignment:
  - .specify/templates/plan-template.md — generic "Constitution Check" gate references remain
    compatible (no principle names hardcoded there); no changes required.
  - .specify/templates/spec-template.md — no constitution-specific references; no changes required.
  - .specify/templates/tasks-template.md — no constitution-specific references; no changes required.
  - .specify/templates/checklist-template.md — no constitution-specific references; no changes required.
  - .claude/skills/*.md — command bodies read the constitution at runtime; no edits needed.
- Follow-up TODOs: none.
-->

# proauto-bot Constitution
<!-- proauto-bot: Telegram bot for auto ads automation (python-telegram-bot, with VK cross-posting) -->

## Core Principles

### I. Code Quality & Maintainability
Code merged into this repository MUST be readable, self-consistent, and no more complex than the
problem requires.

- Functions and modules MUST have a single clear responsibility; large handlers (e.g. Telegram
  command/callback handlers) MUST be decomposed rather than grown indefinitely.
- Public functions and non-trivial logic MUST use descriptive names over comments; comments are
  reserved for non-obvious *why* (rate-limit workarounds, Telegram/VK API quirks, ordering
  constraints), not restatements of *what* the code does.
- No dead code, commented-out blocks, or speculative abstractions ("just in case") MAY be merged.
  Unused code MUST be deleted, not disabled.
- Configuration and constants (target chat IDs, usernames, links, ports, data directories) MUST be
  defined once and read from environment/config, not duplicated as literals across the codebase.
- Error handling MUST be specific to failure modes that can actually occur (Telegram API errors,
  network/httpx failures, malformed data files); broad bare `except:` blocks that silently swallow
  errors are prohibited except at top-level bot/event-loop guards, and even then MUST log the
  exception.
- Rationale: this bot runs unattended against live Telegram/VK APIs and posts to real channels —
  unreadable or overly clever code directly increases the time to diagnose a bad post, a stuck
  scheduler, or a silent failure in production.

### II. Test-First & Testing Standards
Behavior that can break the bot in production (message formatting, scheduling logic, data
persistence, VK/Telegram payload construction) MUST be covered by automated tests before it is
considered done.

- New non-trivial logic (parsing, scheduling, database/state mutations, payload builders) MUST
  ship with unit tests; bug fixes MUST include a regression test that fails before the fix and
  passes after.
- Tests MUST NOT call real Telegram or VK APIs, and MUST NOT require a live `BOT_TOKEN`,
  `VK_TOKEN`, or network access. External calls (`python-telegram-bot`, `httpx` requests to
  `api.vk.com` / `api.telegram.org`) MUST be mocked or wrapped behind a seam that tests substitute.
- Tests MUST NOT depend on or mutate real persisted data in `DATA_DIR`; use temporary directories
  or fixtures.
- A change to `auto_poster.py` or `car_database.py` that alters posting, scheduling, or data-format
  behavior MUST NOT be merged without a passing test run demonstrating the change; purely cosmetic
  or comment-only changes are exempt.
- Test-first (write the failing test before the fix/feature) is the expected default for bug fixes
  and SHOULD be followed for new features; deviations are acceptable for pure prototyping but MUST
  be backfilled with tests before merge to the default branch.
- Rationale: this is a single-operator automation bot with no staging environment — the test suite
  is the only safety net standing between a bad change and an incorrect post landing in a live
  Telegram channel or VK community.

### III. Secure Credential & API Token Handling (NON-NEGOTIABLE)
Telegram bot tokens, VK access tokens, chat/owner IDs, and any other secret MUST never be
committed, logged in full, or exposed outside the process that needs them.

- Secrets (`BOT_TOKEN`, `VK_TOKEN`, and any future API key/webhook secret) MUST be loaded only
  from environment variables or an untracked `.env` file via `python-dotenv`; hardcoding a secret
  value as a string literal in source is prohibited.
- `.env` and any other file that can hold real credentials MUST remain listed in `.gitignore`;
  a change that would cause a secret-bearing file to be tracked by git MUST be rejected.
- Logging, print statements, error messages, and exception traces MUST NOT include a secret value
  in full or in part — not even a truncated prefix (e.g. `token[:10]`) — since partial values still
  narrow brute-force search space and commonly leak into shared logs/screenshots. Logs MAY state
  only whether a required secret is present (`"BOT_TOKEN: OK"` / `"BOT_TOKEN: MISSING"`).
  Existing debug prints that echo any portion of `BOT_TOKEN` or `VK_TOKEN` are a known violation and
  MUST be removed as part of any change that touches that code path.
  Enforcement note: `auto_poster.py` currently prints `BOT_TOKEN[:10]` at startup (line ~3206);
  this is a known violation to be remediated under this principle, not a precedent to extend.
- Committed example/config files (e.g. `.env.example`) MUST use obvious placeholder values, never
  a real or formerly-real token.
- If a real secret is ever committed or otherwise exposed (leaked to a log, a shared channel, a
  public repo), it MUST be treated as compromised: the token MUST be revoked/rotated via the
  issuing platform (BotFather for `BOT_TOKEN`, VK app settings for `VK_TOKEN`) before any other
  work continues, not merely removed from future commits.
- Access-control values that gate privileged actions (`OWNER_ID`, `MANAGER_USER_ID`,
  `TARGET_GROUP_ID`) MUST be treated with the same handling discipline as secrets: sourced from
  environment/config, never assumed from user-supplied input.
- Rationale: a leaked bot token grants full control of the Telegram bot (post, delete, message any
  user it can reach) and a leaked VK token grants equivalent control of the VK community; the blast
  radius of a credential leak here is a real, publicly visible incident, not an abstract risk.

## Security Requirements
<!-- Concrete, checkable rules that operationalize Principle III. -->

- All new external integrations (additional social platforms, webhooks, admin APIs) MUST follow
  the same environment-variable-based credential pattern already used for `BOT_TOKEN` and
  `VK_TOKEN` — no exceptions for "temporary" or "internal-only" integrations.
- Dependency additions (`requirements.txt`) that introduce new network clients or credential
  handling MUST be reviewed for whether they log request/response bodies by default; verbose HTTP
  logging MUST be disabled or scrubbed in production runs.
- Data written under `DATA_DIR` MUST NOT include raw secret values; if a secret must be cached at
  runtime, it MUST stay in memory/environment only.
- Before any commit, the author MUST re-check `git status`/diff for accidentally staged `.env`
  files or literal token strings; this check is required precisely because it is easy to skip.

## Development Workflow & Quality Gates

- Every change to `auto_poster.py` or `car_database.py` MUST be reviewed (self-review at minimum
  for a single-maintainer repo) against Principles I–III before merge: readability, test coverage
  for behavior change, and no credential exposure.
- Changes MUST be run locally (or via CI, once configured) with the test suite passing before
  being pushed to the default branch.
- Commit messages MUST describe the *why* of a change when it is not obvious from the diff
  (e.g. "fix: stop double-posting on scheduler restart"), consistent with this repository's
  existing history conventions.
- Any change that touches token loading, logging setup, or environment-variable handling MUST be
  called out explicitly in the PR/commit description so it receives extra scrutiny under
  Principle III.

## Governance

This constitution supersedes ad hoc practice for this repository. Where existing code conflicts
with a principle here (see the known `BOT_TOKEN[:10]` logging violation under Principle III), the
conflict MUST be tracked and remediated, not treated as an implicit exception.

- **Amendment procedure**: amendments are made by editing this file directly (single-maintainer
  project); a change MUST update the Sync Impact Report header and the version/date footer in the
  same edit.
- **Versioning policy**: semantic versioning applies to this document —
  MAJOR for backward-incompatible governance/principle removals or redefinitions, MINOR for a new
  principle or materially expanded guidance, PATCH for clarification/wording/typo fixes.
- **Compliance review**: every change to `auto_poster.py`, `car_database.py`, or their tests is
  expected to be checked against the Core Principles above before merge; violations found after
  the fact MUST be filed as follow-up work rather than silently ignored.

**Version**: 1.0.0 | **Ratified**: 2026-08-15 | **Last Amended**: 2026-08-15
