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


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_subparsers(dest="cmd")
    ap.parse_args()
    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
