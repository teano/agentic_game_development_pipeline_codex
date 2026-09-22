from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.model import PipelineError
from pipeline_v2.runtime_pin import pin_runtime


class RuntimePinTests(unittest.TestCase):
    def test_pin_returns_runnable_separate_argv_and_preserves_overwrite_and_tamper_guards(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "verified runtime with spaces"
            record = pin_runtime(destination)
            launcher = destination / "skills/gamedev-pipeline/scripts/pipeline_state.py"

            self.assertEqual([sys.executable, str(launcher.resolve())], record["launcher_argv"])
            self.assertEqual(str(launcher.resolve()), record["launcher"])
            self.assertEqual(record, json.loads((destination / "runtime-pin.json").read_text(encoding="utf-8")))
            invoked = subprocess.run([*record["launcher_argv"], "--help"], text=True,
                                     capture_output=True, check=False)
            self.assertEqual(0, invoked.returncode, invoked.stderr)
            self.assertIn("pipeline-v2", invoked.stdout)

            with self.assertRaisesRegex(PipelineError, "cannot be overwritten"):
                pin_runtime(destination)

            runtime = destination / "skills/gamedev-pipeline/scripts/pipeline_v2"
            for target in (runtime / "model.py", destination / "skills/gamedev-pipeline/references/control-return.md"):
                with self.subTest(target=target.name):
                    original = target.read_bytes()
                    try:
                        target.write_bytes(original + b"\n# tampered after pin\n")
                        tamper_probe = subprocess.run([
                            record["launcher_argv"][0], "-B", "-c",
                            "from pipeline_v2.checkout import pipeline_runtime_digest;pipeline_runtime_digest()",
                        ], cwd=launcher.parent, text=True, capture_output=True, check=False)
                        self.assertNotEqual(0, tamper_probe.returncode)
                        self.assertIn("pinned runtime changed", tamper_probe.stderr)
                    finally:
                        target.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
