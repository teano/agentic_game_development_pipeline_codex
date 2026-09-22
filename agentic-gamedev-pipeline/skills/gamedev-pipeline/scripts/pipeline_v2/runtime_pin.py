"""Install a new immutable runtime bundle, never copy a product checkout."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from .checkout import pipeline_runtime_digest
from .model import PipelineError


def pin_runtime(destination: Path) -> dict:
    source = Path(__file__).resolve().parents[4]
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise PipelineError("runtime pin destination already exists; pinned bundles cannot be overwritten")
    if destination == source or source in destination.parents:
        raise PipelineError("runtime pin must be outside the source bundle")
    expected = pipeline_runtime_digest()
    # Reject links rather than accidentally importing bytes outside the bundle.
    files = [path for path in source.rglob("*") if ".git" not in path.parts and "__pycache__" not in path.parts]
    if any(path.is_symlink() or getattr(path, "is_junction", lambda: False)() for path in files):
        raise PipelineError("runtime pin cannot traverse linked bundle paths")
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        if path.is_file() and path.suffix != ".pyc":
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    scripts = destination / "skills/gamedev-pipeline/scripts"
    probe = subprocess.run([sys.executable, "-B", "-c",
                            "from pipeline_v2.checkout import pipeline_runtime_digest;print(pipeline_runtime_digest())"],
                           cwd=scripts, text=True, capture_output=True, check=False)
    if probe.returncode or probe.stdout.strip() != expected or pipeline_runtime_digest() != expected:
        raise PipelineError("runtime pin verification failed; do not use the incomplete destination")
    launcher = str((scripts / "pipeline_state.py").resolve())
    record = {"format": "pipeline-runtime-pin-v1", "runtime_digest": expected,
              "source": str(source), "launcher": launcher,
              "launcher_argv": [sys.executable, launcher]}
    (destination / "runtime-pin.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record
