---
title: "Как измеряют эффективность LLM в задачах программирования"
date: 2026-07-06T21:06:00+03:00
---

_Методологический обзор: бенчмарки, курирование задач, постановка задачи модели, форматы решений, execution-грейдинг и sandbox-инфраструктура._

Оценка кода отличается от оценки генеративного текста одним свойством: у неё есть объективный оракул. Компилятор, тесты, линтер и type-checker дают ground-truth без арбитра-человека и без LLM-судьи. Это делает измерение кодинг-способности одновременно строже (есть чёткий проход/провал) и тоньше (то, как поставлена задача и как устроен грейдинг, сдвигает результат сильнее, чем сама «способность» модели). Обзор проходит по всей цепочке измерения — от того, из чего собирают задачу, до того, в каком контейнере её грейдят.

Три семейства бенчмарков задают три разных вопроса. **Function-level** (HumanEval, MBPP, BigCodeBench) — «напиши функцию по docstring». **Competition-level** (LiveCodeBench, CodeContests) — «реши олимпиадную задачу». **Repository-level / agentic** (SWE-bench и производные, RepoBench, Commit0, Terminal-Bench, Aider polyglot) — «внеси правку в реальный репозиторий, чтобы прошли тесты». Разброс результатов между семействами огромен: одна и та же модель даёт 84–89% на синтетических function-level задачах и лишь 25–34% на реальных class-level задачах.[^22] Эта пропасть — не шум, а следствие того, что именно измеряют.

## Ландшафт бенчмарков

| Бенчмарк | Источник | Размер | Что меряет | Метрика |
|---|---|---|---|---|
| HumanEval | Chen et al. 2021[^4] | 164 рукописных задачи, в среднем 7.7 тестов на задачу | Синтез автономной Python-функции по docstring | pass@k (unbiased estimator) |
| MBPP | Austin et al. 2021[^5] | 974 задачи (374 в fine-tuning-подмножестве) | Короткие функции для начинающих, 3 assert-теста на задачу | pass rate |
| BigCodeBench | Zhuo et al. 2024[^6] | 1 140 задач, 139 библиотек, 7 доменов, 5.6 тестов на задачу, 99% branch coverage | Композиция вызовов функций как инструментов по сложной инструкции | pass rate (Complete / Instruct) |
| LiveCodeBench | Jain et al. 2024[^10] | 400 задач (май 2023 – май 2024), пополняется во времени | Contamination-free оценка на задачах с LeetCode/AtCoder/CodeForces | pass@k, с фильтром по дате релиза |
| CodeContests | Li et al. 2022 (AlphaCode)[^8] | 13 328 train / 117 valid / 165 test | Олимпиадное программирование | solve rate; FP-rate снижен с 30–60% до 4% |
| RepoBench | Liu et al. 2023[^7] | ~25 тыс. train-репо; 1 075 Python + 594 Java test-репо | Retrieval кросс-файлового контекста, next-line completion, pipeline | Accuracy@k, Exact Match / Edit Similarity |
| Commit0 | Zhao et al. 2024[^9] | 54 Python-библиотеки | Генерация библиотеки с нуля по спеке + интерактивным тестам | unit-test pass rate |
| Aider polyglot | Aider 2024[^11] | 225 Exercism-задач, 6 языков (C++, Go, Java, JS, Python, Rust) | Способность решить и корректно применить правку к файлу | pass_rate_# + доля корректного edit-format |
| Terminal-Bench | 2026[^16] | 89 задач (2.0) | Многоходовые CLI-задачи в контейнере, грейдинг по конечному состоянию | pass rate по тестам состояния |
| SWE-bench | Jimenez et al. 2023[^1] | 2 294 задачи из 12 Python-репо | Резолвинг реальных GitHub-issue правкой-патчем | resolve rate (% resolved) |
| SWE-bench Verified | swebench.com[^2] | 500 задач (human-filtered) | То же, но с отфильтрованными некорректными задачами | resolve rate |
| SWE-bench Lite | swebench.com[^29] | 300 задач + 23 dev | Упрощённое однофайловое подмножество | resolve rate |
| SWE-bench Multimodal | 2024[^30] | ~517 test-задач (JS, визуальные) | Issue с изображениями/UI на JavaScript | resolve rate |
| SWE-bench Pro | Scale AI 2025[^31] | 1 865 задач, 41 репо (public/held-out/commercial) | Долгогоризонтные многофайловые правки, contamination-resistant | resolve rate + 95% CI |

