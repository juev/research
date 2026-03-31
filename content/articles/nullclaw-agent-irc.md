---
title: "NullClaw как AI-агент: ветвление тем, IRC-транспорт и переключение моделей"
date: 2026-03-27T11:19:00+03:00
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

## Каналы связи: сравнение поддержки тредов

NullClaw поддерживает 18 каналов связи[^8]. Однако возможности threading и изоляции сессий кардинально различаются между платформами. Ниже — анализ каждого канала с точки зрения ветвления тем.

### Каналы с нативной поддержкой тредов

#### Telegram Forum Topics

Telegram — наиболее зрелый канал для ветвления тем в NullClaw. Форумные группы Telegram предоставляют нативные топики, и NullClaw добавляет `:topic:<threadId>` к ключу сессии, обеспечивая полную изоляцию контекста[^12]. Каждый топик — это отдельная сессия, сообщения из одного топика не попадают в контекст другого[^12].

Ключевое преимущество — per-topic agent binding. Через конфигурацию bindings с `<chat_id>:thread:<topic_id>` каждый топик направляется к своему агенту с собственной моделью[^6]. Команда `/bind` позволяет перепривязывать агентов динамически, без редактирования конфига[^6].

Telegram также поддерживает rich media (изображения, файлы, голосовые сообщения), что делает доступным route hint `vision` для моделей с поддержкой изображений[^12].

#### Slack

Slack-интеграция NullClaw автоматически обнаруживает и поддерживает контекст тредов[^13]. Сообщения внутри треда получают ответы в том же треде, а метаданные треда сохраняются между обменами[^13]. Для явной маршрутизации в конкретный тред используется формат `channel_id:thread_ts`[^13].

Ключи сессий для Slack-тредов формируются по схеме `agent:<agentId>:slack:channel:<channelId>:thread:<threadTs>`[^14]. Это обеспечивает полную изоляцию: параллельные треды в одном канале ведут независимые разговоры.

Slack поддерживает три модели доступа[^13]:

- `allowlist` — только указанные пользователи
- `mention_only` — DM по allowlist, в каналах — по упоминанию
- `open` — без ограничений (не рекомендуется для продакшна)

Соединение через Socket Mode обеспечивает real-time доставку событий[^13].

#### Discord

Discord-треды получают собственный session key: `agent:<agentId>:discord:channel:<threadId>`[^15]. Тред использует свой ID как компонент ключа канала, а не наследует ID родительского канала[^15]. Конфигурация (allowlist, requireMention, skills, prompts) наследуется от родительского канала, если не переопределена явно для конкретного треда[^15].

Discord также поддерживает slash-команды с изолированными сессиями (`agent:<agentId>:discord:slash:<userId>`)[^15] и настройку `autoArchiveDuration` для автоматической архивации тредов[^16].

### Каналы с ограниченной поддержкой тредов

#### Matrix

Matrix поддерживает threading через `m.thread` relation type[^17]. Однако на момент написания обзора в экосистеме Claw-семейства реализация thread-level изоляции сессий для Matrix находится в процессе разработки[^17]. По умолчанию все сообщения в одной комнате (включая треды) попадают в общую сессию, что приводит к «загрязнению контекста» параллельными разговорами[^17].

Планируемое решение включает настройки `channels.matrix.thread` с опциями `historyScope` (`"thread"` для per-thread или `"room"` для общей истории), `inheritParent` и `initialHistoryLimit`[^17]. Slack и Telegram уже реализуют per-thread изоляцию, которая станет образцом для Matrix[^17].

#### IRC

IRC не имеет нативного threading внутри канала. Каждый IRC-канал (`#channel`) — это единая сессия. Для разделения тем требуется создание отдельных каналов, что подробно описано выше в секции «Ветвление тем через IRC-каналы».

### Каналы без поддержки тредов

Signal, iMessage и WhatsApp поддерживают только базовые операции: отправка, чтение и реакции[^16]. Threading в этих каналах не реализован ни на уровне протокола, ни на уровне интеграции. Агентный слой NullClaw учитывает возможности канала и не пытается использовать функции, которых канал не поддерживает[^16].

