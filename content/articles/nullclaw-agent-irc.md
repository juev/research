---
title: "NullClaw как AI-агент: ветвление тем, IRC-транспорт и переключение моделей"
date: 2026-03-27
---

NullClaw — ультралёгкая инфраструктура автономных AI-агентов, написанная на Zig[^1]. Бинарник занимает 678 КБ, потребляет около 1 МБ RAM и стартует менее чем за 2 мс[^2]. Проект позиционируется как минималистичная альтернатива OpenClaw для ресурсо-ограниченных окружений: от Raspberry Pi до облачных VPS за $7/месяц[^3]. Данный обзор исследует, можно ли использовать NullClaw в режиме обычного AI-агента с ветвлением тем по каналам, какую роль играет IRC как транспорт, и как переключать модели в подобной архитектуре.

## Архитектура NullClaw

Ядро NullClaw строится на трёх архитектурных паттернах[^4]:

1. **VTable-полиморфизм** — каждая подсистема (провайдер LLM, канал связи, память, инструменты) определяется через vtable-интерфейс. Это обеспечивает подмену реализаций через конфигурацию без изменения кода[^4].

2. **Event Bus** — структура `Bus` развязывает продюсеров сообщений (каналы) от консюмеров (менеджер сессий) через две очереди: inbound (пользовательские сообщения → SessionManager) и outbound (ответы агента → каналы)[^4].

3. **Daemon Supervisor** — несколько супервизируемых потоков с exponential backoff управляют жизненным циклом подсистем: HTTP-гейтвей, heartbeat, планировщик, мониторинг каналов и диспетчер исходящих сообщений[^4].

Конфигурация хранится в `~/.nullclaw/config.json` и совместима со структурой OpenClaw[^5]. Инициализация выполняется командой `nullclaw onboard --interactive`[^5].

## Режимы работы агента

NullClaw поддерживает три основных режима исполнения[^4]:

- **CLI Mode** — одноразовое сообщение или интерактивный REPL (`nullclaw agent -m "message"`)
- **Daemon Mode** — продакшн-режим с HTTP-гейтвеем и фоновыми каналами (`nullclaw gateway`)
- **Onboarding Mode** — мастер начальной настройки

Уровни автономии задаются через `autonomy.level`[^5]:

- `supervised` — каждое исполнение инструмента требует одобрения оператора
- `read_only` — запрещены операции записи
- `full` — неограниченное исполнение
- `yolo` — агрессивная оптимизация с минимальными ограничениями

Для использования NullClaw как «обычного» AI-агента достаточно запустить Daemon Mode с одним или несколькими каналами связи. Агент обрабатывает входящие сообщения, поддерживает историю сессий, выполняет инструменты и отвечает в контексте разговора[^4].

## Ветвление тем через каналы и bindings

NullClaw не реализует «ветвление разговоров» в стиле ChatGPT (дерево сообщений внутри одной сессии). Вместо этого разделение тем достигается через архитектурный паттерн: **разные каналы или чаты маршрутизируются к разным агентам** с помощью системы bindings[^6].

### Механизм bindings

Конфигурация bindings связывает конкретный канал, аккаунт и peer (чат/группу/топик) с именованным агентом[^5]:

```json
{
  "bindings": [
    {
      "agent_id": "coder",
      "match": {
        "channel": "telegram",
        "account_id": "main",
        "peer": { "kind": "group", "id": "-1001234567890:thread:42" }
      }
    },
    {
      "agent_id": "orchestrator",
      "match": {
        "channel": "telegram",
        "account_id": "main",
        "peer": { "kind": "group", "id": "-1001234567890" }
      }
    }
  ]
}
```

В этом примере топик 42 направляется к агенту `coder`, а остальные топики группы — к `orchestrator`[^6]. Каждый именованный агент может иметь собственную модель, системный промпт и даже изолированное рабочее пространство[^5]:

```json
{
  "agents": {
    "list": [
      {
        "id": "coder",
        "model": { "primary": "ollama/qwen2.5-coder:14b" },
        "system_prompt": "Focus on implementation and tests.",
        "workspace_path": "agents/coder"
      },
      {
        "id": "researcher",
        "model": { "primary": "openrouter/openai/gpt-4.1" },
        "system_prompt": "Focus on investigation and synthesis."
      }
    ]
  }
}
```