Две вещи в этой таблице стоит держать в голове при чтении дальнейшего. Первая: размер многих repo-level наборов измеряется сотнями задач, а не тысячами — SWE-bench Lite это 300 задач, Verified 500. На таких размерах доверительный интервал широкий (об этом ниже). Вторая: «resolve rate» и «pass@k» — не одно и то же, и их нельзя сравнивать между бенчмарками напрямую.

## Метрики: pass@k, resolve rate, pass^k

**pass@k** ввели вместе с HumanEval.[^4] Наивная оценка «сгенерировать одну попытку, проверить, посчитать долю» имеет высокую дисперсию, а формула `1−(1−p)^k` смещена. Вместо этого генерируют n ≥ k образцов (в оригинале n = 200), считают число прошедших c и берут несмещённый estimator:

pass@k := 𝔼[ 1 − C(n−c, k) / C(n, k) ]

Смысл — вероятность, что хотя бы одна из k независимых попыток верна. pass@k растёт с k и отражает выигрыш от inference-time масштабирования: чем больше сэмплов, тем выше шанс, что среди них найдётся правильный.

**resolve rate** в SWE-bench устроен иначе — это доля задач, где патч применился и прошёл двойную проверку тестами.[^1] Задача считается resolved, только если выполнены оба условия: все **FAIL_TO_PASS** тесты (падали до патча, должны пройти после — это подтверждает, что фикс работает) и все **PASS_TO_PASS** тесты (проходили до и должны проходить после — это ловит регрессии). Семантика подтверждается прямо в коде harness (`grading.py`): статус `FULL` = «fail-to-pass = 1 и pass-to-pass = 1», и только `FULL` даёт `resolved = True`.[^28] В оригинальной статье на каждую задачу приходится минимум один fail-to-pass тест и медиана 51 дополнительный тест на проверку сохранности прежней функциональности.[^1] Это ключевой момент: resolve rate по построению штрафует за регрессии, а не только награждает за фикс.

**pass^k** (pass-hat-k) — метрика надёжности, зеркальная к pass@k.[^36] Если pass@k — «хотя бы одна из k попыток удалась», то pass^k — «все k попыток удались»: pass^k := 𝔼[ C(c, k) / C(n, k) ]. Она измеряет консистентность, а не потолок. Разрыв велик: у gpt-4o на τ-retail pass^1 ≈ 61%, но pass^8 < 25%. Модель, решающая задачу «иногда», решает её «каждый раз» втрое реже.[^36] Для промышленного применения, где важно не «может ли модель в принципе», а «сделает ли надёжно», pass^k честнее pass@k.

Есть и метрика самого процесса правки. Aider отдельно репортит **долю корректного edit-format** — как часто модель произвела правку в том формате, который задан в system-prompt и который harness способен применить.[^13] Это измеряет instruction-following в узком, но критичном месте: правка, которую нельзя применить, эквивалентна нерешённой задаче независимо от качества кода.

## Курирование задач и контроль загрязнения

Откуда берут задачи, определяет, что бенчмарк на самом деле проверяет. HumanEval и MBPP — рукописные/краудсорсные функции.[^4][^5] CodeContests и LiveCodeBench — скрейп с соревновательных платформ.[^8][^10] SWE-bench — реальные пары «issue + merged PR» из истории 12 open-source Python-репозиториев: issue даёт задачу, тесты из PR дают оракул, gold-патч даёт эталон.[^1]

**«Verified» — это ручная фильтрация.** SWE-bench Verified собран в коллаборации с OpenAI: аннотаторы прошли по каждой из 500 задач и оставили только те, где описание проблемы понятно, тест-патч корректен, а задача решаема из доступной информации.[^2] Цель — убрать два класса брака: underspecified задачи (условие допускает несколько трактовок, а скрытый тест проверяет лишь одну) и несправедливо оцениваемые задачи (тест требует того, чего в условии нет). SWE-bench Lite фильтрует по структуре: убраны задачи с изображениями, внешними ссылками, правкой более одного файла, gold-патчем более чем в 3 hunk'а.[^29]

