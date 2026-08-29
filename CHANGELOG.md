# История изменений

Значимые изменения Agentic GameDev Pipeline фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии следуют [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.10.0] - 2026-08-29

### Добавлено

- Specification controller получил одноразовый challenge/result handshake с внешним `skill-specification-pipeline`: controller фиксирует точные PRD/spec SHA, язык, route, fingerprints и write boundary, а внешний canonical emitter связывает результат с report/coverage и защищает его от replay.
- Persistent Technical Spec Architect теперь выпускает exact-SHA pre-accept receipt с полным inventory самостоятельных разделов, таблиц, диаграмм и иерархий, чтобы обязательная полнота не сохраняла пустой boilerplate или необоснованную сложность.
- Изолированные Development Plan slices могут явно использовать `shared_touchpoints: none`; controller принимает это только при отсутствии structured touchpoints и пересекающихся editable paths.

### Изменено

- Внешний `skill-specification-pipeline` стал единственным generation/correction engine для GameDev Specification; локальный fallback удалён, а его generic stages, passes и N/A policy не дублируются в GameDev controller.
- Общий scope-and-sufficiency contract ограничивает Generator, Architect и Proofreader подтверждённым PRD scope и материальными текущими дефектами, исключая theoretical risks, future-scale design, optional hardening и поиск необязательных улучшений.
- Docs write authority теперь выводится только из утверждённого Development Plan: exact `not_required` честно завершает фазу без project-file writes, а требуемая документация ограничивается объявленными canonical paths.

### Исправлено

- Major-коррекция Specification больше не наследует acceptance и review credit старых байтов: внешний `fragment-capture` исправляет exact reviewed SHA, после чего обязательны fresh Architect acceptance и новый Proofreader.
- Устранены искусственные shared-boundary и documentation artifacts для минимальных изолированных features без ослабления overlap и plan-authority проверок.

### Проверено

- Canonical regression suite: 375/375 PASS; три Linux PID namespace проверки ожидаемо пропущены на Windows. Specification — 103/103, Development Plan — 103/103, Pipeline v2 core — 120/120.
- Два изолированных E2E достигли `production_ready_candidate`; финальный correction path доказал external generation, Major -> `fragment-capture` correction, fresh acceptance/review, `shared_touchpoints: none` и Docs no-op с независимым аудитом P0/P1/P2 = 0.

## [0.9.1] - 2026-08-28

### Изменено

- Review получает controller-derived `review_target`, ограниченный текущим implementation slice и точными путями принятого candidate diff; остальные доступные для чтения пути используются только как evidence context.
- Reviewer сообщает только конкретные материальные дефекты и внесённую текущим target избыточность по KISS/YAGNI; теоретические, крайне маловероятные и необязательные улучшения исключены, а доказанный bounded target завершается `pass` без findings.

### Исправлено

- Сохранены exact replay и recovery для активных Review assignments, созданных до появления `review_target`: совместимый target проецируется без изменения controller state, а подмена caller-ом отклоняется.

## [0.9.0] - 2026-08-27

### Добавлено

- Bound-v2 Specification теперь поддерживает tokenless rewind после утверждённой PRD revision только при точном public `status -> init`, с nested schema-2 привязкой prior authority и повторной CAS-проверкой runtime state; точный released schema-1 specification-only receipt читается через неперсистирующий compatibility adapter.
- Public `complete`/`status` и свежий remediation assignment теперь показывают безопасный controller-failure capsule для `worker_result` и `controller_result` gates с индексом/return code/digests/excerpt/flags и числом невыполненных команд, не публикуя argv/env/cwd/stdout.

### Изменено

- Planned commands выполняются fail-fast до первого non-zero с inventory/drift-проверкой после каждой реально выполненной команды; reducer принимает только полный all-pass или точный failure-prefix.
- Failure-only evidence получила redacted/path-normalized `stderr_excerpt` не более 4096 UTF-8 bytes с flags, сохранив full stderr digest и совместимость schema 2 с legacy four-field evidence; PAT, database URL, DSN и URI userinfo дополнительно редактируются.
- Plan validator и runtime используют общий строгий parser Context Capsule read paths, включая comma-space lists, и одинаково отклоняют недопустимую грамматику путей.

### Исправлено

- Windows cleanup controller scratch теперь ограниченно снимает read-only только с точного отказавшего пути внутри проверенного scratch, не делает prewalk и не затрагивает цели junction/symlink; отсутствующий scratch удаляется идемпотентно.
- Non-zero controller result атомарно сохраняет неизменённый worker artifact и controller evidence. Для worker `pass` открывается отдельный `controller_result` gate без candidate/phase credit; replay не перезапускает команды, а QA возвращается в Engineering.

