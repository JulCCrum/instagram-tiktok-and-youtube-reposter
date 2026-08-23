import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from instagram_scraper import download_post


class FakeContext:
    def cookies(self):
        return []


class FakePage:
    context = FakeContext()


class DownloadPostTests(unittest.TestCase):
    @patch("subprocess.run")
    def test_ignores_global_config_and_reports_downloader_failure(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 1, stdout="", stderr="caption failed"),
            subprocess.CompletedProcess([], 2, stdout="", stderr="real downloader error"),
        ]

        post = {
            "shortcode": "example",
            "full_url": "https://www.instagram.com/reel/example/",
            "is_reel": True,
        }

        with tempfile.TemporaryDirectory() as directory, io.StringIO() as output:
            with redirect_stdout(output):
                result = download_post(FakePage(), post, Path(directory))

            self.assertIsNone(result)
            self.assertIn("--ignore-config", run.call_args_list[0].args[0])
            self.assertIn("--ignore-config", run.call_args_list[1].args[0])
            self.assertIn("exit=2", output.getvalue())
            self.assertIn("real downloader error", output.getvalue())


if __name__ == "__main__":
    unittest.main()