Насколько хорошо фильтрация работает — предмет отдельной критики. SWE-Bench+ прошёл по исходному SWE-bench и нашёл, что 27.8% «подозрительных» фиксов содержат утечку решения прямо в тексте issue или комментариях, а 41.4% имеют слабые тесты, не проверяющие корректность по-настоящему.[^18] Даже отфильтрованный Verified, по их измерению, сохраняет 1.5% фиксов с утечкой и 7.5% слабых тестов.[^18] То есть ручное курирование снижает брак, но не обнуляет его.

**Загрязнение (contamination) — системная проблема, а не крайний случай.** Несколько независимых работ показывают, что высокие числа на популярных бенчмарках частично объясняются тем, что задачи попали в обучающие данные:

- **SWE-Bench Illusion**[^17] показывает, что SoTA-модели угадывают путь к «багованному» файлу с точностью до 76%, имея только текст issue и не видя структуру репозитория; на репозиториях вне SWE-bench та же способность падает максимум до 53%. Прямой прайм-пробинг даёт instance-level дословное совпадение от 11.7% до 31.6% — авторы читают это как memorization, а не reasoning.
- **Rephrased Samples**[^20] демонстрирует, что простые вариации (перефразирование, перевод) обходят стандартную дедупликацию: 13B-модель, переобученная на перефразированном тесте, догоняет GPT-4. В претрейн-наборах RedPajama и StarCoder-Data 8–18% HumanEval пересекается с обучающими данными.
- **LiveCodeBench** отвечает на это архитектурно: у каждой задачи есть дата релиза с контеста, и модель меряют только на задачах, вышедших после её training cutoff.[^10] Метод сам вскрывает загрязнение — у DeepSeek-моделей заметный провал качества на задачах после августа 2023 (прямо перед релизом), что указывает на contamination более ранних.

Публично об этом высказалась и OpenAI: в блоге «почему мы больше не оцениваемся на SWE-bench Verified» команда объясняет отказ underspecified-задачами и тем, что фронтир-модели воспроизводят специфику gold-патча.[^27] Отдельно существует **SWE-bench Pro** — набор потруднее, где contamination-устойчивость достигается тем, что репозитории берут под copyleft-лицензиями (маловероятно попадание в проприетарный претрейн), исключают тривиальные правки в 1–10 строк и держат held-out и commercial сплиты закрытыми.[^31] Разрыв показателен: топ-модели Opus 4.1 и GPT-5 дают там 23% против более 70% на Verified.[^31]

Крайняя форма проблемы — **reward hacking**: агент не решает задачу, а обманывает оракул. Terminal Wrench собрал 331 terminal-agent-окружение из популярных open-бенчмарков, все демонстрируемо взламываемые, с 3 632 траекториями эксплойтов, где verifier обходят, а не решают задачу.[^23] Инспекция логов в Holistic Agent Leaderboard вскрыла агентов, которые ищут бенчмарк на HuggingFace вместо решения задачи.[^21] Execution-оракул объективен, но не защищён от манипуляции самим оракулом.

## Постановка задачи модели

Реальные кодовые базы не влезают в контекст (в SWE-bench в среднем 438K строк), поэтому центральный вопрос — какой контекст дать модели.[^1] Исторически сложились три режима.

**Oracle** — модели дают ровно те файлы, что правил gold-патч.[^1] Это верхняя граница и заведомо нереалистично: инженер заранее не знает, какие файлы трогать. **BM25 (sparse retrieval)** — разреженный поиск подтягивает релевантные файлы под лимит контекста (в оригинале пробовали 13K/27K/50K токенов).[^1] **Agentic navigation** — модель сама ходит по репозиторию инструментами; в оригинальной статье 2023 года этого режима ещё не было (только oracle и BM25), он появился позже с SWE-agent и последователями.[^1] Разрыв между режимами велик: на моделях 2023 года oracle давал примерно в 2.5–3× больший resolve rate, чем BM25 (Claude 2: 4.8% против 1.96%).[^1] Вывод, важный методологически: результат сильно зависит от качества поданного контекста, а не только от «ума» модели.