### Сравнительная таблица

| Канал | Нативные треды | Изоляция сессий | Per-thread binding | Rich media | Рекомендация |
|---|---|---|---|---|---|
| Telegram Forum | Да | Полная | Да | Да | Лучший выбор для ветвления |
| Slack | Да | Полная | Через thread_ts | Да | Оптимален для команд |
| Discord | Да | Полная | По thread ID | Да | Хорош для сообществ |
| Matrix | Да (протокол) | В разработке | Планируется | Да | Ждёт доработки плагина |
| IRC | Нет (каналы) | По каналам | По каналам | Нет | Для минимализма и контроля |
| Signal | Нет | По чатам | Нет | Ограничено | Только личные беседы |
| iMessage | Нет | По чатам | Нет | Да | Только Apple-экосистема |
| WhatsApp | Нет | По чатам | Нет | Да | Ограниченный функционал |

Для задачи «отдельные темы — отдельные контексты с разными моделями» **Telegram Forum Topics** — наиболее рекомендуемый канал благодаря полной per-topic изоляции, нативным bindings и визуальной навигации. **Slack** — лучший выбор для рабочих команд, уже использующих его как основной мессенджер. **IRC** — осознанный выбор для тех, кому важен полный контроль инфраструктуры и минимальный overhead[^3].

## Ограничение длины сообщений IRC: история и современность

### Происхождение лимита в 512 байт

Утверждение о 512-байтном лимите IRC-сообщений — не приблизительная оценка, а точная цитата из спецификации. RFC 2812 (секция 2.3) формулирует это однозначно[^18]:

> "IRC messages are always lines of characters terminated with a CR-LF (Carriage Return - Line Feed) pair, and these messages SHALL NOT exceed 512 characters in length, counting all characters including the trailing CR-LF."

С учётом 2 байт на CR-LF, доступный объём для команды и параметров составляет **510 байт**[^18]. Это ограничение присутствует уже в RFC 1459 (май 1993)[^19] и сохранено в RFC 2812 (апрель 2000)[^18].

### Почему именно 512 байт

RFC не содержит явного обоснования выбора числа 512. Однако из имплементационных заметок в RFC 1459 можно извлечь контекст[^19]:

> "A buffer size of 512 bytes is used so as to hold 1 full message, although, this will usually hold several commands."

Число 512 — степень двойки (2⁹), стандартный размер дискового сектора и типичный размер буфера в системах конца 1980-х годов. IRC был создан Jarkko Oikarinen в августе 1988 года в Университете Оулу (Финляндия) как замена программы MUT (MultiUser Talk)[^20]. В контексте сетей 1988 года — когда IRC-серверов было единицы, а к середине 1989 года их насчитывалось около 40 по всему миру[^20] — фиксированный буфер в 512 байт был практичным выбором: достаточным для текстового сообщения и удобным для аллокации памяти на серверах с ограниченными ресурсами.

Важно отметить: 512 байт — это **полная длина IRC-сообщения**, включая префикс отправителя, команду и параметры. После вычитания overhead протокола (`:nick!user@host PRIVMSG #channel :`) для полезной нагрузки текста остаётся существенно меньше — как правило, **350–400 байт** в зависимости от длины никнейма, хоста и имени канала.

### Изначально длинные сообщения не поддерживались

Нет — протокол IRC с самого начала (1988, формализован в RFC 1459 в 1993) определял жёсткий лимит в 512 байт на сообщение[^19]. Это не было ограничением конкретной реализации — это фундаментальный параметр протокола, влияющий на другие его элементы. Как отмечает RFC 2812[^18]:

> "Such restriction is necessary because IRC messages are limited to 512 characters in length."

Серверы, получающие сообщения длиннее 512 байт, должны либо вернуть ошибку `ERR_INPUTTOOLONG` (код 417), либо обрезать сообщение на 510-м байте и добавить `\r\n`[^21].

### Современные расширения: IRCv3

Спецификация IRCv3 вводит несколько механизмов преодоления исторического лимита.

#### maxline

