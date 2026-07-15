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


class TestResultsByCommit(unittest.TestCase):
    REPORT = {"results": [
        {"commit": "PRE", "status": "fail",
         "attemptLogMetadata": [{"attempt": 1, "status": "fail", "logFileName": "pre1.log"},
                                {"attempt": 2, "status": "fail", "logFileName": "pre2.log"}]},
        {"commit": "POST", "status": "pass",
         "attemptLogMetadata": [{"attempt": 1, "status": "pass", "logFileName": "post1.log"},
                                {"attempt": 2, "status": "pass", "logFileName": "post2.log"}]},
    ]}

    def test_groups_attempts_and_logs_by_commit(self):
        by = vt.results_by_commit(self.REPORT)
        self.assertEqual(by["PRE"]["attempts"], ["fail", "fail"])
        self.assertEqual(by["POST"]["logs"], ["post1.log", "post2.log"])

    def test_falls_back_to_top_level_status(self):
        by = vt.results_by_commit({"results": [{"commit": "X", "status": "pass"}]})
        self.assertEqual(by["X"]["attempts"], ["pass"])
        self.assertEqual(by["X"]["logs"], [])


class TestLocateReport(unittest.TestCase):
    def test_finds_by_id(self):
        self.assertEqual(vt.locate_report([{"id": "a"}, {"id": "req_9"}], "req_9"),
                         {"id": "req_9"})

    def test_missing_returns_none(self):
        self.assertIsNone(vt.locate_report([{"id": "a"}], "req_9"))


class TestJudgeMatrix(unittest.TestCase):
    def by(self, pre, post):
        d = {}
        if pre is not None:
            d["PRE"] = {"attempts": pre, "logs": []}
        if post is not None:
            d["POST"] = {"attempts": post, "logs": []}
        return d

    def test_verified(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail", "fail"], ["pass", "pass"]),
                                         "PRE", "POST")["verdict"], "VERIFIED")

    def test_verified_with_short_sha_prefix_lookup(self):
        by = {"aaaaaaaaaaaa": {"attempts": ["fail"], "logs": []},
              "bbbbbbbbbbbb": {"attempts": ["pass", "pass"], "logs": []}}
        self.assertEqual(vt.judge_matrix(by, "aaaaaaa", "bbbbbbb")["verdict"], "VERIFIED")

    def test_not_verified_when_prefix_passes(self):
        self.assertEqual(vt.judge_matrix(self.by(["pass", "pass"], ["pass", "pass"]),
                                         "PRE", "POST")["verdict"], "NOT-VERIFIED")

    def test_not_verified_when_postfix_fails(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail", "fail"], ["fail", "fail"]),
                                         "PRE", "POST")["verdict"], "NOT-VERIFIED")

    def test_flaky_when_postfix_mixed(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail", "fail"], ["pass", "fail"]),
                                         "PRE", "POST")["verdict"], "FLAKY")

    def test_inconclusive_when_no_postfix_result(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail"], None), "PRE", "POST")["verdict"],
                         "INCONCLUSIVE")

    def test_inconclusive_when_postfix_infra_error(self):
        self.assertEqual(vt.judge_matrix(self.by(["fail"], ["error"]), "PRE", "POST")["verdict"],
                         "INCONCLUSIVE")

    def test_special_case_waives_prefix_pass(self):
        j = vt.judge_matrix(self.by(["pass", "pass"], ["pass", "pass"]),
                            "PRE", "POST", special_case="core-dump")
        self.assertEqual(j["verdict"], "VERIFIED")
        self.assertIn("waived", j["reason"])

    def test_post_only_waives_prefix(self):
        j = vt.judge_matrix(self.by(None, ["pass", "pass"]), None, "POST")
        self.assertEqual(j["verdict"], "VERIFIED")
        self.assertIn("post-only", j["reason"])


class TestStatusPhase(unittest.TestCase):
    def test_running(self):
        for s in ("running", "queued", "accepted", "already_running"):
            self.assertEqual(vt.status_phase({"status": s}), "running")

    def test_not_found_is_its_own_phase(self):
        self.assertEqual(vt.status_phase({"status": "not_found"}), "not_found")

    def test_error(self):
        self.assertEqual(vt.status_phase({"status": "error"}), "error")

    def test_progress_negative_one_is_error(self):
        self.assertEqual(vt.status_phase({"status": "running", "progress": -1}), "error")


