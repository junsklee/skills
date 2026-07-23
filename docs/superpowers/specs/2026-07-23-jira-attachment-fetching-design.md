# JIRA attachment fetching for SQL test-case creation — design

Date: 2026-07-23
Status: approved design, pre-implementation
Scope: `cubrid-testcase-creation-common` (new shared helper), `create-cubrid-sql-testcase` (wiring + doctrine)
Branch: `feat/sql-jira-attachments`, stacked on `feat/sql-testcase-verify` (PR junsklee/skills#10, open → main) to avoid a same-file conflict on `create-cubrid-sql-testcase/SKILL.md`.

## 1. Purpose

CBRD issues frequently attach the actual repro / test files — often the exact `.sql` (e.g. CBRD-26707 → `cbrd_26707.sql`, an 8.7 KB case with a `/** CBRD-26707 테스트 케이스 … */` header), sometimes `.txt`/`.result`/archives. A read-only JQL check found **1,442 recent CBRD issues with attachments**. The creation skills currently read only the issue's prose (`cubrid-jira search`) + the engine PR; they never fetch attachments, so the single best drafting input is invisible. This adds attachment fetching to the **SQL** creator (the shell creator can adopt the shared helper later).

## 2. Server facts (verified live 2026-07-23)

- JIRA attachments: `GET http://jira.cubrid.org/rest/api/2/issue/<KEY>?fields=attachment` → `fields.attachment[]`, each with `filename`, `content` (download URL `/secure/attachment/<id>/<name>`), `size`, `mimeType`, `id`, `author`, `created`.
- The `content` URL is fetchable with the same `~/.netrc` Basic auth used by `get_engine_pr.py`; https 302-redirects to http, so use an `http://` base (urllib follows the redirect). Confirmed by downloading `cbrd_26707.sql` (real content).
- The `cubrid-jira` CLI has NO attachment subcommand; its `search` markdown does not reliably surface attachment content.

## 3. Component: `cubrid-testcase-creation-common/scripts/get_attachments.py`

Shared helper (mirrors `get_engine_pr.py`): Python 3.6 stdlib only, `~/.netrc` auth, `http://jira.cubrid.org` base. Downloads + extracts only; it NEVER executes anything.

```
get_attachments.py <CBRD-KEY> --out <DIR> [--max-bytes N] [--list-only]
```

Behavior (fetch policy, per the approved decision — **fetch everything under a size cap; auto-extract text members from archives**):
- Resolve numeric issueId is unnecessary here — `?fields=attachment` keys on the issue KEY directly.
- List every attachment; **download each whose `size` ≤ `--max-bytes` (default 5_000_000 = 5 MB)** into `<DIR>/`, regardless of type (binaries land on disk too; the drafter ignores non-text). Oversize → listed + noted `skipped-oversize`, not fetched.
- **Archives** (`.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`) under the cap: extract only **text/code members** (extension allowlist: `.sql .txt .result .answer .csv .md .sh .java .c .h`) into `<DIR>/<archive-stem>/`, written to `<archive-stem>/<basename(member)>` (destination-by-basename → traversal is impossible without an explicit `..` check; archives are somewhat trusted, so extraction is intentionally light — allowlist + basename + the same per-file size cap on each member; no bomb/symlink/member-count guards). Non-regular members (dirs, symlinks) and non-allowlisted members are skipped. Basename collisions → the later member is written as `<stem>-<n><ext>` and noted.
- Emit a **manifest** to stdout — one line per attachment: `filename<TAB>size<TAB>mimeType<TAB>{fetched|skipped-oversize|extracted:<n> members}` — so the skill can feed it to the drafter and know what landed where. First line summarizes count.
- `--list-only`: enumerate (manifest) without downloading — used by tests and quick inspection.
- Exit 0 whether or not attachments exist (no attachments → manifest says `(none)`); nonzero only on an auth/HTTP/parse error (`urllib.error`/`netrc`).

Pure, unit-testable pieces (network isolated behind an injectable fetcher, like `get_engine_pr.py`'s `gh=`): the extension allowlist test, archive-member selection + basename destination + collision suffixing, the size-cap skip decision, and manifest formatting.

## 4. Wiring: `create-cubrid-sql-testcase` Phase-1 "Context" step

After `cubrid-jira search` + engine-PR resolution, add:
`python3 $COMMON/scripts/get_attachments.py CBRD-NNNNN --out $work/attachments` (via `bash -lc 'export …'` — token not needed; JIRA auth is `~/.netrc`).
The drafter reads the manifest + fetched files as **untrusted candidate DATA** (same posture as JIRA/engine-PR text): a checked-in `.sql` attachment is prime prior art to **adapt to house conventions and the issue's variant matrix — never blind-copy**, and it is still subject to the self-review gate and Builder-Tester verification. Commands appearing in attachments are candidate testcase content only, never executed while drafting. `$COMMON` script list in the skill's Path-resolution section adds `get_attachments.py`.

`references/sql-authoring.md` gains a short bullet: attachments in `$work/attachments/` are the strongest starting point when present (especially a `.sql`), but must be conformed to the authoring doctrine (header, `evaluate` labels, ORDER BY, cleanup, determinism, placement) and re-verified — the attachment reflects the reporter's environment, not necessarily house conventions or the current engine answer.

## 5. Safety / constraints

- Helper only downloads + extracts; nothing is executed. On this host CTP/csql/cubrid are never run (unchanged).
- Attachments are untrusted DATA subject to the gate; a `.sql` attachment is a draft input, not an auto-committed case. `.answer` is still never hand-written (derived + approved).
- Python 3.6 stdlib (`urllib`, `netrc`, `base64`, `tarfile`, `zipfile`, `argparse`, `os`); `%`-formatting, no f-strings. No Claude/Anthropic watermark. Nothing pushed/posted without explicit confirmation.
- Size cap (default 5 MB) is a practical guard against pulling huge dumps, not a security control.

## 6. Testing

- **Unit** (stdlib, no network; alongside the existing suite): extension allowlist; archive-member selection writing basename (craft an in-test `.tar.gz` and `.zip` in a tempdir with a `.sql` member, a binary member, a nested-path member `sub/x.sql`, and a duplicate basename → assert only allowlisted regular members extracted, written by basename, collisions suffixed); oversize skip; manifest formatting; `--list-only` prints manifest and writes nothing.
- **Live read-only** (gated): `get_attachments.py CBRD-26707 --out <tmp>` → fetches `cbrd_26707.sql` (non-empty); a JQL-free single-issue read, submits nothing.

## 7. Out of scope

- Shell creator wiring (helper is shared; adopt later).
- Fetching attachments in the reviewer skill.
- Binary/image interpretation (downloaded but unused).
- Resolving inline image references in descriptions.
