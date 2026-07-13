import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from post_review import build_review_payload, curl_fallback


class TestBuildReviewPayload(unittest.TestCase):
    def test_default_is_comment(self):
        p = build_review_payload("본문 리뷰 내용")
        self.assertEqual(p, {"body": "본문 리뷰 내용", "event": "COMMENT"})

    def test_request_changes(self):
        p = build_review_payload("blocking", request_changes=True)
        self.assertEqual(p["event"], "REQUEST_CHANGES")


class TestCurlFallback(unittest.TestCase):
    def test_contains_endpoint_and_payload(self):
        cmd = curl_fallback("CUBRID", "cubrid-testcases", 2956, "/tmp/r.payload.json")
        self.assertIn("/repos/CUBRID/cubrid-testcases/pulls/2956/reviews", cmd)
        self.assertIn("@/tmp/r.payload.json", cmd)
        self.assertIn("$GITHUB_TOKEN", cmd)


if __name__ == "__main__":
    unittest.main()
