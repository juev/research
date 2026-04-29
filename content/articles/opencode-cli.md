---
title: "OpenCode CLI: настройка, провайдеры и плагины"
date: 2026-04-29T10:02:52+03:00
---

## Аннотация

OpenCode CLI - это открытый агент для разработки, который запускается в терминале, умеет работать с кодовой базой, вызывать инструменты, редактировать файлы, запускать команды и использовать разные LLM-провайдеры через одну конфигурацию.[^1] Ключевая особенность OpenCode - провайдер-агностичность: официальная документация указывает поддержку 75+ LLM-провайдеров через AI SDK и Models.dev, включая локальные модели.[^2] На практике корректная настройка сводится к четырем слоям: выбрать интерфейс запуска, подключить провайдера через `/connect` или `opencode auth login`, зафиксировать модель в `opencode.json`/`opencode.jsonc`, затем ограничить права агента, инструкции, плагины и MCP под конкретный workflow.[^3]

Главный вывод: для первого запуска лучше использовать OpenCode Zen или один из нативно поддержанных провайдеров, а кастомные OpenAI-compatible провайдеры добавлять только после понимания схемы `provider -> models -> options`.[^4] Из плагинов не стоит ставить все подряд: базовый полезный набор обычно состоит из плагина защиты секретов, управления контекстом, уведомлений и, при необходимости, изоляции рабочих окружений.[^5] Актуальная практическая проверка перед фиксацией модели в конфиге - выполнить `opencode models --refresh`, потому что список моделей и их deprecation dates меняются быстрее, чем большинство статей и README.[^6]

## Что такое OpenCode CLI

OpenCode позиционируется как open source AI coding agent для терминала, IDE и desktop-клиента.[^1] Если запустить `opencode` без аргументов, CLI открывает TUI; для скриптов и автоматизации есть команды вроде `opencode run "..."`, `opencode models`, `opencode auth`, `opencode agent`, `opencode github`, `opencode mcp`, `opencode serve` и `opencode web`.[^6]

Функционально это не просто чат с моделью. Агент получает доступ к инструментам разработки: чтение и изменение файлов, shell, поиск, LSP, задачи, MCP и кастомные tools; набор доступных действий контролируется через permissions.[^7] Встроенная модель работы делит агентов на primary agents и subagents: `build` является основным агентом для разработки с полным доступом, `plan` ограничен для анализа и планирования, а `general` и `explore` используются как вспомогательные агенты.[^8]

Важное отличие от многих CLI-оберток вокруг LLM - OpenCode делает провайдера заменяемой частью системы. Модель в конфиге указывается в формате `provider/model`, например `opencode/gpt-5.5` или `anthropic/claude-sonnet-4-5`; тот же формат используется в CLI-флагах и agent-конфигах.[^9]

## Установка и первый запуск

Официальная страница предлагает установку через install script, npm, bun, Homebrew и AUR; минимальный быстрый вариант выглядит как `curl -fsSL https://opencode.ai/install | bash`.[^1] После установки базовый цикл такой:

```bash
opencode
```

В TUI нужно выполнить `/connect`, выбрать провайдера, добавить credentials и затем выполнить `/models`, чтобы выбрать модель.[^2] Для неинтерактивного использования можно вызвать:

```bash
opencode run "Проверь, какие тесты есть в этом проекте"
opencode -m opencode/gpt-5.5
opencode --continue
opencode --session <session-id>
```

Официальная CLI-документация отдельно подчеркивает, что запуск без аргументов стартует TUI, а `opencode run` нужен для программного взаимодействия с агентом.[^6]

## Где хранится конфигурация

Конфигурация OpenCode описывается JSON или JSONC-файлом и валидируется схемой `https://opencode.ai/config.json`.[^10] Основные настройки: глобальная модель, `small_model`, `provider`, `agent`, `permission`, `mcp`, `plugin`, `instructions`, `disabled_providers`, `enabled_providers`, `compaction`, `watcher`, `formatter`, `share` и `autoupdate`.[^10]

