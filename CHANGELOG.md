# История изменений

Значимые изменения Agentic GameDev Pipeline фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии следуют [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.20.2] - 2026-09-30

### Изменено

- Настройки директоров и специализированных ролей GameDev Pipeline обновлены с GPT-6 Sol (`gpt-6-sol`) на GPT-6.1 Sol (`gpt-6.1-sol`) с сохранением назначенных уровней размышления. Для QA сохранены GPT-6 Luna (`gpt-6-luna`) и уровень `medium`.
- Явные значения модели при делегировании в инструкциях требований, спецификации и плана разработки согласованы с обновлённой общей политикой назначений.

## [0.20.1] - 2026-09-24

### Изменено

- Настройки директоров и специализированных ролей GameDev Pipeline переведены на GPT-6 Sol с назначенными уровнями размышления; для QA установлен GPT-6 Luna / medium, для отдельной Coverage Advisory — GPT-6 Sol / high.
- Явные значения моделей в инструкциях требований, спецификации и плана разработки согласованы с общей политикой назначений.

## [0.20.0] - 2026-09-24

### Изменено

- Начальные сведения о задании выдаются одной связной карточкой с полными границами доступа, схемой результата и командами. Доработка получает точный индекс замечаний и адресуемые исходные условия с последними независимыми объяснениями; длинный текст читается по продолжению без ограничения объёма работы. Завершение выбранной части не означает прочтение всего задания.
- `check --with-delivery` дополнительно возвращает привязанный к принятой проверке контекст продолжения. Ошибка экспорта или представления не отменяет уже принятую проверку и не разрешает повторять её под новым ID; прежний маршрут `check` сохранён.
- QA отделяет независимую оценку применимости и наблюдений от автоматического оформления результата. Доказанный пробел обязательной проверки можно честно передать на исправление как `not_run / verification_incomplete`: он делает итог приёмки неуспешным, но не изображает выполненный сценарий или отсутствующий внешний доступ. Не связанные с ним недоступные проверки сохраняются.
- Инструкции реализации и проверки сверяют фактические сценарии до первой сдачи и сохраняют действующие доказательства при переписывании. Общие правила имеют однозначные источники и маршруты чтения применимых разделов вместо повторной загрузки всех руководств.
- Неизменная неуспешная попытка Engineering больше не выдаётся автоматически повторно: native-контроллер направляет её на привязанное к текущему состоянию уточнение у существующих специалистов. Продолжение требует принятой оценки с проверяемыми версиями исходников; оно не закрывает замечания и не даёт PASS. Это внутренний автоматический маршрут, не лимит попыток и не дополнительное согласование с пользователем.
- Полный режим `assignment-read --view work` сохранён для совместимости. Обычный маршрут доработки читает индекс и полные выбранные элементы с точной проверкой списка; неполные legacy-данные не превращаются в пустую работу.
- Директор использует длительное прерываемое ожидание событий вместо коротких периодических пробуждений. Сообщение агента или пользователя обрабатывается сразу; пустой таймаут только продлевает ожидание и не вызывает опросов, повторной передачи контекста или переоценки процесса. Максимум ожидания инструмента не ограничивает время работы специалиста.
- CLI возвращает краткие управляющие ответы по умолчанию, включая `check`; полный диагностический вывод доступен явно через `--full`. Проверка и последующая доставка сохраняют отдельные границы фиксации и replay, в том числе при совместном вызове.
- Доставка v2 выносит неизменное QA-определение в проверяемый общий ресурс и заменяет только точные дубликаты замечаний/свидетельств ссылками. Каноническое состояние и приёмка не меняются; прежние пакеты остаются читаемыми.
- `assignment-read` по умолчанию выдаёт точные поля одного уровня и ссылки на вложенные данные без рекурсивного раскрытия всего контекста. Сохранены явные режимы индекса и полного значения для машинной обработки; полнота вложенных данных не приписывается прочитанной карточке. Инструкции ролей используют готовый bootstrap, сохраняют реально прочитанные неизменные ресурсы и действующие разрешения в фактических методах и prerequisites.
- Engineer и Review переработаны в конкретный, независимый от стека порядок работы: обязательство и ожидаемый результат, фактический рабочий путь, достаточное подтверждение, готовность первой реализации и закрытие последней причины отказа. Review возвращает полный пакет независимо закрываемых условий и сохраняет валидные подтверждения на доработках; Engineering готовность отделена от итогового QA.
- Review получает применимые существующие свидетельства исполнения из того же механизма привязки, что QA, без новых прав на команды или автоматического зачёта. Инженер, ревьюер и Documentation получают точный, соответствующий их роли список условий со ссылками на исходный текст и последнюю независимую проверку.
- Контракт QA явно различает строковое evidence идентичности и массив свидетельств отдельных утверждений; пример Documentation согласован с полями доработки. Старые выданные схемы сохраняют совместимость.
- При самостоятельном native check работник сохраняет дескриптор процесса и собирает результат исходного вызова до продолжения. Пустой stdout или завершение внешней оболочки не разрешают повторную команду, пока внутренний процесс работает.
- Убраны обязательные числовые бюджеты контекста, которые планирование добавляло без запроса пользователя. Доставка опирается на нужные источники, ссылки, страницы, дельты и сохранение незавершённой работы; старые планы читаются без применения их оценок как блокирующих порогов.
- Общие методы QA могут храниться один раз и использоваться через ссылки без потери условий или доказательств.