Как модель взаимодействует с репозиторием, задаёт **scaffold** (harness). Здесь есть спектр от полностью агентного до полностью фиксированного:

- **SWE-agent** ввёл agent-computer interface (ACI): специальные команды `find_file`/`search_file`/`search_dir` (не более 50 результатов на запрос), файл-вьюер окном в 100 строк, команда `edit` с заменой диапазона строк и встроенным линтером, отбраковывающим невалидные правки.[^3] Агент работает в ReAct-цикле: на каждом шаге мысль + команда + инкорпорация вывода. ACI дал +64% относительно shell-only-бейзлайна, а сам SWE-agent с GPT-4 Turbo поднял resolve rate с прежних 3.8% до 12.47%.[^3]
- **OpenHands** (ex-OpenDevin) — платформа, где действия и наблюдения агента образуют event stream; унифицированное action-space по образцу CodeAct позволяет исполнять произвольный Python и bash в изолированном Docker-контейнере, в который монтируют рабочую директорию.[^33]
- **Agentless** — контрпример: авторы прямо спрашивают «а нужны ли вообще автономные агенты?» и строят фиксированный трёхфазный конвейер localization → repair → patch validation без права LLM решать следующие действия и без сложных инструментов.[^32] Результат — 32.00% на SWE-bench Lite при средней стоимости $0.70 на задачу, дешевле открытых агентных систем. Это прямой довод, что структура процесса может заменять агентную свободу.
- **Moatless Tools** — та же философия «строить хорошие инструменты, а не полагаться на reasoning агента»; предлагает function-calling и ReAct-варианты под разные модели.[^34]

Бюджет тоже часть постановки. В агентных harness обычно ограничивают не число шагов, а стоимость: у SWE-agent per-instance-бюджет $4, при превышении текущие правки сабмитятся автоматически; успешные решения GPT-4 завершаются в медиане за $1.21 и 12 шагов против $2.52 и 21 шага у неуспешных, и авторы заключают, что повышение бюджета вряд ли сильно поднимет качество.[^3]

## Форматы решения

Способ, которым модель выражает правку, — измеримая ось, а не деталь реализации. SWE-bench требует **патч-файл** (unified diff), указывающий, какие строки менять; грейдинг применяет его через unix `patch` и гоняет тесты.[^1] Aider систематизировал спектр edit-форматов и померил их влияние:[^15]

- **whole** — модель возвращает файл целиком. Проще всего для LLM, но дорого по токенам и упирается в лимит размера файла.[^13]
- **diff (search/replace)** — набор блоков «найти/заменить»; модель возвращает только изменившиеся куски, что эффективнее и снимает потолок размера файла.[^15]
- **udiff (unified diff)** — упрощённый unified-diff, вводился в основном под GPT-4 Turbo, потому что снижал его «ленивое» кодирование с плейсхолдерами.[^15]
- **diff-fenced** — путь к файлу внутри fence; под Gemini, который иначе путается в fencing.[^15]

Влияние формата измеримо. Переход GPT-4 Turbo с search/replace на unified diff поднял его результат на code-editing-бенчмарке Aider с 20% до 61% и втрое снизил «ленивые» правки.[^14] Отключение гибкого патчинга давало 9-кратный рост ошибок правки.[^14] Поэтому измеряют не только «решила ли модель задачу», но и «смогла ли выразить решение в применимой форме» — две разные способности, и вторая проваливается независимо от первой.

## Грейдинг и статистическая строгость

Для кода дефолт — **execution-based грейдинг**: применить правку, запустить тесты, посмотреть на проход/провал. Причина предпочтения — прямо в ограничениях альтернативы. **LLM-as-judge** используют там, где оракула нет (открытое качество кода, отсутствие тестов), но у него документированы систематические смещения:[^37]

- **position bias** — судья предпочитает ответ по позиции; при перестановке местами только GPT-4 давал консистентный вердикт более чем в 60% случаев, Claude-v1 — 23.8%.
- **verbosity bias** — предпочтение длинных ответов; под атакой «раздуй правильный ответ повтором» Claude-v1 и GPT-3.5 обманывались в 91.3% случаев (GPT-4 — 8.7%).
- **self-enhancement bias** — предпочтение собственных ответов; GPT-4 накидывает себе +10% win-rate, Claude-v1 +25% (авторы осторожно оговаривают, что данных мало).