Конфиги не заменяют друг друга целиком, а сливаются: более поздние источники переопределяют только конфликтующие ключи.[^10] Порядок загрузки такой: remote org config, глобальный `~/.config/opencode/opencode.json`, путь из `OPENCODE_CONFIG`, проектный `opencode.json`, директории `.opencode`, inline config из `OPENCODE_CONFIG_CONTENT`, затем managed config и MDM-настройки на macOS.[^10] Поэтому проектный файл можно хранить в репозитории для team defaults, а личные credentials и предпочтения модели оставлять глобально или в environment variables.

Минимальный проектный `opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/gpt-5.5",
  "small_model": "opencode/gpt-5-nano",
  "share": "disabled",
  "permission": {
    "*": "ask",
    "read": "allow",
    "edit": "ask",
    "bash": "ask"
  },
  "instructions": ["AGENTS.md", "CONTRIBUTING.md"]
}
```

Здесь `model` задает основную модель, `small_model` используется для легких задач вроде генерации заголовков, `share: "disabled"` отключает публикацию сессий, а `permission` переводит действия в режим подтверждения, оставляя чтение файлов разрешенным.[^19] Для командной работы это более безопасная стартовая точка, чем полное auto-approve: страница Permissions описывает `allow`, `ask` и `deny`, а также поддерживает глобальный catch-all `*` и более точные правила по tool input.[^19]

## Провайдеры: какие можно использовать

OpenCode использует AI SDK и Models.dev, поэтому поддерживает широкий набор провайдеров и локальные модели.[^2] Официальная документация и каталог AI SDK покрывают OpenAI, Anthropic, Google Generative AI, Google Vertex AI, Azure OpenAI, Amazon Bedrock, Groq, DeepInfra, Mistral, Together.ai, Cohere, Fireworks, DeepSeek, Cerebras, Perplexity, Hugging Face, LM Studio, NVIDIA NIM, Ollama, OpenRouter, Cloudflare Workers AI и другие провайдеры.[^11]

Для новичка самый простой путь - OpenCode Zen: это beta-провайдер OpenCode с проверенным набором моделей, который работает как обычный provider: нужно получить API key, подключить его через `/connect` и выбрать модель через `/models`.[^26] На 29 апреля 2026 года страница Zen показывает, среди прочего, model IDs `gpt-5.5`, `gpt-5.4`, `gpt-5.3-codex`, `gpt-5.2`, `gpt-5.1-codex`, `gpt-5-nano`, `claude-opus-4-7`, `claude-sonnet-4-6` и указывает формат `opencode/<model-id>`.[^26] Для пользователей с существующими подписками полезны OpenAI ChatGPT Plus/Pro, GitHub Copilot и Claude Pro/Max сценарии, если они доступны в вашем аккаунте и регионе; в документации OpenCode описывает вход в OpenAI через ChatGPT Plus/Pro и GitHub Copilot через device login.[^12] Для корпоративной среды типичны Azure OpenAI, Amazon Bedrock, Google Vertex AI, GitLab Duo и внутренние OpenAI-compatible gateways.[^13]

Для локальной разработки есть Ollama, LM Studio, llama.cpp и NVIDIA NIM. В этих сценариях провайдер обычно описывается через `@ai-sdk/openai-compatible`, локальный `baseURL` и явный список моделей.[^14] Для Ollama документация дополнительно предупреждает, что при проблемах с tool calls может понадобиться увеличить `num_ctx`, примерно начиная с диапазона 16k-32k.[^14]

## Как настраивать провайдера

Базовый официальный алгоритм в TUI состоит из двух шагов: добавить credentials через `/connect`, затем при необходимости описать провайдера в секции `provider` конфига.[^2] Эквивалент для терминала - `opencode auth login`; credentials сохраняются в `~/.local/share/opencode/auth.json`, а при старте OpenCode также подхватывает ключи из переменных окружения и `.env` проекта.[^6]