Capability `oragono.io/maxline-2` позволяет серверу и клиенту согласовать увеличенный лимит[^22]. Значение должно быть не менее 512 и рекомендуется не менее 2048 байт[^22]. Ergo (IRC-сервер на Go, используемый в кейсе Digital Doorman) поддерживает эту capability нативно[^22].

При отправке длинного сообщения клиенту, не поддерживающему maxline, сервер автоматически разбивает его на стандартные 512-байтные фрагменты с разрывом по пробелам, не разделяя UTF-8 символы[^22]. Тег `oragono.io/truncated` сигнализирует о произошедшей обрезке[^22].

#### Multiline Messages

Спецификация `draft/multiline` (в стадии черновика) позволяет отправлять сообщения, которые содержат переносы строк и превышают обычный лимит[^23]. Механизм основан на batch-отправке: несколько PRIVMSG/NOTICE объединяются в один логический блок[^23].

Сервер объявляет параметры[^23]:

- `max-bytes` — максимальный суммарный объём полезной нагрузки
- `max-lines` — максимальное число строк в batch

Ergo поддерживает multiline с настраиваемыми параметрами[^24]:

```text
multiline:
  max-bytes: 4096  # 0 — отключено
  max-lines: 100   # 0 — без лимита
```

При доставке клиенту без поддержки multiline сервер разворачивает batch в отдельные сообщения[^23].

#### Message Tags

IRCv3 Message Tags расширяют формат сообщения метаданными с лимитом 8191 байт на теги[^25]. Теги не входят в основной лимит 512 байт и позволяют передавать дополнительную информацию (ID сообщения, timestamps, клиентские данные) без влияния на полезную нагрузку[^25].

### Практические следствия для NullClaw

При использовании Ergo как IRC-сервера (рекомендуемый стек для NullClaw[^3]) ограничение в 512 байт фактически снято: maxline позволяет увеличить лимит до 2048+ байт, а multiline — отправлять структурированные многострочные ответы. Таким образом, заявление об «ограничении IRC в 512 байт» в контексте NullClaw + Ergo является **устаревшим** — при условии, что клиент поддерживает IRCv3-расширения.

Однако если пользователь подключается стандартным IRC-клиентом без поддержки maxline/multiline, он получит автоматически фрагментированные сообщения. Это не проблема для машинного взаимодействия (агент → агент), но может быть неудобно для чтения человеком.

## Альтернативы NullClaw/OpenClaw для работы с тредами

NullClaw и OpenClaw — не единственные варианты для AI-агента с разделением тем по тредам. Экосистема 2026 года предлагает широкий спектр альтернатив: от минималистичных Claw-семейств до полноценных chat-интерфейсов и фреймворков оркестрации.

### Claw-семейство

Все «клешни» (Claw-*) разделяют общую архитектурную идею — автономный AI-агент с multi-channel доставкой — но отличаются языком реализации, ресурсными требованиями и зрелостью threading.

#### ZeroClaw (Rust)

ZeroClaw — реимплементация на Rust, где каждая подсистема — swappable trait[^26]. Потребляет менее 5 МБ RAM и стартует за менее чем 10 мс[^26]. Поддержка Telegram Forum Topics реализована: `:topic:<threadId>` добавляется к ключу сессии, обеспечивая изоляцию контекста между топиками[^27]. Memory auto-save также скопирован по topic ID, исключая утечку воспоминаний между темами[^27]. Однако в текущей версии нет per-topic конфигурации системных промптов или переопределения моделей — все топики используют одного агента[^27].

#### PicoClaw (Go)

PicoClaw написан на Go, занимает менее 10 МБ RAM и поддерживает экзотические архитектуры: x86_64, ARM64, MIPS, RISC-V, LoongArch[^26]. Поддержка Telegram Topics добавлена через PR #202: функция `parseTelegramChatID` разбирает формат `chatID:threadID`, а `MessageThreadID` включается в исходящие сообщения[^28]. Каналы: Telegram и Discord из коробки[^26].

#### NanoClaw (Python/Anthropic SDK)

