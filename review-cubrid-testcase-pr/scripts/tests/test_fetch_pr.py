import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fetch_pr import parse_pr_url, extract_jira_key, detect_categories


class TestParsePrUrl(unittest.TestCase):
    def test_full_url(self):
        self.assertEqual(
            parse_pr_url("https://github.com/CUBRID/cubrid-testcases/pull/2956"),
            ("CUBRID", "cubrid-testcases", 2956))

    def test_full_url_with_trailing_segment(self):
        self.assertEqual(
            parse_pr_url("https://github.com/CUBRID/cubrid-testcases-private-ex/pull/3621/files"),
            ("CUBRID", "cubrid-testcases-private-ex", 3621))

    def test_short_form(self):
        self.assertEqual(parse_pr_url("CUBRID/cubrid-testcases#2956"),
                         ("CUBRID", "cubrid-testcases", 2956))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_pr_url("http://jira.cubrid.org/browse/CBRD-26563")


class TestExtractJiraKey(unittest.TestCase):
    def test_refer_to_first_line(self):
        body = "Refer to: http://jira.cubrid.org/browse/CBRD-26563\n\ndetails"
        self.assertEqual(extract_jira_key("title", body, []), "CBRD-26563")

    def test_bare_angle_url_first_line(self):
        # real shape from cubrid-testcases-private-ex#3621
        body = "<http://jira.cubrid.org/browse/CBRD-26862>\n\nRevise expected count"
        self.assertEqual(extract_jira_key("title", body, []), "CBRD-26862")

    def test_second_line_fallback(self):
        body = "Some intro line\nRefer to: http://jira.cubrid.org/browse/CBRD-27001"
        self.assertEqual(extract_jira_key("title", body, []), "CBRD-27001")

    def test_title_fallback(self):
        # real shape from cubrid-testcases#2956: key only in the title
        self.assertEqual(
            extract_jira_key("[CBRD-26906] Backport from develop to 11.4", "backport #2931", []),
            "CBRD-26906")

    def test_path_fallback(self):
        paths = ["shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh"]
        self.assertEqual(extract_jira_key("no key", "no key", paths), "CBRD-27000")

    def test_lowercase_in_body(self):
        self.assertEqual(extract_jira_key("t", "fixes cbrd-25913 regression", []),
                         "CBRD-25913")

    def test_none_when_absent(self):
        self.assertIsNone(extract_jira_key("no key", "no key", ["sql/foo/cases/a.sql"]))

    def test_none_body(self):
        self.assertEqual(extract_jira_key("[CBRD-11111] t", None, []), "CBRD-11111")


class TestDetectCategories(unittest.TestCase):
    def test_sql_and_medium_grouped_as_sql(self):
        cats = detect_categories([
            "sql/_13_issues/_26_1h/cases/cbrd_26906.sql",
            "medium/_01_fixed/answers/fview1.answer"])
        self.assertEqual(sorted(cats.keys()), ["sql"])
        self.assertEqual(len(cats["sql"]), 2)

    def test_shell(self):
        cats = detect_categories(["shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh"])
        self.assertEqual(sorted(cats.keys()), ["shell"])

    def test_excluded_list_separated_from_shell(self):
        cats = detect_categories([
            "shell/config/daily_regression_test_excluded_list_linux.conf",
            "shell/_06_issues/_26_1h/cbrd_27000/cases/cbrd_27000.sh"])
        self.assertEqual(sorted(cats.keys()), ["excluded_list", "shell"])

    def test_other(self):
        cats = detect_categories(["isolation/_01_basic/cases/x.ctl", "README.md"])
        self.assertEqual(sorted(cats.keys()), ["other"])
        self.assertEqual(len(cats["other"]), 2)


if __name__ == "__main__":
    unittest.main()