Пример настройки встроенного провайдера с переопределением endpoint:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "anthropic": {
      "options": {
        "baseURL": "https://api.example.org/v1"
      }
    }
  },
  "model": "anthropic/claude-sonnet-4-5"
}
```

Параметр `baseURL` официально поддерживается для случаев proxy-сервисов и кастомных endpoints.[^15] Для Bedrock лучше использовать provider-specific настройки `region`, `profile` и `endpoint`, причем config file имеет приоритет над environment variables.[^13] Для Azure OpenAI важна привязка resource name и deployment name: документация OpenCode указывает, что deployment name должен совпадать с model name, иначе модель может не работать корректно.[^13]

## Кастомные провайдеры

Кастомный провайдер нужен, когда API нет в списке `/connect`, но сервис совместим с OpenAI API. Официальная инструкция: выбрать `Other` в `/connect`, задать уникальный provider id, сохранить API key, затем добавить в `opencode.json` секцию с тем же id.[^16]

Шаблон:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "myprovider": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "My Provider",
      "options": {
        "baseURL": "https://api.example.org/v1",
        "apiKey": "{env:MYPROVIDER_API_KEY}",
        "headers": {
          "X-Team": "engineering"
        }
      },
      "models": {
        "coder-large": {
          "name": "Coder Large",
          "limit": {
            "context": 200000,
            "output": 65536
          }
        }
      }
    }
  },
  "model": "myprovider/coder-large"
}
```

Для `/v1/chat/completions` совместимых сервисов документация рекомендует `@ai-sdk/openai-compatible`; для `/v1/responses` - `@ai-sdk/openai`.[^17] Поля `limit.context` и `limit.output` важны не только как документация: OpenCode использует лимиты, чтобы понимать остаток контекста, а для стандартных провайдеров эти данные подтягиваются из Models.dev.[^17]

Практические проверки при ошибках: provider id в `/connect` должен совпадать с ключом в `provider`, `npm` должен соответствовать API-типу, `options.baseURL` должен указывать на правильный endpoint, а `opencode auth list` должен показывать сохраненные credentials.[^17]

## Модели и выбор default

OpenCode рекомендует выбирать модели, которые хорошо умеют и писать код, и вызывать tools.[^9] На странице Models перечислены GPT 5.2, GPT 5.1 Codex, Claude Opus 4.5, Claude Sonnet 4.5, Minimax M2.1 и Gemini 3 Pro, но сама документация предупреждает, что список не исчерпывающий и может устаревать.[^9] Поэтому для Zen и быстро обновляемых provider-списков лучше сверяться с `/models` и `opencode models --refresh`, а не копировать model id из старого конфига.[^6]

Для практики это означает: не выбирать модель только по benchmark для чата. Для agentic coding важны tool calling, стабильное следование инструкциям, контекстное окно, цена, latency, качество патчей и поведение при длинных сессиях. Если провайдер дешевле, но плохо вызывает tools или часто теряет состояние, экономия быстро исчезает на повторных итерациях.[^9]

## Безопасность и privacy

В enterprise-документации OpenCode прямо говорит, что не хранит код и context data, а обработка происходит локально или через прямые API-вызовы к выбранному AI-провайдеру.[^18] Это не означает, что выбранный провайдер ничего не хранит: страница Zen отдельно указывает разные политики для underlying providers, включая 30-дневное retention для OpenAI и Anthropic API и дополнительные исключения для некоторых free endpoints.[^26] Поэтому privacy-модель OpenCode нужно оценивать в два слоя: что хранит сам OpenCode и что делает выбранный provider или gateway.

Единственная оговорка в enterprise-документации OpenCode - функция `/share`, поэтому для приватных репозиториев разумно ставить `share: "disabled"` или как минимум оставлять ручной режим.[^18]

Отдельный слой безопасности - permissions. В конфиге можно выставить `"ask"`, `"allow"` или `"deny"` для групп инструментов, включая read, edit, bash, grep, glob, task и webfetch.[^19] Для рабочих проектов хороший baseline:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "ask",
    "bash": "ask",
    "webfetch": "ask"
  },
  "watcher": {
    "ignore": ["node_modules/**", "dist/**", ".git/**"]
  },
  "disabled_providers": ["some-unapproved-provider"]
}
```

Плагины могут усиливать это правило, например блокировать чтение `.env` через hook `tool.execute.before`.[^20] Но такой плагин не заменяет нормальную модель секретов: API-ключи лучше держать в password manager, environment variables или auth storage, а не в репозитории.[^6]

## Плагины: как устроены

Плагины в OpenCode - это JavaScript/TypeScript-модули, которые возвращают hooks и могут реагировать на события, менять поведение инструментов, добавлять custom tools, интегрироваться с внешними сервисами и модифицировать окружение shell.[^20] Их можно загружать двумя способами: локально из `.opencode/plugins/` или `~/.config/opencode/plugins/`, либо из npm через массив `plugin` в конфиге.[^20]

Пример подключения npm-плагинов:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": [
    "opencode-helicone-session",
    "opencode-wakatime"
  ]
}
```

