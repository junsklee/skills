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


def build_sql_request(script_text, answer_text, commits, worker_ip_list,
                      run_mode="fixed-runs", min_runs=1, max_runs=1,
                      build_type="debug", callback_url=None,
                      commit_build_mode="checkout"):
    if not answer_text:
        raise ValueError(
            "customSqlAnswer must be non-empty (the builder 400s without it); "
            "derive it first with 'derive-answer --test-type sql'")
    return {
        "commits": list(commits),
        "testType": "sql",
        "customSqlScript": script_text,
        "customSqlAnswer": answer_text,
        "workerIps": list(worker_ip_list),
        "runMode": run_mode, "minRuns": min_runs, "maxRuns": max_runs,
        "buildType": build_type, "commitBuildMode": commit_build_mode,
        "callbackUrl": callback_url or (builder_url() + "/callback"),
    }


def resolve_answer_path(script_path):
    """Sibling answers/<name>.answer for a cases/<name>.sql; else alongside."""
    d = os.path.dirname(os.path.abspath(script_path))
    stem = os.path.splitext(os.path.basename(script_path))[0]
    if os.path.basename(d) == "cases":
        return os.path.join(os.path.dirname(d), "answers", stem + ".answer")
    return os.path.join(d, stem + ".answer")


def has_queryplan_sidecar(script_path):
    """True if a sibling <name>.queryPlan exists next to the .sql (plan test)."""
    stem = os.path.splitext(os.path.abspath(script_path))[0]
    return os.path.exists(stem + ".queryPlan")


def find_artifacts(report, commit_sha, artifact_type):
    """logFileNames of artifact entries of the given type for the commit."""
    if not commit_sha:
        return []
    out = []
    for r in report.get("results", []):
        c = r.get("commit") or ""
        if not (c.startswith(commit_sha[:7]) or commit_sha.startswith(c[:7] or "x")):
            continue
        for a in r.get("attemptLogMetadata", []):
            if a.get("artifactType") == artifact_type and a.get("logFileName"):
                out.append(a["logFileName"])
    return out


def report_test_type(report):
    tt = report.get("testType")
    if tt:
        return tt
    for r in report.get("results", []):
        if r.get("testType"):
            return r["testType"]
    return "shell"


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
        logs = [a.get("logFileName") for a in meta
                if a.get("logFileName") and not a.get("artifactType")]
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


def plan_commits(pre, post, engine_pair, post_only):
    """Decide the commits list + (pre, post). engine_pair is a resolved
    (pre, post) tuple or None; explicit pre/post override it."""
    if engine_pair:
        pre = pre or engine_pair[0]
        post = post or engine_pair[1]
    if post_only:
        if not post:
            raise ValueError("--post-only requires a post-fix commit (--post or --engine-pr/--issue)")
        return ([post], None, post)
    if not pre or not post:
        raise ValueError("need a pre/post pair: pass --engine-pr/--issue REF or --pre SHA --post SHA")
    return ([pre, post], pre, post)


def elide_payload(req):
    """A print-safe copy: large content fields shown as size + sha256."""
    def mark(s):
        b = s.encode("utf-8")
        return "<%d bytes sha256:%s>" % (len(b), hashlib.sha256(b).hexdigest()[:12])
    safe = dict(req)
    for k in ("customShellScript", "customSqlScript", "customSqlAnswer"):
        if k in req:
            safe[k] = mark(req[k])
    if "customAttachments" in req:
        safe["customAttachments"] = [
            {"targetPath": a["targetPath"], "contentBase64": mark(a["contentBase64"])}
            for a in req["customAttachments"]]
    return safe


def _engine_pair_and_owner(args):
    """Resolve --engine-pr/--issue to ((pre,post) or None, owner, repo). Explicit
    --pre/--post leave the pair None and default owner/repo to CUBRID/cubrid."""
    ref = args.engine_pr
    if getattr(args, "issue", None) and not ref:
        ref = resolve_issue_to_ref(args.issue, token())
        print("resolved %s -> %s" % (args.issue, ref))
    if ref:
        owner, repo, _num = parse_pr_ref(ref)
        return (resolve_commit_pair(ref, token()), owner, repo)
    return (None, "CUBRID", "cubrid")


