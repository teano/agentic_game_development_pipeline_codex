#!/usr/bin/env python3
"""Grade external Agentic GameDev semantic-eval responses without invoking an LLM.

Candidate JSON uses ``{"schema_version": 1, "responses": [...]}``. JSONL uses
one response object per non-empty line and includes ``schema_version`` on each
line. Every response contains: case_id, activation, current_action,
completion_token, next_action, forbidden_actions, attempted_actions,
references_read, stop_result, and authority_result.
``references_read`` contains repository skill-reference paths only; omit the
activated SKILL.md and ordinary project/source artifacts. Requirements interview
responses also contain ``requirements_round`` with the observed round shape.

Examples:
  python scripts/grade_semantic_forward_eval.py --candidate candidate.json
  python scripts/grade_semantic_forward_eval.py --candidate response.jsonl \
      --case stage_to_stage_execution_prohibited
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = SCRIPT_ROOT / "tests" / "semantic_forward_eval_cases.v1.json"
CANDIDATE_SCHEMA_VERSION = 1
CANDIDATE_FIELDS = {
    "case_id",
    "activation",
    "current_action",
    "completion_token",
    "next_action",
    "forbidden_actions",
    "attempted_actions",
    "references_read",
    "stop_result",
    "authority_result",
}
OPTIONAL_CANDIDATE_FIELDS = {"requirements_round"}
REQUIREMENTS_ROUND_FIELDS = {
    "question_count",
    "related_group",
    "options_count",
    "options_grounded",
    "proposals_not_confirmed",
    "preserves_partial_answers",
}
LIST_FIELDS = {
    "activation",
    "forbidden_actions",
    "attempted_actions",
    "references_read",
}


class GradeInputError(ValueError):
    """Raised when the corpus or external candidate format is invalid."""


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GradeInputError(f"Cannot read {label} JSON {path}: {exc}") from exc


def load_corpus(path: Path) -> dict[str, Any]:
    value = read_json(path, "corpus")
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise GradeInputError("Corpus must be an object with a cases array")
    if value.get("candidate_schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise GradeInputError(
            "Corpus candidate_schema_version does not match this grader"
        )
    case_ids = [case.get("id") for case in value["cases"] if isinstance(case, dict)]
    if len(case_ids) != len(value["cases"]) or any(not item for item in case_ids):
        raise GradeInputError("Every corpus case must be an object with a non-empty id")
    if len(case_ids) != len(set(case_ids)):
        raise GradeInputError("Corpus case ids must be unique")
    return value


def validate_candidate_response(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GradeInputError(f"{label} must be a JSON object")
    response = dict(value)
    response_version = response.pop("schema_version", CANDIDATE_SCHEMA_VERSION)
    if response_version != CANDIDATE_SCHEMA_VERSION:
        raise GradeInputError(
            f"{label} schema_version must be {CANDIDATE_SCHEMA_VERSION}"
        )
    missing = sorted(CANDIDATE_FIELDS - set(response))
    extra = sorted(set(response) - CANDIDATE_FIELDS - OPTIONAL_CANDIDATE_FIELDS)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("unexpected=" + ",".join(extra))
        raise GradeInputError(f"{label} has an invalid field set: " + "; ".join(details))
    if not isinstance(response["case_id"], str) or not response["case_id"]:
        raise GradeInputError(f"{label}.case_id must be a non-empty string")
    for field in LIST_FIELDS:
        values = response[field]
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item for item in values
        ):
            raise GradeInputError(f"{label}.{field} must be an array of non-empty strings")
        if len(values) != len(set(values)):
            raise GradeInputError(f"{label}.{field} must not contain duplicates")
    for field in (
        "current_action",
        "completion_token",
        "next_action",
        "stop_result",
        "authority_result",
    ):
        if response[field] is not None and not isinstance(response[field], str):
            raise GradeInputError(f"{label}.{field} must be a string or null")
    requirements_round = response.get("requirements_round")
    if requirements_round is not None:
        if not isinstance(requirements_round, dict) or set(requirements_round) != REQUIREMENTS_ROUND_FIELDS:
            raise GradeInputError(
                f"{label}.requirements_round must use the exact interview-round fields"
            )
        for field in ("question_count", "options_count"):
            if isinstance(requirements_round[field], bool) or not isinstance(
                requirements_round[field], int
            ):
                raise GradeInputError(
                    f"{label}.requirements_round.{field} must be an integer"
                )
        for field in REQUIREMENTS_ROUND_FIELDS - {"question_count", "options_count"}:
            if not isinstance(requirements_round[field], bool):
                raise GradeInputError(
                    f"{label}.requirements_round.{field} must be boolean"
                )
    return response


def load_candidate(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".jsonl":
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise GradeInputError(f"Cannot read candidate JSONL {path}: {exc}") from exc
        responses: list[dict[str, Any]] = []
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GradeInputError(
                    f"Candidate JSONL line {line_number} is invalid: {exc}"
                ) from exc
            if not isinstance(value, dict) or "schema_version" not in value:
                raise GradeInputError(
                    f"Candidate JSONL line {line_number} must include schema_version"
                )
            responses.append(
                validate_candidate_response(value, f"candidate line {line_number}")
            )
    else:
        value = read_json(path, "candidate")
        if isinstance(value, dict) and "responses" in value:
            if value.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
                raise GradeInputError(
                    f"Candidate wrapper schema_version must be {CANDIDATE_SCHEMA_VERSION}"
                )
            if set(value) != {"schema_version", "responses"}:
                raise GradeInputError(
                    "Candidate wrapper accepts only schema_version and responses"
                )
            raw_responses = value["responses"]
        elif isinstance(value, list):
            raw_responses = value
        elif isinstance(value, dict):
            if "schema_version" not in value:
                raise GradeInputError("Single candidate response must include schema_version")
            raw_responses = [value]
        else:
            raise GradeInputError(
                "Candidate JSON must be a wrapper object, response object, or response array"
            )
        if not isinstance(raw_responses, list):
            raise GradeInputError("Candidate responses must be an array")
        responses = [
            validate_candidate_response(item, f"candidate response {index}")
            for index, item in enumerate(raw_responses, 1)
        ]
    ids = [response["case_id"] for response in responses]
    if len(ids) != len(set(ids)):
        raise GradeInputError("Candidate case_id values must be unique")
    return responses


def scalar_dimension(expected: Any, actual: Any) -> dict[str, Any]:
    return {"pass": expected == actual, "expected": expected, "actual": actual}


def set_dimension(expected: list[str], actual: list[str]) -> dict[str, Any]:
    expected_set = set(expected)
    actual_set = set(actual)
    return {
        "pass": expected_set == actual_set,
        "expected": expected,
        "actual": actual,
        "missing": sorted(expected_set - actual_set),
        "unexpected": sorted(actual_set - expected_set),
    }


def requirements_round_dimension(expected: Any, actual: Any) -> dict[str, Any]:
    if expected is None:
        return scalar_dimension(None, actual)
    if not isinstance(actual, dict):
        return {"pass": False, "expected": expected, "actual": actual}
    questions = expected["question_count"]
    checks = {
        "question_count": questions["minimum"] <= actual["question_count"] <= questions["maximum"],
        "related_group": actual["related_group"] is True,
        "options_count": actual["options_count"] in expected["options_count"]["allowed"],
        "options_grounded": actual["options_count"] == 0 or actual["options_grounded"] is True,
        "proposals_not_confirmed": actual["proposals_not_confirmed"] is True,
        "preserves_partial_answers": actual["preserves_partial_answers"] is True,
    }
    return {
        "pass": all(checks.values()),
        "expected": expected,
        "actual": actual,
        "checks": checks,
    }


def grade_response(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    forbidden_attempts = sorted(
        set(expected["forbidden_actions"]) & set(response["attempted_actions"])
    )
    dimensions = {
        "activation": set_dimension(expected["activation"], response["activation"]),
        "current_action": scalar_dimension(
            expected["allowed_action"], response["current_action"]
        ),
        "completion_token": scalar_dimension(
            expected["completion_token"], response["completion_token"]
        ),
        "next_action": scalar_dimension(
            expected["next_action"], response["next_action"]
        ),
        "forbidden_actions": set_dimension(
            expected["forbidden_actions"], response["forbidden_actions"]
        ),
        "attempted_actions": {
            "pass": not forbidden_attempts,
            "expected": "no oracle-forbidden action attempted",
            "actual": response["attempted_actions"],
            "forbidden_attempts": forbidden_attempts,
        },
        "references_read": set_dimension(
            expected["required_references"], response["references_read"]
        ),
        "stop_result": scalar_dimension(
            expected["stop_result"], response["stop_result"]
        ),
        "authority_result": scalar_dimension(
            expected["authority_result"], response["authority_result"]
        ),
        "requirements_round": requirements_round_dimension(
            expected.get("requirements_round"), response.get("requirements_round")
        ),
    }
    return {
        "case_id": case["id"],
        "pass": all(item["pass"] for item in dimensions.values()),
        "dimensions": dimensions,
    }


def grade_candidates(
    corpus: dict[str, Any],
    responses: list[dict[str, Any]],
    selected_case_ids: list[str] | None = None,
) -> dict[str, Any]:
    case_map = {case["id"]: case for case in corpus["cases"]}
    if selected_case_ids:
        unknown_selected = sorted(set(selected_case_ids) - set(case_map))
        if unknown_selected:
            raise GradeInputError(
                "Unknown selected case ids: " + ", ".join(unknown_selected)
            )
        target_ids = list(dict.fromkeys(selected_case_ids))
    else:
        target_ids = list(case_map)
    response_map = {response["case_id"]: response for response in responses}
    missing_cases = sorted(set(target_ids) - set(response_map))
    unexpected_cases = sorted(set(response_map) - set(target_ids))
    results = [
        grade_response(case_map[case_id], response_map[case_id])
        for case_id in target_ids
        if case_id in response_map
    ]
    passed_cases = sum(item["pass"] for item in results)
    failed_cases = len(results) - passed_cases + len(missing_cases) + len(unexpected_cases)
    passed = failed_cases == 0 and len(results) == len(target_ids)
    return {
        "grade_schema_version": 1,
        "corpus_schema_version": corpus["schema_version"],
        "candidate_schema_version": CANDIDATE_SCHEMA_VERSION,
        "results": results,
        "summary": {
            "pass": passed,
            "target_cases": len(target_ids),
            "graded_cases": len(results),
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "missing_cases": missing_cases,
            "unexpected_cases": unexpected_cases,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--candidate", type=Path, required=True, help="Candidate JSON or JSONL file"
    )
    parser.add_argument(
        "--corpus", type=Path, default=DEFAULT_CORPUS, help="Versioned oracle corpus"
    )
    parser.add_argument(
        "--case",
        dest="case_ids",
        action="append",
        help="Grade only this case id; may be repeated",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        corpus = load_corpus(args.corpus.resolve())
        responses = load_candidate(args.candidate.resolve())
        report = grade_candidates(corpus, responses, args.case_ids)
    except GradeInputError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
