#!/usr/bin/env python3
"""The 7.2 preview fetcher must never refresh or reuse an unpinned ZIP."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fetch_windows_platform_tools.sh"
URL = "https://dl.google.com/android/repository/platform-tools_r37.0.3-win.zip"
SHA = "89d108360a3bf2924d3bea837239edaccc22fd6ff5befd3787c4348a9fe4f09d"


class PlatformToolsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.archive = self.root / "tools dir/platform-tools.zip"
        self.log = self.root / "curl-call"
        curl = self.bin / "curl"
        curl.write_text("""#!/bin/bash
set -euo pipefail
printf '%s\\n' "$@" > "$MOCK_CURL_LOG"
while (( $# > 2 )); do shift; done
printf corrupted > "$1"
""")
        curl.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        MOCK_CURL_LOG=str(self.log))

    def run_cli(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True, env=self.env, timeout=10)

    def test_pins_the_versioned_upstream_object(self):
        result = self.run_cli("--print-pin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["version=37.0.3", f"url={URL}", f"sha256={SHA}"])
        self.assertFalse(self.log.exists())

    def test_rejects_an_existing_wrong_archive_without_overwriting(self):
        self.archive.parent.mkdir()
        self.archive.write_bytes(b"existing archive")
        result = self.run_cli("--fetch", self.archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertEqual(self.archive.read_bytes(), b"existing archive")
        self.assertFalse(self.log.exists())

    def test_rejects_bad_download_and_cleans_its_own_partial_file(self):
        result = self.run_cli("--fetch", self.archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertFalse(self.archive.exists())
        self.assertEqual(list(self.archive.parent.iterdir()), [])
        args = self.log.read_text().splitlines()
        self.assertIn("--disable", args)
        self.assertIn("--proto-redir", args)
        self.assertEqual(args[-1], URL)
        self.assertEqual(args[-3], "--output")

    def test_does_not_follow_a_symlink_or_fetch_a_missing_input_in_verify_mode(self):
        self.archive.parent.mkdir()
        missing = self.run_cli("--verify", self.archive)
        self.assertNotEqual(missing.returncode, 0)
        self.archive.symlink_to(self.root / "never-created")
        result = self.run_cli("--fetch", self.archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular archive", result.stderr)
        self.assertTrue(self.archive.is_symlink())
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