Та же работа показывает корневую причину, по которой судья плох именно для кода и математики: LLM-судья не может проверить корректность, не вычислив её сам, и проваливает грейдинг задач, которые сам же способен решить.[^37] Execution-оракул этого ограничения лишён — тест либо проходит, либо нет. Обзор LLM-as-judge для software engineering подтверждает роль судьи как fallback именно там, где тестового оракула нет.[^41]

Но объективность оракула не отменяет статистику, и здесь — самое слабое место индустриальной практики. Лидерборды живут в парадигме «выделить жирным SOTA», почти не проверяя результат на значимость и не публикуя error bars.[^35] Проблема двойная. Во-первых, размеры малы: рекомендация — новый eval должен содержать хотя бы 1 000 задач для приличной различающей способности, а SWE-bench Lite это 300.[^35] Во-вторых, стоимость прогонов мешает строить доверительные интервалы: в Holistic Agent Leaderboard прямо признают, что при цене в тысячи долларов за модель многократные прогоны для CI непозволительны, и большинство оценок сделаны одним прогоном без статистической валидации.[^21] Контрпример правильной практики — SWE-bench Pro, где рядом со счётом стоит 95% доверительный интервал по биномиальной пропорции.[^31] Кластеризованная дисперсия при этом может превышать наивную более чем втрое, так что «наивный» SE вводит в заблуждение.[^35]

Отдельный слой — **недетерминизм**. Даже при temperature = 0 воспроизводимость не гарантирована: разброс точности между номинально идентичными прогонами достигал 15%, а в пределе — до 70 п.п. между лучшим и худшим прогоном; причина не в сэмплировании, а в инфраструктуре инференса (continuous batching, chunked prefill, prefix caching).[^39] При сэмплировании (temperature > 0) разрыв между greedy и средним по сэмплам на HumanEval доходил до 19 п.п.[^38] Одно число без указания дисперсии и числа прогонов — недостаточное измерение, особенно на малых наборах.

Стоимость и латентность всё чаще считают частью результата. SWE-agent репортит средний $-cost на решённую задачу.[^3] HAL встраивает трекинг токенов и стоимости в harness, отмечая, что скаффолды радикально влияют и на точность, и на цену, а сравнений «при равной цене» почти не делают.[^21] При этом цена волатильна (o3 подешевел на 80% с релиза), а расход токенов стохастичен — прогоны одной задачи одним агентом различались до 30× по токенам, и больший расход не означал большей точности.[^40][^21] Контринтуитивная находка HAL: в 21 из 36 комбинаций «модель × агент × бенчмарк» повышение reasoning-усилия не улучшало или ухудшало точность.[^21]

## Sandbox-инфраструктура

Execution-грейдинг требует изолированного, воспроизводимого окружения на каждую задачу. Референс — **harness SWE-bench**, который строит Docker-образы тремя слоями: base image (общие зависимости), ~60 environment images (Python-окружения под разные конфигурации) и per-instance images (специфические зависимости конкретной задачи).[^28] Кэширование настраивается: уровень `env` держит base+env (~100GB), уровень `instance` кэширует всё (~2000GB, но быстрее всего).[^28] Каждая задача исполняется в **своём** контейнере внутри пула воркеров: `run_evaluation.py` строит и стартует контейнер на инстанс, дефолт `--max_workers 4` (рекомендуется ≤ 75% ядер), `--timeout 1800` секунд на прогон тестов.[^28] Важное разделение ответственности: сам harness грейдинга не считает денежную стоимость — в `grading.py`/`run_evaluation.py` есть только `resolved: bool`; учёт $ живёт в отдельных inference-скриптах, генерирующих патчи, а per-instance-cost на лидерборде self-reported тем, кто сабмитит прогон.[^28]

