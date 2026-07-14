#!/usr/bin/env python3
"""Create/refresh a test-case branch on the fork and open the PR (Python 3.6, stdlib).

DRY-RUN BY DEFAULT — without --yes nothing is written to GitHub.

Subcommands:
  status --upstream O/R --fork-owner U --branch BR [--base-ref develop]
  push   --upstream O/R --fork-owner U --branch BR --package-dir DIR --message MSG
         [--base-ref develop] [--update] [--yes]
  pr     --upstream O/R --fork-owner U --branch BR --title T --body-file F
         [--base-ref develop] [--yes]
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghlib import API, gh_request, parse_repo, token


def branch_name(key):
    """'CBRD-12345' / 'cbrd_12345' / text containing either -> 'cbrd_12345_tc'."""
    m = re.search(r"(?i)cbrd[-_](\d+)", key)
    if not m:
        raise ValueError("no CBRD key in: " + key)
    return "cbrd_%s_tc" % m.group(1)


def collect_package(package_dir):
    """Walk a staging dir -> sorted [(repo_path, abs_path)]. Skips dot-entries."""
    out = []
    base = os.path.abspath(package_dir)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ap = os.path.join(root, f)
            out.append((os.path.relpath(ap, base).replace(os.sep, "/"), ap))
    return sorted(out)


def answers_empty(sizes):
    """{repo_path: byte_size} -> sorted list of empty .answer/.answer_cci paths."""
    return sorted(p for p, s in sizes.items()
                  if s == 0 and (p.endswith(".answer") or p.endswith(".answer_cci")))


def answer_paths(filenames):
    """Filter an iterable of repo paths to .answer/.answer_cci files, sorted."""
    return sorted(p for p in filenames
                  if p.endswith(".answer") or p.endswith(".answer_cci"))


def build_pr_payload(title, body, fork_owner, branch, base_ref):
    return {"title": title, "body": body,
            "head": "%s:%s" % (fork_owner, branch), "base": base_ref}


def get_branch_sha(owner, repo, branch, tok):
    try:
        ref = gh_request("/repos/%s/%s/git/ref/heads/%s" % (owner, repo, branch), tok)
        return ref["object"]["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def sync_fork_base(fork_owner, repo, base_ref, tok):
    """Fast-forward the fork's base branch from upstream via merge-upstream."""
    try:
        out = gh_request("/repos/%s/%s/merge-upstream" % (fork_owner, repo), tok,
                         data={"branch": base_ref})
        return out.get("merge_type", "unknown")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            sys.exit("fork %s/%s branch %s has diverged from upstream; sync it manually"
                     % (fork_owner, repo, base_ref))
        if e.code == 404:
            sys.exit("repo %s/%s is not a fork or has no branch %s — cannot merge-upstream"
                     % (fork_owner, repo, base_ref))
        if e.code == 422:
            sys.exit("merge-upstream failed for %s/%s branch %s: HTTP 422\n%s"
                     % (fork_owner, repo, base_ref, e.read().decode("utf-8", "replace")))
        raise


def curl_fallback(payload_path, endpoint):
    return ("curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" "
            "-H \"Accept: application/vnd.github+json\" -d @%s %s%s"
            % (payload_path, API, endpoint))


def cmd_status(args):
    tok = token()
    uo, ur = parse_repo(args.upstream)
    base_sha = get_branch_sha(uo, ur, args.base_ref, tok)
    branch_sha = get_branch_sha(args.fork_owner, ur, args.branch, tok)
    empty = []
    pkg_files = []
    if branch_sha:
        cmp = gh_request("/repos/%s/%s/compare/%s...%s"
                         % (args.fork_owner, ur, args.base_ref, args.branch), tok)
        pkg_files = [f["filename"] for f in cmp.get("files", [])]
        sizes = {}
        for p in answer_paths(pkg_files):
            entry = gh_request("/repos/%s/%s/contents/%s?ref=%s"
                               % (args.fork_owner, ur, urllib.parse.quote(p),
                                  args.branch), tok)
            sizes[p] = entry.get("size", 0)
        empty = answers_empty(sizes)
    prs = gh_request("/repos/%s/%s/pulls?head=%s:%s&state=all"
                     % (uo, ur, args.fork_owner, args.branch), tok)
    pr, pr_state = None, None
    if prs:
        open_prs = [p for p in prs if p.get("state") == "open"]
        chosen = open_prs[0] if open_prs else max(prs, key=lambda p: p.get("created_at", ""))
        pr = chosen["number"]
        if chosen.get("state") == "open":
            pr_state = "open"
        elif chosen.get("merged_at"):
            pr_state = "merged"
        else:
            pr_state = "closed"
    print(json.dumps({"branch_exists": bool(branch_sha), "base_sha": base_sha,
                      "branch_sha": branch_sha, "empty_answers": empty,
                      "package_files": pkg_files,
                      "pr": pr, "pr_state": pr_state}, indent=2))


