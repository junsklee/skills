#!/usr/bin/env python3
"""Preview or create CUBRID cubrid-testtools-internal GitHub PRs."""

from __future__ import print_function

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_REPO = os.path.expanduser("~/cubrid-testtools-internal")
DEFAULT_BASE = "develop"
DEFAULT_ORIGIN_OWNER = "junsklee"
DEFAULT_UPSTREAM_OWNER = "CUBRID"
REPO_NAME = "cubrid-testtools-internal"
GITHUB_API = "https://api.github.com"
JIRA_BROWSE_BASE = "http://jira.cubrid.org/browse"
PROTECTED_BRANCHES = ("develop", "master", "main")
KOREAN_RE = re.compile(r"[\uac00-\ud7a3]")


def run_git(repo, args, check=True, strip=True):
    cmd = ["git", "-C", repo] + args
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
    )
    stdout, stderr = proc.communicate()
    if check and proc.returncode != 0:
        message = stderr.strip() or stdout.strip()
        raise SystemExit("git command failed: {0}\n{1}".format(" ".join(cmd), message))
    if strip:
        stdout = stdout.strip()
        stderr = stderr.strip()
    return proc.returncode, stdout, stderr


def sanitize_remote_url(url):
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        return scheme + "://" + rest
    return re.sub(r"//[^/@:]+:[^/@]+@", "//", url)


def remote_url(repo, name, push=False):
    args = ["remote", "get-url"]
    if push:
        args.append("--push")
    args.append(name)
    _, stdout, _ = run_git(repo, args)
    return stdout


def normalized_github_path(url):
    clean = sanitize_remote_url(url)
    if clean.startswith("git@github.com:"):
        path = clean[len("git@github.com:") :]
    else:
        parsed = urllib.parse.urlparse(clean)
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path


def assert_remote(repo, remote, owner):
    fetch_url = remote_url(repo, remote, push=False)
    push_url = remote_url(repo, remote, push=True)
    expected = "{0}/{1}".format(owner, REPO_NAME)
    for label, url in (("fetch", fetch_url), ("push", push_url)):
        actual = normalized_github_path(url)
        if actual != expected:
            raise SystemExit(
                "{0} {1} remote points to {2}, expected {3}".format(
                    remote, label, actual, expected
                )
            )
    return {"fetch": sanitize_remote_url(fetch_url), "push": sanitize_remote_url(push_url)}


def current_branch(repo):
    _, branch, _ = run_git(repo, ["symbolic-ref", "--short", "HEAD"])
    if not branch:
        raise SystemExit("Current checkout is detached; switch to a feature branch first.")
    return branch


def status_summary(repo):
    _, stdout, _ = run_git(repo, ["status", "--porcelain"], check=True, strip=False)
    lines = [line for line in stdout.splitlines() if line.strip()]
    return {"dirty": bool(lines), "count": len(lines), "entries": lines[:20]}


def infer_jira_key(repo, branch):
    pattern = re.compile(r"\b((?:CUBRIDQA|CBRD|APIS)-\d+)\b")
    match = pattern.search(branch)
    if match:
        return match.group(1)
    _, stdout, _ = run_git(repo, ["log", "-20", "--format=%s"], check=False)
    match = pattern.search(stdout)
    if match:
        return match.group(1)
    return ""


def format_title(jira_key, title):
    title = title.strip()
    title = re.sub(r"^\[(?:CUBRIDQA|CBRD|APIS)-\d+\]\s*", "", title)
    return "[{0}] {1}".format(jira_key, title)


def read_body_file(path):
    if not path:
        return ""
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def comparison_ref(repo, base):
    for ref in ("upstream/" + base, "origin/" + base, base):
        code, _, _ = run_git(repo, ["rev-parse", "--verify", ref], check=False)
        if code == 0:
            return ref
    return ""


def default_body(repo, base):
    ref = comparison_ref(repo, base)
    if not ref:
        return ""
    _, stdout, _ = run_git(repo, ["log", "--format=- %s", ref + "..HEAD"], check=False)
    if not stdout.strip():
        return ""
    return (
        "커밋 기준 변경 사항을 PR 설명으로 정리 필요.\n\n"
        "Changes\n\n"
        + stdout.strip()
    )


def build_body(repo, base, jira_key, body_file):
    jira_url = "{0}/{1}".format(JIRA_BROWSE_BASE, jira_key)
    body = read_body_file(body_file).strip() if body_file else default_body(repo, base).strip()
    if body.startswith(jira_url):
        return body
    if body:
        return jira_url + "\n\n" + body
    return jira_url


