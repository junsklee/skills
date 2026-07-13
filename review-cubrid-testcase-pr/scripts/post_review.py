#!/usr/bin/env python3
"""Post a review to a CUBRID test-case PR.

DRY-RUN BY DEFAULT: without --yes nothing is sent to GitHub; the payload is
saved next to the body file and an equivalent curl command is printed.

Usage:
    python3 post_review.py <pr-ref> --body-file review.md [--request-changes] [--yes]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_pr import API, parse_pr_url


def build_review_payload(body_text, request_changes=False):
    return {"body": body_text,
            "event": "REQUEST_CHANGES" if request_changes else "COMMENT"}


def curl_fallback(owner, repo, number, payload_path):
    return ("curl -sS -X POST -H \"Authorization: Bearer $GITHUB_TOKEN\" "
            "-H \"Accept: application/vnd.github+json\" "
            "-d @%s %s/repos/%s/%s/pulls/%d/reviews"
            % (payload_path, API, owner, repo, number))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pr", help="PR URL or OWNER/REPO#N")
    ap.add_argument("--body-file", required=True, help="markdown file with the review body")
    ap.add_argument("--request-changes", action="store_true",
                    help="submit as REQUEST_CHANGES instead of COMMENT")
    ap.add_argument("--yes", action="store_true",
                    help="actually send the review (default: dry-run)")
    args = ap.parse_args()

    owner, repo, number = parse_pr_url(args.pr)
    with open(args.body_file, encoding="utf-8") as fh:
        body = fh.read().strip()
    if not body:
        sys.exit("review body is empty; refusing to post")

    payload = build_review_payload(body, args.request_changes)
    payload_path = args.body_file + ".payload.json"
    with open(payload_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    url = "%s/repos/%s/%s/pulls/%d/reviews" % (API, owner, repo, number)
    if not args.yes:
        print("[dry-run] would POST %s" % url)
        print("[dry-run] event=%s, body=%d chars" % (payload["event"], len(body)))
        print("[dry-run] payload saved to %s" % payload_path)
        print("[dry-run] manual send: " + curl_fallback(owner, repo, number, payload_path))
        return

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set; run via: bash -lc 'export GITHUB_TOKEN; ...'")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "review-cubrid-testcase-pr"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        print("review posted: %s" % (out.get("html_url") or out.get("id")))
    except urllib.error.HTTPError as e:
        sys.stderr.write("POST failed: HTTP %d\n%s\n"
                         % (e.code, e.read().decode("utf-8", "replace")))
        sys.stderr.write("payload preserved at %s\nmanual send: %s\n"
                         % (payload_path, curl_fallback(owner, repo, number, payload_path)))
        sys.exit(1)
    except urllib.error.URLError as e:
        sys.stderr.write("POST failed: %s\n" % e)
        sys.stderr.write("payload preserved at %s\nmanual send: %s\n"
                         % (payload_path, curl_fallback(owner, repo, number, payload_path)))
        sys.exit(1)


if __name__ == "__main__":
    main()