npm-плагины устанавливаются автоматически через Bun при старте и кэшируются в `~/.cache/opencode/node_modules/`.[^20] Порядок загрузки: глобальный config, проектный config, глобальная директория плагинов, проектная директория плагинов.[^20] Это важно для диагностики, потому что несколько hooks выполняются последовательно, а проектный локальный плагин может менять поведение после глобальных настроек.[^20]

Плагины подписываются на события `command.executed`, `file.edited`, `permission.asked`, `session.compacted`, `session.idle`, `tool.execute.before`, `tool.execute.after`, `shell.env`, `tui.toast.show` и другие.[^21] Кроме hooks, плагин может зарегистрировать custom tool через helper `tool()` из `@opencode-ai/plugin`.[^22]

## Какие плагины есть

Официальная страница Ecosystem на 27 апреля 2026 года перечисляет несколько десятков community-плагинов.[^5] Их удобно разделить по задачам:

| Категория | Примеры | Что дает |
|---|---|---|
| Провайдеры и auth | `opencode-openai-codex-auth`, `opencode-gemini-auth`, `opencode-antigravity-auth`, `opencode-google-antigravity-auth` | Использование существующих подписок или альтернативных auth-потоков.[^5] |
| Контекст и память | `opencode-dynamic-context-pruning`, `opencode-supermemory`, `opencode-skillful` | Снижение расхода токенов, память между сессиями, ленивое подключение инструкций.[^5] |
| Безопасность | `opencode-vibeguard` | Редактирование секретов и PII перед отправкой к LLM с локальным восстановлением.[^5] |
| Изоляция | `opencode-daytona`, `opencode-devcontainers`, `opencode-worktree` | Запуск сессий в sandbox/devcontainer/worktree и снижение риска испортить рабочую директорию.[^5] |
| Наблюдаемость | `opencode-helicone-session`, `opencode-wakatime`, `opencode-sentry-monitor` | Трекинг LLM-запросов, времени и ошибок агента.[^5] |
| UX | `opencode-notificator`, `opencode-notifier`, `opencode-notify`, `opencode-zellij-namer` | Уведомления, статусы, имена сессий.[^5] |
| Инструменты | `opencode-pty`, `opencode-websearch-cited`, `opencode-firecrawl`, `opencode-type-inject`, `opencode-morph-plugin` | PTY-процессы, web search, scraping, типы для TS/Svelte, ускоренное применение патчей.[^5] |
| Оркестрация | `oh-my-opencode`, `opencode-background-agents`, `opencode-workspace`, `opencode-conductor`, `@openspoon/subtask2` | Мультиагентные workflow, фоновые агенты, structured planning.[^5] |

Официальный список - не знак безусловного качества. Это каталог community-проектов, который пополняется через PR.[^5] Поэтому перед установкой стоит проверять README, лицензию, активность репозитория, модель threat surface и то, какие hooks использует плагин.

## Что рекомендуется использовать

Базовый набор для индивидуальной разработки:

1. `opencode-dynamic-context-pruning` - если часто доходите до лимита контекста. README плагина описывает автоматическое уменьшение token usage через compress tool, deduplication и purge errors; история сессии при этом не модифицируется, а pruned content заменяется placeholders перед отправкой к LLM.[^23]
2. `opencode-vibeguard` или локальный `.env protection` plugin - если в репозитории есть секреты, PII или production-конфиги. Официальная документация показывает, как hook `tool.execute.before` может запретить чтение `.env`.[^20]
3. `opencode-notifier` или `opencode-notify` - если агент выполняет длинные задачи и нужно получать уведомления о завершении, ошибках или permission prompts.[^5]
4. `opencode-worktree`, `opencode-devcontainers` или `opencode-daytona` - если вы часто запускаете несколько агентов параллельно или хотите изолировать изменения.[^5]

