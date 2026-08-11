# История изменений

Значимые изменения Agentic GameDev Pipeline фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии следуют [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.4.0] - 2026-08-11

### Добавлено

- Явно запускаемые Decision Recorder, Coverage Steward и Documentation Finisher с append-only ledger, schema-2 coverage и раздельными normative/derived documentation gates.
- Schema-9 runtime state с раздельными implementation/feature-verification состояниями, эксклюзивными write leases, bounded context capsules и controller-generated schema-2 handoff.
- Отдельные coverage-planning/finalization и post-QA derived-documentation фазы; manual QA может оставаться pending после завершённой инженерной реализации.

### Изменено

- Engineer возвращает только проверяемую семантическую аннотацию фактического diff; контроллер атомарно вычисляет revisions, change/diff manifests и handoff, а затем освобождает lease.
- Development-plan controller требует decision ledger, Decision/Coverage/Documentation contracts и пять числовых context-capsule limits.
- Runtime state schema доработана до v9; state ранних схем отклоняется с требованием явной повторной инициализации.

### Исправлено

- Все status/gate/readiness загрузки повторно хешируют текущий revision inventory; единственное контролируемое исключение действует внутри завершения точного активного writer lease.
- `scope_expansion_hold` атомарно сохраняет candidate snapshot/diff/history, отзывает старую lease после approved rebaseline и требует свежие capsule/lease для завершения сохранённого кандидата или безопасного rollback.
- Evidence recovery атомарно переносит machine checks, schema-2 coverage aggregate, implementation credit и Review identities на новую support/evidence revision; готовность требует свежие recovery Review и QA.
- Coverage continuity, decision authorities, component credits и write scopes теперь проверяют точные пути, SHA, ID/AC mappings, lens sets, role/domain restrictions и append-only authority chains.
- QA требует worker budget, уникальный run, свежую относительно всех write/Review ролей identity, exact-current Review chain и неизменяемый evidence path/SHA для каждого executed manual identity.
- Runtime использует тот же строгий approved-plan parser, что и planning controller; caller не может изобрести capsule budgets или documentation `not_required` policy.
- User decision authority теперь появляется только через отдельный lease-free `user-authority-accept` checkpoint с неизменяемым controller receipt; capsule/Recorder не могут self-issue authority, а поздние решения после начала реализации отклоняются с требованием replan/reinit.
- Удалён legacy recovery entrypoint с caller-provided revision hashes; Final Review rework route выводится из зарегистрированного `finding_kind` и отклоняет evidence-to-product misroute без изменения state.
- Coverage amendments валидируют полный append-only prefix и exact semantic AC diff, а readiness требует точного равенства terminal handoff coverage текущему feature aggregate.

### Проверено

- Добавлены негативные и миграционные проверки leases, capsules, decision ledger, exact coverage-set equality, manual-QA boundary и fresh derived-documentation closure.
- Полный набор из 125 тестов покрывает inventory drift, safe rebaseline, remediation circuit breakers, evidence recovery до `ready`, QA independence и immutable evidence, authority receipts, late-decision/recovery-hash fail-closed paths, semantic coverage amendments, sequential composition, owner/wave budgets, terminal coverage equality, deferred routing, component credits, residual risk и path confinement.

## [0.3.1] - 2026-08-10

### Исправлено

- Контроллеры больше не требуют `docs/features/<feature>/...`: они принимают явные repository-owned пути внутри project root, сохраняют регистр и namespace проекта и останавливаются для уточнения только при неоднозначности.
- Для пустого репозитория прежний layout остаётся рекомендацией, требующей подтверждения, а не автоматически создаваемой схемой.

### Изменено

- Specification, planning и production controllers принимают как плоские `source_prd_*` / `source_spec_*`, так и вложенные `product_authority` / `specification_authority` trace-контракты.

### Проверено

- Полный набор из 99 тестов проходит на repository-owned namespace `docs/Features/template/...`, включая nested authority trace и запрет путей за пределами project root.

## [0.3.0] - 2026-08-09

### Добавлено

- Восемь запускаемых только по явному запросу режимов: ведение продуктовых требований, создание технической спецификации, планирование разработки, управление pipeline, реализация, ограниченное исследование, независимое ревью и runtime QA.
- Director-процесс подготовки спецификации из approved PRD: генерация с нуля, независимая вычитка, исправления постоянным Technical Spec Architect и точный `SPEC_READY` gate. Один Architect ограничен пятью циклами вычитки и исправления; дальнейшая попытка открывает hold вместо продолжения на сжатом контексте.
- Утверждаемый пользователем development plan, который выбирает одного владельца либо последовательные вертикальные срезы по размеру, связанности и контекстному бюджету задачи.
- Последовательная реализация с одним writing owner за раз, запечатанными handoff между срезами, привязкой владельцев и ограниченными возвратами на исправление.
- Делегируемый read-only research-режим с узкими исследовательскими brief, лимитами областей и проверкой свежести результатов относительно конкретной ревизии.
- Машиночитаемая защита скоупа: allowlist, touchpoints, exclusions, бюджеты изменений, change manifest, diff summary и отдельный user-approved rebaseline для материального расширения границ.
- Детерминированная классификация findings по типу, серьёзности, отношению к скоупу, достижимости в production и влиянию на acceptance criteria.
- Атомарный deferred-findings backlog с устойчивыми идентификаторами, дедупликацией и расширением существующих записей новыми условиями, последствиями и доказательствами.
- Ограниченные convergence-проверки: не более двух полных волн на срез, targeted closure для локальных исправлений, повторное использование component credits и финальный composition audit.
- QA capability preflight для точной ревизии и правила возобновления при недоступной среде вместо бесконечного ожидания.

### Изменено

- Pipeline исполняет только exact-hash approved PRD, спецификацию и development plan и не активируется автоматически по типу задачи или наличию артефактов.
- Внескоуповые проблемы, не блокирующие текущую фичу, больше не расширяют реализацию: они регистрируются в deferred backlog и не входят в revision inputs.
- Runtime state доведён до schema v8. Состояния ранних схем несовместимы и должны быть повторно инициализированы перед продолжением pipeline.

### Проверено

- Полный набор из 97 тестов контроллеров, активации и межрежимных контрактов.
- Валидация manifest плагина и всех восьми skill-пакетов.

[Unreleased]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/teano/agentic_game_development_pipeline_codex/releases/tag/v0.3.0
