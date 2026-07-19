---
title: "context-mode и Dynamic Context Pruning: управление контекстом coding agents"
date: 2026-07-19T20:18:51+03:00
---

## Аннотация

`context-mode` и Dynamic Context Pruning (DCP) решают одну задачу разными способами: уменьшают объём истории, которую coding agent отправляет модели. `context-mode` заранее направляет большие данные в локальный MCP server, индексирует их и возвращает модели только результат поиска или вычисления. DCP работает внутри OpenCode и перед очередным запросом заменяет старые сообщения summary и placeholders.

Выбор зависит от источника лишнего контекста. `context-mode` подходит для логов, HTML, JSON и больших файлов, если agent может получить их через инструменты плагина. DCP полезнее в длинных сессиях OpenCode, где tool outputs уже накопились в истории. Оба инструмента стоит сначала проверять в изолированном пилоте: опубликованные данные подтверждают сокращение контекста, но не доказывают сохранение качества на произвольных задачах.[^1][^2]

## Короткий ответ

| Сценарий | Рекомендация |
|---|---|
| Большие локальные файлы, логи, HTML или JSON | Проверить `context-mode` с явными вызовами MCP tools |
| Длинная история OpenCode с повторяющимися tool outputs | Проверить DCP в manual mode |
| Большой ответ уже вернул сторонний MCP server | `context-mode` не удалит его из текущей истории; DCP сможет сократить его только в OpenCode |
| Короткие сессии и небольшие ответы | Не устанавливать дополнительный plugin |
| Критичны старые approvals, точные errors или детали миграции | Не включать автономное сжатие без проверки summary |

## Как работает context-mode

`context-mode` добавляет MCP server и набор hooks. Инструменты плагина сохраняют большие результаты команд, страниц и файлов в SQLite с FTS5-индексом, а в model context возвращают короткий результат поиска, агрегат или ссылку на сохранённые данные.[^1] Дополнительные tools выполняют JavaScript или shell над данными и передают модели только вычисленный итог.

Это не сжатие всей истории перед запросом к модели. Agent должен заранее выбрать `ctx_*` tool или получить от hook указание изменить маршрут. Если сторонний MCP server уже вернул большой payload, `context-mode` не может задним числом убрать его из истории Codex.[^3][^4]

Такой подход даёт два преимущества:

- исходные данные остаются в локальном поисковом индексе и доступны через `ctx_search`;
- модель получает только нужные фрагменты или итог вычисления.

Ограничения следуют из той же архитектуры:

- выигрыш зависит от правильной маршрутизации до получения данных;
- retrieval может пропустить редкую, но важную деталь;
- `ctx_execute` и связанные tools исполняют код с правами MCP-процесса, а не в полноценном OS sandbox;[^1]
- hooks требуют отдельного доверия со стороны Codex.[^5]

Собственный benchmark проекта показывает значительное сокращение объёма вывода, но измеряет прежде всего размер результата. Он не проверяет, завершит ли agent реальную задачу без потери важных деталей.[^2]

## Как работает Dynamic Context Pruning

DCP — npm plugin для OpenCode. Он использует `experimental.chat.messages.transform`, добавляет tool `compress` и перед отправкой запроса заменяет выбранные сообщения summaries и placeholders.[^6][^7][^8] Исходная история сессии остаётся в storage, поэтому отдельное сжатие можно отменить через `/dcp decompress`.[^6]

DCP применяет три механизма:

- `compress range` выбирает завершённый участок истории и создаёт техническое summary;
- deduplication удаляет старые результаты одинаковых tool calls с одинаковыми arguments;
- purge errors удаляет крупные inputs неуспешных calls после нескольких turns, сохраняя error message.[^6][^8]

DCP работает позже, чем `context-mode`: данные уже попали в историю, после чего plugin сокращает будущие запросы. Поэтому он лучше подходит для длинных сессий OpenCode и старых ответов сторонних tools.

