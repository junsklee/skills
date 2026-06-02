# cubrid-jira setup (one-time)

`cubrid-jira` (https://github.com/vimkim/cubrid-jira) is a Python CLI for CUBRID's
on-prem **JIRA Server 7.7.1** at `http://jira.cubrid.org`. The `cubrid-jira-ops` skill
drives this CLI; it does **not** install anything. The user runs the steps below once.

## Prerequisites (currently absent on this host)

`uv`, `pandoc`, and `cubrid-jira` itself are not installed; only the system `python3`
exists. Install them in order:

1. **`uv`** — provisions an isolated Python 3.14 interpreter (the missing system
   `python3.14` is therefore not a problem):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **`pandoc`** — required by `cubrid-jira` to convert JIRA wiki markup to markdown.
   This is an EL8 host:

   ```bash
   sudo dnf install -y pandoc
   ```

   If `sudo` is unavailable, install a static `pandoc` binary from a release tarball
   and put it on `PATH`.

3. **`cubrid-jira`**:

   ```bash
   uv tool install git+https://github.com/vimkim/cubrid-jira.git
   # fallback: pipx install git+https://github.com/vimkim/cubrid-jira.git
   ```

## Credentials — use `~/.netrc`

`cubrid-jira` authenticates with HTTP Basic Auth. The cleanest single source of truth is
`~/.netrc`, which the tool reads natively for `jira.cubrid.org`:

```
machine jira.cubrid.org
  login jlee16
  password <password-or-token>
```

```bash
chmod 600 ~/.netrc
```

- Never print or commit the password.
- The alternative is the `CUBRID_JIRA_USER` / `CUBRID_JIRA_PASSWORD` env vars, but
  `~/.netrc` keeps the secret out of the shell environment.
- The legacy creation script (`draft-korean-jira-from-diff/scripts/create_jira_issue.py`)
  keeps using its own `JIRA_USER` / `JIRA_PASSWORD` env vars — untouched here, so there is
  no clash.

## Verify

```bash
command -v cubrid-jira && cubrid-jira --help
pandoc --version | head -1
stat -c '%a' ~/.netrc          # expect 600
cubrid-jira search <known CUBRIDQA key> --output json
```

The last command should print a real summary/status and warm the read cache at
`~/.local/share/cubrid-jira/issues/` (override with `CUBRID_JIRA_DIR`).

## Notes

- The tool's default project key is `CBRD`; this team uses **`CUBRIDQA`** — always pass
  `--project CUBRIDQA` on writes.
- The host is plain `http://` (no HTTPS): Basic-auth credentials cross the network
  unencrypted. Rely on the internal network / VPN, keep `~/.netrc` at mode `600`, and
  never log credentials.
