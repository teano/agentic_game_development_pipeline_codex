# Research bundle contract

The assigned bundle is one closed object with exactly `schema_version: 1`, `brief`, and `result`.

The brief has non-empty `brief_id`, `question`, `slice_id`, `base_revision`, `stop_condition`, and `output_path`; positive integer `max_files`; and non-empty string arrays `requirement_ids`, `seed_paths`, `allowed_paths`, `allowed_symbols`, `exclusions`, and `requested_evidence`. `requirement_ids` is duplicate-free, contains at least one active-slice `PRD-REQ-*` and one active-slice `PRD-AC-*`, and contains nothing else. Seeds exist and remain inside one allowed path.

The result has exact non-empty `brief_id`, `researcher_id`, `base_revision`, and `brief_sha256`; `status: complete|limit_reached`; and string arrays `inspected_paths`, `inspected_symbols`, `owners_contracts_precedents`, `lifecycle_integration_risks`, `minimal_edit_reuse_points`, `unresolved_questions`, and `out_of_brief_pointers`.

Inspected paths exist inside the allowlist and do not exceed `max_files`; inspected symbols are allowed; IDs/revision match the current brief/controller values and `brief_sha256` is the canonical-JSON digest of `brief`. Persist only this result bundle. After controller acceptance its exact path/SHA and `brief_id` selector are mandatory Engineer capsule evidence. `RESEARCH_COMPLETE` is a returned stage token, not persisted controller state.
