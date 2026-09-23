# xaloAC-x410m1s0
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "xaloAC.py"
ENV = {**os.environ, "PYTHONUTF8": "1"}


class XaloACSmokeTests(unittest.TestCase):
    def test_version_command(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env=ENV,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("xaloAC 1.0.0", result.stdout)

    def test_stats_respects_custom_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "demo.txt").write_text("hello from xaloAC\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--fresh", "stats"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                env=ENV,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"Kök     : {root}", result.stdout)
            self.assertIn("demo.txt", result.stdout)


if __name__ == "__main__":
    unittest.main()