### Добавлено

- Единый привязанный к утверждённым источникам QA-контракт: условия, разрешённые методы и альтернативы, требуемые свидетельства, применимость, зависимости и конкретные причины `not_run`. Полнота проверяется при любом результате; Engineer, Review и QA получают одну и ту же модель приёмки.
- Отдельное связывание QA-контракта для существующего утверждённого плана без пересоздания PRD/SPEC/PLAN; смена контракта не переносит прежний зачёт QA или изменённых завершённых слайсов.
- Структурированные условия Review и карты исправления/независимого закрытия. Пропущенные и частично исправленные условия остаются открытыми; формат и полнота проверяются до запуска команд.

### Проверка и ограничения

- В сравнительном прогоне ветки `test/optimization_test_1` Engineering и независимый Review приняты; процесс остановлен перед QA. При одинаковых исходных документах относительно v1.19.0 расход Director снизился на 33,4%, общий processing — на 2,7%; длительность осталась практически той же. Один прогон не подтверждает стабильность преимущества или качество полной игровой приёмки.
- Сохраняются известные ограничения QA-ремедиации: точный незакрытый остаток после смены кандидата не всегда становится обязательным входом следующего Review. Корректный формат QA-артефакта сам по себе не подтверждает достаточность его доказательств.

## [1.19.0] - 2026-09-22

### Добавлено

- Единый контракт исполнения и полный дескриптор передачи задания: корень проекта, runtime launcher, назначенный владелец, ссылки и хеши неизменяемого контекста, схема результата, разрешённые пути и точная граница возврата управления.
- Непрерывный цикл Engineer в пределах задания: запуск разрешённой проверки, получение свежих данных, исправление и повторная проверка без обязательного завершения host turn или подтверждения Director после каждого результата. Полномочия на команды контроллера выдаются отдельно и ограничиваются текущим заданием.
- Явное право записи единственного назначенного terminal artifact, включая результаты Review и QA, независимо от права изменения продуктовых файлов.
- Адресная команда `recover-capability` для возобновления после изменения подтверждённого prerequisite с сохранением применимых результатов Engineering, Review, кандидата, свидетельств и владельцев; история блокировки архивируется.
- Неизменяемая привязка runtime к прогону, контролируемое обслуживание и перепривязка, а также контракт возврата управления вызывающей стороне. `step --through-handoff` проводит разрешённые механические переходы до следующей передачи управления.

### Изменено

- Director работает по событиям и карте переходов; инструкции и подробные материалы выдаются по необходимости. Стабильный Engineer сохраняет владение исправлениями, Review и QA остаются независимыми, а рабочий контекст передаётся через ограниченные checkpoints.
- Review собирает обязательные замечания в пределах всего назначенного scope за один проход; повторная проверка учитывает сохранённые findings. Engineer должен закрывать каждое условие составного замечания и приводить соответствующие свидетельства в существующем summary.
- Нативные проверки используют привязанные машинные результаты и консервативное повторное использование применимых свидетельств. Новый логический `check` получает непрозрачный ID вызывающей стороны, отдельный от recipe и ID действий контроллера; повтор неопределённого запроса сохраняет исходный ID и входные данные.
- Фаза Documentation пропускается только при согласованном отсутствии работы и подтверждении этого фактическими артефактами, без искусственного Docs PASS.
- Инструкции ролей используют общие контракты полномочий, технических решений, ошибок и восстановления; удалены дублирующие руководства по UI-вопросам. Явно делегированные решения и incident authority сохраняются без подмены пользовательского согласия или расширения разрешённых действий.

