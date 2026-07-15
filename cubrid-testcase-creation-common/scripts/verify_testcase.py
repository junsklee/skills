#!/usr/bin/env python3
"""Verify a CTP shell test case against the Builder-Tester service (Python 3.6, stdlib).

Submits a drafted shell script in custom-script mode, builds a pre-fix and a
post-fix engine commit, and judges VERIFIED iff the post-fix build passes all
attempts and the pre-fix build fails at least one (special cases exempted).
Can also derive a .answer file from a real post-fix run.

DRY-RUN BY DEFAULT — build submission requires --yes.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btlib import (BuilderTesterError, bt_get_text, bt_request, builder_url,
                   worker_ips)
from fetch_context import parse_pr_ref
from ghlib import gh_request, token

# Characters the builder's validateAttachmentTargetPath rejects in a path segment.
_BAD_TARGET_RE = re.compile(r"""[\s"'`$]""")


def b64_file(abs_path):
    with open(abs_path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def validate_target(rel):
    """Reject any relative targetPath the builder would 400 on
    (Builder.java validateAttachmentTargetPath): leading '/', NUL, whitespace,
    quotes/backtick/'$', or a '.'/'..' path segment."""
    if not rel or rel.startswith("/") or "\x00" in rel:
        raise ValueError("attachment path not allowed by builder: %r" % rel)
    for seg in rel.split("/"):
        if seg in ("", ".", "..") or _BAD_TARGET_RE.search(seg):
            raise ValueError(
                "attachment name not allowed by builder: %r "
                "(no spaces, quotes, backtick, '$', or dot segments — rename it)"
                % rel)


def collect_attachments(case_dir, entry_abs):
    """Every non-entry, non-dot file under the entry script's own directory as
    a customAttachment, targetPath relative to that directory. Validates each
    name against the builder's rules so submission fails fast on a bad name."""
    base = os.path.abspath(case_dir)
    entry_abs = os.path.abspath(entry_abs)
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            ap = os.path.abspath(os.path.join(root, f))
            if ap == entry_abs:
                continue
            rel = os.path.relpath(ap, base).replace(os.sep, "/")
            validate_target(rel)
            out.append({"targetPath": rel, "contentBase64": b64_file(ap)})
    return sorted(out, key=lambda d: d["targetPath"])


def build_request(script_text, commits, worker_ip_list, attachments=None,
                  run_mode="fixed-runs", min_runs=2, max_runs=2,
                  build_type="debug", callback_url=None,
                  commit_build_mode="checkout"):
    req = {
        "commits": list(commits),
        "customShellScript": script_text,
        "workerIps": list(worker_ip_list),
        "runMode": run_mode,
        "minRuns": min_runs,
        "maxRuns": max_runs,
        "buildType": build_type,
        "commitBuildMode": commit_build_mode,
        "callbackUrl": callback_url or (builder_url() + "/callback"),
    }
    if attachments:
        req["customAttachments"] = attachments
    return req


def parse_submit_response(resp):
    task_id = resp.get("taskId")
    if resp.get("status") == "error" or not task_id:
        raise BuilderTesterError("build not accepted: %s" % resp)
    return task_id


_KNOWN_STATUS = ("pass", "fail")


def locate_report(items, task_id):
    for it in items:
        if it.get("id") == task_id:
            return it
    return None


def results_by_commit(report):
    """commit sha -> {'attempts': [status,...], 'logs': [logFileName,...]}."""
    out = {}
    for r in report.get("results", []):
        commit = r.get("commit")
        if not commit:
            continue
        meta = r.get("attemptLogMetadata", [])
        attempts = [a.get("status") for a in meta if a.get("status")]
        logs = [a.get("logFileName") for a in meta if a.get("logFileName")]
        if not attempts and r.get("status"):
            attempts = [r.get("status")]
        entry = out.setdefault(commit, {"attempts": [], "logs": []})
        entry["attempts"].extend(attempts)
        entry["logs"].extend(logs)
    return out


def _lookup(by_commit, sha):
    """Exact match, else unique prefix match (allows short --pre/--post shas)."""
    if sha in by_commit:
        return by_commit[sha]
    hits = [v for k, v in by_commit.items() if k.startswith(sha) or sha.startswith(k)]
    return hits[0] if len(hits) == 1 else {}


def _all_pass(attempts):
    return bool(attempts) and all(a == "pass" for a in attempts)


def _has_infra(attempts):
    return any(a not in _KNOWN_STATUS for a in attempts)


def _mixed(attempts):
    return ("pass" in attempts) and any(a != "pass" for a in attempts)


def judge_matrix(by_commit, pre_sha, post_sha, special_case=None):
    post_e = _lookup(by_commit, post_sha) if post_sha else {}
    pre_e = _lookup(by_commit, pre_sha) if pre_sha else {}
    post, pre = post_e.get("attempts", []), pre_e.get("attempts", [])
    j = {"verdict": None, "reason": "", "pre_sha": pre_sha, "post_sha": post_sha,
         "pre_attempts": pre, "post_attempts": post,
         "pre_logs": pre_e.get("logs", []), "post_logs": post_e.get("logs", []),
         "special_case": special_case}

    if not post:
        j["verdict"] = "INCONCLUSIVE"
        j["reason"] = "no post-fix result for %s" % (post_sha or "?")[:7]
        return j
    if _has_infra(post):
        j["verdict"] = "INCONCLUSIVE"
        j["reason"] = "post-fix build/infra error (non pass/fail attempt status)"
        return j
    if _mixed(post):
        j["verdict"] = "FLAKY"
        j["reason"] = "post-fix build produced mixed pass/fail attempts"
        return j
    if not _all_pass(post):
        j["verdict"] = "NOT-VERIFIED"
        j["reason"] = "post-fix build did not pass all attempts"
        return j

    if pre_sha is None:
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix expectation waived: post-only run"
        return j
    if not pre or _has_infra(pre):
        if special_case:
            j["verdict"] = "VERIFIED"
            j["reason"] = "pre-fix expectation waived: %s" % special_case
        else:
            j["verdict"] = "INCONCLUSIVE"
            j["reason"] = "no clean pre-fix result for %s" % pre_sha[:7]
        return j
    if not _all_pass(pre):
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix reproduced the bug (>=1 attempt failed); post-fix all pass"
        return j
    if special_case:
        j["verdict"] = "VERIFIED"
        j["reason"] = "pre-fix expectation waived: %s (pre-fix did not fail)" % special_case
    else:
        j["verdict"] = "NOT-VERIFIED"
        j["reason"] = "pre-fix build passed; test does not reproduce the bug"
    return j


def inconclusive(reason, pre_sha, post_sha):
    return {"verdict": "INCONCLUSIVE", "reason": reason,
            "pre_sha": pre_sha, "post_sha": post_sha,
            "pre_attempts": [], "post_attempts": [],
            "pre_logs": [], "post_logs": [], "special_case": None}


def format_verdict_block(judged, task_id):
    base = builder_url()

    def line(label, sha, attempts, expect):
        if sha is None:
            return "  %-9s (skipped): expected %s" % (label, expect)
        got = ", ".join("attempt %d %s" % (i + 1, s)
                        for i, s in enumerate(attempts)) or "no result"
        return "  %-9s %s: %s   (expected %s)" % (label, sha[:7], got, expect)

    out = ["VERDICT: %s" % judged["verdict"],
           "  %s" % judged["reason"],
           line("pre-fix", judged["pre_sha"], judged["pre_attempts"],
                "fail" if not judged["special_case"] else "fail (waived)"),
           line("post-fix", judged["post_sha"], judged["post_attempts"], "pass")]
    for label, logs in (("pre-fix", judged["pre_logs"]), ("post-fix", judged["post_logs"])):
        for fn in logs:
            out.append("  log %s: %s/api/log/%s/tests/%s" % (label, base, task_id, fn))
    pre_reproduced = "fail" in judged["pre_attempts"]
    if judged["verdict"] == "VERIFIED" and judged["pre_sha"] and pre_reproduced:
        out.append("  Verified: pre-fix %s -> NOK / post-fix %s -> OK"
                   % (judged["pre_sha"][:7], judged["post_sha"][:7]))
    elif judged["verdict"] == "VERIFIED" and judged["post_sha"]:
        waiver = judged["special_case"] or "post-only"
        out.append("  Verified: post-fix %s -> OK (pre-fix waived: %s)"
                   % (judged["post_sha"][:7], waiver))
    return "\n".join(out)


def status_phase(status_resp):
    if status_resp.get("progress") == -1:
        return "error"
    s = status_resp.get("status")
    if s == "not_found":
        return "not_found"
    if s == "error":
        return "error"
    return "running"


# Matches a `compare_result_between_files <produced> <answer> [norm...]` command
# anywhere on a line (bare or inside an `if`/`while`/`!` guard), capturing the
# first two args and swallowing any trailing normalization args up to a shell
# separator, so only the command span is replaced.
_COMPARE_RE = re.compile(
    r"compare_result_between_files[ \t]+(?P<a1>[^\s;&|]+)[ \t]+"
    r"(?P<a2>[^\s;&|]+)(?P<rest>[^\n;&|]*)")
_B64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def has_compare_calls(script_text):
    return "compare_result_between_files" in script_text


def capture_transform(script_text):
    """Replace each `compare_result_between_files <produced> <answer> [norm]`
    command with a `{ echo SENTINEL; base64 <produced>; echo SENTINEL; }`
    compound that dumps the first (produced-log) argument. The brace group
    keeps surrounding control flow valid (e.g. `if ! <call>; then` becomes
    `if ! { ... }; then`) and always exits 0. Returns (new_text,
    mappings=[(n, produced_arg, answer_arg), ...])."""
    mappings = []
    counter = [0]

    def repl(m):
        counter[0] += 1
        n = counter[0]
        mappings.append((n, m.group("a1"), m.group("a2")))
        return ('{ echo "ANSWER_BEGIN_%d"; base64 %s; echo "ANSWER_END_%d"; }'
                % (n, m.group("a1"), n))

    return _COMPARE_RE.sub(repl, script_text), mappings


def extract_answers(log_text, mappings):
    """Decode the base64 payload between the exact-line sentinels for each n.
    Robust to interleaved `sh -x` trace lines (they never equal the bare
    sentinel and are not pure base64)."""
    lines = log_text.splitlines()
    out = {}
    for n, _produced, _answer in mappings:
        begin, end = "ANSWER_BEGIN_%d" % n, "ANSWER_END_%d" % n
        try:
            bi = lines.index(begin)
            ei = lines.index(end, bi + 1)
        except ValueError:
            continue
        payload = "".join(x.strip() for x in lines[bi + 1:ei]
                          if _B64_LINE_RE.match(x.strip()))
        if not payload:
            continue
        try:
            out[n] = base64.b64decode(payload)
        except Exception:
            continue
    return out


def suggest_answer_name(answer_arg, entry_stem, n):
    """Target filename for a derived answer: the literal basename if the source
    used one, else <entry_stem>[_n].answer when it was a shell variable."""
    if "$" not in answer_arg and answer_arg not in (".", ".."):
        return os.path.basename(answer_arg)
    return "%s.answer" % entry_stem if n == 1 else "%s_%d.answer" % (entry_stem, n)


def merged_pair(merge_sha, first_parent_sha):
    return (first_parent_sha, merge_sha)


def open_pair(merge_base_sha, head_sha):
    return (merge_base_sha, head_sha)


def resolve_commit_pair(ref, tok, gh=None):
    """Resolve an engine PR reference to (pre_fix_sha, post_fix_sha).
    Merged PR: (merge commit's first parent, merge commit) — robust to squash
    and true merges. Open PR: (merge-base against base branch, head)."""
    gh = gh or gh_request
    owner, repo, num = parse_pr_ref(ref)
    pr = gh("/repos/%s/%s/pulls/%d" % (owner, repo, num), tok)
    if pr.get("merged_at"):
        merge_sha = pr.get("merge_commit_sha")
        if not merge_sha:
            raise BuilderTesterError("merged PR #%d has no merge_commit_sha" % num)
        commit = gh("/repos/%s/%s/commits/%s" % (owner, repo, merge_sha), tok)
        parents = commit.get("parents", [])
        if not parents:
            raise BuilderTesterError("merge commit %s has no parents" % merge_sha[:7])
        return merged_pair(merge_sha, parents[0]["sha"])
    base = pr["base"]["ref"]
    head_sha = pr["head"]["sha"]
    cmp = gh("/repos/%s/%s/compare/%s...%s" % (owner, repo, base, head_sha), tok)
    mb = cmp.get("merge_base_commit", {}).get("sha")
    if not mb:
        raise BuilderTesterError("cannot resolve merge base for PR #%d" % num)
    return open_pair(mb, head_sha)


def resolve_issue_to_ref(issue_key, tok, gh=None):
    """Find the single CUBRID/cubrid PR whose title contains the CBRD key.
    Returns 'CUBRID/cubrid#N'; raises listing candidates on 0 or >1 matches."""
    gh = gh or gh_request
    q = "%s repo:CUBRID/cubrid in:title type:pr" % issue_key
    res = gh("/search/issues?q=" + urllib.parse.quote(q), tok)
    items = res.get("items", [])
    if not items:
        raise BuilderTesterError(
            "no CUBRID/cubrid PR found with %s in the title; pass --engine-pr" % issue_key)
    if len(items) > 1:
        listing = "; ".join("#%d %s" % (it["number"], it.get("title", "")) for it in items)
        raise BuilderTesterError(
            "%d PRs match %s — pass --engine-pr to pick one: %s"
            % (len(items), issue_key, listing))
    return "CUBRID/cubrid#%d" % items[0]["number"]


def commit_subject(owner, repo, sha, tok, gh=None):
    gh = gh or gh_request
    try:
        c = gh("/repos/%s/%s/commits/%s" % (owner, repo, sha), tok)
        return (c.get("commit", {}).get("message", "") or "").splitlines()[0]
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_subparsers(dest="cmd")
    ap.parse_args()
    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
