# Agentic Game Development Skills

Пользовательский bundle Codex skills для разработки игровой фичи до production-ready candidate через ранний resource/runtime preflight, phase-scoped writing leases, bounded context capsules, независимые роли решений/coverage/docs, одну controller-required read-only проверку на фазу и feature-focused runtime QA.

Codex обнаруживает bundle через одну пользовательскую junction: `~/.codex/skills/agentic-gamedev-pipeline` указывает на каталог `agentic-gamedev-pipeline/skills` этого репозитория. Plugin manifest и marketplace-регистрация не используются.

Полный локальный regression suite запускается командой `python agentic-gamedev-pipeline/scripts/test_skills.py`.

## Активация только по запросу

Плагин не должен автоматически включаться для обычной разработки игры, планирования, реализации, исследования репозитория, ревью, тестирования или релиза. Режим запускается только когда пользователь в текущей задаче явно называет соответствующий skill (`$gamedev-requirements`, `$gamedev-specification`, `$gamedev-development-plan`, `$gamedev-pipeline`, `$gamedev-engineer`, `$gamedev-research`, `$gamedev-decision-recorder`, `$gamedev-coverage-steward`, `$gamedev-documentation-finisher`, `$gamedev-recovery-remediator`, `$gamedev-review` или `$gamedev-qa`) либо прямо просит запустить соответствующий режим Agentic GameDev Pipeline.

Явный запуск `$gamedev-pipeline` разрешает контроллеру делегировать его внутренние этапы остальным GameDev skills. Наличие игрового репозитория, PRD/спецификации, `.agentic-pipeline/`, незавершённой работы или подходящего типа задачи само по себе не является разрешением на активацию.

## Принцип

До запуска Engineer технический директор проверяет числовые бюджеты спецификации/контекста и заранее фиксирует утверждённые проектом capability prerequisites. Director занимается только оркестрацией: каждая специализированная фаза выполняется отдельным non-Director субагентом, а недоступность делегирования останавливает этап до начала работы. Один logical verifier ID можно сохранить для последовательных Review/QA/documentation-closure фаз, но каждая фаза запускается в новой `fork_turns:none`-сессии без Director- или worker-chat history. `single_owner` означает один implementation write-scope, а не одного Engineer на весь lifecycle: каждый Decision Recorder, Engineer, Documentation Finisher или Recovery Remediator получает отдельную фазовую lease, причём одновременно разрешён только один writer. Workers получают exact paths/SHA/IDs/evidence в bounded context capsule и возвращают компактные ссылки на неизменяемые артефакты. После code freeze контроллер доказывает exact expected/actual identity equality и automated evidence; Review и QA остаются независимыми и immutable.

## Skills

- `$gamedev-requirements` — продуктовая беседа и ведение канонического PRD по правилам текущего репозитория;
- `$gamedev-specification` — отдельный Director-цикл от approved PRD до `SPEC_READY`: optional Generator, постоянный Technical Spec Architect и свежие read-only Proofreaders, максимум пять циклов на одного Architect;
- `$gamedev-development-plan` — fresh Planning Analyst, выбор `single_owner` или последовательных вертикальных срезов и явное утверждение точного plan SHA пользователем;
- `$gamedev-pipeline` — технический директор и детерминированный контроллер цикла;
- `$gamedev-engineer` — production implementation/root-cause, тесно связанные automated tests, targeted checks, final diff inspection и короткий semantic handoff;
- `$gamedev-research` — свежий read-only исследователь одного ограниченного controller-approved brief;
- `$gamedev-decision-recorder` — append-only фиксация уже принятых решений и ADR sync без принятия или додумывания решений;
- `$gamedev-coverage-steward` — только явно запрошенный standalone read-only аудит предоставленных coverage-данных; runtime coverage принадлежит `$gamedev-pipeline`;
- `$gamedev-documentation-finisher` — normative docs до Review и derived support docs после QA без новых решений;
- `$gamedev-recovery-remediator` — только controller-assigned support/evidence recovery по frozen finding set без product drift;
- `$gamedev-review` — независимый read-only risk audit, финальное ревью или targeted closure без Studio и редактирования;
- `$gamedev-qa` — feature-focused проверка реального игрового поведения через runtime и Computer Use.

## Цикл