### Проверено

- Полный canonical regression suite: 333/333 PASS; три Linux PID namespace runtime-теста ожидаемо пропущены на Windows.
- Два изолированных `TEST FIXTURE ONLY` E2E завершились terminal `production_ready_candidate`: полный PRD r2 -> Specification -> Plan rewind/reconvergence достиг generation 21, а controller-result remediation после worker `pass` и non-zero check — generation 22; без изменений игровых путей и без утверждений пользовательского approval или `$feature-finish`.

## [0.8.0] - 2026-08-26

### Добавлено

- Добавлен модульный controller-owned Pipeline v2 с семью фиксированными фазами, девятью публичными командами, атомарным state store, native process lock и единым `active_assignment` вместо разрозненных leases, capsules и recovery handlers.
- Controller теперь самостоятельно выводит worker identity, read/write scope, output path, checks, checkout inventory, command intent и replay receipts; workers возвращают только ограниченные semantic artifacts своей роли.
- Добавлены fail-closed reconfiguration, schema-10 import, process-tree containment и regression coverage для Windows/POSIX, lost-response replay, stale CAS, authority drift, reparse paths и interrupted writes.
- Добавлен общий operational-invariant test, который проверяет согласованность stable launcher, skill contracts и единственного runtime v2.

### Изменено

- Стабильный `pipeline_state.py` теперь является компактным launcher для `pipeline_v2`; основной runtime использует schema 2 и последовательность `plan -> slice -> engineering -> review -> qa -> docs -> ready`.
- Requirements, Specification и Development Plan сохраняют только явно подтверждённые решения, требуют semantic coverage и направляют пользовательские ограничения без engine-specific предположений.
- Engineering и Docs остаются единственными writing roles; Review и QA получают свежие независимые identities, а любое rework инвалидирует downstream credit и требует повторной проверки текущего candidate.
- Development Plan и runtime используют controller-owned ordered slices с раздельными read/write paths; public `status` возвращает один точный `next_action`, а reconfiguration и replay используют ту же canonical authority.
- Test runner рекурсивно обнаруживает модульные runtime-тесты и распространяет запрет bytecode-cache в дочерние процессы.

### Исправлено

- Исправлены checkout/evidence recovery, stale replay baselines, nonzero planned-command gate и восстановление после Docs без ручной правки controller state.
- Исправлены mixed authority binding, delegated technical approval, retired lineage, integer/bool generation contracts и выбор актуальной same-plan archive при продолжении Development Plan.
- Exact replay для committed Specification и sealed Slice completion теперь возвращает byte-identical no-op; изменённый intent, stale generation или authority drift отклоняются до mutation.
- Review/QA больше не переносят устаревший credit через rework, а `ready` повторно сверяет authority, inventory, gates, questions и завершение ordered slices.

### Удалено

- Удалены legacy Decision Recorder, Research и Recovery Remediator skills, deferred-findings runtime, semantic-forward grader и монолитные schema-10 controller tests/references.
- Удалены отдельные legacy handlers и контракты, дублировавшие controller-owned decisions, remediation gates, scope и replay bookkeeping.

### Миграция

- Существующий schema-10 run импортируется только явной командой `migrate` в пустой v2 state. Legacy candidate и lineage сохраняются как audit context, но не получают v2 verification credit; выполнение возобновляется с Plan и проходит полный v2 lifecycle.
- Интеграции, вызывавшие удалённые Decision Recorder, Research, Recovery Remediator или deferred-findings entrypoints, должны использовать `$gamedev-pipeline` и оставшиеся role-owned semantic artifacts.
- Публичный launcher сохраняет прежний путь, но callers должны использовать девять команд v2 и controller-derived `next_action`, не передавая собственные assignment, scope, hashes или replay identity.

### Проверено

- Полный shared-pipeline regression: 310/310 PASS; три POSIX-only process-tree проверки ожидаемо пропускаются на Windows.
- Реальный Roblox UI System run достиг generation 228, `production_ready_candidate`, с финальными Review/QA, 17/17 Studio checks и 397/397 product tests.
- Exact replay, authority/inventory reconciliation, cache hygiene и отсутствие ручных controller-state edits независимо перепроверены; неблокирующие deferred P2 не включались в release scope.

## [0.7.0] - 2026-08-15

### Добавлено

