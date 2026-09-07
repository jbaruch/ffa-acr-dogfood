"""Exercise the optional Tessl hook without invoking Tessl or personal state."""

from pathlib import Path
import subprocess
import tempfile
import unittest


HOOK = Path(__file__).resolve().parents[2] / "hooks/session-start-tessl-update.sh"
BASH = Path("/bin/bash")


class SessionStartTesslUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="ffa-hook-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # The hook's env shebang can find bash, but never an installed Tessl.
        (self.bin / "bash").symlink_to(BASH)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.log = self.root / "invocation.log"
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(self.root),
            "HOOK_TEST_LOG": str(self.log),
        }

    def stub_tessl(self, status: int) -> None:
        stub = self.bin / "tessl"
        stub.write_text(
            '#!/bin/bash\nset -euo pipefail\n'
            'printf "%s\\n" "$PWD" "$#" "$@" >> "$HOOK_TEST_LOG"\n'
            'printf "stub update output\\n"\n'
            'printf "stub update diagnostic\\n" >&2\n'
            f'exit {status}\n'
        )
        stub.chmod(0o755)

    def run_hook(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(HOOK)], cwd=self.project, env=self.env,
            capture_output=True, text=True, check=False,
        )

    def assert_invocation(self) -> None:
        self.assertEqual(
            self.log.read_text().splitlines(),
            [str(self.project), "2", "update", "--yes"],
        )

    def test_missing_tessl_skips_optional_update(self) -> None:
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Tessl update skipped", result.stderr)
        self.assertIn("optional Tessl CLI not found on PATH", result.stderr)
        self.assertIn("Install Tessl and add it to PATH", result.stderr)
        self.assertFalse(self.log.exists())

    def test_present_tessl_runs_update_in_project(self) -> None:
        self.stub_tessl(0)
        result = self.run_hook()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "stub update output\n")
        self.assertEqual(result.stderr, "stub update diagnostic\n")
        self.assert_invocation()

    def test_update_failure_preserves_status_and_reports_recovery(self) -> None:
        self.stub_tessl(23)
        result = self.run_hook()
        self.assertEqual(result.returncode, 23)
        self.assertEqual(result.stdout, "stub update output\n")
        self.assertTrue(result.stderr.startswith("stub update diagnostic\n"))
        self.assertIn("Tessl update failed (exit 23)", result.stderr)
        self.assertIn('rerun "tessl update --yes" in this project', result.stderr)
        self.assertNotIn("skipped", result.stderr)
        self.assert_invocation()

    def test_sourcing_does_not_run_or_report_an_update(self) -> None:
        for status in (None, 0, 23):
            with self.subTest(tessl_status=status):
                if status is not None:
                    self.stub_tessl(status)
                result = subprocess.run(
                    [str(BASH), "-c", 'source "$1"; printf "sourced\\n"',
                     "hook-source-test", str(HOOK)],
                    cwd=self.project, env=self.env,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "sourced\n")
                self.assertEqual(result.stderr, "")
                self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
