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
