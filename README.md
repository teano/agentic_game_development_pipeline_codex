# Agentic Game Development Pipeline

Локальный пакет Codex для разработки игровой фичи до production-ready candidate через ранний resource/runtime preflight, одного writing owner за раз, параллельную read-only проверку, финальное ревью и feature-focused runtime QA.

## Активация только по запросу

Плагин не должен автоматически включаться для обычной разработки игры, планирования, реализации, исследования репозитория, ревью, тестирования или релиза. Режим запускается только когда пользователь в текущей задаче явно называет соответствующий skill (`$gamedev-requirements`, `$gamedev-specification`, `$gamedev-development-plan`, `$gamedev-pipeline`, `$gamedev-engineer`, `$gamedev-research`, `$gamedev-review` или `$gamedev-qa`) либо прямо просит запустить соответствующий режим Agentic GameDev Pipeline.

Явный запуск `$gamedev-pipeline` разрешает контроллеру делегировать его внутренние этапы остальным GameDev skills. Наличие игрового репозитория, PRD/спецификации, `.agentic-pipeline/`, незавершённой работы или подходящего типа задачи само по себе не является разрешением на активацию.

## Принцип

До запуска Engineer технический директор проверяет числовые бюджеты спецификации и заранее фиксирует доступность Studio/Rojo, опубликованных конфигов, DataStore, place topology и ручного управления. В режиме `single_owner` один Engineer остаётся владельцем product-исправлений; в режиме `sequential_slices` владельцы работают строго последовательно и получают запечатанные handoff. После изменений два или три независимых read-only аудитора одновременно проверяют одну неизменную ревизию по разным risk-линзам и возвращают общий batch владельцу маршрута. После чистой convergence-wave два финальных Review проверяют кандидат. Локальные исправления закрывает один targeted reviewer; documentation/test-only изменения не сбрасывают runtime-аудит. QA проверяет только новую фичу, затронутые общие границы и небольшой обоснованный smoke-набор.

## Skills

- `$gamedev-requirements` — продуктовая беседа и ведение `docs/features/<feature>/product-requirements.md`;
- `$gamedev-specification` — отдельный Director-цикл от approved PRD до `SPEC_READY`: optional Generator, постоянный Technical Spec Architect и свежие read-only Proofreaders, максимум пять циклов на одного Architect;
- `$gamedev-development-plan` — fresh Planning Analyst, выбор `single_owner` или последовательных вертикальных срезов и явное утверждение точного plan SHA пользователем;
- `$gamedev-pipeline` — технический директор и детерминированный контроллер цикла;
- `$gamedev-engineer` — реализация, полный аудит, пакетная доработка и verification в одном проходе;
- `$gamedev-research` — свежий read-only исследователь одного ограниченного controller-approved brief;
- `$gamedev-review` — независимый read-only risk audit, финальное ревью или targeted closure без Studio и редактирования;
- `$gamedev-qa` — feature-focused проверка реального игрового поведения через runtime и Computer Use.

## Цикл

```text
requirements conversation
  -> docs/features/<feature>/product-requirements.md (approved, tracked)
  -> specification Director
       -> optional Generator for a missing/stale specification
       -> persistent Technical Spec Architect
       -> fresh read-only Proofreader <-> Architect (max 5 cycles per Architect)
       -> SPEC_READY on one exact PRD/spec hash pair
  -> docs/features/<feature>/technical-specification.md (approved, tracked)
  -> development-plan Director
       -> fresh Planning Analyst
       -> single integration owner + milestones OR sequential vertical slices
       -> explicit user approval of one exact draft SHA
  -> docs/features/<feature>/development-plan.md (approved, tracked)
  -> director preflight
       -> resource/config invariants
       -> runtime capabilities + manual operator plan
  -> active-slice Engineer owner (one writer)
       -> 1-3 bounded briefs delegated to fresh read-only Researchers, or explicit research_not_required
       -> frozen finding batch
       -> batch remediation + tests + full resweep
       -> incomplete -> resume the same Engineer
       -> after 3 remediation returns -> sealed handoff to a fresh owner without budget reset
       -> product changed -> parallel read-only convergence
  -> Risk Audit A || Risk Audit B [|| Risk Audit C]
       -> findings -> one aggregate batch -> same Engineer owner
       -> pass -> final Review
  -> Review A || Review B
       -> both finish before aggregation
       -> local product batch -> same owner + 1 targeted closure reviewer
       -> architectural/broad batch -> same owner + new full Review pair
       -> support/evidence batch -> bounded remediator + 1 recovery reviewer
       -> both pass -> QA
  -> feature-focused in-game QA
       -> fail_product -> same Engineer owner
       -> blocked_user/environment or error_test -> remain in QA
       -> pass -> production-ready candidate
```

Первая найденная проблема не завершает аудит. Контроллер принимает owner-pass только с `AUDIT_COMPLETE: yes` и структурированным coverage manifest. Convergence и финальные reviewers не исправляют код и не запускают повторно уже зелёные Studio/integration suites. Главный агент дожидается всей параллельной волны и объединяет findings по корневой причине. Support/test-only remediation сохраняет неизменный runtime product hash: remediator запускает targeted, affected и aggregate suites, после чего один свежий reviewer проверяет только закрытие recovery batch.

Контроллер раздельно хранит composite, product, support и evidence revisions. Только изменение runtime/public contract сбрасывает чистое инженерное и архитектурное evidence; документация и тесты используют bounded recovery lane. По умолчанию разрешено не более 14 уникальных workers и двух полных Review-waves; на каждый slice действует отдельный жёсткий максимум двух full convergence waves, который нельзя расширить authorization или handoff. Свежие workers получают пути и IDs без наследования разросшейся истории чата, а статус публикуется только при смене фазы.

## Артефакты

```text
<game-project>/
  docs/features/<feature>/
    product-requirements.md        # tracked in Git
    technical-specification.md     # tracked in Git
    development-plan.md            # tracked in Git
  tests/<feature>/                 # ignored by Git
    verification/
    reviews/
    qa/
  .agentic-pipeline/               # runtime controller state
```

`tests/<feature>/` содержит генерируемые отчёты, логи, скриншоты и runtime evidence. Контроллер добавляет `/tests/` в `.gitignore`. Невыполненный сценарий классифицируется как `blocked_user`, `blocked_environment` или `error_test`, а не как product failure.

## Структура пакета

```text
agentic-gamedev-pipeline/
  .codex-plugin/plugin.json
  skills/
    gamedev-requirements/
    gamedev-specification/
    gamedev-development-plan/
    gamedev-pipeline/
    gamedev-engineer/
    gamedev-research/
    gamedev-review/
    gamedev-qa/
```

После `SPEC_READY` вызывается `$gamedev-development-plan`; реализация начинается только по утверждённому плану через `$gamedev-pipeline`.