def _echo_pair(owner, repo, pre, post):
    # Best-effort subjects: soft-read the token (never sys.exit here) so the
    # --pre/--post path needs no GITHUB_TOKEN; commit_subject swallows errors.
    tok = os.environ.get("GITHUB_TOKEN")
    for label, sha in (("pre-fix", pre), ("post-fix", post)):
        if sha:
            subj = commit_subject(owner, repo, sha, tok) if tok else ""
            print("  %-8s %s  %s" % (label, sha[:9], subj))


def _resolve_and_echo(args):
    pair, owner, repo = _engine_pair_and_owner(args)
    try:
        commits, pre, post = plan_commits(
            getattr(args, "pre", None), getattr(args, "post", None),
            pair, getattr(args, "post_only", False))
    except ValueError as e:
        sys.exit(str(e))
    print("Commit pair to build:")
    _echo_pair(owner, repo, pre, post)
    return commits, pre, post


def _load_script(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _post_build(req):
    print("Submitting to %s (consumes shared builder/tester capacity)..." % builder_url())
    return parse_submit_response(bt_request("/api/builder/build", method="POST", data=req))


def _submit(script_text, entry_abs, commits, args, yes):
    case_dir = os.path.dirname(os.path.abspath(entry_abs))
    atts = collect_attachments(case_dir, entry_abs)
    req = build_request(script_text, commits, worker_ips(), attachments=atts,
                        run_mode=args.run_mode, min_runs=args.min_runs,
                        max_runs=args.max_runs, build_type=args.build_type)
    if not yes:
        print("[dry-run] POST %s/api/builder/build" % builder_url())
        print(json.dumps(elide_payload(req), indent=2))
        print("[dry-run] pass --yes to submit")
        return None
    task_id = _post_build(req)
    print("taskId: %s" % task_id)
    return task_id


def _fetch_report(task_id):
    data = bt_request("/api/reports?q=%s&pageSize=50" % task_id)
    rep = locate_report(data.get("items", []), task_id)
    if rep is not None:
        return rep
    data = bt_request("/api/reports?pageSize=100")
    return locate_report(data.get("items", []), task_id)


def _pending(task_id):
    """True if task_id is currently queued or actively building. If the
    all-tasks status endpoint cannot be reached, assume the task is STILL
    pending (conservative): a transient blip must never be read as 'finished
    without a report'. A persistently-down endpoint then times out honestly
    in _wait rather than raising a false completion."""
    try:
        st = bt_request("/api/builder/status")
    except BuilderTesterError:
        return True
    if task_id in st.get("queuedTaskIds", []):
        return True
    return any(t.get("taskId") == task_id for t in st.get("activeTasks", []))


def _wait(task_id, timeout):
    """Block until the report for task_id lands. Returns the report dict, or
    raises BuilderTesterError on timeout / finished-without-report."""
    print("Waiting for %s (timeout %ds)..." % (task_id, timeout))
    deadline = time.time() + timeout
    delay = 10
    while time.time() < deadline:
        try:
            st = bt_request("/api/builder/status?taskId=%s" % task_id)
            phase = status_phase(st)
        except BuilderTesterError:
            # A blip on the per-task status endpoint must not abort the wait:
            # fall through to the report/pending check, whose source of truth is
            # /api/reports (which may well be up).
            st, phase = {}, "not_found"
        if phase == "error":
            raise BuilderTesterError("builder reported error for %s" % task_id)
        if phase == "running":
            print("  ... running %s" % (st.get("progressSummary") or st.get("progress") or ""))
        else:  # not_found: queued, finished, or absent
            rep = _fetch_report(task_id)
            if rep is not None:
                return rep
            if not _pending(task_id):
                raise BuilderTesterError(
                    "%s is neither building, queued, nor reported — it finished "
                    "without a report or never started; inspect the dashboard" % task_id)
            print("  ... queued (waiting for the build slot)")
        time.sleep(delay)
        delay = min(delay + 5, 30)
    raise BuilderTesterError(
        "timed out after %ds waiting for %s (still queued/running)" % (timeout, task_id))


_EXIT = {"VERIFIED": 0, "NOT-VERIFIED": 2, "FLAKY": 3, "INCONCLUSIVE": 4}


def _print_and_exit(judged, task_id):
    print(format_verdict_block(judged, task_id))
    sys.exit(_EXIT.get(judged["verdict"], 1))


def cmd_submit(args):
    commits, _pre, _post = _resolve_and_echo(args)
    _submit(_load_script(args.script), args.script, commits, args, args.yes)


def cmd_wait(args):
    _wait(args.task_id, args.timeout)
    print("report available for %s" % args.task_id)


def cmd_judge(args):
    _commits, pre, post = _resolve_and_echo(args)
    report = _fetch_report(args.task_id)
    if report is None:
        _print_and_exit(inconclusive("no report found for %s" % args.task_id, pre, post),
                        args.task_id)
    _print_and_exit(judge_matrix(results_by_commit(report), pre, post, args.special_case),
                    args.task_id)


def cmd_run(args):
    commits, pre, post = _resolve_and_echo(args)
    task_id = _submit(_load_script(args.script), args.script, commits, args, args.yes)
    if task_id is None:
        return  # dry-run
    try:
        report = _wait(task_id, args.timeout)
    except BuilderTesterError as e:
        _print_and_exit(inconclusive(str(e), pre, post), task_id)
    _print_and_exit(judge_matrix(results_by_commit(report), pre, post, args.special_case),
                    task_id)


def _derive_meta(report, post_sha):
    """Pick the post-fix results entry's first attempt log, guarding structure."""
    results = report.get("results") or []
    entry = next((r for r in results if (r.get("commit") or "").startswith(post_sha[:7])
                  or post_sha.startswith((r.get("commit") or "x")[:7])), None)
    entry = entry or (results[0] if results else None)
    if not entry:
        return None
    for a in entry.get("attemptLogMetadata", []):
        if a.get("logFileName"):
            return a["logFileName"]
    return None


def cmd_derive_answer(args):
    entry_abs = os.path.abspath(args.script)
    script_text = _load_script(args.script)
    if not has_compare_calls(script_text):
        sys.exit("no compare_result_between_files call found; nothing to derive")
    capture, mappings = capture_transform(script_text)
    if not mappings:
        sys.exit("compare_result_between_files present but no line matched the expected "
                 "'compare_result_between_files <log> <answer>' form; check the script")
    pair, owner, repo = _engine_pair_and_owner(args)
    post = args.post or (pair[1] if pair else None)
    if not post:
        sys.exit("need a post-fix commit: pass --post SHA or --engine-pr/--issue REF")
    print("Deriving answers from post-fix build:")
    _echo_pair(owner, repo, None, post)
    if not args.yes:
        print("[dry-run] would submit the capture variant (post-only) to derive %d answer(s)"
              % len(mappings))
        print(capture)
        print("[dry-run] pass --yes to submit")
        return
    case_dir = os.path.dirname(entry_abs)
    atts = collect_attachments(case_dir, entry_abs)
    req = build_request(capture, [post], worker_ips(), attachments=atts,
                        run_mode="fixed-runs", min_runs=1, max_runs=1,
                        build_type=args.build_type)
    task_id = _post_build(req)
    print("taskId: %s" % task_id)
    report = _wait(task_id, args.timeout)
    log_name = _derive_meta(report, post)
    if not log_name:
        sys.exit("post-fix run produced no attempt log for %s; cannot derive "
                 "(the build may have failed) — inspect report %s" % (post[:7], task_id))
    log = bt_get_text("/api/log/%s/tests/%s" % (task_id, log_name))
    answers = extract_answers(log, mappings)
    if not answers:
        sys.exit("no answer payload found in the post-fix run log; inspect %s" % task_id)
    entry_stem = os.path.splitext(os.path.basename(entry_abs))[0]
    for n, produced, answer_arg in mappings:
        if n not in answers:
            print("WARNING: no captured content for compare #%d (%s)" % (n, produced))
            continue
        dest = os.path.join(case_dir, suggest_answer_name(answer_arg, entry_stem, n))
        with open(dest, "wb") as fh:
            fh.write(answers[n])
        print("\n=== derived answer #%d -> %s (%d bytes) ===" % (n, dest, len(answers[n])))
        sys.stdout.buffer.write(answers[n])
        print("\n=== end answer #%d ===" % n)
    print("\nREVIEW REQUIRED: confirm each derived .answer matches the JIRA to-be "
          "behavior before using it. It was machine-derived from a real run.")


def cmd_health(args):
    ok = False
    for ep in ("/health", "/api/builder/health", "/api/reports?pageSize=1"):
        try:
            print("%s -> %s" % (ep, json.dumps(bt_request(ep))[:200]))
            ok = True
        except BuilderTesterError as e:
            print("%s -> UNREACHABLE: %s" % (ep, e))
    if not ok:
        sys.exit(1)


def _add_commit_args(p):
    p.add_argument("--engine-pr", help="engine PR ref (URL or OWNER/REPO#N)")
    p.add_argument("--issue", help="CBRD-XXXXX; resolves to its CUBRID/cubrid PR")
    p.add_argument("--pre", help="explicit pre-fix commit sha")
    p.add_argument("--post", help="explicit post-fix commit sha")
    p.add_argument("--post-only", action="store_true",
                   help="submit only the post-fix commit")


def _add_run_args(p):
    p.add_argument("--run-mode", default="fixed-runs")
    p.add_argument("--min-runs", type=int, default=2)
    p.add_argument("--max-runs", type=int, default=2)
    p.add_argument("--build-type", default="debug")
    p.add_argument("--special-case", default=None,
                   choices=["core-dump", "flaky-repro", "feature"],
                   help="waive the pre-fix-must-fail expectation")
    p.add_argument("--timeout", type=int, default=10800)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    ps = sub.add_parser("submit")
    ps.add_argument("--script", required=True)
    _add_commit_args(ps)
    _add_run_args(ps)
    ps.add_argument("--yes", action="store_true")

    pw = sub.add_parser("wait")
    pw.add_argument("--task-id", required=True)
    pw.add_argument("--timeout", type=int, default=10800)

    pj = sub.add_parser("judge")
    pj.add_argument("--task-id", required=True)
    _add_commit_args(pj)
    pj.add_argument("--special-case", default=None,
                    choices=["core-dump", "flaky-repro", "feature"])

    prn = sub.add_parser("run")
    prn.add_argument("--script", required=True)
    _add_commit_args(prn)
    _add_run_args(prn)
    prn.add_argument("--yes", action="store_true")

    pd = sub.add_parser("derive-answer")
    pd.add_argument("--script", required=True)
    pd.add_argument("--engine-pr")
    pd.add_argument("--issue")
    pd.add_argument("--post")
    pd.add_argument("--build-type", default="debug")
    pd.add_argument("--timeout", type=int, default=10800)
    pd.add_argument("--yes", action="store_true")

    sub.add_parser("health")

    args = ap.parse_args()
    try:
        handler = {"submit": cmd_submit, "wait": cmd_wait, "judge": cmd_judge,
                   "run": cmd_run, "derive-answer": cmd_derive_answer,
                   "health": cmd_health}.get(args.cmd)
        if handler is None:
            ap.print_help()
            sys.exit(2)
        handler(args)
    except BuilderTesterError as e:
        sys.exit("Builder-Tester unavailable: %s" % e)


if __name__ == "__main__":
    main()
