---
name: cubrid-jira-ops
description: Read and operate on CUBRID's on-prem JIRA (jira.cubrid.org, project CUBRIDQA) via the cubrid-jira CLI — look up an issue by key, read/add comments, list/apply transitions, and link issues. Use for any CUBRID JIRA read/transition/comment work. Reads are immediate; every write is dry-run by default and requires explicit user confirmation before adding --yes. Issue creation is out of scope (use draft-korean-jira-from-diff).
---

# CUBRID Jira Ops

## Overview

Operate on CUBRID's on-prem **JIRA Server 7.7.1** (`http://jira.cubrid.org`, project
`CUBRIDQA`) through the [`cubrid-jira`](https://github.com/vimkim/cubrid-jira) CLI. This
skill fills the read / search / transition / comment / link gap that the generic
`jira-integration` skill (Atlassian Cloud) does not cover on this host.

Scope split:
- **Issue creation stays in `draft-korean-jira-from-diff`** — do not create issues here.
- This skill is the home for everything else against CUBRID JIRA.

## Prerequisite

`cubrid-jira` must be installed and `~/.netrc` configured. If `cubrid-jira` is not on
`PATH`, stop and walk the user through [references/setup.md](references/setup.md) instead of
erroring opaquely.

```bash
command -v cubrid-jira || echo "run references/setup.md first"
```

## Safety model

- **Reads are free** (`search`, `comment-list`, `transition` with no `--to`). Run them
  freely; they are cache-first and do not mutate JIRA.
- **Every write is dry-run by default.** Run the command **without** `--yes` first, show the
  user the previewed change, and add `--yes` only after explicit confirmation. This is the
  same "preview → confirm" gate used by the other CUBRID skills.
- Always pass **`--project CUBRIDQA`** explicitly — never rely on the tool's `CBRD` default.
- Never print credentials; `~/.netrc` is the auth source.

## Operations

### Look up an issue (read)

`search` takes a single **issue key or browse URL** and prints the issue as markdown to
stdout (cache-first). It has no `--output json`.

> Requires the local read-auth patch (see [references/setup.md](references/setup.md)).
> Without it, `search` returns HTTP 401 on this instance because upstream's read path is
> unauthenticated. The authenticated commands below work regardless.

```bash
cubrid-jira search CUBRIDQA-1370               # markdown to stdout, cache-first
cubrid-jira search CUBRIDQA-1370 --no-recurse  # fetch only this issue, skip linked issues
cubrid-jira search CUBRIDQA-1370 --force       # bypass cache, re-fetch
```

### Finding issues by query (JQL) — not supported

`search` accepts only one key/URL; cubrid-jira 1.0.0 has **no** JQL or search-by-assignee
command. To find "my open issues", use the JIRA web UI / a saved filter to get the keys,
then `cubrid-jira search <KEY>` each one.

### Read comments (read)

```bash
cubrid-jira comment-list CUBRIDQA-1370            # most recent 50 by default
cubrid-jira comment-list CUBRIDQA-1370 --limit 0  # all comments
```

### Add a comment (write — dry-run → confirm → --yes)

Write the Korean comment body to a temp file, preview, then commit after confirmation:

```bash
cubrid-jira comment CUBRIDQA-1370 --body-file /tmp/cubrid-jira-comment.md            # dry-run preview
cubrid-jira comment CUBRIDQA-1370 --body-file /tmp/cubrid-jira-comment.md --yes      # after user confirms
```

### Transition status (write — list first, then --yes)

```bash
cubrid-jira transition CUBRIDQA-1370                          # list available transitions (read)
cubrid-jira transition CUBRIDQA-1370 --to "In Progress"       # dry-run preview
cubrid-jira transition CUBRIDQA-1370 --to "In Progress" --yes # after user confirms
```

### Link issues (write — dry-run → confirm → --yes)

```bash
cubrid-jira link CUBRIDQA-1370 --type Relates --to CUBRIDQA-1371        # dry-run
cubrid-jira link CUBRIDQA-1370 --type Relates --to CUBRIDQA-1371 --yes  # after confirm
```

Link types: `Relates`, `Blocks`, `Cloners`, `Duplicate`.

## Conventions

- Comment bodies in Korean (consistent with the PR / JIRA skills); identifiers, paths, and
  class/method names stay in English.
- All write subcommands accept `--output {text|json}`, `--server URL`, and `--dir DIR`.
- The host is `http://` (not HTTPS) — see the security note in `references/setup.md`.

## What to report back

After an operation, tell the user: the issue key, what was read or changed, and — for any
write — confirm it was a dry-run preview or that `--yes` was applied only after their
confirmation.