Каждый агент получает изолированное пространство памяти с namespace `agent:<agent-id>` и собственными файлами `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `MEMORY.md`[^5].

### Slash-команды для управления привязками

Оператор может динамически перепривязывать агентов прямо из чата[^6]:

- `/bind <agent>` — привязать текущий чат к агенту
- `/bind status` — показать текущий маршрут
- `/bind clear` — удалить привязку, откат к fallback

Топик-специфичные привязки имеют приоритет над fallback-привязкой группы[^6].

### Субагенты

Помимо bindings, NullClaw поддерживает делегирование задач через субагенты[^7]. Команда `/subagents spawn --agent <id>` запускает одноразовый субагент, а для персистентных сессий используется `sessions_spawn` с `thread: true`[^7]. Субагенты исполняются в изолированных сессиях с ограниченными политиками инструментов[^7]. Однако вложенные субагенты (субагент создаёт субагента) на текущий момент не поддерживаются[^7].

## IRC как канал связи

### Почему IRC

IRC-протокол (RFC 1459, 1993) оказывается неожиданно удачным транспортом для AI-агентов. George Larson, разработавший систему «Digital Doorman» на базе NullClaw, описывает причины выбора IRC[^3]:

> IRC — протокол 1988 года, который оказался идеальным транспортом для AI-агента: никакого SDK, никакого API-версионирования, никакой привязки к вендору — только сообщения в канале.

Преимущества IRC как транспорта:

- **Полный контроль стека** — собственный IRC-сервер, никаких зависимостей от сторонних платформ
- **Минимальный overhead** — текстовый протокол без JSON, REST или WebSocket-оболочек
- **Стабильность** — протокол не менялся десятилетиями
- **Мультиканальность** — нативная поддержка множества каналов для разных тем

### Конфигурация IRC в NullClaw

IRC является одним из 18 встроенных каналов NullClaw[^8]. Конфигурация выглядит следующим образом[^4]:

```json
{
  "channels": {
    "irc": {
      "enabled": true,
      "servers": [
        {
          "server": "irc.example.com",
          "port": 6667,
          "tls": true,
          "nick": "botname",
          "user": "username",
          "channels": ["#general", "#dev"]
        }
      ]
    }
  }
}
```

IRC-канал реализует polling-паттерн: супервизируемый поток активно получает сообщения через raw socket + TLS, а health check выполняется через PING/PONG[^4]. Поддерживается подключение к нескольким серверам и каналам одновременно (multi-account)[^4].

### Ветвление тем через IRC-каналы

В IRC каждый канал (`#channel`) — это изолированное пространство сообщений. NullClaw создаёт отдельную сессию для каждого `chat_id` (в случае IRC — для каждого канала)[^4]. Это означает, что **разные IRC-каналы автоматически получают раздельные контексты разговора**.

Для реализации ветвления тем через IRC достаточно:

1. Создать отдельные IRC-каналы для каждой темы (#coding, #research, #devops)
2. Через bindings привязать каждый канал к соответствующему агенту с нужной моделью
3. Каждый канал будет иметь независимую сессию и историю

Пример конфигурации для ветвления:

```json
{
  "channels": {
    "irc": {
      "enabled": true,
      "servers": [{
        "server": "localhost",
        "port": 6697,
        "tls": true,
        "nick": "assistant",
        "channels": ["#coding", "#research", "#general"]
      }]
    }
  },
  "bindings": [
    {
      "agent_id": "coder",
      "match": { "channel": "irc", "peer": { "id": "#coding" } }
    },
    {
      "agent_id": "researcher",
      "match": { "channel": "irc", "peer": { "id": "#research" } }
    }
  ]
}
```

### Практический пример: Digital Doorman

Реальный кейс IRC-деплоя NullClaw описан George Larson[^3]. Архитектура «Digital Doorman» использует двухуровневую модель:

- **NullClaw** (публичный агент) — на VPS за $7/месяц, обрабатывает публичные запросы через IRC-канал `#lobby`
- **IronClaw** (приватный агент) — на изолированном оборудовании, управляет чувствительными данными

Коммуникация между агентами происходит через приватный IRC-канал `#backoffice`, а сетевая изоляция обеспечивается через Tailscale[^3]. Публичный агент никогда не имеет прямого доступа к приватному контексту.

Стек: Ergo (IRC-сервер на Go, 2.7 МБ RAM) + Gamja (web-клиент IRC, 152 КБ) + NullClaw (678 КБ)[^3].

## Переключение моделей

NullClaw предлагает несколько механизмов переключения моделей, от статического до полностью автоматического.

### Уровень 1: Статическое назначение через конфигурацию

Модель по умолчанию задаётся в `agents.defaults.model.primary` в формате `provider/vendor/model`[^5]:

```json
{
  "agents": {
    "defaults": {
      "model": { "primary": "openrouter/anthropic/claude-sonnet-4" }
    }
  }
}
```

Каждый именованный агент может переопределить модель[^5]:

```json
{
  "agents": {
    "list": [
      {
        "id": "coder",
        "model": { "primary": "openrouter/qwen/qwen3-coder" }
      },
      {
        "id": "researcher",
        "model": { "primary": "openrouter/openai/gpt-4.1" }
      }
    ]
  }
}
```

### Уровень 2: Автоматическая маршрутизация через model_routes

Секция `model_routes` определяет таблицу маршрутизации для автоматического выбора модели на каждом turn[^5][^9]:

```json
{
  "model_routes": [
    {
      "hint": "fast",
      "provider": "groq",
      "model": "llama-3.3-70b",
      "cost_class": "free",
      "quota_class": "unlimited"
    },
    {
      "hint": "balanced",
      "provider": "openrouter",
      "model": "anthropic/claude-sonnet-4",
      "cost_class": "standard"
    },
    {
      "hint": "deep",
      "provider": "anthropic",
      "model": "claude-opus-4",
      "cost_class": "premium"
    },
    {
      "hint": "vision",
      "provider": "anthropic",
      "model": "claude-sonnet-4",
      "cost_class": "standard"
    }
  ]
}
```

Распознаваемые route hints[^5][^9]:

| Hint | Назначение |
|---|---|
| `fast` | Короткие структурированные задачи (классификация, извлечение) |
| `balanced` | Нормальный fallback |
| `deep` / `reasoning` | Исследование, планирование, длинные контексты |
| `vision` | Turns с изображениями |

Route metadata (`cost_class`, `quota_class`) влияет на скоринг, но не определяет маршрут однозначно: неоднозначные промпты остаются на `balanced`, а `fast` срабатывает только при высокой уверенности в дешёвой задаче[^9]. Команда `/model` показывает последнее решение авто-роутера[^9].

### Уровень 3: Провайдерный стек

Архитектура провайдеров в NullClaw — трёхслойная[^4]:

```text
ReliableProvider (retry/backoff)
    ↓
RouterProvider (выбор backend)
    ↓
Concrete Provider (OpenAI, Anthropic, Gemini...)
```

`ReliableProvider` автоматически деградирует маршрут после ошибок квоты или rate-limit и пропускает его до истечения cooldown[^9]. NullClaw поддерживает 22+ провайдеров[^8], организованных в тиры[^4]:

- **Tier 1** (гейтвеи): OpenRouter, Anthropic, OpenAI, Azure
- **Tier 2** (облако): Gemini, DeepSeek, Groq, Vertex
- **Tier 3** (OAI-совместимые): Mistral, Together AI, Fireworks
- **Tier 9** (локальные): Ollama, LM Studio

Для кастомных провайдеров формат: `custom:<url>` с переменной окружения для API-ключа[^4].

### Уровень 4: Переключение через переменные окружения

Быстрое переопределение без редактирования конфига[^5]:

```bash
NULLCLAW_PROVIDER=anthropic
NULLCLAW_MODEL=claude-opus-4
```

### Комбинирование с ветвлением тем

В контексте ветвления тем переключение моделей выглядит органично. Bindings связывают каналы/топики с агентами, а каждый агент определяет свою модель. Таким образом:

- `#coding` → агент `coder` → `qwen3-coder` (быстрая, специализированная на коде)
- `#research` → агент `researcher` → `gpt-4.1` (аналитика и синтез)
- `#general` → агент по умолчанию → `claude-sonnet-4` с авто-роутингом

Внутри каждого агента `model_routes` дополнительно оптимизирует выбор модели по сложности конкретного turn.

## Дискуссионные вопросы и противоречия

### Ветвление vs. IRC-каналы

Настоящее ветвление разговоров (fork/merge внутри одной сессии) — активно обсуждаемая тема как в экосистеме OpenClaw, так и в Claude Code[^10]. NullClaw не реализует эту функциональность нативно. Использование отдельных IRC-каналов — это обходное решение, а не полноценная замена: **нет механизма слияния контекстов** из разных каналов обратно в одну сессию. Если ветвление нужно именно для «исследования идеи с возможностью вернуться к развилке», IRC-каналы этого не обеспечивают.

### Зрелость экосистемы

NullClaw — молодой проект с ~2 600 звёздами на GitHub[^11] и ограниченной документацией по сравнению с OpenClaw. Некоторые критики отмечают[^11]:

- Меньше plug-and-play агентов по сравнению с крупными платформами
- Продвинутые интеграции требуют ручной настройки
- Edge-ориентированность не подходит для крупномасштабных enterprise-задач

### IRC-специфичные ограничения

IRC как транспорт имеет объективные ограничения:

- Отсутствие нативной поддержки изображений и файлов (модель `vision` при IRC-транспорте неприменима)
- Ограничение длины сообщения (512 байт по RFC 2812) требует разбиения длинных ответов
- Нет нативного threading внутри канала (в отличие от Slack или Telegram Forum Topics)

### Сравнение с Telegram Forum Topics

Telegram предоставляет нативную поддержку топиков внутри группы, и NullClaw умеет привязывать разные агенты к разным топикам через `<chat_id>:thread:<topic_id>`[^6]. Для ветвления тем Telegram может быть более удобным каналом, чем IRC, благодаря визуальной навигации по топикам и поддержке rich media.

## Quality Metrics

| Метрика | Значение |
|---|---|
| Источников найдено | 18 |
| Источников процитировано | 11 |
| Типы источников | official: 4, industry: 3, blog: 2, news: 1, wiki: 1 |
| Покрытие цитатами | 92% |
| Подвопросов исследовано | 5 |
| Раундов исследования | 2 |
| Вопросов в ходе анализа | 3 |
| Разрешённых вопросов | 3 |
| Вопросов без данных | 0 |

[^1]: [NullClaw — GitHub](https://github.com/nullclaw/nullclaw)
[^2]: [Meet NullClaw: The 678 KB Zig AI Agent Framework — MarkTechPost](https://www.marktechpost.com/2026/03/02/meet-nullclaw-the-678-kb-zig-ai-agent-framework-running-on-1-mb-ram-and-booting-in-two-milliseconds/)
[^3]: [Building a $7/Month AI Agent Using IRC and Zig — AIToolly](https://aitoolly.com/ai-news/article/2026-03-27-building-a-digital-doorman-deploying-an-ai-agent-on-a-7-monthly-vps-using-irc-transport)
[^4]: [NullClaw Architecture — DeepWiki](https://deepwiki.com/nullclaw/nullclaw)
[^5]: [NullClaw Configuration Documentation — GitHub](https://github.com/nullclaw/nullclaw/blob/main/docs/en/configuration.md)
[^6]: [Per-topic agent/model bindings — OpenClaw/NullClaw Issues](https://github.com/openclaw/openclaw/issues/17732)
[^7]: [Sub-Agents — OpenClaw Documentation](https://docs.openclaw.ai/tools/subagents)
[^8]: [NullClaw Introduction — Mintlify](https://nullclaw-nullclaw.mintlify.app/introduction)
[^9]: [NullClaw Model Routes — Configuration Documentation](https://github.com/nullclaw/nullclaw/blob/main/docs/en/configuration.md)
[^10]: [Chat Branching: Spawn side-chain conversations — Claude Code Issues](https://github.com/anthropics/claude-code/issues/10370)
[^11]: [OpenClaw Alternatives Comparison — Till Freitag](https://till-freitag.com/en/blog/openclaw-alternatives-en)
