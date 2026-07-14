#!/usr/bin/env python3
"""Read-only context fetcher for test-case creation (Python 3.6, stdlib).

Subcommands:
  engine-pr <pr-ref> --out FILE                    # PR title/description/files -> markdown
  tree <owner/repo> --grep TOKEN [--prefix P] [--ref develop]   # matching blob paths
  get <owner/repo> PATH... --out DIR [--ref develop]            # download files (contained)
"""
import argparse
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ghlib import gh_paginate, gh_request, parse_repo, token

_PR_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
_SHORT_RE = re.compile(r"^([^/\s#]+)/([^/\s#]+)#(\d+)$")


def parse_pr_ref(ref):
    m = _PR_RE.search(ref) or _SHORT_RE.match(ref.strip())
    if not m:
        raise ValueError("unrecognized PR reference: " + ref)
    return m.group(1), m.group(2), int(m.group(3))


def filter_tree(paths, contains, prefix=None):
    """Case-insensitive substring match over repo paths, optional prefix scope."""
    needle = contains.lower()
    out = []
    for p in paths:
        if prefix and not p.startswith(prefix):
            continue
        if needle in p.lower():
            out.append(p)
    return out


def safe_dest(base_dir, name):
    """Resolve a repo-relative path under base_dir, never outside it."""
    clean = name.lstrip("/\\")
    dest = os.path.normpath(os.path.join(base_dir, clean))
    if not dest.startswith(base_dir + os.sep):
        dest = os.path.join(base_dir, clean.replace("..", "__"))
    return dest


def subtree_sha(owner, repo, root_sha, prefix, tok):
    """Descend from the root tree along prefix segments; return the subtree sha."""
    sha = root_sha
    for seg in [s for s in prefix.strip("/").split("/") if s]:
        tree = gh_request("/repos/%s/%s/git/trees/%s" % (owner, repo, sha), tok)
        match = [e for e in tree.get("tree", []) if e["path"] == seg and e["type"] == "tree"]
        if not match:
            sys.exit("prefix path not found in tree: %s (at segment %s)" % (prefix, seg))
        sha = match[0]["sha"]
    return sha


def cmd_engine_pr(args):
    tok = token()
    owner, repo, num = parse_pr_ref(args.ref)
    base = "/repos/%s/%s" % (owner, repo)
    pr = gh_request("%s/pulls/%d" % (base, num), tok)
    files = gh_paginate("%s/pulls/%d/files" % (base, num), tok)
    lines = ["# Engine PR %s/%s#%d" % (owner, repo, num), "",
             "Title: %s" % pr.get("title"),
             "State: %s merged: %s" % (pr.get("state"), pr.get("merged_at")), "",
             "## Description", pr.get("body") or "(none)", "", "## Changed files"]
    lines += ["- %s (+%d/-%d)" % (f["filename"], f["additions"], f["deletions"])
              for f in files]
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("engine-pr written: %s (%d files)" % (args.out, len(files)))


def cmd_tree(args):
    tok = token()
    owner, repo = parse_repo(args.repo)
    ref = gh_request("/repos/%s/%s/git/ref/heads/%s" % (owner, repo, args.ref), tok)
    commit = gh_request("/repos/%s/%s/git/commits/%s"
                        % (owner, repo, ref["object"]["sha"]), tok)
    root_sha = commit["tree"]["sha"]
    if args.prefix:
        pre = args.prefix.rstrip("/") + "/"
        list_sha = subtree_sha(owner, repo, root_sha, args.prefix, tok)
    else:
        pre = ""
        list_sha = root_sha
    tree = gh_request("/repos/%s/%s/git/trees/%s?recursive=1"
                      % (owner, repo, list_sha), tok)
    if tree.get("truncated"):
        sys.stderr.write("warning: tree listing truncated by GitHub; results may be partial\n")
    paths = [pre + e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
    for p in filter_tree(paths, args.grep, None):
        print(p)


def cmd_get(args):
    tok = token()
    owner, repo = parse_repo(args.repo)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    failed = 0
    for path in args.paths:
        try:
            blob = gh_request("/repos/%s/%s/contents/%s?ref=%s"
                              % (owner, repo, urllib.parse.quote(path), args.ref),
                              tok, accept="application/vnd.github.raw", raw=True)
        except Exception as e:
            sys.stderr.write("fetch failed for %s: %s\n" % (path, e))
            failed += 1
            continue
        dest = safe_dest(out_dir, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(blob)
        print("fetched %s (%d bytes)" % (path, len(blob)))
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("engine-pr")
    p1.add_argument("ref")
    p1.add_argument("--out", required=True)
    p2 = sub.add_parser("tree")
    p2.add_argument("repo")
    p2.add_argument("--grep", required=True)
    p2.add_argument("--prefix", default=None)
    p2.add_argument("--ref", default="develop")
    p3 = sub.add_parser("get")
    p3.add_argument("repo")
    p3.add_argument("paths", nargs="+")
    p3.add_argument("--out", required=True)
    p3.add_argument("--ref", default="develop")
    args = ap.parse_args()
    if args.cmd == "engine-pr":
        cmd_engine_pr(args)
    elif args.cmd == "tree":
        cmd_tree(args)
    elif args.cmd == "get":
        cmd_get(args)
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