def has_korean_prose(body):
    without_urls = re.sub(r"https?://\S+", "", body)
    without_headers = re.sub(r"(?m)^#{0,6}\s*Changes\s*$", "", without_urls)
    return bool(KOREAN_RE.search(without_headers))


def github_request(method, path, token, payload=None):
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "codex-cubrid-testtools-pr-skill",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        GITHUB_API + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.getcode(), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise SystemExit("GitHub API failed with HTTP {0}: {1}".format(exc.code, raw))
    except urllib.error.URLError as exc:
        raise SystemExit("GitHub API request failed: {0}".format(exc.reason))


def existing_pr(token, head, base):
    query = urllib.parse.urlencode({"state": "open", "head": head, "base": base})
    _, data = github_request(
        "GET",
        "/repos/{0}/{1}/pulls?{2}".format(DEFAULT_UPSTREAM_OWNER, REPO_NAME, query),
        token,
    )
    if data:
        return data[0]
    return None


def create_pr(token, title, body, head, base):
    payload = {"title": title, "body": body, "head": head, "base": base}
    _, data = github_request(
        "POST",
        "/repos/{0}/{1}/pulls".format(DEFAULT_UPSTREAM_OWNER, REPO_NAME),
        token,
        payload,
    )
    return data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Preview or create a GitHub PR for cubrid-testtools-internal."
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--jira-key", help="JIRA key such as CUBRIDQA-1370.")
    parser.add_argument("--title", required=True, help="Actual PR title without JIRA key.")
    parser.add_argument("--body-file", help="Optional PR body file, or '-' for stdin.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--submit", action="store_true", help="Push and create the PR.")
    parser.add_argument(
        "--confirmed", action="store_true", help="Required with --submit after preview."
    )
    parser.add_argument(
        "--allow-base-branch",
        action="store_true",
        help="Allow running from protected/default branches.",
    )
    parser.add_argument(
        "--allow-non-korean-body",
        action="store_true",
        help="Allow submit even when the PR body has no Korean prose.",
    )
    parser.add_argument("--no-infer-jira", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main():
    args = parse_args()
    repo = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo, ".git")):
        raise SystemExit("Not a git repository: {0}".format(repo))

    branch = current_branch(repo)
    if not args.allow_base_branch and (
        branch == args.base or branch in PROTECTED_BRANCHES or branch.startswith("release/")
    ):
        raise SystemExit(
            "Refusing to create a PR from protected/default branch '{0}'.".format(branch)
        )

    remotes = {
        "origin": assert_remote(repo, "origin", DEFAULT_ORIGIN_OWNER),
        "upstream": assert_remote(repo, "upstream", DEFAULT_UPSTREAM_OWNER),
    }
    status = status_summary(repo)
    jira_key = args.jira_key or ("" if args.no_infer_jira else infer_jira_key(repo, branch))
    if not jira_key:
        raise SystemExit("JIRA key is required. Pass --jira-key CUBRIDQA-####.")

    title = format_title(jira_key, args.title)
    body = build_body(repo, args.base, jira_key, args.body_file)
    korean_body = has_korean_prose(body)
    head = "{0}:{1}".format(DEFAULT_ORIGIN_OWNER, branch)
    push_ref = "HEAD:{0}".format(branch)
    preview = {
        "repo": repo,
        "branch": branch,
        "base": args.base,
        "head": head,
        "push": {"remote": "origin", "refspec": push_ref},
        "remotes": remotes,
        "status": status,
        "pr": {
            "repo": "{0}/{1}".format(DEFAULT_UPSTREAM_OWNER, REPO_NAME),
            "title": title,
            "body": body,
            "korean_body": korean_body,
        },
    }

    if not args.submit:
        print(json.dumps({"dry_run": True, "preview": preview}, ensure_ascii=False, indent=2))
        return 0

    if not args.confirmed:
        print("Refusing to submit without --confirmed.", file=sys.stderr)
        return 2

    if not korean_body and not args.allow_non_korean_body:
        print(
            "Refusing to submit because the PR body has no Korean prose. "
            "Write the description in Korean or pass --allow-non-korean-body.",
            file=sys.stderr,
        )
        return 2

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Set GITHUB_TOKEN before submitting.", file=sys.stderr)
        return 2

    run_git(repo, ["push", "origin", push_ref])

    pr = existing_pr(token, head, args.base)
    if pr:
        print(
            json.dumps(
                {
                    "existing": True,
                    "number": pr.get("number"),
                    "url": pr.get("html_url"),
                    "title": pr.get("title"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    created = create_pr(token, title, body, head, args.base)
    print(
        json.dumps(
            {
                "created": True,
                "number": created.get("number"),
                "url": created.get("html_url"),
                "title": created.get("title"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