### Исправлено

- Привязка checkout не позволяет историческому URL или унаследованному cwd выбрать чужой проект. Передача полного и изменённого контекста сохраняет текущие Review findings, QA identities и применимые результаты проверок.
- Восстановление синтетического блокера сохраняет предшествующие технические решения и разрешённые изменения исполнения. Реальные семантические изменения проходят Review и QA; перенос recovery evidence ограничен актуальными epoch, scope и кандидатом.
- Уточнены обработка асинхронных процессов, контроль дерева процессов и маршрутизация типизированных ошибок. Исправления результата возвращаются назначенному владельцу с сохранением границ задания и доказательств.
- Неполное обязательное QA-покрытие и недоступные проверки сохраняют фактические `not_run` / blocked; статические результаты и частичные наблюдения не превращаются в полную приёмку.

## [1.18.0] - 2026-09-12

### Исправлено

- Обязательные замечания проверки, результаты QA, текущие технические решения и действующие ответы на вопросы передаются без потери элементов и текста. Старые обрезанные данные восстанавливаются только из соответствующего канонического источника; неполное или непривязанное свидетельство не даёт зачёта.

- Устранена повторная обработка уже сформированного контекста при выдаче задания; замечания Review сохраняются при восстановлении после ремонта контроллера.
- Восстановление после разрешённых изменений рабочего дерева сохраняет историю и ранее выполненную работу без переноса устаревшего зачёта.

### Добавлено

- Универсальные команды экспорта неизменяемого задания, доставки полных данных частями, передачи изменений тому же исполнителю и чтения разрешённых исходников с проверкой версии.
- Краткий режим ответов Director: состояние, действие и привязки без повторного вывода полного задания и журнала.
- Исполнение одного точного механического действия контроллера без повторного написания обёрток; вопросы, восстановление, готовность и отсутствующий результат сохраняют собственные границы.

- Маршруты контролируемого обслуживания активного задания и возврата из заблокированного QA в Engineering по новым подтверждённым дефектам; все переходы привязаны к разрешению, кандидату и актуальному runtime.

### Изменено

- Director ожидает события агентов с десятиминутной проверкой состояния вместо частого опроса. Управление владельцем и потребление каждого результата сохранены.
- Общее ядро инструкций отделено от процедур Director, взаимодействия со средой и сопровождения ремонта. Выбор рабочих материалов отделён от разрешённой области чтения; правила конкретных движков не добавлены.
- Настройки effort для семантической проверки требований, архитектора спецификации, аналитика плана, runtime Plan и Review повышены до `high`; действующие владельцы не заменяются ради применения новых настроек.

## [0.17.0] - 2026-09-08

### Добавлено

- Единый стек-независимый манифест технических решений: Engineer исследует неожиданные ситуации и самостоятельно разрешает технические препятствия в пределах утверждённых требований, продуктовых решений, технологий и обязательных проверок.
- Текущий журнал технических решений на фичу с постоянными ID, перезаписью исправленного решения без цепочек отмен и фиксацией каждого блокера, включая самостоятельно устранённый. Журнал отделён от пользовательской authority и planning DEC ledger.
- Команды technical-observe и technical-decision для контролируемого принятия конкретных сопутствующих файлов и перестановки существующих проверок без расширения продуктовых полномочий или сокращения обязательного покрытия.

### Изменено

- Engineer, Review, QA, Documentation, Director и advisory-роли используют актуальные решения; Review и QA независимо проверяют основания и последствия и возвращают технические ошибки через существующие маршруты исправления.
- Повторные Requirements, Specification и Planning учитывают журнал без автоматического превращения технических решений в требования. Specification связывает helper и review evidence с текущим журналом и поддерживает обновление незавершённой проверки без изменения исходного документа.
- Журнал и применимые технические поправки сохраняются при reinitialization; обновление решения обновляет assignment и зависимый verification credit. При усечении контекста обязательна загрузка текущих записей перед работой или оценкой.

### Исправлено

