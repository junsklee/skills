import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_context import filter_tree, parse_pr_ref, safe_dest


class TestParsePrRef(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(parse_pr_ref("https://github.com/CUBRID/cubrid/pull/7213"),
                         ("CUBRID", "cubrid", 7213))

    def test_short_form(self):
        self.assertEqual(parse_pr_ref("CUBRID/cubrid-testcases#2988"),
                         ("CUBRID", "cubrid-testcases", 2988))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_pr_ref("http://jira.cubrid.org/browse/CBRD-25709")


class TestFilterTree(unittest.TestCase):
    PATHS = ["sql/_13_issues/_26_2h/cases/cbrd_25709.sql",
             "sql/_13_issues/_26_2h/answers/cbrd_25709.answer",
             "shell/_06_issues/_26_1h/cbrd_26563/cases/cbrd_26563.sh",
             "sql/_36_guava/cbrd_26486/cases/01_uuid_basic.sql"]

    def test_substring_case_insensitive(self):
        self.assertEqual(len(filter_tree(self.PATHS, "CBRD_25709")), 2)

    def test_prefix_scope(self):
        got = filter_tree(self.PATHS, "cbrd", prefix="shell/")
        self.assertEqual(got, ["shell/_06_issues/_26_1h/cbrd_26563/cases/cbrd_26563.sh"])

    def test_no_match(self):
        self.assertEqual(filter_tree(self.PATHS, "cbrd_99999"), [])


class TestSafeDest(unittest.TestCase):
    def setUp(self):
        self.base = os.path.abspath("/data/ctx")

    def test_normal(self):
        self.assertEqual(safe_dest(self.base, "sql/cases/a.sql"),
                         os.path.join(self.base, "sql", "cases", "a.sql"))

    def test_traversal_contained(self):
        self.assertTrue(safe_dest(self.base, "../../etc/passwd")
                        .startswith(self.base + os.sep))

    def test_absolute_contained(self):
        self.assertTrue(safe_dest(self.base, "/etc/passwd")
                        .startswith(self.base + os.sep))


if __name__ == "__main__":
    unittest.main()
