"""Raw sinks preserve process bytes without changing bounded diagnostic tails."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest

from pipeline_v2 import process_tree


class ProcessCaptureTests(unittest.TestCase):
    def test_reader_marks_failed_sink_without_losing_drain_or_stream_digest(self):
        class BrokenSink:
            def write(self, _):
                raise OSError("disk write failed")
        raw = b"original" * 20000
        reader = process_tree._DigestReader(io.BytesIO(raw), sink=BrokenSink(), tail_limit=8)
        reader.start()
        reader.join()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), reader.hexdigest())
        self.assertEqual("disk write failed", reader.capture_error)

    @unittest.skipUnless(os.name == "nt", "Windows process-tree integration")
    def test_exact_binary_streams_and_timeout_close_sinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, error = root / "stdout.bin", root / "stderr.bin"
            result = process_tree.run_process_tree([sys.executable, "-c",
                "import os; os.write(1,b'\\x00\\xff\\r\\n'*40000); os.write(2,b'original stderr\\r\\n')"],
                cwd=root, env=os.environ.copy(), timeout=10, stdout_path=output, stderr_path=error)
            self.assertEqual(0, result.returncode)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), result.stdout_sha256)
            self.assertEqual(hashlib.sha256(error.read_bytes()).hexdigest(), result.stderr_raw_sha256)
            self.assertEqual(result.stderr_raw_sha256, result.stderr_sha256)
            self.assertGreater(output.stat().st_size, len(result.stdout_tail))
            output.unlink(); error.unlink()
            result = process_tree.run_process_tree([sys.executable, "-c", "import os,time; os.write(2,b'actual error'); time.sleep(10)"],
                cwd=root, env=os.environ.copy(), timeout=0.2, stdout_path=output, stderr_path=error)
            self.assertEqual(124, result.returncode)
            self.assertEqual(b"actual error", error.read_bytes())
            self.assertEqual(hashlib.sha256(error.read_bytes()).hexdigest(), result.stderr_raw_sha256)
            self.assertIn(b"timed out", result.stderr_tail)
            output.unlink(); error.unlink()  # Windows fails if handles leaked.


if __name__ == "__main__":
    unittest.main()