- Исключены дубли fallback-блокеров, потеря разрешённых сопутствующих путей после перезапуска и требование нового ID при переоценке прежнего решения.
- Загрузчик журнала отклоняет отсутствующую, относительную или чужую привязку проекта. Техническая запись не разрешает обход authority, принятие посторонних изменений или пропуск обязательных проверок.

## [0.16.2] - 2026-09-07

### Изменено

- Значения по умолчанию Sol high заменены на `gpt-6-astra` с `reasoning_effort="low"` для Requirements, Specification и Development Plan, а также semantic review, Architect, Generator/helper, Proofreader, Planning Analyst, runtime Plan и Review. Entrypoints и Specification helper передают обновлённую пару при создании соответствующих workers.
- Сохранены настройки Terra для implementation Director и Engineering (`xhigh`), research, Slice, QA и Coverage Advisory (`high`), Docs (`medium`), приоритет явных overrides и продолжение назначенных workers с прежними настройками.

## [0.16.1] - 2026-09-07

### Изменено

- Добавлена единая политика моделей и reasoning effort для существующих ролей GameDev: Requirements, Specification и Development Plan рекомендуют Sol high, implementation Director и Engineering — Terra xhigh; semantic review и planning используют Sol high, research, Slice, QA и Coverage Advisory — Terra high, Docs — Terra medium.
- Entrypoints стадий и Specification helper передают фактические `fork_turns`, `model` и `reasoning_effort` при создании новых внутренних workers; настройки и применимые overrides передаются в orchestration packet вне immutable assignments, helper schemas и controller state.

### Уточнено

- Явный выбор пользователя и ограничения назначенного владельца сохраняют приоритет. Persistent workers продолжаются с прежними настройками; применение defaults не разрешает замену владельца, перезапуск задачи, новую review wave или reinitialization.
- Рекомендации для новых stage sessions не меняют текущую модель Director и не считаются выбором пользователя при создании видимой Codex task.

## [0.16.0] - 2026-09-06

### Исправлено

- Specification поддерживает пересмотр утверждённого PRD во время незавершённой генерации и review: прежняя authority и helper evidence архивируются без переноса readiness credit; superseded helper request закрывается только с зафиксированным terminal handoff, после чего выполняется свежая конвергенция.
- Proofreader evidence теперь берётся из фактического UTF-8 отчёта с проверкой назначенного автора, PRD/spec SHA, findings и unresolved questions; controller хранит SHA отчёта и не выдаёт новый credit для отсутствующих или изменённых evidence bytes.
- Передача Specification новому Architect требует его собственного exact-SHA preaccept и свежего acceptance. Добавлена ранняя передача до первого acceptance/review без искусственных циклов и hold.
- QA pass требует точного набора обязательных identities из утверждённого плана и одного результата с evidence на каждую identity; пропуски, дубли, посторонние IDs, fail и not_run не дают phase credit. После Docs учитывается обязательное покрытие завершённых slices.
- Замечания Review к документации возвращаются Documentation Finisher с утверждёнными путями; product Review и QA failures возвращаются Engineering. Владелец исправления определяется назначенной фазой и target, а не текстом finding.
- Runtime reconfiguration сохраняет историю и retained Engineering paths, включает их в последующий scope и Review target и сбрасывает устаревший phase credit. Добавлены ограниченное принятие явно авторизованного prerequisite baseline после первого Engineering blocker и перепривязка idle run после отдельно разрешённого runtime maintenance.

### Уточнено

- Director после потребления результата worker продолжает разрешённый controller next_action; завершение отдельной фазы не завершает run. Ошибка формата возвращается тому же владельцу для исправления только artifact в неизменном assignment.
- Technical questions допустимы только при pass и внутри согласованной authority; product/scope conflicts используют blocked с точным upstream decision. Сохраняются назначенные владельцы стадий, ограничения пользователя и источник каждого ограничения.
- Engineering и QA могут применять доступные editor/computer tools в пределах соответствующих persistent и temporary прав. Перед действием требуется установить фактический эффект и destination; прежняя авторизация сохраняется для того же действия и назначения. Непроверенный production path не получает credit из fixture или aggregate tests.
- Уточнены read-delivery после усечения вывода, сериализация утверждённых методов в caller-owned planned_commands и восстановление после blocker через существующий status/init при разрешённом prerequisite, включая source-grounded опровержение ошибочно заявленного authority conflict.
- Planning documentation приведена к текущей schema 3 Specification и фактическим runtime механизмам: advisory capability IDs, context estimates, research briefs и handoff context не описываются как отсутствующие автоматические gates или generated state.