def cmd_push(args):
    tok = token()
    uo, ur = parse_repo(args.upstream)
    files = collect_package(args.package_dir)
    if not files:
        sys.exit("package dir is empty: " + args.package_dir)
    base_sha = get_branch_sha(uo, ur, args.base_ref, tok)
    if not base_sha:
        sys.exit("cannot resolve upstream %s head" % args.base_ref)
    branch_sha = get_branch_sha(args.fork_owner, ur, args.branch, tok)
    if branch_sha and not args.update:
        sys.exit("branch %s already exists on %s/%s; pass --update to add a commit"
                 % (args.branch, args.fork_owner, ur))
    if not args.yes:
        if not branch_sha:
            print("[dry-run] would sync fork %s/%s from upstream %s first"
                  % (args.fork_owner, ur, args.base_ref))
        print("[dry-run] would %s branch %s on %s/%s (base %s @ %s)"
              % ("update" if branch_sha else "create", args.branch,
                 args.fork_owner, ur, args.base_ref, base_sha[:9]))
        for rp, ap in files:
            print("[dry-run]   + %s (%d bytes)" % (rp, os.path.getsize(ap)))
        print("[dry-run] commit message: %s" % args.message)
        return
    branch_created_now = False
    step = "sync fork"
    try:
        if not branch_sha:
            step = "sync fork"
            sync_fork_base(args.fork_owner, ur, args.base_ref, tok)
            fork_base_sha = get_branch_sha(args.fork_owner, ur, args.base_ref, tok)
            if not fork_base_sha:
                sys.exit("cannot resolve fork %s/%s branch %s after sync"
                         % (args.fork_owner, ur, args.base_ref))
            step = "create branch"
            gh_request("/repos/%s/%s/git/refs" % (args.fork_owner, ur), tok,
                       data={"ref": "refs/heads/" + args.branch, "sha": fork_base_sha})
            branch_created_now = True
            head = fork_base_sha
        else:
            head = branch_sha
        step = "resolve head commit"
        head_commit = gh_request("/repos/%s/%s/git/commits/%s"
                                 % (args.fork_owner, ur, head), tok)
        entries = []
        for rp, ap in files:
            step = "upload blob %s" % rp
            with open(ap, "rb") as fh:
                content = fh.read()
            blob = gh_request("/repos/%s/%s/git/blobs" % (args.fork_owner, ur), tok,
                              data={"content": base64.b64encode(content).decode("ascii"),
                                    "encoding": "base64"})
            entries.append({"path": rp, "mode": "100644", "type": "blob",
                            "sha": blob["sha"]})
        step = "create tree"
        tree = gh_request("/repos/%s/%s/git/trees" % (args.fork_owner, ur), tok,
                          data={"base_tree": head_commit["tree"]["sha"], "tree": entries})
        step = "create commit"
        commit = gh_request("/repos/%s/%s/git/commits" % (args.fork_owner, ur), tok,
                            data={"message": args.message, "tree": tree["sha"],
                                  "parents": [head]})
        step = "update ref"
        gh_request("/repos/%s/%s/git/refs/heads/%s" % (args.fork_owner, ur, args.branch),
                   tok, method="PATCH", data={"sha": commit["sha"]})
    except urllib.error.HTTPError as e:
        sys.stderr.write("push failed at step: %s\nHTTP %d\n%s\n"
                         % (step, e.code, e.read().decode("utf-8", "replace")))
        if branch_created_now:
            sys.stderr.write(
                "note: branch %s was created at base %s in this run before the "
                "failure; a stub branch now exists at base — retry with --update "
                "(or delete the branch) rather than re-running create.\n"
                % (args.branch, args.base_ref))
        sys.exit(1)
    print("pushed %d file(s) to %s/%s@%s (commit %s)"
          % (len(files), args.fork_owner, ur, args.branch, commit["sha"][:9]))


def cmd_pr(args):
    tok = token()
    uo, ur = parse_repo(args.upstream)
    with open(args.body_file, encoding="utf-8") as fh:
        body = fh.read().strip()
    if not body:
        sys.exit("PR body is empty; refusing")
    payload = build_pr_payload(args.title, body, args.fork_owner, args.branch,
                               args.base_ref)
    payload_path = args.body_file + ".payload.json"
    with open(payload_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    endpoint = "/repos/%s/%s/pulls" % (uo, ur)
    if not args.yes:
        print("[dry-run] would POST %s%s" % (API, endpoint))
        print("[dry-run] head=%s base=%s title=%s"
              % (payload["head"], payload["base"], args.title))
        print("[dry-run] payload saved to %s" % payload_path)
        print("[dry-run] manual send: " + curl_fallback(payload_path, endpoint))
        return
    try:
        out = gh_request(endpoint, tok, data=payload)
        print("PR created: %s" % out.get("html_url"))
    except urllib.error.HTTPError as e:
        sys.stderr.write("POST failed: HTTP %d\n%s\n"
                         % (e.code, e.read().decode("utf-8", "replace")))
        sys.stderr.write("payload preserved at %s\nmanual send: %s\n"
                         % (payload_path, curl_fallback(payload_path, endpoint)))
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write("POST failed: %s\npayload preserved at %s\nmanual send: %s\n"
                         % (e, payload_path, curl_fallback(payload_path, endpoint)))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    for name in ("status", "push", "pr"):
        p = sub.add_parser(name)
        p.add_argument("--upstream", required=True)
        p.add_argument("--fork-owner", required=True)
        p.add_argument("--branch", required=True)
        p.add_argument("--base-ref", default="develop")
        if name == "push":
            p.add_argument("--package-dir", required=True)
            p.add_argument("--message", required=True)
            p.add_argument("--update", action="store_true")
            p.add_argument("--yes", action="store_true")
        if name == "pr":
            p.add_argument("--title", required=True)
            p.add_argument("--body-file", required=True)
            p.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    if args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "push":
        cmd_push(args)
    elif args.cmd == "pr":
        cmd_pr(args)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
