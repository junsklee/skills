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


def _make_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("case.sql", "select 1;\n")
        zf.writestr("img.png", b"\x89PNG binary")
        zf.writestr("sub/nested.sql", "select 2;\n")
        zf.writestr("other/case.sql", "select 3;\n")   # basename collision
        zf.writestr("dir/", "")


def _make_targz(path):
    with tarfile.open(path, "w:gz") as tf:
        for name, content in (("readme.txt", b"hi\n"), ("bin.dat", b"\x00\x01"),
                              ("d/inner.answer", b"===\n1\n")):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))


class TestExtractArchive(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_zip_text_members_by_basename_with_collision(self):
        zp = os.path.join(self.d, "case.zip")
        _make_zip(zp)
        with open(zp, "rb") as fh:
            data = fh.read()
        n = ga.extract_archive(data, "case.zip", self.d, 5000000)
        sub = os.path.join(self.d, "case")
        got = sorted(os.listdir(sub))
        self.assertEqual(n, 3)                             # 3 .sql, no png, no dir
        self.assertEqual(got, ["case-2.sql", "case.sql", "nested.sql"])
        with open(os.path.join(sub, "nested.sql")) as fh:
            self.assertEqual(fh.read(), "select 2;\n")

    def test_targz_text_members_only(self):
        tp = os.path.join(self.d, "repro.tar.gz")
        _make_targz(tp)
        with open(tp, "rb") as fh:
            data = fh.read()
        n = ga.extract_archive(data, "repro.tar.gz", self.d, 5000000)
        sub = os.path.join(self.d, "repro")
        self.assertEqual(n, 2)
        self.assertEqual(sorted(os.listdir(sub)), ["inner.answer", "readme.txt"])

    def test_oversize_member_skipped(self):
        zp = os.path.join(self.d, "big.zip")
        with zipfile.ZipFile(zp, "w") as zf:
            zf.writestr("big.sql", "x" * 100)
            zf.writestr("ok.sql", "select 1;\n")
        with open(zp, "rb") as fh:
            data = fh.read()
        n = ga.extract_archive(data, "big.zip", self.d, 50)   # cap below big.sql
        self.assertEqual(n, 1)
        self.assertEqual(os.listdir(os.path.join(self.d, "big")), ["ok.sql"])


class TestProcessArchiveFlow(unittest.TestCase):
    def test_archive_saved_and_extracted_with_manifest(self):
        d = tempfile.mkdtemp()
        try:
            zbuf = io.BytesIO()
            with zipfile.ZipFile(zbuf, "w") as zf:
                zf.writestr("case.sql", "select 1;\n")
            zdata = zbuf.getvalue()
            atts = {"fields": {"attachment": [
                {"filename": "case.zip", "size": len(zdata), "mimeType": "application/zip",
                 "content": "http://jira/secure/attachment/9/case.zip"}]}}
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ga.process("CBRD-1", d, 5000000, False,
                           get_json=lambda p: atts, get_bytes=lambda u: zdata)
            self.assertTrue(os.path.exists(os.path.join(d, "case.zip")))
            self.assertTrue(os.path.exists(os.path.join(d, "case", "case.sql")))
            self.assertIn("case.zip\t%d\tapplication/zip\textracted:1 members" % len(zdata),
                          buf.getvalue())
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