- Общие строгие контракты acceptance criteria и development plan теперь одинаково используются Requirements, Specification, Planning и runtime-контроллерами; literal producer output принимается downstream без локальных dialects.
- Добавлен explicit-only Recovery Remediator для controller-assigned support/evidence recovery, а Research, Review, QA и semantic write packets получили компактные role-owned output schemas.
- Requirements Collector задаёт до пяти связанных вопросов за раунд, предлагает только grounded варианты с trade-offs и сохраняет частичные ответы, не превращая предложения в подтверждённые требования.
- Test runner получил fast/runtime partitions, детерминированный discovery и пригодные для CI summaries без немых многоминутных запусков.

### Изменено

- Runtime state обновлён до schema 10: `state.json` является единственным атомарным authority, `findings.json` — восстанавливаемой projection; snapshots хранят только bounded digests/line hashes без raw checkout text и секретов.
- Director startup context сокращён примерно вдвое до 12 271 байта: он загружает authority/phase/hold/lease/checkpoint summary, а worker schemas и фазовые детали раскрываются только по требованию.
- Happy path использует одного Engineer и один logical Verifier ID; convergence, Final Review и QA запускаются в свежих `fork_turns:none` sessions с точными phase capsules и без sibling conclusions.
- Preflight и QA capabilities выводятся из approved plan и фактически исполняемых manual identities вместо глобального engine-specific набора; Research briefs и waiver reason теперь буквально связаны с approved plan.
- Scope discipline привязан к Product Outcome и назначенным PRD-REQ/AC: side issues требуют deferred backlog с owner, impact, rationale и точной occurrence binding, а rebaseline — immutable user-authority receipt для exact hold и plan SHA.
- Coverage, QA, decision, documentation source-map и handoff contracts сделаны closed и controller-bound; opaque reports остаются audit-only и не используются как authority.

### Исправлено

- Устранены ложные material-scope holds и PLAN revision churn для заранее утверждённых lifecycle/ownership/public-contract изменений; повторное утверждение требуется только для нового material scope.
- Generated/cache/vendor noise настраивается project policy и одинаково исключается из snapshots и semantic diff, не скрывая tracked source.
- Decision ledger, lifecycle receipts и canonical findings сохраняются crash-safe; `status` не мутирует legacy/current state, а одинаковый lost-response retry возвращает прежний результат без дублирования.
- Исправлены dead ends и replay-конфликты в decision recording, coverage re-finalization после remediation, Engineer continuation, context-exhausted owner handoff, documentation closure и QA recovery.
- Approved PRD acceptance inventory, slice coverage и shared-AC aggregation используют exact literal IDs; диапазоны, дубликаты, hidden Markdown authority и несовместимые producer/consumer schemas отклоняются до runtime.
- Final Review/QA больше не получают human-readable conclusions предыдущего reviewer; documentation closure требует structured credit/report, exact hashes и отклоняет последующий tamper.

### Миграция

- Active schema-9 state мигрируется автоматически при следующей authorized mutation; read-only `status` остаётся byte-for-byte nonmutating. Изменённый или недоказуемый legacy candidate сохраняет файлы, отзывает stale lease и требует fresh owner handoff.
- `slice-research-not-required` должен повторять exact approved plan reason, а Research completion — exact набор из 1–3 plan brief IDs.
- Legacy deferred entries остаются читаемыми, но не могут авторизовать scope, пока не дополнены owner, impact, rationale и exact finding occurrence.
- Integrations должны использовать новые role-owned Research/Review/QA/semantic schemas и не считать generic report body машинным authority.

### Проверено

- Exact discovery: 403 теста; 399 проходят, 4 Windows symlink-сценария ожидаемо пропущены без link-creation privilege, failures отсутствуют.
- Все 235 runtime-state тестов покрыты десятью непересекающимися partitions без пропусков или дубликатов; fast suite — 168/168.
- Все 20 Python-файлов компилируются; `git diff --check`, secret/raw-snapshot/runtime-artifact scans проходят без замечаний.

## [0.6.0] - 2026-08-12

### Изменено

- Bundle переведён из Codex plugin в обычные пользовательские skills: plugin manifest/marketplace больше не используются, а весь каталог `skills/` подключается одной junction из `~/.codex/skills/agentic-gamedev-pipeline`.
- Runtime Director теперь строго orchestration-only: каждый специализированный этап обязан выполняться отдельным non-Director субагентом без наследования длинной истории, а разные роли нельзя совмещать в одном агентном контексте.
- Continuation после context compaction или замены Director восстанавливается из compact controller status, capsules, leases и sealed handoffs; потеря разговорного окна не считается пользовательским блокером.
- После каждой controller mutation атомарно обновляется hash-bound `director-checkpoint.json`; обычный цикл запрещает повторный `--help`, `status --full`, неограниченный polling и более 32 Director-вызовов без stage boundary.

