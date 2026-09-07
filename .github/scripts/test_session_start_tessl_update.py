"""Exercise the optional Tessl hook without invoking Tessl or personal state.

Every case runs twice: against the hook as committed, and against the copy an
ACR realization materializes into an agent's hook directory. Materialization
copies the bytes and the mode, so a status the source emits and the copy does
not would be a path assumption in the hook, not a realization bug.

The assertions cover the process contract — exit status, streams, and a JSON
envelope that decodes to the documented payload. A decoded payload is not proof
that a live agent displayed the message; that acceptance is a session-level
check, outside a deterministic suite.
"""

from pathlib import Path
import json
import os
import stat
import subprocess
import tempfile
import unittest


HOOK = Path(__file__).resolve().parents[2] / "hooks/session-start-tessl-update.sh"
BASH = Path("/bin/bash")
MARKER = "Session-start status — "
# Where an ACR realization writes this hook for Claude Code, mirrored here so the
# materialized copy under test sits at the path an agent actually runs.
MATERIALIZED = (
    ".claude/hooks/acr__jbaruch__ffa-acr-dogfood__session-start-tessl-update"
    "/session-start-tessl-update.sh"
)


def ansi_c_quote(text: str) -> str:
    """Quote text for Bash byte for byte, so a stub emits exactly these bytes."""
    return "$'" + "".join(f"\\x{byte:02x}" for byte in text.encode()) + "'"


class SessionStartTesslUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = tempfile.TemporaryDirectory(prefix="ffa-hook-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # The hook's env shebang can find bash, but never an installed Tessl.
        # Nothing else is on PATH: the hook runs at session start, so it may
        # not reach for a command that a thin environment could be missing.
        (self.bin / "bash").symlink_to(BASH)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.log = self.root / "invocation.log"
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(self.root),
            "HOOK_TEST_LOG": str(self.log),
        }
        self.materialized = self.root / MATERIALIZED
        self.materialized.parent.mkdir(parents=True)
        self.materialized.write_bytes(HOOK.read_bytes())
        self.materialized.chmod(HOOK.stat().st_mode & 0o7777)

    def hooks(self) -> list[tuple[str, Path]]:
        return [("source", HOOK), ("materialized", self.materialized)]

    def stub_tessl(self, status: int, out: str = "stub update output\n") -> None:
        stub = self.bin / "tessl"
        stub.write_text(
            "#!/bin/bash\nset -euo pipefail\n"
            'printf "%s\\n" "$PWD" "$#" "$@" >> "$HOOK_TEST_LOG"\n'
            f"printf '%s' {ansi_c_quote(out)}\n"
            'printf "stub update diagnostic\\n" >&2\n'
            f"exit {status}\n"
        )
        stub.chmod(0o755)

    def run_hook(self, hook: Path, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(hook)], cwd=self.project, env={**self.env, **env},
            capture_output=True, text=True, check=False,
        )

    def reset_log(self) -> None:
        if self.log.exists():
            self.log.unlink()

    def assert_invocation(self) -> None:
        self.assertEqual(
            self.log.read_text().splitlines(),
            [str(self.project), "2", "update", "--yes"],
        )

    def decode_payload(self, stdout: str, cursor: bool = False) -> str:
        """Return the context text of the one JSON object the hook printed."""
        self.assertTrue(stdout.endswith("\n"), stdout)
        envelope = json.loads(stdout)
        if cursor:
            self.assertEqual(list(envelope), ["additional_context"])
            return envelope["additional_context"]
        self.assertEqual(list(envelope), ["hookSpecificOutput"])
        specific = envelope["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SessionStart")
        return specific["additionalContext"]

    def test_hook_is_a_directly_executable_file(self) -> None:
        mode = HOOK.stat().st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o755)
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_missing_tessl_skips_and_reports_the_skip(self) -> None:
        for label, hook in self.hooks():
            with self.subTest(hook=label):
                result = self.run_hook(hook)
                self.assertEqual(result.returncode, 0)
                self.assertIn("Tessl update skipped", result.stderr)
                self.assertIn("optional Tessl CLI not found on PATH", result.stderr)
                self.assertIn("Install Tessl and add it to PATH", result.stderr)
                payload = self.decode_payload(result.stdout)
                self.assertEqual(
                    payload,
                    MARKER + "Tessl update skipped: optional Tessl CLI not found"
                    " on PATH. Install Tessl and add it to PATH to enable updates.",
                )
                self.assertFalse(self.log.exists())

    def test_present_tessl_runs_update_in_project_and_reports_its_output(self) -> None:
        self.stub_tessl(0)
        for label, hook in self.hooks():
            with self.subTest(hook=label):
                self.reset_log()
                result = self.run_hook(hook)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, "stub update diagnostic\n")
                payload = self.decode_payload(result.stdout)
                self.assertEqual(
                    payload,
                    MARKER + "Tessl update completed.\nstub update output",
                )
                self.assert_invocation()

    def test_silent_successful_update_reports_nothing(self) -> None:
        self.stub_tessl(0, out="")
        for label, hook in self.hooks():
            with self.subTest(hook=label):
                self.reset_log()
                result = self.run_hook(hook)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "stub update diagnostic\n")
                self.assert_invocation()

    def test_update_failure_preserves_status_and_reports_recovery(self) -> None:
        self.stub_tessl(23)
        for label, hook in self.hooks():
            with self.subTest(hook=label):
                self.reset_log()
                result = self.run_hook(hook)
                self.assertEqual(result.returncode, 23)
                self.assertEqual(
                    result.stderr.splitlines(),
                    [
                        "stub update diagnostic",
                        "stub update output",
                        'Tessl update failed (exit 23). Resolve the error above'
                        ' and rerun "tessl update --yes" in this project.',
                    ],
                )
                payload = self.decode_payload(result.stdout)
                self.assertEqual(
                    payload,
                    MARKER + "Tessl update failed (exit 23).\nstub update output\n"
                    "Resolve the error and rerun `tessl update --yes` in this project.",
                )
                self.assertNotIn("skipped", payload)
                self.assert_invocation()

    def test_quotes_newlines_and_control_bytes_keep_the_envelope_parseable(self) -> None:
        noisy = 'say "hi"\\ then\ttab\nsecond \x1b[31mred\x1b[0m line\r\ntrailing\n'
        self.stub_tessl(0, out=noisy)
        for label, hook in self.hooks():
            with self.subTest(hook=label):
                self.reset_log()
                result = self.run_hook(hook)
                self.assertEqual(result.returncode, 0)
                payload = self.decode_payload(result.stdout)
                # Quotes, backslashes, tabs and newlines survive as themselves;
                # the terminal escapes are gone and took nothing else with them.
                self.assertEqual(
                    payload,
                    MARKER + "Tessl update completed.\n"
                    'say "hi"\\ then\ttab\nsecond [31mred[0m line\r\ntrailing',
                )
                self.assert_invocation()

    def test_cursor_receives_its_own_envelope_shape(self) -> None:
        self.stub_tessl(0)
        for label, hook in self.hooks():
            with self.subTest(hook=label):
                self.reset_log()
                result = self.run_hook(hook, CURSOR_VERSION="1.2.3")
                self.assertEqual(result.returncode, 0)
                payload = self.decode_payload(result.stdout, cursor=True)
                self.assertEqual(
                    payload,
                    MARKER + "Tessl update completed.\nstub update output",
                )
                self.assert_invocation()

    def test_sourcing_does_not_run_or_report_an_update(self) -> None:
        for label, hook in self.hooks():
            for status in (None, 0, 23):
                with self.subTest(hook=label, tessl_status=status):
                    self.reset_log()
                    if status is not None:
                        self.stub_tessl(status)
                    result = subprocess.run(
                        [str(BASH), "-c", 'source "$1"; printf "sourced\\n"',
                         "hook-source-test", str(hook)],
                        cwd=self.project, env=self.env,
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "sourced\n")
                    self.assertEqual(result.stderr, "")
                    self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