NanoClaw — контейнеризированный агент, построенный на Anthropic Agents SDK[^29]. Каждая группа получает изолированный контейнер, файловую систему, IPC namespace и Claude-сессию[^29]. Группы не имеют доступа к данным друг друга. В Telegram поддерживаются multi-agent группы, где каждый субагент может иметь собственную bot-идентичность[^29]. Каналы: WhatsApp, Telegram, Slack, Discord, Gmail, Signal[^29].

#### Moltis (Rust)

Moltis — Rust-нативный агент из 46 модульных crates (~196K строк)[^30]. Поддерживает voice, memory, scheduling, browser automation и MCP-серверы[^30]. Каналы: Telegram, Discord, web-интерфейс[^30]. Архитектура основана на trait-based provider system с 56 trait-определениями и 160 точками инъекции `Arc<dyn ...>`[^30]. Детальная информация о per-thread изоляции сессий в публичной документации отсутствует.

#### IronClaw (Rust)

IronClaw фокусируется на безопасности: каждый инструмент исполняется внутри WebAssembly-песочницы, credentials никогда не экспонируются инструментам[^26]. Набор каналов ограничен — осознанный выбор для минимизации attack surface[^26]. Threading-функциональность не документирована.

### Nanobot (Python)

Nanobot — ультралёгкий AI-агент из ~4 000 строк Python с 26 800+ звёздами на GitHub[^31]. Интегрируется с Telegram, Discord, WhatsApp, Slack, Feishu, QQ и DingTalk[^31]. Поддерживает Slack thread isolation и Discord threading[^31]. Для Discord в group policy `open` рекомендуется создавать приватные треды и упоминать бота в них[^31]. Архитектура: пятислойная (User Interfaces → Gateway с MessageBus → Core Agent Engine → LLM Provider Layer → Tool Layer)[^31]. Multi-model: OpenAI, Anthropic, Gemini, DeepSeek, Groq, OpenRouter, Ollama[^31].

### Chat-интерфейсы с ветвлением

В отличие от multi-channel агентов, chat-интерфейсы предлагают ветвление как UI-функцию внутри веб-приложения.

#### LibreChat

LibreChat реализует полноценное forking разговоров[^32]. Fork создаёт новый разговор, начинающийся от выбранного сообщения, с тремя режимами включения контекста[^32]:

- **Visible messages only** — копирует только прямой путь к целевому сообщению
- **Include related branches** — прямой путь плюс ответвления вдоль него
- **Include all to/from here** — все сообщения, включая соседние ветки

Опция «Start fork here» позволяет продолжить fork от выбранного сообщения вперёд, а не назад к началу[^32]. Ветки сохраняются при шаринге разговоров[^32].

#### TypingMind

TypingMind создаёт отдельный тред при каждом редактировании или регенерации сообщения[^33]. Навигация между ветками через стрелки ← →. Можно возобновить разговор из любой предыдущей версии без потери других веток[^33]. Применения: сравнение разных подходов к решению задачи, тестирование альтернативных формулировок[^33].

#### LobeChat

LobeChat поддерживает fork разговора от любого сообщения для исследования альтернативного хода мысли без потери оригинального контекста[^34].

#### Open WebUI

Open WebUI предоставляет «Reply in Thread» для создания вложенных разговоров и multi-model conversations, где модели общаются в round-robin или group chat режиме[^35]. Функция conversation branching (клик по слову для создания sub-conversation) находится в стадии feature request[^35].

### Фреймворки оркестрации

#### LangGraph

LangGraph (LangChain) использует `thread_id` как ключ сессии: при смене `thread_id` агент начинает с чистого контекста[^36]. Два типа памяти[^36]:

- **In-thread memory** — история сообщений внутри одной сессии, сохраняемая через checkpointer
- **Cross-thread memory** — пользовательские или application-level данные, доступные во всех тредах

Checkpointers поддерживают PostgreSQL, Redis, MongoDB и другие бэкенды[^36]. LangGraph не предоставляет каналы связи (Telegram, Discord) из коробки — это фреймворк для построения агентов, а не готовое решение.

#### CoPaw (Alibaba)