### Совместимость

- Coverage Contract требует непустой точный список mandatory_identity_ids; QA checks имеют форму {id, outcome, evidence}. record-proofread принимает назначенный Proofreader и путь к отчёту вместо дублирующих счётчиков и флагов результата.

## [0.15.0] - 2026-09-04

### Изменено

- Requirements discovery теперь опирается только на активную задачу, фактически определённый стек проекта, инструкции и соглашения текущего репозитория, текущий PRD и минимально необходимый source evidence; абстрактные чек-листы, чужие стеки и поиск необязательных улучшений исключены.
- Ответы на нумерованные вопросы обрабатываются независимо и дают authority только соответствующему решению; просьба об уточнении не считается ответом, а неоднозначность или противоречие сначала разрешается минимальным отдельным вопросом без потери остальных подтверждённых ответов.
- Интервью стало clarification-first: один компактный раунд содержит до пяти, а не обязательно пять, наиболее значимых вопросов; если prerequisite или конфликт блокирует остальные решения, сначала задаётся один уточняющий вопрос.
- Рекомендации и варианты обязаны быть полезными и обоснованными текущим проектом: применимые best-practice и существенно более простые альтернативы допускаются без выдумывания вариантов ради количества и без требования искусственной взаимоисключаемости совместимых решений.
- Persistent read-only subagent lanes запускаются условно только для нетривиального исследования, review или явной делегации; root Requirements сохраняет исключительное владение интерпретацией решений, canonical PRD и approval, потребляет все terminal results и следует общей ссылке на stage handoff invariant с порогами checkpoint/handoff 70/90.
- Промежуточный discovery output сокращён до важных новых решений, blockers, evidence и следующего material question; revision, ID и SHA boilerplate требуется только в terminal handoff.

### Уточнено

- Approval разрешён только для показанной пользователю точной текущей revision после подтверждения её полноты, feasibility и testability; conditional approval не распространяется на невидимые semantic edits, а каждый material behavior должен иметь observable acceptance и требуемую evidence category.
- Evidence явно разделяется на static inspection, compilation/build, automated runtime, interactive editor runtime, published/deployed execution и manual observation; ни одна категория, validator, reviewer, demo, sample, fixture, example или placeholder не получает более сильную доказательную или product authority автоматически.
- Завершение Requirements не запускает следующую стадию автоматически: handoff ограничен готовностью текущего PRD и точными данными текущего workflow.

## [0.14.1] - 2026-09-04

### Исправлено

- Specification controller теперь определяет канонический JSON SHA-256, используемый путями authority `accept-spec`, что предотвращает воспроизведённый `NameError`.
- Корректные correction cycles теперь допускают изменение байтов и revision, при этом принятая revision независимо привязана к входу active wave; подменённый acceptance при byte-noop отклоняется, а для уже активных wave schema 3 binding восстанавливается.

## [0.14.0] - 2026-09-04

### Изменено

- После запуска phase worker Director обязан дождаться его terminal result, подтвердить через public controller status владение exact active assignment и returned output artifact, выполнить exact `complete`, включая `blocked`, и снова прочитать status; финальный ответ запрещён, пока child остаётся live или завершённый artifact не потреблён контроллером.
- Write scope каждого slice теперь является единым ordered contract: `Owned Paths`, `Scope Contract.editable_paths` и runtime `allowed_paths` должны точно совпадать по составу и порядку. `Expected Paths` остаются отдельным read/integration context, не дают write authority, должны быть disjoint с write scope и покрываться sealed Context Capsule read scope.

### Совместимость

- Ранее принятые планы с несовпадающими или переставленными write scopes либо некорректными `Expected Paths` теперь отклоняются fail-closed и требуют исправления, повторной валидации и approval, а затем fresh runtime `init`.

## [0.13.0] - 2026-09-03

### Изменено

- Requirements передаёт точные `FEATURE` и `WORKFLOW_PATH`, а контроллеры Specification, Development Plan и Pipeline требуют явный `--feature` и работают только с выбранным workflow.
- Все служебные состояния и evidence одного процесса размещаются в `.agentic-pipeline/Workflows/<feature>/`: `specification-state.json`, `development-plan-state.json`, `pipeline-state.json`, lock, helper requests/results, review receipts и assignment outputs.
- Схемы Specification, Development Plan и Pipeline повышены до 3, 2 и 4 соответственно; прежние состояния без feature/workflow binding несовместимы и требуют свежей инициализации в новом каталоге.

