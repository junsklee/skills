import base64
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import btlib
import verify_testcase as vt


class TestBtlibConfig(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("BUILDER_TESTER_URL", "BUILDER_TESTER_WORKER_IPS")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_builder_url_default(self):
        self.assertEqual(btlib.builder_url(), "http://192.168.2.154:8091")

    def test_builder_url_env_override_strips_trailing_slash(self):
        os.environ["BUILDER_TESTER_URL"] = "http://host:9000/"
        self.assertEqual(btlib.builder_url(), "http://host:9000")

    def test_worker_ips_default(self):
        self.assertEqual(btlib.worker_ips(), ["192.168.2.154:8090"])

    def test_worker_ips_env_override_trims_and_drops_empty(self):
        os.environ["BUILDER_TESTER_WORKER_IPS"] = " a:1 , ,b:2 ,"
        self.assertEqual(btlib.worker_ips(), ["a:1", "b:2"])

    def test_error_is_exception(self):
        self.assertTrue(issubclass(btlib.BuilderTesterError, Exception))


class TestValidateTarget(unittest.TestCase):
    def test_accepts_plain_relative(self):
        vt.validate_target("helper.c")
        vt.validate_target("sub/data.txt")

    def test_rejects_absolute_and_dotdot(self):
        for bad in ("/etc/passwd", "../x", "a/../b", "./x"):
            with self.assertRaises(ValueError):
                vt.validate_target(bad)

    def test_rejects_builder_forbidden_chars(self):
        for bad in ("a b.txt", 'a".txt', "a$b.txt", "a`b.txt", "a'b.txt"):
            with self.assertRaises(ValueError):
                vt.validate_target(bad)


class TestCollectAttachments(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cases = os.path.join(self.d, "shell", "_06_issues", "cbrd_1", "cases")
        os.makedirs(self.cases)
        self.entry = os.path.join(self.cases, "cbrd_1.sh")
        with open(self.entry, "w") as fh:
            fh.write("#!/bin/bash\n")
        with open(os.path.join(self.cases, "helper.c"), "w") as fh:
            fh.write("int main(){return 0;}\n")
        with open(os.path.join(self.cases, "cbrd_1.answer"), "w") as fh:
            fh.write("expected\n")
        os.makedirs(os.path.join(self.cases, "sub"))
        with open(os.path.join(self.cases, "sub", "data.txt"), "w") as fh:
            fh.write("x\n")
        with open(os.path.join(self.cases, ".hidden"), "w") as fh:
            fh.write("secret\n")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_walks_case_dir_excludes_entry_and_dotfiles(self):
        atts = vt.collect_attachments(self.cases, self.entry)
        paths = [a["targetPath"] for a in atts]
        self.assertEqual(paths, ["cbrd_1.answer", "helper.c", "sub/data.txt"])
        for a in atts:
            self.assertNotIn("..", a["targetPath"])
            self.assertTrue(a["contentBase64"])

    def test_ignores_sibling_dirs_outside_case_dir(self):
        # A sibling answers/ dir (SQL-style layout) is not walked.
        sib = os.path.join(self.d, "shell", "_06_issues", "cbrd_1", "answers")
        os.makedirs(sib)
        with open(os.path.join(sib, "x.answer"), "w") as fh:
            fh.write("y\n")
        paths = [a["targetPath"] for a in vt.collect_attachments(self.cases, self.entry)]
        self.assertNotIn("../answers/x.answer", paths)
        self.assertEqual(paths, ["cbrd_1.answer", "helper.c", "sub/data.txt"])

    def test_rejects_helper_with_forbidden_name(self):
        with open(os.path.join(self.cases, "bad name.sh"), "w") as fh:
            fh.write("x\n")
        with self.assertRaises(ValueError):
            vt.collect_attachments(self.cases, self.entry)


class TestBuildRequest(unittest.TestCase):
    def test_shape_omits_tests_and_scriptpath_and_defaults(self):
        req = vt.build_request("#!/bin/bash\n", ["aaa", "bbb"],
                               ["h:8090"], callback_url="http://cb/callback")
        self.assertNotIn("tests", req)
        self.assertNotIn("customScriptTestPath", req)
        self.assertEqual(req["commits"], ["aaa", "bbb"])
        self.assertEqual(req["customShellScript"], "#!/bin/bash\n")
        self.assertEqual(req["workerIps"], ["h:8090"])
        self.assertEqual(req["runMode"], "fixed-runs")
        self.assertEqual(req["minRuns"], 2)
        self.assertEqual(req["maxRuns"], 2)
        self.assertEqual(req["buildType"], "debug")
        self.assertEqual(req["commitBuildMode"], "checkout")
        self.assertEqual(req["callbackUrl"], "http://cb/callback")
        self.assertNotIn("customAttachments", req)

    def test_includes_attachments_when_present(self):
        atts = [{"targetPath": "a.c", "contentBase64": "eA=="}]
        req = vt.build_request("s", ["aaa"], ["h:8090"], attachments=atts,
                               callback_url="http://cb/callback")
        self.assertEqual(req["customAttachments"], atts)


class TestParseSubmitResponse(unittest.TestCase):
    def test_accepted_returns_task_id(self):
        self.assertEqual(vt.parse_submit_response(
            {"status": "accepted", "taskId": "req_1"}), "req_1")

    def test_queued_returns_task_id(self):
        self.assertEqual(vt.parse_submit_response(
            {"status": "queued", "taskId": "req_2"}), "req_2")

    def test_error_raises(self):
        with self.assertRaises(btlib.BuilderTesterError):
            vt.parse_submit_response({"status": "error", "message": "boom"})

    def test_missing_taskid_raises(self):
        with self.assertRaises(btlib.BuilderTesterError):
            vt.parse_submit_response({"status": "accepted"})