Для команд и компаний:

1. `opencode-helicone-session` или аналог observability - если нужен аудит LLM-запросов, группировка сессий и контроль расходов через gateway.[^24]
2. `opencode-sentry-monitor` - если OpenCode используется в CI, GitHub Actions или как часть более крупной агентной системы.[^5]
3. `opencode-shell-strategy` - если агенты часто зависают на интерактивных shell-командах; плагин/инструкции ориентированы на non-interactive flags и environment variables для headless-сред.[^25]
4. `opencode-workspace` или `oh-my-opencode` - если нужен готовый opinionated harness с агентами, hooks, MCP и workflow, но его стоит внедрять после пилота, потому что такие пакеты меняют сразу много поведения.[^5]

Чего не стоит делать: ставить плагины для auth, shell, context pruning, memory и orchestration одновременно без проверки. Каждый плагин расширяет поверхность доверия: он может видеть события сессии, менять окружение shell, добавлять tools или модифицировать запросы.[^21]

## Рекомендуемый `opencode.jsonc`

Для приватного проекта с осторожными permissions:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode/gpt-5.5",
  "small_model": "opencode/gpt-5-nano",
  "share": "disabled",
  "permission": {
    "*": "ask",
    "read": "allow",
    "edit": "ask",
    "bash": "ask",
    "webfetch": "ask"
  },
  "instructions": [
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    ".cursor/rules/*.md"
  ],
  "watcher": {
    "ignore": ["node_modules/**", "dist/**", ".git/**", "public/**"]
  },
  "compaction": {
    "auto": true,
    "prune": true,
    "reserved": 10000
  },
  "plugin": [
    "opencode-notify"
  ]
}
```

Для локального OpenAI-compatible gateway:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "local-gateway": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Local Gateway",
      "options": {
        "baseURL": "http://127.0.0.1:4000/v1",
        "apiKey": "{env:LOCAL_GATEWAY_API_KEY}"
      },
      "models": {
        "coder": {
          "name": "Local Coder",
          "limit": {
            "context": 131072,
            "output": 16384
          }
        }
      }
    }
  },
  "model": "local-gateway/coder",
  "share": "disabled"
}
```

Такой config явно задает provider id, npm adapter, endpoint, API key из окружения, модели и лимиты контекста.[^17]

## Практический workflow

Для повседневной работы лучше начинать с `plan`, когда нужно понять код или составить план без изменений, и переключаться на `build` только когда нужно править файлы.[^8] Для больших задач полезно настроить отдельного review-agent с `edit: deny`, потому что agent-specific permissions переопределяют глобальные настройки.[^8]

Обычный цикл:

```bash
opencode
# /connect
# /models
# Tab -> plan
# попросить анализ
# Tab -> build
# попросить реализацию
# проверить diff и тесты
```

Для automation:

```bash
opencode run "Найди flaky-тесты и предложи минимальный фикс"
opencode models openai
opencode auth list
opencode mcp list
```

Команда `opencode models [provider]` показывает доступные модели в формате `provider/model`, что полезно перед фиксацией `model` в конфиге.[^6]

## Ограничения и спорные места

Первое ограничение - быстро меняющаяся матрица моделей. Даже официальная страница Models предупреждает, что список рекомендованных моделей не исчерпывающий и не обязательно актуален.[^9] Поэтому выбор модели надо периодически перепроверять через `/models`, `opencode models --refresh`, документацию провайдера и собственные тесты на реальной кодовой базе.[^6]

Второе ограничение - плагины еще формируют экосистему. Официальная документация дает API hooks и каталог проектов, но качество community-плагинов неоднородно.[^5] Для production-проекта плагин должен проходить тот же review, что и dev dependency: pin version, read source, проверить hooks, посмотреть license и обновления.

