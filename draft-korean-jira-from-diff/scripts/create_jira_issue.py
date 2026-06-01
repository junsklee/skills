#!/usr/bin/env python3
"""Create CUBRIDQA JIRA issues for the draft-korean-jira-from-diff skill."""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://jira.cubrid.org"
DEFAULT_PROJECT = "CUBRIDQA"
DEFAULT_ISSUE_TYPE = "Task"
DEFAULT_SUMMARY_PREFIX = "[QAHome] "


def read_description(args):
    if args.description is not None and args.description_file is not None:
        raise SystemExit("Use either --description or --description-file, not both.")
    if args.description is not None:
        return args.description
    if args.description_file == "-":
        return sys.stdin.read()
    if args.description_file:
        with open(args.description_file, "r", encoding="utf-8") as handle:
            return handle.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("Description is required. Use --description, --description-file, or stdin.")


def build_summary(title, prefix):
    title = title.strip()
    if title.startswith(prefix):
        return title
    return prefix + title


def build_payload(args, description):
    return {
        "fields": {
            "project": {"key": args.project},
            "issuetype": {"name": args.issue_type},
            "summary": build_summary(args.title, args.summary_prefix),
            "description": description.strip(),
        }
    }


def jira_request(url, payload, user, password):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": "Basic " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return response.getcode(), body


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build or submit a CUBRIDQA Task issue to JIRA."
    )
    parser.add_argument("--title", required=True, help="Issue title without the [QAHome] prefix.")
    parser.add_argument("--description", help="JIRA description text.")
    parser.add_argument("--description-file", help="Path to description text, or '-' for stdin.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("JIRA_BASE_URL", DEFAULT_BASE_URL),
        help="JIRA base URL. Defaults to JIRA_BASE_URL or http://jira.cubrid.org.",
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="JIRA project key.")
    parser.add_argument("--issue-type", default=DEFAULT_ISSUE_TYPE, help="JIRA issue type name.")
    parser.add_argument(
        "--summary-prefix",
        default=DEFAULT_SUMMARY_PREFIX,
        help="Prefix prepended to the title when missing.",
    )
    parser.add_argument("--submit", action="store_true", help="POST the issue to JIRA.")
    parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Required with --submit after the user confirms the payload.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    description = read_description(args)
    payload = build_payload(args, description)
    issue_url = args.base_url.rstrip("/") + "/rest/api/2/issue"

    if not args.submit:
        print(
            json.dumps(
                {"dry_run": True, "url": issue_url, "payload": payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not args.confirmed:
        print("Refusing to submit without --confirmed.", file=sys.stderr)
        return 2

    user = os.environ.get("JIRA_USER")
    password = os.environ.get("JIRA_PASSWORD")
    if not user or not password:
        print("Set JIRA_USER and JIRA_PASSWORD before submitting.", file=sys.stderr)
        return 2

    try:
        _, body = jira_request(issue_url, payload, user, password)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"JIRA request failed with HTTP {exc.code}.", file=sys.stderr)
        print(error_body, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"JIRA request failed: {exc.reason}", file=sys.stderr)
        return 1

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        print(body)
        return 0

    key = result.get("key", "")
    browse_url = args.base_url.rstrip("/") + "/browse/" + key if key else ""
    print(json.dumps({"created": True, "key": key, "url": browse_url}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