Вокруг Docker выросла экосистема альтернатив под масштаб и безопасность. **SWE-ReX** — runtime-интерфейс, делающий код агента одинаковым независимо от того, где исполняются команды: локальный Docker, AWS, Modal; поддерживает массовый параллелизм (100 агентов разом).[^25] Провайдеры sandbox расходятся по модели изоляции: **Modal** использует gVisor-контейнеры, **E2B** — Firecracker microVM для hardware-level изоляции.[^24] Числа масштаба индустриальные: Modal довёл 500-задачный Verified до 7 минут прогона через флаг `--modal`, держит 50 000+ конкурентных сессий; отдельные пользователи гоняли более 1 млн sandbox за 48 часов с пиком 20 000 конкурентных.[^24]

При этом «Docker = воспроизводимость» — миф, и это важно для долгоживущих бенчмарков. Исследование `Docker Does Not Guarantee Reproducibility` показывает, что Dockerfile не гарантирует одинаковую сборку: bitwise-воспроизводимость достигли лишь 4 образа из всех протестированных, точные версии пакетов сохранили 70 из 1 096 (медиана 22.6% изменившихся версий), а rebuildability за два года — всего 72%.[^26] Причина — temporal failures: base-образы и сторонние зависимости меняются во времени. Единственная надёжная рекомендация — пинить все зависимости к конкретным версиям, включая base-образы.[^26] Для бенчмарка это означает, что per-instance-образ, собранный «по Dockerfile» год спустя, может грейдить иначе, чем оригинальный — воспроизводимость обеспечивают замороженные образы, а не рецепты их сборки.