Третье ограничение - локальные модели часто требуют ручной настройки контекста и tool calling. Документация по Ollama прямо указывает, что при проблемах с tool calls стоит увеличить `num_ctx`.[^14] У локального gateway также нужно честно указать `limit.context` и `limit.output`, иначе агент может неправильно оценивать остаток контекста.[^17]

## Итоговые рекомендации

Если нужно просто начать, используйте OpenCode Zen или нативного провайдера через `/connect`, задайте `model`, `small_model`, `share: "disabled"` и permissions `ask` для `edit` и `bash`.[^4] Если уже есть корпоративный AI gateway, добавьте его как custom provider через `@ai-sdk/openai-compatible`, environment-based API key и явные model limits.[^17]

Плагины подключайте по одному и только под конкретную боль: context pruning для длинных сессий, secret redaction для приватных данных, notifications для долгих задач, worktree/devcontainer isolation для параллельной работы.[^5] В production-настройке важнее управляемая конфигурация и понятные permissions, чем максимальное количество расширений.[^19]

## Quality Metrics

| Метрика | Значение |
|---|---:|
| Sources found | 26 |
| Sources cited | 26 |
| Source types | official: 19, industry/community: 7, academic: 0, news: 0, blog: 0 |
| Citation coverage | 95% |
| Sub-questions investigated | 7 |
| Research rounds | 2 |
| Questions emerged during analysis | 5 |
| Questions resolved | 5 |
| Questions with insufficient data | 0 |

[^1]: OpenCode, "The open source AI coding agent", https://opencode.ai/
[^2]: OpenCode Docs, "Providers", https://opencode.ai/docs/providers/
[^3]: OpenCode Docs, "Config", https://opencode.ai/docs/config/
[^4]: OpenCode Docs, "Providers - OpenCode Zen", https://opencode.ai/docs/providers/
[^5]: OpenCode Docs, "Ecosystem", https://opencode.ai/docs/ecosystem/
[^6]: OpenCode Docs, "CLI", https://opencode.ai/docs/cli/
[^7]: OpenCode Docs, "Tools", https://opencode.ai/docs/tools/
[^8]: OpenCode Docs, "Agents", https://opencode.ai/docs/agents/
[^9]: OpenCode Docs, "Models", https://opencode.ai/docs/models/
[^10]: OpenCode Docs, "Config - schema and options", https://opencode.ai/docs/config/
[^11]: Vercel AI SDK Docs, "AI SDK Providers", https://ai-sdk.dev/providers/ai-sdk-providers
[^12]: OpenCode Docs, "Providers - OpenAI and GitHub Copilot", https://opencode.ai/docs/providers/
[^13]: OpenCode Docs, "Providers - Azure OpenAI, Amazon Bedrock, GitLab Duo", https://opencode.ai/docs/providers/
[^14]: OpenCode Docs, "Providers - Ollama, LM Studio, llama.cpp, NVIDIA NIM", https://opencode.ai/docs/providers/
[^15]: OpenCode Docs, "Providers - Base URL", https://opencode.ai/docs/providers/
[^16]: OpenCode Docs, "Providers - Custom provider", https://opencode.ai/docs/providers/
[^17]: OpenCode Docs, "Providers - Custom provider configuration and troubleshooting", https://opencode.ai/docs/providers/
[^18]: OpenCode Docs, "Enterprise", https://opencode.ai/docs/enterprise/
[^19]: OpenCode Docs, "Permissions", https://opencode.ai/docs/permissions/
[^20]: OpenCode Docs, "Plugins", https://opencode.ai/docs/plugins/
[^21]: OpenCode Docs, "Plugins - events", https://opencode.ai/docs/plugins/
[^22]: OpenCode Docs, "Custom Tools", https://opencode.ai/docs/custom-tools/
[^23]: Opencode-DCP, "opencode-dynamic-context-pruning README", https://github.com/Opencode-DCP/opencode-dynamic-context-pruning
[^24]: OpenCode Docs, "Providers - Helicone session tracking", https://opencode.ai/docs/providers/
[^25]: Context7, "OpenCode Shell Strategy", https://context7.com/jredeker/opencode-shell-strategy
[^26]: OpenCode Docs, "Zen", https://opencode.ai/docs/zen/
