import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import get_attachments as ga


class TestClassifiers(unittest.TestCase):
    def test_is_archive(self):
        for n in ("a.zip", "b.TAR", "c.tar.gz", "d.tgz", "e.tar.bz2"):
            self.assertTrue(ga.is_archive(n), n)
        for n in ("a.sql", "b.txt", "c.gz", "d.tar.xz"):
            self.assertFalse(ga.is_archive(n), n)

    def test_is_text_member(self):
        for n in ("x.sql", "sub/y.TXT", "z.answer", "w.result", "m.md", "s.sh",
                  "j.java", "c.c", "h.h", "d.csv"):
            self.assertTrue(ga.is_text_member(n), n)
        for n in ("i.png", "b.bin", "noext", "a.svg", "t.tar.gz"):
            self.assertFalse(ga.is_text_member(n), n)

    def test_archive_stem(self):
        self.assertEqual(ga.archive_stem("case.tar.gz"), "case")
        self.assertEqual(ga.archive_stem("case.tgz"), "case")
        self.assertEqual(ga.archive_stem("case.tar.bz2"), "case")
        self.assertEqual(ga.archive_stem("dir/case.zip"), "case")
        self.assertEqual(ga.archive_stem("case.tar"), "case")


class TestDestName(unittest.TestCase):
    def test_no_collision(self):
        self.assertEqual(ga.dest_name("a.sql", set()), "a.sql")

    def test_collision_suffixes(self):
        taken = {"a.sql"}
        self.assertEqual(ga.dest_name("a.sql", taken), "a-2.sql")
        taken.add("a-2.sql")
        self.assertEqual(ga.dest_name("a.sql", taken), "a-3.sql")


class TestManifestLine(unittest.TestCase):
    def test_tab_separated(self):
        self.assertEqual(ga.manifest_line("a.sql", 10, "application/x-sql", "fetched"),
                         "a.sql\t10\tapplication/x-sql\tfetched")


class TestListAndListOnly(unittest.TestCase):
    ATTS = {"fields": {"attachment": [
        {"filename": "cbrd_1.sql", "size": 100, "mimeType": "application/x-sql",
         "content": "http://jira/secure/attachment/1/cbrd_1.sql"},
        {"filename": "big.dump", "size": 99999999, "mimeType": "application/octet-stream",
         "content": "http://jira/secure/attachment/2/big.dump"},
    ]}}

    def test_list_attachments_uses_injected_fetcher(self):
        got = ga.list_attachments("CBRD-1", get_json=lambda p: self.ATTS)
        self.assertEqual([a["filename"] for a in got], ["cbrd_1.sql", "big.dump"])

    def test_no_attachments_is_empty(self):
        got = ga.list_attachments("CBRD-1", get_json=lambda p: {"fields": {"attachment": []}})
        self.assertEqual(got, [])

    def test_list_only_writes_nothing_and_prints_manifest(self):
        d = tempfile.mkdtemp()
        try:
            import contextlib
            buf = io.StringIO()
            calls = []
            with contextlib.redirect_stdout(buf):
                rc = ga.process("CBRD-1", d, 5000000, True,
                                get_json=lambda p: self.ATTS,
                                get_bytes=lambda u: calls.append(u) or b"x")
            self.assertEqual(rc, 0)
            self.assertEqual(calls, [])                      # nothing downloaded
            self.assertEqual(os.listdir(d), [])              # nothing written
            out = buf.getvalue()
            self.assertIn("2 attachment(s) for CBRD-1", out)
            self.assertIn("cbrd_1.sql\t100\tapplication/x-sql\tlisted", out)
        finally:
            shutil.rmtree(d)

    def test_oversize_is_skipped_not_fetched(self):
        d = tempfile.mkdtemp()
        try:
            import contextlib
            buf = io.StringIO()
            fetched = []
            with contextlib.redirect_stdout(buf):
                ga.process("CBRD-1", d, 5000000, False,
                           get_json=lambda p: self.ATTS,
                           get_bytes=lambda u: fetched.append(u) or b"content")
            self.assertEqual(len(fetched), 1)                # only the small one
            self.assertIn("big.dump\t99999999\tapplication/octet-stream\tskipped-oversize",
                          buf.getvalue())
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
