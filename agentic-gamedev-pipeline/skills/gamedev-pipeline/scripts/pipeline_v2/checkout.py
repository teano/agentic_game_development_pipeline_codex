"""Controller-owned Git candidate trees and path confinement."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .model import PipelineError, digest, is_git_oid, normalize_literal_path, normalize_rule

CHECKOUT_MODEL = "git-tree-v1"
CONTROL_PATHS = (
    ".agentic-pipeline",
    ".agentic-pipeline-v2",
)
REPOSITORY_POLICY_NAMES = (".gitignore", ".gitattributes", ".gitmodules")


def safe_path(root: Path, supplied: str | Path | None, label: str, *, strict: bool = False) -> Path:
    """Confine a lexical path and reject every symlink/junction/reparse component."""
    root = Path(os.path.abspath(root))
    candidate = root if supplied is None else Path(supplied)
    candidate = Path(os.path.abspath(candidate if candidate.is_absolute() else root / candidate))
    try:
        if os.path.commonpath((os.path.normcase(root), os.path.normcase(candidate))) != os.path.normcase(root):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise PipelineError(f"{label} escapes the project root") from exc
    components = list(reversed(root.parents[:-1])) + [root]
    if candidate != root:
        current = root
        for part in candidate.relative_to(root).parts:
            current /= part
            components.append(current)
    for component in components:
        try:
            stat = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PipelineError(f"cannot inspect {label}: {exc}") from exc
        if component.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & 0x400):
            raise PipelineError(f"{label} crosses a symlink/junction/reparse component: {component}")
    if strict and not candidate.exists():
        raise PipelineError(f"{label} does not exist: {candidate}")
    return candidate


def canonical_project_root(supplied: str | Path) -> Path:
    """Return the existing physical root spelling after rejecting reparse traversal."""
    lexical = Path(supplied)
    if not lexical.is_absolute():
        raise PipelineError("project root must be absolute")
    lexical = safe_path(lexical, None, "project root", strict=True)
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"cannot resolve project root: {exc}") from exc
    return safe_path(resolved, None, "project root", strict=True)


def path_identity(value: str) -> str:
    """Compare paths using the host filesystem's case rules."""
    native = value.replace("/", os.sep)
    return os.path.normcase(os.path.normpath(native)).replace(os.sep, "/")