### Исправлено

- Engineer capsule теперь получает точный finding set активного slice/integration remediation batch; ошибочная проверка невозможного `route == "engineer"` заменена валидацией реальных controller routes и покрыта независимыми regression-тестами.
- Integration remediation теперь получает finalized feature coverage, а targeted closure reviewer — точный frozen finding set.
- Controller автоматически и fail-closed согласует единственный доказанный lifecycle-only drift даты в generated feature dashboard во время продолжения engineering remediation: требует exact batch/findings, неизменные support/evidence identities и уникальное обратное доказательство frozen product/composite revision; сохраняет append-only receipt, per-file records/guard, инвалидирует затронутые credits и stale unused Engineer capsules. Никакие Pause/Continue-скрипты не меняются.
- Engineer lease теперь выдаётся только после current exact-base scope check; legacy lease восстанавливается отдельным audit receipt без rollback/EOL-реконструкции, а `prepare-engineer-continuation` идемпотентно подготавливает scope, capsule, lease и точный handoff.
- Успешная targeted Final Review closure с возвратом в QA сохраняет exact convergence/review/remediation lineage в `engineer_clean`; исторический ready-state deadlock восстанавливается одноразовой fail-closed командой без повторного Review, QA или изменения checkout.
- Создание off-phase capsule отклоняется до записи артефактов с сохранением только документированных cross-phase маршрутов Decision Recorder и Documentation Finisher.

### Проверено

- Полный regression suite из 260 тестов проходит; 6 symlink-сценариев ожидаемо пропускаются без соответствующих Windows-привилегий.
- Skill validation, whitespace-проверка staged diff и независимый аудит controller recovery/state-machine изменений проходят без блокирующих замечаний.

## [0.5.0] - 2026-08-11

### Добавлено

- Общий stage-handoff инвариант: специализированный этап сохраняет результат, возвращает точный `NEXT_ACTION` и останавливается; следующий именованный этап может активировать только пользователь или явно запущенный Director.
- Progressive-disclosure маршрутизация для engineering/coverage и review/QA/recovery контрактов, а также статические бюджеты описаний, initial bundle и условных reference-пакетов.
- Компактный schema-versioned `status` по умолчанию с диагностическими `--section` и `--full`, плюс внешний semantic-forward-eval grader с положительными и отрицательными fixtures.
- Версионированное доказательство полного environment preflight и явный `reinitialize-preflight` для безопасной миграции прежних schema-9 состояний.

### Изменено

- Requirements, Specification, Engineer и остальные специализированные этапы больше не запускают соседние GameDev-этапы напрямую; Director сохраняет порядок `PRD_READY` → `SPEC_READY` → `PLAN_READY` → runtime.
- Справка контроллера и длинные фазовые правила разделены на каноническое компактное ядро и условно загружаемые контракты без дублирования статического command manual.
- Capability prerequisites нормализованы единым lowercase-hyphen контрактом на planning, preflight и QA границах; `metric_scope` фиксируется как `capsule_plus_referenced_files`.
- Reviewer, QA и recovery capsules теперь требуют точные текущие coverage, findings, evidence, credits и handoff-наборы; лишняя или устаревшая authority отклоняется.
- QA выводит смешанные gates детерминированно, а support remediation отделён от product-blocking формулы.

### Исправлено

- Generic `resolve-finding` переведён в fail-closed режим, а принятие остаточного риска требует неизменяемого user-authority receipt с точной statement binding.
- Documentation source maps проверяют неизменяемый pre-write SHA и запрещают самоавторизацию либо перекрёстную авторизацию изменяемых путей.
- Старые или неполные preflight proofs больше не позволяют пройти в специализированный runtime: контроллер переводит их в `preflight_migration_hold` до явной повторной проверки.
- Компактный status ограничивает длинные списки findings, gates и capability blockers, сохраняя полное состояние только в адресной диагностике.
- Командные контракты синхронизированы с argparse, включая обязательный coverage manifest и документированные recovery/closure переходы.

### Проверено

- Полный набор из 177 тестов покрывает stage isolation, command parity, статические context budgets, compact output, migration hold, exact role capsules, immutable documentation authority и semantic-forward fixtures.
- Все 11 skill-пакетов проходят локальную валидацию; `git diff --check` и проверка локальных Markdown-ссылок проходят без ошибок.

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

[Unreleased]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/teano/agentic_game_development_pipeline_codex/releases/tag/v0.3.0