У подхода есть обратная сторона. Модель видит summary вместо исходных сообщений, пока пользователь не выполнит decompression. Качество зависит от выбранного диапазона, prompt и модели. Известны случаи, когда summaries оказывались больше исходного фрагмента или переносили старое разрешение пользователя как действующее.[^9][^10]

## Сравнение

| Критерий | context-mode | DCP |
|---|---|---|
| Поддерживаемый host | Codex и другие MCP clients[^1] | Только OpenCode[^6] |
| Момент обработки | До попадания большого результата в историю | Перед следующим model request |
| Основной механизм | Execution-over-data, FTS5 index, routing hooks | Summary, deduplication, purge errors |
| Уже накопленная история | Не переписывается | Сокращается для будущих запросов |
| Возврат к детали | Поиск по индексу | Summary или ручной decompress |
| Дополнительное исполнение кода | Есть в `ctx_execute` | Отдельного универсального executor нет |
| Главный риск качества | Retrieval miss или устаревший индекс | Semantic drift в summary |
| Публичная оценка task success | Нет независимого A/B benchmark | Нет опубликованного task-success benchmark[^11] |

## Когда использовать context-mode

Пилот оправдан, если одновременно выполняются три условия:

1. Сессии регулярно обрабатывают большие логи, HTML, JSON или файлы.
2. Эти данные можно получать через `ctx_execute`, `ctx_execute_file` или `ctx_fetch_and_index`.
3. Уже измерена проблема: compaction теряет детали, задачи требуют повторного чтения либо растут latency и input tokens.

Плагин не даст большого выигрыша, если основные источники уже используют filters и pagination или если объёмные данные приходят только из сторонних MCP servers. Не стоит устанавливать его только ради заявленного процента экономии без проверки task success.[^2]

Для первого пилота:

1. Использовать отдельный Codex profile или изолированный `CODEX_HOME`.
2. Сначала вызывать MCP tools явно, без routing hooks.
3. Выбрать повторяемые задачи с большими файлами, логами и web-страницами.
4. Сравнить baseline и вариант с `context-mode` при одинаковых model и reasoning effort.
5. Измерить task success, повторные чтения, elapsed time, compaction, input tokens и peak RSS.
6. Проверять hooks отдельным экспериментом, потому что они меняют маршрутизацию.

Внутреннюю статистику `ctx_stats` следует считать диагностикой. В issue проекта зафиксированы противоречивые значения savings, поэтому решение лучше принимать по внешним метрикам и результату задач.[^12]

## Когда использовать DCP

DCP подходит для сессий OpenCode, которые регулярно состоят из десятков turns, а старые tool outputs занимают заметную часть каждого запроса. Для коротких задач plugin обычно не нужен: compression добавляет model/tool call и меняет prompt prefix.

Безопасная начальная конфигурация:

1. Установить точную версию пакета, а не плавающий диапазон.
2. Выключить `autoUpdate`, чтобы поведение не менялось между A/B-запусками.[^13]
3. Включить `manualMode.enabled: true`.
4. Запрашивать compression после завершения этапа исследования, а не во время approval, миграции или deploy.
5. Проверять каждое summary: оно должно быть короче исходного диапазона и сохранять paths, errors и принятые decisions.
6. Сравнивать provider input/cache tokens, повторные чтения, task success и итоговый diff.

Автономный режим не стоит включать, пока пилот не подтвердит сохранение результата. Особая осторожность нужна там, где старые approvals или граница между plan и write имеют юридическое или операционное значение: summary не должно выдавать новые полномочия.[^10]

## Риски эксплуатации

Оба плагина расширяют доверенную поверхность agent-среды.

Для `context-mode` это отдельный Node.js-процесс, SQLite index, hooks и tools для исполнения кода. В проекте также были открыты issues о статистике, восстановлении состояния и ранжировании памяти.[^12][^14][^15] Поэтому индекс требует контроля срока хранения, а важные выводы — проверки по первичному источнику.

