# Agentic Game Development Pipeline

Локальный пакет Codex для разработки игровой фичи до production-ready candidate через ранний resource/runtime preflight, одного постоянного writing owner, параллельную read-only проверку, финальное ревью и feature-focused runtime QA.

## Принцип

До запуска Engineer технический директор проверяет числовые бюджеты спецификации и заранее фиксирует доступность Studio/Rojo, опубликованных конфигов, DataStore, place topology и ручного управления. Один Engineer остаётся владельцем всех product-исправлений. После его изменений два или три независимых read-only аудитора одновременно проверяют одну неизменную ревизию по разным risk-линзам и возвращают общий batch тому же владельцу. После чистой convergence-wave два финальных Review проверяют кандидат. Локальные исправления закрывает один targeted reviewer; documentation/test-only изменения не сбрасывают runtime-аудит. QA проверяет только новую фичу, затронутые общие границы и небольшой обоснованный smoke-набор.

## Skills

- `$gamedev-requirements` — продуктовая беседа и ведение `docs/features/<feature>/product-requirements.md`;
- `$gamedev-pipeline` — технический директор и детерминированный контроллер цикла;
- `$gamedev-engineer` — реализация, полный аудит, пакетная доработка и verification в одном проходе;
- `$gamedev-review` — независимый read-only risk audit, финальное ревью или targeted closure без Studio и редактирования;
- `$gamedev-qa` — feature-focused проверка реального игрового поведения через runtime и Computer Use.

## Цикл

```text
requirements conversation
  -> docs/features/<feature>/product-requirements.md (approved, tracked)
  -> docs/features/<feature>/technical-specification.md (approved, tracked)
  -> director preflight
       -> resource/config invariants
       -> runtime capabilities + manual operator plan
  -> persistent Engineer owner
       -> full read-only discovery
       -> frozen finding batch
       -> batch remediation + tests + full resweep
       -> incomplete -> resume the same Engineer
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

Контроллер раздельно хранит composite, product, support и evidence revisions. Только изменение runtime/public contract сбрасывает чистое инженерное и архитектурное evidence; документация и тесты используют bounded recovery lane. По умолчанию разрешено не более 14 уникальных workers и двух полных Review-waves; продолжение требует явного director budget authorization. Свежие workers получают пути и IDs без наследования разросшейся истории чата, а статус публикуется только при смене фазы.

## Артефакты

```text
<game-project>/
  docs/features/<feature>/
    product-requirements.md        # tracked in Git
    technical-specification.md     # tracked in Git
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
    gamedev-pipeline/
    gamedev-engineer/
    gamedev-review/
    gamedev-qa/
```

Главная точка входа после утверждения спецификации — `$gamedev-pipeline`. Технический директор переиспользует writing owner и QA при продолжении, а свежие субагенты запускает только для независимых read-only проверок.