CoPaw — open-source workstation от команды Tongyi (Alibaba Cloud), выпущенный в феврале 2026[^37]. Построен на AgentScope и поддерживает DingTalk, Feishu, Discord, QQ, iMessage и Slack как CLI-плагины[^37]. Каждый канал добавляется или удаляется без изменения логики агента[^37].

Обработка сообщений включает session-aware batching: пока сессия обрабатывается, новые сообщения той же сессии попадают в pending-словарь и мержатся при завершении обработки[^37]. Per-session locks предотвращают race conditions[^37]. Persistent memory через ReMe обеспечивает сохранение контекста между сессиями и платформами[^37].

### Сравнительная таблица альтернатив

| Проект | Язык | Threading | Каналы | Per-thread binding | Multi-model |
|---|---|---|---|---|---|
| OpenClaw | TypeScript | Полный | 22+ | Да | Да |
| NullClaw | Zig | По каналам | 18 | Да | Да |
| ZeroClaw | Rust | Telegram topics | ~10 | Нет (v1) | Да |
| PicoClaw | Go | Telegram topics | 2-3 | Нет | Да |
| NanoClaw | Python | По контейнерам | 6+ | Multi-agent группы | Claude SDK |
| Moltis | Rust | Не документирован | 3+ | Нет данных | Да |
| Nanobot | Python | Slack/Discord | 7+ | Нет | Да |
| CoPaw | Python | Session-aware | 6+ | Нет данных | Да |
| LibreChat | TypeScript | Fork UI | Web | N/A | Да |
| TypingMind | TypeScript | Branch UI | Web | N/A | Да |
| LangGraph | Python | thread_id API | Нет (фреймворк) | Программно | Да |

**Вывод**: для полноценного per-thread agent binding с разными моделями на разные темы OpenClaw и NullClaw остаются наиболее зрелыми вариантами. ZeroClaw и PicoClaw догоняют по Telegram-тредам, но пока без per-topic переопределения модели. Chat-интерфейсы (LibreChat, TypingMind) предлагают ветвление как UI-функцию, но не multi-channel агентность. LangGraph — мощный фреймворк для custom-решений, но требует самостоятельной реализации каналов.

## Дискуссионные вопросы и противоречия

### Ветвление vs. отдельные каналы/треды

Настоящее ветвление разговоров (fork/merge внутри одной сессии) — активно обсуждаемая тема как в экосистеме OpenClaw, так и в Claude Code[^10]. NullClaw не реализует эту функциональность нативно. Использование отдельных каналов или тредов — это архитектурное решение для разделения контекстов, а не полноценная замена tree-based branching: **нет механизма слияния контекстов** из разных тредов обратно в одну сессию. Если ветвление нужно именно для «исследования идеи с возможностью вернуться к развилке», текущая модель этого не обеспечивает.

### Зрелость экосистемы

NullClaw — молодой проект с ~2 600 звёздами на GitHub[^11] и ограниченной документацией по сравнению с OpenClaw. Некоторые критики отмечают[^11]:

- Меньше plug-and-play агентов по сравнению с крупными платформами
- Продвинутые интеграции требуют ручной настройки
- Edge-ориентированность не подходит для крупномасштабных enterprise-задач

### IRC vs. Telegram vs. Slack: выбор канала

Выбор канала для ветвления тем — это компромисс между контролем и удобством:

- **IRC** даёт полный контроль инфраструктуры, минимальный overhead и независимость от вендоров, но лишён нативных тредов, rich media и удобного UI
- **Telegram** предоставляет лучшую поддержку per-topic bindings, визуальную навигацию и rich media, но привязывает к инфраструктуре Telegram
- **Slack** оптимален для рабочих команд с существующим Slack-workflow, но зависим от подписки и API Slack

### Matrix: обещание без реализации

Matrix — единственный канал с открытым протоколом, поддержкой E2E-шифрования и нативными тредами на уровне протокола (`m.thread`), но при этом per-thread изоляция сессий в NullClaw/OpenClaw ещё не реализована[^17]. Для пользователей, которым важны одновременно открытость протокола и ветвление тем, Matrix остаётся перспективным, но пока незавершённым вариантом.