Для DCP основные риски связаны с качеством summary, experimental hook API и обновлениями пакета. Есть reports об ошибках загрузки из-за runtime dependencies и о feedback loop с отрицательной экономией.[^9][^16] Исходная история позволяет выполнить decompression, но модель не сделает это сама, если summary выглядит правдоподобно.

Перед внедрением следует также проверить лицензии: `context-mode` распространяется по Elastic License 2.0, DCP — по AGPL-3.0-or-later.[^1][^17]

## Рекомендации

`context-mode` стоит рассматривать как специализированный слой для работы с большими данными, а не как глобальную замену обычным tools. Начинать лучше с явных вызовов на задачах, где исходные данные велики и доступны через `ctx_*` tools.

DCP стоит рассматривать как инструмент обслуживания длинной истории OpenCode. Начальный режим — ручное сжатие, фиксированная версия и просмотр каждого summary. Autonomous mode требует отдельного подтверждения на реальных задачах.

Если проблема с контекстом не измерена, сначала достаточно ограничить tool output у источника: использовать filters, pagination, узкие запросы и сохранять большие артефакты в файлы. Дополнительный plugin оправдан только тогда, когда даёт воспроизводимый выигрыш без снижения task success.

## Ограничения оценки

- Нет независимого task-success benchmark для актуальных версий обоих плагинов.
- Benchmark `context-mode` подтверждает сокращение объёма, но не качество решения задач.[^2]
- DCP зависит от experimental API OpenCode, модели и prompt для summary.[^6]
- Release status, defaults и открытые issues меняются; срез зафиксирован на 19 июля 2026 года.

## Quality Metrics

| Метрика | Значение |
|---|---:|
| Проверенных проектов | 2 |
| Процитированных источников | 17 |
| Основные типы источников | документация, исходный код, issues |
| Независимый task-success benchmark | не найден |

[^1]: context-mode, [README: architecture, tools and security model](https://github.com/mksglu/context-mode/blob/main/README.md).
[^2]: context-mode, [BENCHMARK.md](https://github.com/mksglu/context-mode/blob/main/BENCHMARK.md).
[^3]: context-mode, [Codex hook capabilities and limitations](https://github.com/mksglu/context-mode/blob/main/src/adapters/codex/hooks.ts).
[^4]: context-mode, [external MCP routing hook](https://github.com/mksglu/context-mode/blob/main/hooks/routing-block.mjs).
[^5]: OpenAI, [Build plugins: hooks require explicit trust](https://developers.openai.com/codex/plugins/build/).
[^6]: Dynamic Context Pruning, [README: mechanism, defaults and project status](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/blob/master/README.md).
[^7]: Dynamic Context Pruning, [OpenCode plugin hooks](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/blob/master/index.ts).
[^8]: Dynamic Context Pruning, [message pruning implementation](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/blob/master/lib/messages/prune.ts).
[^9]: DCP issue [#573: compression feedback loop and net-negative summaries](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/issues/573).
[^10]: DCP issue [#560: stale approval replayed through compressed context](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/issues/560).
[^11]: DCP issue [#437: request for compression-efficiency and re-read metrics](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/issues/437).
[^12]: context-mode issue [#950: ctx_stats reports impossible savings](https://github.com/mksglu/context-mode/issues/950).
[^13]: Dynamic Context Pruning, [automatic update implementation](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/blob/master/lib/update.ts).
[^14]: context-mode issue [#902: stale resume snapshot](https://github.com/mksglu/context-mode/issues/902).
[^15]: context-mode issue [#895: stale memory can outrank current-session results](https://github.com/mksglu/context-mode/issues/895).
[^16]: DCP issue [#585: latest plugin silently fails to load in one OpenCode configuration](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/issues/585).
[^17]: Dynamic Context Pruning, [package.json](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning/blob/master/package.json).
