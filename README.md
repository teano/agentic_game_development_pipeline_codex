# Agentic Game Development Skills

Пользовательский bundle explicit-only Codex skills для подготовки игровой фичи к статусу production-ready candidate. Основной runtime — компактный controller-owned Pipeline v2: семь фаз, девять CLI-команд и одна минимальная Git-tree модель состояния.

Bundle обнаруживается через пользовательскую junction `~/.codex/skills/agentic-gamedev-pipeline`, указывающую на `agentic-gamedev-pipeline/skills` этого репозитория. Полный regression suite:

```text
python agentic-gamedev-pipeline/scripts/test_skills.py
```

## Активация

GameDev skills запускаются только когда пользователь явно называет соответствующий skill или просит запустить Agentic GameDev Pipeline. Наличие игрового проекта, документов или runtime-state само по себе не разрешает активацию.

Доступные роли:

- `$gamedev-requirements` — утверждённый product requirements document;
- `$gamedev-specification` — утверждённая техническая спецификация;
- `$gamedev-development-plan` — утверждённый план и ограниченные slice records;
- `$gamedev-pipeline` — единственный Director/controller runtime;
- `$gamedev-engineer` — реализация или product remediation в controller-derived slice scope;
- `$gamedev-review` — независимый read-only Review;
- `$gamedev-qa` — независимая read-only QA;
- `$gamedev-documentation-finisher` — ограниченная документационная запись;
- `$gamedev-coverage-steward` — отдельный advisory-only аудит предоставленного coverage.

Явный запуск `$gamedev-pipeline` разрешает Director делегировать внутренние фазы остальным активным ролям. Каждый assignment использует новый worker session ID. Engineer никогда не может быть Review или QA worker того же run.

Если Director или worker подозревает дефект controller/runtime/skill/protocol/state transition, product run немедленно останавливается. Агент подробно, но bounded и redacted описывает действие, фазу/generation, фактическое и ожидаемое поведение, влияние на candidate и условие восстановления. Ему запрещено самостоятельно менять, патчить, обходить или локально подменять pipeline и продолжать run на изменённой версии. Отдельная pipeline-maintenance работа разрешается только новой явной командой пользователя.

## Pipeline v2

Стабильный launcher:

```text
python agentic-gamedev-pipeline/skills/gamedev-pipeline/scripts/pipeline_state.py --help
```

Фазы строго фиксированы:

```text
plan -> slice -> engineering -> review -> qa -> docs -> ready
```

Команды строго фиксированы: `init`, `status`, `next`, `complete`, `answer`, `resume`, `accept`, `migrate`, `ready`.

`init` принимает ровно три authority key: `requirements`, `specification`, `plan`. Он также требует один или несколько упорядоченных slice records с полями `id`, `allowed_paths`, `planned_commands`. Каждый slice последовательно проходит Engineering, свежие Review и QA; только после последнего начинается Docs. Engineering write access и controller-run команды выводятся из текущего slice, поэтому caller не может подменить их через `next` или выдать Engineer доступ `**`.

Review получает отдельный controller-derived `context.review_target`: `required_scope` указывает обязательную границу текущего slice, а `candidate_changes` содержит точные пути из принятого Engineering diff; после Docs этот exact diff одновременно является всей целью. Более широкий read access к authority, `read_paths`, untouched code и завершённым slice служит только evidence context. Finding о внесённом дефекте или лишней сложности обязан быть привязан к `candidate_changes`; вне них допустимы только пропущенная обязательная реализация внутри required scope или доказанная direct regression. Finding требует конкретного current-candidate evidence, достижимого поддерживаемого игрового пути или детерминированного trace и материального нарушения обязательного поведения либо конкретной лишней сложности. Теоретические риски, misuse/manual tampering, future-scale hardening и необязательные улучшения исключены; при выполненных требованиях и минимальной KISS/YAGNI-реализации Reviewer сразу возвращает `pass` с пустым списком.

`status` всегда возвращает один controller-derived `next_action`: command ID, generation, assignment/session identity, output path, access, checks, Review target и recovery reason не вводятся вручную. Если утверждённая authority изменилась, точный `init` из `next_action` выполняет CAS-защищённую reconfiguration, сохраняет старый candidate/history как audit context и возвращает run в Plan. Активная работа прерывается только после controller proof, что checkout diff оставался в прежнем scope; новый scope затем приходит как обычный semantic result Slicer и обязан покрыть эти Engineering paths.

Workers возвращают только простые semantic artifacts:

```text
plan/engineering/docs: outcome + non-empty summary
slice: outcome + summary + optional ordered slice records
review: outcome + findings[{text,severity,kind}]
qa: outcome + checks
blocked: every role also requires blocker + required_action
```

Git tree OID, changed paths, authority/runtime digests и process receipts принадлежат controller, а не worker artifact. `init` требует чистый committed Git root и tracked authority. Pipeline контролирует tracked и новые non-ignored candidate paths; ignored editor/cache/log files полностью вне его границы. Planned command обязан оставить candidate tree неизменным, а изменение `.gitignore`, `.gitattributes` или `.gitmodules` требует fresh `init`.

## Rework и readiness

Review/QA остаются read-only. `fail` в Review или QA создаёт сохраняемый gate с finding/check context и точным candidate base; после `resume` controller возвращает run в writable `engineering`, инвалидирует engineering и downstream artifacts, а затем требует свежие Review и QA. `blocked` требует непустые `blocker` и `required_action`, не запускает planned commands, не выдаёт candidate/phase credit и после устранения внешней причины повторяет исходную фазу с новым worker session ID.

Изменившая candidate документация также инвалидирует Review/QA. `ready` требует доказанное завершение всех ordered slices, повторно сравнивает live checkout с последним независимо reviewed/tested candidate и только тогда устанавливает `PRODUCTION_READY_CANDIDATE`. Это не разрешает deployment, публикацию, spending, store submission или risk acceptance.

## Schema-10 cutover

`migrate` сохранён только как fail-closed tombstone. Миграция schema-10 не поддерживается `git-tree-v1`: legacy state/findings нужно архивировать и запустить свежие Plan/`init`. Import, reconstruction и продолжение старого assignment не выполняются; свежий run проходит полный путь:

```text
plan -> slice -> engineering -> review -> qa -> docs -> ready
```

Pipeline v2 не вызывает legacy handlers, Decision Recorder, deferred-findings или recovery-role handlers. Консервативные Director decisions, completed actor IDs и remediation gates хранятся внутри controller state.