```text
requirements conversation
  -> <repository-owned PRD path> (approved, tracked)
  -> specification Director
       -> optional Generator for a missing/stale specification
       -> persistent Technical Spec Architect
       -> fresh read-only Proofreader <-> Architect (max 5 cycles per Architect)
       -> SPEC_READY on one exact PRD/spec hash pair
  -> <repository-owned specification path> (approved, tracked)
  -> development-plan Director
       -> fresh Planning Analyst
       -> single integration owner + milestones OR sequential vertical slices
       -> explicit user approval of one exact draft SHA
  -> <repository-owned development-plan path> (approved, tracked)
  -> director preflight
       -> resource/config invariants
       -> runtime capabilities + manual operator plan + context budgets
  -> active-slice bounded research
       -> 1-3 bounded briefs delegated to fresh read-only Researchers, or explicit research_not_required
  -> controller-owned exact automated/manual identity planning
  -> phase-scoped Engineer lease (one writer)
       -> production implementation/root-cause + tightly coupled automated tests
       -> targeted checks + final diff inspection + short semantic handoff
       -> ENGINEERING_PASS with manual QA normally pending
  -> controller-owned exact registration equality + automated execution + manual QA matrix
  -> implementation_state=pass
  -> Documentation Finisher: normative docs before immutable Review
  -> one controller-required read-only convergence Review
       -> findings -> one frozen batch -> same Engineer owner
       -> pass -> one Final Review in a fresh no-history session
  -> one controller-required Final Review
       -> local product batch -> origin-routed Engineer lease + 1 targeted closure reviewer
       -> architectural/broad batch -> routed Engineer lease + new full convergence/Final Review lineage
       -> support/evidence batch -> Recovery Remediator + 1 recovery reviewer
       -> pass -> QA
  -> feature-focused in-game QA
       -> exact registered manual identities executed/passed/deferred
       -> fail_product -> origin-routed exclusive Engineer lease
       -> blocked_user/environment or error_test -> remain in QA
       -> pass -> Documentation Finisher derived support docs
       -> fresh read-only documentation closure on unchanged product/evidence
       -> feature_verification_state=pass -> production-ready candidate
```

Первая найденная проблема не завершает аудит. Engineer pass отделён от feature verification: pending manual QA, DataStore или operator capability не превращают `ENGINEERING_PASS` в `INCOMPLETE`. Coverage хранит раздельно AC mapping, exact identity registration, automated execution и manual execution/defer. Convergence/Review/QA не исправляют код. Контроллер генерирует и валидирует revision/change/diff/handoff mechanics и всегда добавляет в handoff `decision_ids`, `coverage_state`, `documentation_state` и `open_assumptions`.

Контроллер раздельно хранит composite, product, support и evidence revisions. Append-only decision ledger и normative docs входят в product; derived operator/index/handoff docs — в support; tests/fixtures — в evidence. Post-QA support-only docs сохраняют QA credit только при exact unchanged product/evidence и fresh documentation closure. По умолчанию разрешено не более 14 уникальных workers и двух Review-remediation cycles на одной candidate lineage; capsule budget и фактические file/byte/token metrics сохраняются append-only.

## Артефакты

Namespace и регистр путей принадлежат проекту. Контроллер сначала использует явные пути пользователя, инструкции репозитория, feature manifests/indexes и уже существующие документы. Если из контекста получается одна каноническая тройка, он принимает её без переименований. При нескольких вариантах задаёт один уточняющий вопрос. Он не создаёт копии, symlink, переносы или параллельный источник истины ради собственной схемы.

Для пустого проекта без соглашений контроллер может предложить следующий layout, но создаёт его только после подтверждения пользователя:

```text
<game-project>/
  docs/features/<feature>/
    product-requirements.md        # tracked in Git
    technical-specification.md     # tracked in Git
    development-plan.md            # tracked in Git
    decision-ledger.jsonl          # tracked, append-only normative product input
  tests/<feature>/                 # ignored by Git
    verification/
    reviews/
    qa/
  .agentic-pipeline/               # runtime controller state
```

Это рекомендация для нового репозитория, а не обязательный namespace плагина. Поддерживаются как плоские trace-поля `source_prd_*` / `source_spec_*`, так и эквивалентные вложенные `product_authority` / `specification_authority`.

`tests/<feature>/` содержит генерируемые отчёты, логи, скриншоты и runtime evidence. Контроллер добавляет `/tests/` в `.gitignore`. Невыполненный сценарий классифицируется как `blocked_user`, `blocked_environment` или `error_test`, а не как product failure.

## Структура пакета

```text
agentic-gamedev-pipeline/
  skills/
    gamedev-requirements/
    gamedev-specification/
    gamedev-development-plan/
    gamedev-pipeline/
    gamedev-engineer/
    gamedev-research/
    gamedev-decision-recorder/
    gamedev-coverage-steward/
    gamedev-documentation-finisher/
    gamedev-recovery-remediator/
    gamedev-review/
    gamedev-qa/
```

После `SPEC_READY` вызывается `$gamedev-development-plan`; реализация начинается только по утверждённому плану через `$gamedev-pipeline`.