def authority_items_equal(
    left: dict[str, dict[str, str]], right: dict[str, dict[str, str]],
) -> bool:
    """Compare authority path identity and exact bytes without spelling aliases."""
    if set(left) != set(right):
        return False
    return all(
        left[name].get("sha256") == right[name].get("sha256")
        and path_identity(left[name].get("path", ""))
        == path_identity(right[name].get("path", ""))
        for name in left
    )


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _git(
    root: Path, args: list[str], *, env: dict[str, str] | None = None,
    label: str = "Git operation",
) -> bytes:
    environment = os.environ.copy()
    if env:
        environment.update(env)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
        )
    except OSError as exc:
        raise PipelineError(f"cannot run Git for {label}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        if len(detail) > 512:
            detail = detail[-512:]
        raise PipelineError(f"{label} failed: {detail or f'return code {result.returncode}'}")
    return result.stdout


def require_repository_root(root: Path) -> Path:
    """Require project_root to be the exact root of one ordinary Git worktree."""
    root = canonical_project_root(root)
    try:
        top = _git(root, ["rev-parse", "--show-toplevel"], label="Git root discovery")
        top_text = top.decode("utf-8").strip()
    except UnicodeError as exc:
        raise PipelineError("Git root is not valid UTF-8") from exc
    discovered = canonical_project_root(top_text)
    if path_identity(str(discovered)) != path_identity(str(root)):
        raise PipelineError("project root must be the exact Git worktree root")
    inside = _git(root, ["rev-parse", "--is-inside-work-tree"], label="Git worktree check")
    if inside.strip() != b"true":
        raise PipelineError("project root must be a Git worktree")
    return root


def _control_pathspecs() -> list[str]:
    result: list[str] = []
    for path in CONTROL_PATHS:
        result.extend((f":(exclude){path}", f":(exclude){path}/**"))
    return result


def _is_control_path(path: str) -> bool:
    return any(
        path == control or path.startswith(f"{control}/")
        for control in CONTROL_PATHS
    )


def _require_no_gitlinks(root: Path) -> None:
    staged = _git(
        root,
        ["ls-files", "--stage", "-z"],
        label="Git gitlink check",
    )
    if any(record.startswith(b"160000 ") for record in staged.split(b"\0") if record):
        raise PipelineError(
            "gitlinks/submodules are unsupported; remove them before fresh init"
        )


def _git_path_is_ignored(root: Path, path: str) -> bool:
    """Return whether Git excludes one existing path from candidate traversal."""
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--quiet", "--no-index", "--", path],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode in {0, 1}:
        return result.returncode == 0
    detail = result.stderr.decode("utf-8", errors="replace").strip()
    if len(detail) > 512:
        detail = detail[-512:]
    raise PipelineError(
        "Git candidate traversal check failed: "
        + (detail or f"return code {result.returncode}")
    )


def _repository_policy_files(root: Path, candidate_paths: bytes) -> list[str]:
    """Classify policy paths through the same effective candidate boundary."""
    pathspecs = [
        pathspec
        for name in REPOSITORY_POLICY_NAMES
        for pathspec in (name, f":(glob)**/{name}")
    ]
    try:
        visible = [
            item.decode("utf-8")
            for item in candidate_paths.split(b"\0")
            if item and item.rsplit(b"/", 1)[-1].decode("utf-8") in REPOSITORY_POLICY_NAMES
        ]
        ignored = [
            item.decode("utf-8")
            for item in _git(
                root,
                [
                    "ls-files", "--others", "--ignored", "--exclude-standard", "-z",
                    "--", *pathspecs, *_control_pathspecs(),
                ],
                label="Git repository-policy discovery",
            ).split(b"\0")
            if item
        ]
    except UnicodeError as exc:
        raise PipelineError("Git repository-policy paths must be valid UTF-8") from exc
    records = [path for path in visible if not _is_control_path(path)]
    for path in ignored:
        if _is_control_path(path):
            continue
        parent = path.rpartition("/")[0]
        if not parent or not _git_path_is_ignored(root, parent):
            records.append(path)
    return sorted(dict.fromkeys(records))


def head_tree_oid(root: Path) -> str:
    root = require_repository_root(root)
    try:
        value = _git(root, ["rev-parse", "HEAD^{tree}"], label="Git HEAD tree").decode("ascii").strip()
    except UnicodeError as exc:
        raise PipelineError("Git returned a malformed HEAD tree OID") from exc
    if not is_git_oid(value):
        raise PipelineError("Git returned a malformed HEAD tree OID")
    return value


def require_clean_head(root: Path) -> str:
    """Require a committed, clean versioned baseline; ignored files stay invisible."""
    root = require_repository_root(root)
    _require_no_gitlinks(root)
    status = _git(
        root,
        [
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
            ".", *_control_pathspecs(),
        ],
        label="clean Git baseline check",
    )
    if status:
        raise PipelineError(
            "init requires a clean Git checkout with no tracked or non-ignored changes"
        )
    raw_head = head_tree_oid(root)
    head = _projected_tree_oid(root, raw_head, include_worktree=False)
    live = _projected_tree_oid(root, raw_head, include_worktree=True)
    if live != head:
        policy = repository_policy_changed(root, head, live)
        detail = f": {', '.join(policy)}" if policy else ""
        raise PipelineError(
            "init requires repository policy files to be committed and match HEAD"
            + detail
        )
    return head


def _projected_tree_oid(root: Path, base_tree_oid: str, *, include_worktree: bool) -> str:
    """Project a Git tree through the controller-path boundary in a temporary index."""
    with tempfile.TemporaryDirectory(prefix="agentic-pipeline-git-index-") as temporary:
        index = Path(temporary) / "index"
        index_env = {"GIT_INDEX_FILE": str(index)}
        _git(
            root, ["read-tree", base_tree_oid], env=index_env,
            label="temporary Git index initialization",
        )
        _git(
            root,
            ["--literal-pathspecs", "rm", "-r", "--cached", "--ignore-unmatch", "--", *CONTROL_PATHS],
            env=index_env,
            label="controller path baseline exclusion",
        )
        if include_worktree:
            candidate_paths = _git(
                root,
                [
                    "ls-files", "--cached", "--others", "--exclude-standard", "-z",
                    "--", ".", *_control_pathspecs(),
                ],
                env=index_env,
                label="Git candidate path discovery",
            )
            pathspec_file = Path(temporary) / "candidate-paths"
            pathspec_file.write_bytes(candidate_paths)
            _git(
                root,
                [
                    "--literal-pathspecs", "add", "-A",
                    f"--pathspec-from-file={pathspec_file}", "--pathspec-file-nul",
                ],
                env=index_env,
                label="Git candidate staging",
            )
            _git(
                root,
                ["--literal-pathspecs", "rm", "-r", "--cached", "--ignore-unmatch", "--", *CONTROL_PATHS],
                env=index_env,
                label="controller path exclusion",
            )
            policy_files = _repository_policy_files(root, candidate_paths)
            if policy_files:
                _git(
                    root,
                    ["--literal-pathspecs", "add", "-f", "--", *policy_files],
                    env=index_env,
                    label="Git repository-policy staging",
                )
        try:
            value = _git(root, ["write-tree"], env=index_env, label="Git projected tree").decode("ascii").strip()
        except UnicodeError as exc:
            raise PipelineError("Git returned a malformed projected tree OID") from exc
    if not is_git_oid(value):
        raise PipelineError("Git returned a malformed projected tree OID")
    return value


def candidate_tree_oid(root: Path) -> str:
    """Write the live tracked plus non-ignored worktree into an external temporary index."""
    root = require_repository_root(root)
    return _projected_tree_oid(root, head_tree_oid(root), include_worktree=True)


def changed_paths(root: Path, base_tree_oid: str, candidate_tree_oid_value: str) -> list[str]:
    """Return the exact sorted path delta between two Git trees."""
    if not is_git_oid(base_tree_oid) or not is_git_oid(candidate_tree_oid_value):
        raise PipelineError("Git tree comparison requires valid tree OIDs")
    raw = _git(
        require_repository_root(root),
        [
            "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "-z",
            base_tree_oid, candidate_tree_oid_value,
        ],
        label="Git candidate diff",
    )
    try:
        paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    except UnicodeError as exc:
        raise PipelineError("Git candidate paths must be valid UTF-8") from exc
    normalized = [normalize_literal_path(path) for path in paths]
    return sorted(dict.fromkeys(normalized))


def repository_policy_changed(root: Path, base_tree_oid: str, candidate_tree_oid_value: str) -> list[str]:
    return [
        path for path in changed_paths(root, base_tree_oid, candidate_tree_oid_value)
        if path.rsplit("/", 1)[-1] in REPOSITORY_POLICY_NAMES
    ]


def matches(path: str, rule: str) -> bool:
    path = normalize_literal_path(path)
    rule = normalize_rule(rule)
    if rule == "**":
        return True
    if rule.endswith("/**"):
        prefix = rule[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == rule


def violations(paths: list[str], write_rules: list[str]) -> list[str]:
    return [path for path in paths if not any(matches(path, rule) for rule in write_rules)]


def authority_items(root: Path, paths: dict[str, str]) -> dict[str, dict[str, str]]:
    root = require_repository_root(root)
    items = {}
    for name, relative in paths.items():
        literal = normalize_literal_path(relative)
        pathspec = f":({'icase,' if os.name == 'nt' else ''}literal){literal}"
        tracked = _git(
            root,
            ["ls-files", "-z", "--error-unmatch", "--", pathspec],
            label=f"tracked authority path {literal}",
        )
        try:
            tracked_paths = [
                normalize_literal_path(item.decode("utf-8"))
                for item in tracked.split(b"\0") if item
            ]
        except UnicodeError as exc:
            raise PipelineError("tracked authority paths must be valid UTF-8") from exc
        if (
            len(tracked_paths) != 1
            or path_identity(tracked_paths[0]) != path_identity(literal)
        ):
            raise PipelineError(f"authority path must be Git-tracked: {literal}")
        canonical = tracked_paths[0]
        path = safe_path(root, canonical, "authority path", strict=True)
        if not path.is_file():
            raise PipelineError(f"authority path is not a file: {canonical}")
        items[name] = {"path": canonical, "sha256": file_sha256(path)}
    return items


def verify_authority(root: Path, authority: dict[str, Any]) -> None:
    actual = authority_items(root, {name: item["path"] for name, item in authority["items"].items()})
    if not authority_items_equal(actual, authority["items"]):
        raise PipelineError(
            "authority bytes changed; run status and execute its init reconfiguration"
        )


def pipeline_runtime_digest() -> str:
    """Hash one fixed production manifest; never discover runtime files by walking."""
    skill_root = Path(__file__).resolve().parents[2]
    bundle_root = skill_root.parents[1]
    skills_root = skill_root.parent
    runtime_dir = Path(__file__).resolve().parent
    manifest = (
        (skill_root / "SKILL.md", "skill/SKILL.md"),
        (skill_root / "agents" / "openai.yaml", "skill/agents/openai.yaml"),
        (skill_root / "references" / "pipeline-protocol.md", "skill/references/pipeline-protocol.md"),
        (skill_root / "references" / "semantic-write-packet.md", "skill/references/semantic-write-packet.md"),
        (skill_root / "references" / "stage-handoff-invariant.md", "skill/references/stage-handoff-invariant.md"),
        (skill_root / "scripts" / "pipeline_state.py", "skill/scripts/pipeline_state.py"),
        (skills_root / "gamedev-engineer" / "SKILL.md", "delegates/engineering/SKILL.md"),
        (skills_root / "gamedev-review" / "SKILL.md", "delegates/review/SKILL.md"),
        (skills_root / "gamedev-review" / "references" / "review-output-contract.md", "delegates/review/review-output-contract.md"),
        (skills_root / "gamedev-qa" / "SKILL.md", "delegates/qa/SKILL.md"),
        (skills_root / "gamedev-qa" / "references" / "qa-output-contract.md", "delegates/qa/qa-output-contract.md"),
        (skills_root / "gamedev-documentation-finisher" / "SKILL.md", "delegates/docs/SKILL.md"),
        (skills_root / "gamedev-documentation-finisher" / "references" / "documentation-contract.md", "delegates/docs/documentation-contract.md"),
        (runtime_dir / "__init__.py", "pipeline_v2/__init__.py"),
        (runtime_dir / "checkout.py", "pipeline_v2/checkout.py"),
        (runtime_dir / "cli.py", "pipeline_v2/cli.py"),
        (runtime_dir / "legacy_gen53.py", "pipeline_v2/legacy_gen53.py"),
        (runtime_dir / "model.py", "pipeline_v2/model.py"),
        (runtime_dir / "process_tree.py", "pipeline_v2/process_tree.py"),
        (runtime_dir / "reducer.py", "pipeline_v2/reducer.py"),
        (runtime_dir / "runner.py", "pipeline_v2/runner.py"),
        (runtime_dir / "transaction.py", "pipeline_v2/transaction.py"),
        (bundle_root / "scripts" / "development_plan_contract.py", "scripts/development_plan_contract.py"),
    )
    records = []
    for path, label in manifest:
        if not path.is_file():
            raise PipelineError(f"pipeline runtime manifest file is missing: {label}")
        records.append({"path": label, "sha256": file_sha256(path)})
    return digest(records)