## Quality Metrics

| Метрика | Значение |
|---|---|
| Источников найдено | 42 |
| Источников процитировано | 37 |
| Типы источников | official/RFC: 7, technical docs: 10, industry: 8, blog: 5, wiki: 3, news: 2, community: 2 |
| Покрытие цитатами | 93% |
| Подвопросов исследовано | 16 |
| Раундов исследования | 4 |
| Вопросов в ходе анализа | 7 |
| Разрешённых вопросов | 7 |
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
[^12]: [Telegram Integration — OpenClaw Documentation](https://docs.openclaw.ai/channels/telegram)
[^13]: [NullClaw Slack Channel — Mintlify](https://www.mintlify.com/nullclaw/nullclaw/channels/slack)
[^14]: [Session Management — OpenClaw Documentation](https://www.learnclawdbot.org/docs/concepts/session)
[^15]: [Discord Integration — OpenClaw DeepWiki](https://deepwiki.com/openclaw/openclaw/4.3-discord-integration)
[^16]: [OpenClaw Channel Architecture — DeepWiki](https://deepwiki.com/openclaw/openclaw/4.1-channel-architecture)
[^17]: [Matrix thread session isolation — OpenClaw Issues](https://github.com/openclaw/openclaw/issues/29729)
[^18]: [RFC 2812: Internet Relay Chat: Client Protocol — IETF](https://datatracker.ietf.org/doc/html/rfc2812)
[^19]: [RFC 1459: Internet Relay Chat Protocol — IETF](https://datatracker.ietf.org/doc/html/rfc1459)
[^20]: [IRC History — Wikipedia](https://en.wikipedia.org/wiki/Internet_Relay_Chat)
[^21]: [Modern IRC Client Protocol Specification](https://modern.ircdocs.horse/)
[^22]: [oragono.io/maxline-2 Capability — Ergo](https://oragono.io/maxline-2)
[^23]: [Multiline Messages — IRCv3](https://ircv3.net/specs/extensions/multiline)
[^24]: [Ergo IRC Server Manual — GitHub](https://github.com/ergochat/ergo/blob/master/docs/MANUAL.md)
[^25]: [Message Tags — IRCv3](https://ircv3.net/specs/extensions/message-tags)
[^26]: [A Quick Look at Claw-Family — DEV Community](https://dev.to/0xkoji/a-quick-look-at-claw-family-28e3)
[^27]: [Per-topic session isolation for Telegram forum groups — ZeroClaw Issues](https://github.com/zeroclaw-labs/zeroclaw/issues/1532)
[^28]: [Support for Telegram Topic and Threaded mode — PicoClaw PR #202](https://github.com/sipeed/picoclaw/pull/202)
[^29]: [NanoClaw — Secure AI Agent for WhatsApp, Telegram & More](https://nanoclaw.dev/)
[^30]: [Moltis — A Rust-native claw you can trust — GitHub](https://github.com/moltis-org/moltis)
[^31]: [Nanobot — The Ultra-Lightweight OpenClaw — GitHub](https://github.com/HKUDS/nanobot)
[^32]: [Forking Chats — LibreChat Documentation](https://www.librechat.ai/docs/features/fork)
[^33]: [Chat Thread — TypingMind Documentation](https://docs.typingmind.com/chat-management/chat-thread)
[^34]: [LobeChat: A Deep Dive into the Ultimate AI Productivity Hub — Skywork](https://skywork.ai/skypage/en/LobeChat-A-Deep-Dive-into-the-Ultimate-AI-Productivity-Hub/1976182835206221824)
[^35]: [Features — Open WebUI Documentation](https://docs.openwebui.com/features/)
[^36]: [Memory overview — LangGraph Documentation](https://docs.langchain.com/oss/python/langgraph/memory)
[^37]: [Alibaba Open-Sources CoPaw — MarkTechPost](https://www.marktechpost.com/2026/03/01/alibaba-team-open-sources-copaw-a-high-performance-personal-agent-workstation-for-developers-to-scale-multi-channel-ai-workflows-and-memory/)