class TestFormatVerdictBlock(unittest.TestCase):
    def test_includes_verdict_log_urls_and_verified_line(self):
        os.environ.pop("BUILDER_TESTER_URL", None)
        judged = {"verdict": "VERIFIED", "reason": "ok",
                  "pre_sha": "aaaaaaabbb", "post_sha": "cccccccddd",
                  "pre_attempts": ["fail"], "post_attempts": ["pass", "pass"],
                  "pre_logs": ["pre1.log"], "post_logs": ["post1.log", "post2.log"],
                  "special_case": None}
        out = vt.format_verdict_block(judged, "req_x")
        self.assertIn("VERDICT: VERIFIED", out)
        self.assertIn("/api/log/req_x/tests/post1.log", out)
        self.assertIn("Verified: pre-fix aaaaaaa", out)
        self.assertIn("NOK", out)
        self.assertIn("OK", out)

    def test_special_case_waived_line_not_nok(self):
        judged = {"verdict": "VERIFIED", "reason": "waived",
                  "pre_sha": "aaaaaaabbb", "post_sha": "cccccccddd",
                  "pre_attempts": ["pass", "pass"], "post_attempts": ["pass"],
                  "pre_logs": [], "post_logs": [], "special_case": "core-dump"}
        out = vt.format_verdict_block(judged, "req_x")
        self.assertNotIn("-> NOK", out)
        self.assertIn("pre-fix waived: core-dump", out)

    def test_post_only_waived_line(self):
        judged = {"verdict": "VERIFIED", "reason": "post-only",
                  "pre_sha": None, "post_sha": "cccccccddd",
                  "pre_attempts": [], "post_attempts": ["pass", "pass"],
                  "pre_logs": [], "post_logs": [], "special_case": None}
        out = vt.format_verdict_block(judged, "req_x")
        self.assertIn("pre-fix waived: post-only", out)
        self.assertNotIn("-> NOK", out)


class TestInconclusive(unittest.TestCase):
    def test_shape(self):
        j = vt.inconclusive("builder unreachable", "PRE", "POST")
        self.assertEqual(j["verdict"], "INCONCLUSIVE")
        self.assertEqual(j["pre_attempts"], [])
        self.assertEqual(j["post_logs"], [])


class TestCaptureTransform(unittest.TestCase):
    def test_replaces_compare_calls_and_records_mapping(self):
        src = ("#!/bin/bash\n"
               "csql ... > a.log 2>&1\n"
               "    compare_result_between_files a.log a.answer\n"
               "finish\n")
        new, mapping = vt.capture_transform(src)
        self.assertEqual(mapping, [(1, "a.log", "a.answer")])
        self.assertIn('echo "ANSWER_BEGIN_1"', new)
        self.assertIn("base64 a.log", new)
        self.assertIn('echo "ANSWER_END_1"', new)
        self.assertNotIn("compare_result_between_files", new)
        self.assertIn("    echo", new)  # indentation preserved

    def test_tolerates_trailing_arg_and_if_guard(self):
        src = ("if ! compare_result_between_files x.log x.answer sort; then\n"
               "  write_nok\nfi\n")
        new, mapping = vt.capture_transform(src)
        self.assertEqual(mapping, [(1, "x.log", "x.answer")])
        self.assertIn("base64 x.log", new)

    def test_multiple_calls_numbered(self):
        src = ("compare_result_between_files x.log x.answer\n"
               "compare_result_between_files y.log y.answer\n")
        new, mapping = vt.capture_transform(src)
        self.assertEqual([m[0] for m in mapping], [1, 2])
        self.assertIn("ANSWER_BEGIN_2", new)

    def test_no_compare_calls_is_noop(self):
        src = "echo hi\nfinish\n"
        new, mapping = vt.capture_transform(src)
        self.assertEqual(mapping, [])
        self.assertEqual(new, src)
        self.assertFalse(vt.has_compare_calls(src))

    def test_has_compare_calls_true_when_present(self):
        self.assertTrue(vt.has_compare_calls("x=1; compare_result_between_files a b\n"))


class TestExtractAnswers(unittest.TestCase):
    def test_extracts_base64_between_exact_sentinels(self):
        payload = base64.b64encode(b"expected output\n").decode("ascii")
        log = ("+ echo ANSWER_BEGIN_1\n"      # sh -x trace (ignored)
               "ANSWER_BEGIN_1\n"             # real stdout sentinel
               "+ base64 a.log\n"             # trace (ignored)
               + payload + "\n"
               "ANSWER_END_1\n"
               "+ echo ANSWER_END_1\n")
        got = vt.extract_answers(log, [(1, "a.log", "a.answer")])
        self.assertEqual(got[1], b"expected output\n")

    def test_extracts_multiline_wrapped_base64(self):
        raw = b"x" * 200  # base64 wraps at 76 cols -> multiple payload lines
        payload = base64.b64encode(raw).decode("ascii")
        wrapped = "\n".join(payload[i:i + 76] for i in range(0, len(payload), 76))
        log = "ANSWER_BEGIN_1\n" + wrapped + "\nANSWER_END_1\n"
        self.assertEqual(vt.extract_answers(log, [(1, "a.log", "a.answer")])[1], raw)

    def test_missing_block_is_skipped(self):
        self.assertNotIn(1, vt.extract_answers("nothing\n", [(1, "a.log", "a.answer")]))


class TestSuggestAnswerName(unittest.TestCase):
    def test_literal_answer_arg_uses_basename(self):
        self.assertEqual(vt.suggest_answer_name("dir/cbrd_1.answer", "cbrd_1", 1),
                         "cbrd_1.answer")

    def test_variable_answer_arg_falls_back_to_stem(self):
        self.assertEqual(vt.suggest_answer_name("$db.answer", "cbrd_1", 1),
                         "cbrd_1.answer")

    def test_variable_multiple_uses_index(self):
        self.assertEqual(vt.suggest_answer_name("$db.answer", "cbrd_1", 2),
                         "cbrd_1_2.answer")