### Исправлено

- Параллельные процессы разных features больше не блокируют друг друга общими state-файлами, одинаковыми helper/assignment ID или активными стадиями соседнего workflow.
- Контроллеры не сканируют, не архивируют, не перемещают и не удаляют соседние workflow; скопированное чужое состояние, несовпадающая authority и небезопасный путь отклоняются до записи.

### Удалено

- Удалено переключение Specification через архивирование завершённой другой feature и частный recovery `supersede-helper-request`; изоляция обеспечивается непосредственно namespace выбранного workflow.

### Проверено

- Feature-isolation regressions: 7/7 PASS; сквозной A/B сценарий с проверкой побайтовой неизменности соседнего workflow: 1/1 PASS; затронутые Runtime regressions: 4/4 PASS.
- Все изменённые Python-модули проходят `py_compile`, а `git diff --check` не находит ошибок. Полный regression suite не запускался.

## [0.12.0] - 2026-09-03

### Изменено

- Pipeline v2 упрощён до schema 3: `blocked` завершает run с требованием fresh `init`, Review/QA failures напрямую возвращают Engineering без `resume` gates, а workers больше не запускают controller-owned checks или внешние интерактивные mutators.
- Candidate boundary применяет единую Git-классификацию: tracked controller/history artifacts остаются в истории репозитория, но не входят в product candidate; repository policies остаются governed только там, где способны влиять на видимые candidate paths.
- Plan и Specification проверяют bound runtime через текущую каноническую schema-модель; удалённая gate-модель больше не участвует в sanctioned revision и quiescence checks.

### Исправлено

- Инициализация Specification безопасно архивирует завершённый `SPEC_READY` workflow другой feature в `.agentic-pipeline/Workflows/<feature>`, сначала валидирует новые входы и повторно проверяет prior acceptance; nonterminal, active, linked, внешние, неоднозначные источники и непустое место назначения отклоняются fail-closed.
- Post-complete checkout drift теперь отзываeт устаревший candidate credit и возвращает точный `checkout_recovery_required` вместо сохранения ложного `ready` для изменившихся байтов.

### Проверено

- Shared operational invariant: 6/6 PASS.
- Bound runtime schema-3 regressions для Development Plan: 5/5 PASS.
- Specification archive и sanctioned revision regressions: 8/8 PASS.

## [0.11.0] - 2026-09-02

### Добавлено

- Specification helper request теперь привязан к точному пути и SHA-256 текущего GameDev controller; перед публикацией immutable result внешний helper получает controller-issued preflight envelope, который подтверждает request/output/controller chain, authority, язык и разрешённую write boundary.
- Добавлен ограниченный `reject-helper-result` recovery для несовместимого pre-preflight результата начальной generation: controller сохраняет specification и evidence bytes, фиксирует audit receipt и выдаёт новый последовательный generation request, а drift, повторное использование и более поздний workflow progress отклоняются fail-closed.

### Изменено

- Pipeline v2 использует Git tree как единственную candidate boundary: чистый committed baseline, `base_tree_oid`/`candidate_tree_oid`, tracked и новые non-ignored пути, без физической inventory, engine profiles и контроля ignored editor/cache файлов.
- Planned commands обязаны оставлять Git candidate tree неизменным; изменения `.gitignore`, `.gitattributes` или `.gitmodules` требуют fresh `init`, а runtime привязан к digest фиксированного production manifest.
- `blocked` semantic artifact требует `blocker` и `required_action`, закрывает assignment без запуска planned commands и без candidate/phase credit; exact replay также не запускает checks.
- При подозрении на дефект pipeline/controller/runtime/skill агент обязан остановить product run, подробно и redacted сообщить incident и не имеет права самостоятельно менять или обходить pipeline без новой явной maintenance-команды пользователя.
- Schema-10 bridge заменён явным fail-closed tombstone: legacy state/findings архивируются, после чего запускаются свежие Plan/`init`; import и reconstruction больше не выполняются.

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

[Unreleased]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.14.1...HEAD
[0.14.1]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.14.0...v0.14.1
[0.14.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/teano/agentic_game_development_pipeline_codex/compare/v0.10.0...v0.11.0
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