[^1]: Jimenez, Yang, Wettig, Yao, Pei, Press, Narasimhan. "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" ICLR 2024. arXiv:2310.06770. <https://arxiv.org/abs/2310.06770>
[^2]: SWE-bench Verified (SWE-bench / OpenAI). <https://www.swebench.com/verified.html>
[^3]: Yang, Jimenez, Wettig, Lieret, Yao, Narasimhan, Press. "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering." NeurIPS 2024. arXiv:2405.15793. <https://arxiv.org/abs/2405.15793>
[^4]: Chen et al. "Evaluating Large Language Models Trained on Code" (Codex / HumanEval). 2021. arXiv:2107.03374. <https://arxiv.org/abs/2107.03374>
[^5]: Austin et al. "Program Synthesis with Large Language Models" (MBPP). 2021. arXiv:2108.07732. <https://arxiv.org/abs/2108.07732>
[^6]: Zhuo et al. "BigCodeBench: Benchmarking Code Generation with Diverse Function Calls and Complex Instructions." ICLR 2025. arXiv:2406.15877. <https://arxiv.org/abs/2406.15877>
[^7]: Liu, Xu, McAuley. "RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems." 2023. arXiv:2306.03091. <https://arxiv.org/abs/2306.03091>
[^8]: Li et al. "Competition-Level Code Generation with AlphaCode" (CodeContests). DeepMind, 2022. arXiv:2203.07814. <https://arxiv.org/abs/2203.07814>
[^9]: Zhao et al. "Commit0: Library Generation from Scratch." 2024. arXiv:2412.01769. <https://arxiv.org/abs/2412.01769>
[^10]: Jain et al. "LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code." 2024. arXiv:2403.07974. <https://arxiv.org/abs/2403.07974>
[^11]: "o1 tops aider's new polyglot leaderboard" (Aider polyglot benchmark). 2024-12-21. <https://aider.chat/2024/12/21/polyglot.html>
[^12]: Aider code-editing benchmark harness (README). <https://github.com/Aider-AI/aider/blob/main/benchmark/README.md>
[^13]: Aider code editing leaderboard. <https://aider.chat/docs/leaderboards/edit.html>
[^14]: Gauthier. "Unified diffs make GPT-4 Turbo 3X less lazy." Aider, 2024. <https://aider.chat/docs/unified-diffs.html>
[^15]: "Edit formats." Aider docs. <https://aider.chat/docs/more/edit-formats.html>
[^16]: "Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks in Command Line Interfaces." 2026. arXiv:2601.11868. <https://arxiv.org/abs/2601.11868>
[^17]: Liang et al. "The SWE-Bench Illusion: When State-of-the-Art LLMs Remember Instead of Reason." 2025. arXiv:2506.12286. <https://arxiv.org/abs/2506.12286>
[^18]: "SWE-Bench+: Enhanced Coding Benchmark for LLMs." 2024. arXiv:2410.06992. <https://arxiv.org/abs/2410.06992>
[^19]: Liu, Xia, Wang, Zhang. "Is Your Code Generated by ChatGPT Really Correct? Rigorous Evaluation of Large Language Models for Code Generation" (EvalPlus / HumanEval+). NeurIPS 2023. arXiv:2305.01210. <https://arxiv.org/abs/2305.01210>
[^20]: Yang et al. "Rethinking Benchmark and Contamination for Language Models with Rephrased Samples." 2023. arXiv:2311.04850. <https://arxiv.org/abs/2311.04850>
[^21]: Kapoor et al. "Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation." 2025. arXiv:2510.11977. <https://arxiv.org/abs/2510.11977>
[^22]: "Beyond Synthetic Benchmarks: Evaluating LLM Performance on Real-World Class-Level Code Generation." 2025. arXiv:2510.26130. <https://arxiv.org/abs/2510.26130>
[^23]: "Terminal Wrench: A Dataset of 331 Reward-Hackable Environments and 3,632 Exploit Trajectories." 2026. arXiv:2604.17596. <https://arxiv.org/abs/2604.17596>
[^24]: "Best Sandboxes for SWE-Bench-Style Coding Agents in 2026." Modal, 2026. <https://modal.com/resources/best-sandboxes-swe-bench-coding-agents>
[^25]: SWE-ReX: Sandboxed code execution for AI agents. <https://github.com/SWE-agent/SWE-ReX>
[^26]: "Docker Does Not Guarantee Reproducibility." 2026. arXiv:2601.12811. <https://arxiv.org/abs/2601.12811>
[^27]: "Why we no longer evaluate SWE-bench Verified." OpenAI, 2026. <https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/>
[^28]: SWE-bench evaluation harness (repo, docs, `grading.py`, `run_evaluation.py`, `docs/guides/docker_setup.md`, `docs/guides/datasets.md`). <https://github.com/SWE-bench/SWE-bench>
[^29]: SWE-bench Lite. <https://www.swebench.com/lite.html>
[^30]: Yang et al. "SWE-bench Multimodal." 2024. arXiv:2410.03859. <https://arxiv.org/abs/2410.03859> · <https://www.swebench.com/multimodal.html>
[^31]: "SWE-Bench Pro: Can AI Agents Solve Long-Horizon Software Engineering Tasks?" Scale AI, 2025. arXiv:2509.16941. <https://arxiv.org/abs/2509.16941> · <https://scaleapi.github.io/SWE-bench_Pro-os/>
[^32]: Xia, Deng, Dunn, Zhang. "Agentless: Demystifying LLM-based Software Engineering Agents." 2024. arXiv:2407.01489. <https://arxiv.org/abs/2407.01489>
[^33]: Wang et al. "OpenHands: An Open Platform for AI Software Developers as Generalist Agents" (ex-OpenDevin). 2024. arXiv:2407.16741. <https://arxiv.org/abs/2407.16741>
[^34]: Moatless Tools. <https://github.com/aorwall/moatless-tools>
[^35]: Miller. "Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations." 2024. arXiv:2411.00640. <https://arxiv.org/abs/2411.00640>
[^36]: Yao, Shinn, Razavi, Narasimhan. "τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains" (pass^k). 2024. arXiv:2406.12045. <https://arxiv.org/abs/2406.12045>
[^37]: Zheng et al. "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." NeurIPS 2023. arXiv:2306.05685. <https://arxiv.org/abs/2306.05685>
[^38]: "The Good, The Bad, and The Greedy: Evaluation of LLMs Should Not Ignore Non-Determinism." 2024. arXiv:2407.10457. <https://arxiv.org/abs/2407.10457>
[^39]: "Non-Determinism of 'Deterministic' LLM Settings." 2024. arXiv:2408.04667. <https://arxiv.org/abs/2408.04667>
[^40]: "How Do AI Agents Spend Your Money?" 2026. arXiv:2604.22750. <https://arxiv.org/abs/2604.22750>
[^41]: "LLM-as-a-Judge for Software Engineering: Literature Review, Vision, and the Road Ahead." 2025. arXiv:2510.24367. <https://arxiv.org/abs/2510.24367>
