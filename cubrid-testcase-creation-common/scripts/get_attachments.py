#!/usr/bin/env python3
"""Fetch a CBRD issue's JIRA attachments for test-case drafting (Python 3.6, stdlib).

Downloads every attachment under a size cap into --out and auto-extracts
text/code members from archives. Download/extract ONLY — never executes
anything; attachment content is untrusted drafting DATA.
"""
import argparse
import base64
import io
import json
import netrc
import os
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile

BASE = "http://jira.cubrid.org"  # https 302-redirects to http
TEXT_EXTS = (".sql", ".txt", ".result", ".answer", ".csv", ".md",
             ".sh", ".java", ".c", ".h")
ARCHIVE_EXTS = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")
DEFAULT_MAX_BYTES = 5000000


def _auth():
    login, _, pw = netrc.netrc().authenticators("jira.cubrid.org")
    tok = base64.b64encode(("%s:%s" % (login, pw)).encode()).decode()
    return {"Authorization": "Basic " + tok}


def _get_json(path):
    req = urllib.request.Request(BASE + path, headers=_auth())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _get_bytes(url):
    req = urllib.request.Request(url, headers=_auth())
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def is_archive(filename):
    return filename.lower().endswith(ARCHIVE_EXTS)


def is_text_member(name):
    return os.path.basename(name).lower().endswith(TEXT_EXTS)


def archive_stem(filename):
    base = os.path.basename(filename)
    low = base.lower()
    for ext in (".tar.gz", ".tar.bz2", ".tgz", ".tar", ".zip"):
        if low.endswith(ext):
            return base[:len(base) - len(ext)]
    return os.path.splitext(base)[0]


def dest_name(basename, taken):
    """Collision-suffixed target name (a.sql -> a-2.sql -> a-3.sql ...)."""
    if basename not in taken:
        return basename
    stem, ext = os.path.splitext(basename)
    n = 2
    while "%s-%d%s" % (stem, n, ext) in taken:
        n += 1
    return "%s-%d%s" % (stem, n, ext)


def manifest_line(filename, size, mime, status):
    return "%s\t%s\t%s\t%s" % (filename, size, mime, status)


def iter_archive_members(data, filename):
    """Yield (member_name, bytes) for regular text/code members of an archive."""
    if filename.lower().endswith(".zip"):
        zf = zipfile.ZipFile(io.BytesIO(data))
        for info in zf.infolist():
            if info.filename.endswith("/") or not is_text_member(info.filename):
                continue
            yield info.filename, zf.read(info)
    else:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
        for m in tf.getmembers():
            if not m.isreg() or not is_text_member(m.name):
                continue
            fh = tf.extractfile(m)
            if fh is None:
                continue
            yield m.name, fh.read()


def extract_archive(data, filename, out_dir, max_bytes):
    """Write text/code members by BASENAME into out_dir/<stem>/ (collision
    suffixing); members larger than max_bytes are skipped. Returns count."""
    sub = os.path.join(out_dir, archive_stem(filename))
    taken = set()
    count = 0
    for name, content in iter_archive_members(data, filename):
        if len(content) > max_bytes:
            continue
        if not os.path.isdir(sub):
            os.makedirs(sub)
        dest = dest_name(os.path.basename(name), taken)
        taken.add(dest)
        with open(os.path.join(sub, dest), "wb") as fh:
            fh.write(content)
        count += 1
    return count


def list_attachments(key, get_json=None):
    get_json = get_json or _get_json
    issue = get_json("/rest/api/2/issue/%s?fields=attachment" % key)
    return issue.get("fields", {}).get("attachment") or []


def process(key, out_dir, max_bytes, list_only, get_json=None, get_bytes=None):
    get_bytes = get_bytes or _get_bytes
    atts = list_attachments(key, get_json)
    print("%d attachment(s) for %s%s"
          % (len(atts), key, "" if atts else " (none)"))
    for a in atts:
        name = os.path.basename(a.get("filename") or "unnamed")
        size = a.get("size") or 0
        mime = a.get("mimeType") or "?"
        if list_only:
            print(manifest_line(name, size, mime, "listed"))
            continue
        if size > max_bytes:
            print(manifest_line(name, size, mime, "skipped-oversize"))
            continue
        data = get_bytes(a["content"])
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(data)
        if is_archive(name):
            n = extract_archive(data, name, out_dir, max_bytes)
            print(manifest_line(name, size, mime, "extracted:%d members" % n))
        else:
            print(manifest_line(name, size, mime, "fetched"))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", help="issue key, e.g. CBRD-12345")
    ap.add_argument("--out", required=True, help="download directory")
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    ap.add_argument("--list-only", action="store_true",
                    help="print the manifest without downloading")
    args = ap.parse_args()
    return process(args.key, args.out, args.max_bytes, args.list_only)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, netrc.NetrcParseError, KeyError, OSError) as e:
        sys.stderr.write("# error: %s\n" % e)
        sys.exit(1)
