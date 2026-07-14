import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from push_package import (answer_paths, answers_empty, branch_name,
                          build_pr_payload, collect_package)


class TestBranchName(unittest.TestCase):
    def test_jira_key(self):
        self.assertEqual(branch_name("CBRD-25709"), "cbrd_25709_tc")

    def test_lower_underscore(self):
        self.assertEqual(branch_name("cbrd_26563"), "cbrd_26563_tc")

    def test_embedded(self):
        self.assertEqual(branch_name("[CBRD-26572] uuid tests"), "cbrd_26572_tc")

    def test_rejects_no_key(self):
        with self.assertRaises(ValueError):
            branch_name("no key here")


class TestCollectPackage(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "sql", "_13_issues", "_26_2h", "cases"))
        os.makedirs(os.path.join(self.d, "sql", "_13_issues", "_26_2h", "answers"))
        with open(os.path.join(self.d, "sql/_13_issues/_26_2h/cases/cbrd_1.sql"), "w") as fh:
            fh.write("select 1;")
        open(os.path.join(self.d, "sql/_13_issues/_26_2h/answers/cbrd_1.answer"), "w").close()
        with open(os.path.join(self.d, ".hidden"), "w") as fh:
            fh.write("x")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_walk_skips_dotfiles_and_uses_repo_paths(self):
        got = collect_package(self.d)
        paths = [p for p, _ in got]
        self.assertEqual(paths, ["sql/_13_issues/_26_2h/answers/cbrd_1.answer",
                                 "sql/_13_issues/_26_2h/cases/cbrd_1.sql"])
        for _, ap in got:
            self.assertTrue(os.path.isabs(ap))


class TestAnswersEmpty(unittest.TestCase):
    def test_flags_only_empty_answer_files(self):
        sizes = {"a/cases/x.sql": 10, "a/answers/x.answer": 0,
                 "a/answers/y.answer": 5, "a/answers/x.answer_cci": 0,
                 "a/cases/empty.queryPlan": 0}
        self.assertEqual(answers_empty(sizes),
                         ["a/answers/x.answer", "a/answers/x.answer_cci"])


class TestAnswerPaths(unittest.TestCase):
    def test_filters_and_sorts(self):
        files = ["b/answers/x.answer", "a/cases/x.sql", "a/answers/y.answer_cci", "a/x.queryPlan"]
        self.assertEqual(answer_paths(files), ["a/answers/y.answer_cci", "b/answers/x.answer"])

    def test_empty_input(self):
        self.assertEqual(answer_paths([]), [])


class TestBuildPrPayload(unittest.TestCase):
    def test_shape(self):
        p = build_pr_payload("[CBRD-1] t", "본문", "junsklee", "cbrd_1_tc", "develop")
        self.assertEqual(p, {"title": "[CBRD-1] t", "body": "본문",
                             "head": "junsklee:cbrd_1_tc", "base": "develop"})


if __name__ == "__main__":
    unittest.main()
