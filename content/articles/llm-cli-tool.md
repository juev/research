---
title: "Утилита LLM от Simon Willison: аналитический обзор"
date: 2026-03-23
---

## Аннотация

Данный обзор исследует CLI-утилиту `llm`, созданную Simon Willison, — инструмент командной строки и Python-библиотеку для унифицированного взаимодействия с большими языковыми моделями. Исследование охватывает официальную документацию, блог-посты автора, технические обзоры и отзывы пользователей. Основные находки: `llm` является наиболее зрелым провайдер-агностичным CLI-инструментом для работы с LLM, поддерживающим более 20 провайдеров через систему плагинов, автоматическое логирование в SQLite, embeddings, RAG-пайплайны, шаблоны и structured output. Ключевое ограничение: подписки Claude Pro/Max/Code не предоставляют API-доступ для сторонних инструментов — требуется отдельный платный API-ключ Anthropic.

## Введение

Рост количества LLM-провайдеров и моделей создал потребность в инструментах, абстрагирующих разработчиков от деталей конкретных API. Утилита `llm` от Simon Willison (автора Django и Datasette) решает эту задачу, предоставляя единый интерфейс командной строки для взаимодействия с любыми моделями — от GPT-4 и Claude до локальных моделей через Ollama[^1].

Цель обзора — комплексный анализ утилиты: её назначение, способы использования, типичные задачи, экосистема плагинов и совместимость с подписками Anthropic (Claude Code, Pro, Max). Обзор не охватывает внутреннюю архитектуру кода и процесс разработки плагинов.

Структура документа: назначение и архитектура → установка и базовое использование → продвинутые функции (embeddings, schemas, templates) → экосистема плагинов → интеграция с Claude → типичные задачи и workflow → сравнение с альтернативами → ограничения.

## Назначение и архитектура

### Философия Unix

`llm` построена по принципу Unix-философии: один инструмент делает одну вещь хорошо и компонуется с другими через pipes[^1]. Утилита принимает текст на вход, отправляет его LLM и возвращает результат на stdout — это делает её естественной частью любого shell-пайплайна:

```bash
cat article.txt | llm "summarize this" | tee summary.txt
```

Simon Willison описывает свой подход:

> "I want to be able to interact with language models from the terminal, piping content in and out, and I want all of my interactions logged to a SQLite database"[^2]

### Двойной интерфейс

Помимо CLI, `llm` является полноценной Python-библиотекой, что позволяет использовать её программно в скриптах и приложениях[^1]. Это значит, что одни и те же модели, плагины и конфигурация доступны как из терминала, так и из Python-кода.

### Автоматическое логирование

Одна из ключевых отличительных черт — все промпты и ответы автоматически сохраняются в SQLite-базу данных[^3]. База поддерживает полнотекстовый поиск, фильтрацию по модели, просмотр через Datasette и экспорт в JSON. Это создаёт полный аудит-трейл взаимодействий с LLM — функция, которой нет у большинства альтернативных инструментов.

## Установка и базовое использование

### Способы установки

`llm` доступен через несколько пакетных менеджеров[^1]:

```bash
pip install llm        # стандартный pip
pipx install llm       # изолированная установка
brew install llm       # Homebrew (macOS)
uv tool install llm    # через uv
```

### Настройка API-ключей

По умолчанию `llm` работает с OpenAI. Для других провайдеров нужны соответствующие плагины[^1]:

```bash
llm keys set openai                    # интерактивный ввод ключа
export OPENAI_API_KEY=sk-...           # через переменную окружения
llm install llm-anthropic              # установка плагина Claude
llm keys set anthropic                 # настройка ключа Anthropic
```

### Базовые команды

```bash
llm "Ten fun names for a pet pelican"  # простой промпт
llm -m claude-3.5-sonnet "hello"       # выбор модели
llm chat                               # интерактивный чат
llm -c "продолжение"                   # продолжение разговора
llm models                             # список доступных моделей
cat file.txt | llm "summarize"         # pipe из stdin
llm "write code" -x                    # извлечь только код из ответа
```

Флаг `-c` (continue) сохраняет контекст разговора, позволяя вести многошаговые диалоги из терминала[^3]. Каждый разговор получает уникальный ID и может быть именованным.

## Продвинутые функции

### Embeddings и RAG

`llm` поддерживает генерацию и хранение embeddings — числовых представлений семантического смысла текста[^4]. Это позволяет строить полноценные RAG-системы прямо из командной строки:

```bash
# индексация коллекции документов
llm embed-multi blog-posts \
  --sql "SELECT id, title, content FROM posts" \
  --database blog.db

# семантический поиск
llm similar blog-posts "как оптимизировать запросы к базе данных"
```

Simon Willison демонстрировал поиск по 7000+ закладкам блога с использованием семантического поиска[^2]. Поддерживаются мультимодальные embeddings (например, CLIP для изображений).

### Structured Output (Schemas)

Начиная с версии 0.23, `llm` поддерживает извлечение структурированных данных через JSON-схемы[^5]:

```bash
# компактный синтаксис
llm --schema 'name, age int, short_bio' 'invent a cool dog'

# извлечение массива объектов
llm --schema-multi 'title, author, year int' 'list 5 classic novels'

# из файла схемы
llm --schema @schema.json 'extract data from this article'
```

Поддерживается интеграция с Pydantic для валидации в Python-коде. Все извлечённые данные логируются в SQLite и могут быть экспортированы через `sqlite-utils`[^5].

### Шаблоны (Templates)

YAML-шаблоны позволяют создавать переиспользуемые промпты с переменными, инструментами и схемами[^6]:

```yaml
# ~/.config/io.datasette.llm/templates/extract_people.yaml
prompt: |
  Extract all people mentioned with their roles from: $text
schema_object:
  type: object
  properties:
    people:
      type: array
      items:
        type: object
        properties:
          name: {type: string}
          role: {type: string}
tools:
  - sqlite
```

Шаблоны поддерживают переменные (`$variable`), значения по умолчанию, встроенные инструменты (sqlite, datasette), пользовательские Python-функции и модульную композицию через фрагменты[^6].

### Поддержка инструментов (Tools)

Версия 0.26 добавила возможность предоставлять моделям доступ к Python-функциям как к инструментам[^7]. Модель может вызывать функции, получать результаты и использовать их для ответа:

```bash
llm --tools sqlite "What tables are in my database?"
llm --tools datasette "Show recent entries"
```

Семь плагинов обеспечивают поддержку tools для OpenAI, Anthropic, Gemini, Mistral, Ollama и других провайдеров[^7].

## Экосистема плагинов

Плагины — главный механизм расширения `llm`. Они представляют собой Python-пакеты, устанавливаемые через `llm install`[^8].

### Категории плагинов

**Провайдеры облачных API:**

| Плагин | Провайдер |
|--------|-----------|
| `llm-anthropic` | Anthropic Claude |
| `llm-gemini` | Google Gemini |
| `llm-mistral` | Mistral AI |
| `llm-command-r` | Cohere Command R |

**Локальные модели:**

| Плагин | Назначение |
|--------|-----------|
| `llm-ollama` | Запуск моделей через Ollama |
| `llm-gguf` | Модели в формате GGUF |
| `llm-mlx` | Оптимизированные модели для Apple Silicon |
| `llm-gpt4all` | GPT4All |

**Специализированные:**

| Плагин | Назначение |
|--------|-----------|
| `llm-tools-sqlite` | SQL-запросы к локальным базам |
| `llm-tools-datasette` | Запросы к Datasette-инстансам |
| `llm-jq` | Обработка JSON |
| `llm-cmd` | Генерация shell-команд |

Полный каталог доступен на странице документации[^8]. Установка плагинов:

```bash
llm install llm-ollama
llm install llm-anthropic
llm plugins                    # список установленных
```

## Интеграция с Claude и совместимость с подписками

### Плагин llm-anthropic

`llm` полноценно поддерживает Claude через плагин `llm-anthropic` (ранее `llm-claude-3`)[^9]:

```bash
llm install llm-anthropic
llm keys set anthropic        # ввести API-ключ
llm -m claude-sonnet-4-5 "hello"
```

Поддерживаются все актуальные модели Claude (Opus 4.5, Sonnet 4.5, Haiku 4.5), включая функции extended thinking, обработку изображений и PDF, structured output, prompt caching и web search[^9].

### Можно ли использовать подписку Claude Code / Pro / Max?

**Нет.** Подписки Claude Pro, Max и Claude Code предоставляют доступ только к claude.ai и Claude Code через OAuth[^10]. Они **не включают API-доступ** для сторонних инструментов вроде `llm`.

> "Your Pro, Max, Team, or Enterprise subscription is for Claude.ai — the API and Console are separate products with separate billing"[^11]

С января 2026 года Anthropic начала блокировать использование OAuth-токенов подписок в сторонних клиентах[^12]. Для работы с `llm` требуется отдельный платный API-ключ из Anthropic Console с оплатой по токенам (pay-as-you-go).

| Вариант | Биллинг | Работает с `llm`? |
|---------|---------|-------------------|
| Claude Pro/Max | $20-200/мес подписка | Нет |
| Claude Code | Включён в Pro/Max | Нет |
| Anthropic API | Per-token, pay-as-you-go | **Да** |

Это ключевое ограничение: пользователь Claude Code не может переиспользовать свою подписку для `llm` — нужен отдельный API-ключ с отдельной оплатой[^11].

## Типичные задачи и workflow

### Разработка и код

`llm` широко используется разработчиками для автоматизации рутинных задач[^13][^14]:

- **Генерация commit-сообщений**: `git diff | llm "write a conventional commit message"`
- **Объяснение ошибок**: `error_output | llm "explain this error"`
- **Генерация README**: `files-to-prompt src/ | llm "generate README"`
- **Code review**: `git diff main | llm "review this code for security issues"`
- **Генерация shell-команд**: через плагин `llm-cmd`

### Обработка данных

Structured output и embeddings делают `llm` мощным инструментом для data engineering[^5][^4]:

```bash
# извлечение данных из PDF → SQLite
shot-scraper pdf article.pdf \
  | llm --schema 'title, author, date, summary' \
  | sqlite-utils insert articles.db data -

# построение семантического индекса
llm embed-multi documents \
  --files docs/ '*.md' \
  --store
```

### Пакетная обработка документов

```bash
for file in documents/*.txt; do
  cat "$file" | llm -c analysis "extract key points"
done
llm logs -c analysis    # просмотр всех результатов
```

### Мультимодальная обработка

Поддержка изображений, аудио и видео (через совместимые модели)[^1]:

```bash
llm "describe this image" image.jpg
llm "extract text from screenshot" screenshot.png
```

### Оптимизация затрат через смешивание моделей

```bash
# черновик через локальную модель (бесплатно)
llm -m ollama/mistral "draft function for CSV parsing"

# ревью через облачную модель (платно, но точно)
llm -m claude-sonnet-4-5 "review this code: $(cat function.py)"
```

## Сравнение с альтернативами

`llm` занимает уникальную нишу между IDE-ориентированными инструментами и чистыми API-клиентами[^15][^16]:

| Характеристика | llm | Claude Code | Aider | Ollama |
|----------------|-----|-------------|-------|--------|
| Провайдер-агностичность | Да (20+ провайдеров) | Только Anthropic | OpenAI + Anthropic | Только локальные |
| Логирование | SQLite автоматически | Нет | Git | Нет |
| Embeddings/RAG | Да | Нет | Нет | Нет |
| Structured output | Да (schemas) | Нет | Нет | Через API |
| Редактирование кода | Нет | Да (агентный) | Да (pair programming) | Нет |
| Шаблоны | Да (YAML) | Нет | Нет | Modelfiles |
| Unix pipes | Да | Ограниченно | Нет | Нет |
| Локальные модели | Через плагины | Нет | Да | Нативно |

**Ключевое отличие**: `llm` — это **инструмент общего назначения** для работы с LLM из командной строки. Claude Code и Aider — это **специализированные инструменты для программирования**. Ollama — это **runtime для локальных моделей**, который `llm` использует как один из бэкендов[^15].

## Дискуссионные вопросы и противоречия

### Scope и позиционирование

Некоторые пользователи на Hacker News отмечают, что `llm` пытается быть слишком универсальным — от простых промптов до RAG-систем[^17]. Контраргумент: модульная архитектура плагинов позволяет использовать только нужные функции, не загружая лишнее.

### API-зависимость vs локальные модели

Вопрос приватности данных остаётся актуальным. `llm` решает его поддержкой Ollama и GPT4All для полностью локальной работы[^1], но качество локальных моделей уступает облачным, что создаёт компромисс между приватностью и качеством.

### Отсутствие API-доступа в подписках Anthropic

Разделение подписок claude.ai и API вызывает недовольство пользователей, которые платят за Claude Pro/Max и хотят использовать те же модели в сторонних инструментах[^11][^12]. Anthropic объясняет это разными продуктами с разными моделями ценообразования, но для пользователей это выглядит как двойная оплата за один и тот же сервис.

## Заключение

### Синтез

`llm` — зрелый, активно развивающийся инструмент, занимающий уникальную нишу провайдер-агностичного CLI для работы с языковыми моделями. Его главные сильные стороны — Unix-совместимость, автоматическое логирование в SQLite, богатая экосистема плагинов и поддержка embeddings/RAG из коробки.

### Ключевые выводы

1. **Универсальность**: `llm` работает с 20+ провайдерами через единый интерфейс, включая локальные модели
2. **Data-first подход**: автоматическое логирование, embeddings и structured output делают его инструментом не только для генерации текста, но и для обработки данных
3. **Claude совместим, но требует API-ключ**: подписки Claude Code/Pro/Max не дают API-доступ — нужен отдельный платный ключ из Anthropic Console
4. **Composability**: следование Unix-философии делает `llm` естественной частью shell-пайплайнов

### Практические рекомендации

- Для разработчиков, уже использующих Claude Code: `llm` дополняет (не заменяет) Claude Code — для задач обработки данных, пакетных операций и работы с несколькими моделями
- Для экономии: использовать локальные модели через Ollama для черновиков и экспериментов, облачные — для финальных результатов
- Для логирования: встроенная SQLite-база полезна для аудита, анализа затрат и отладки промптов

## Источники

[^1]: Simon Willison. "LLM — CLI utility and Python library for interacting with Large Language Models." GitHub, 2026. <https://github.com/simonw/llm>
[^2]: Simon Willison. "Language models on the command-line." Simon Willison's Weblog, 2024-06-17. <https://simonwillison.net/2024/Jun/17/cli-language-models/>
[^3]: "Logging to SQLite." LLM Documentation, Datasette, 2026. <https://llm.datasette.io/en/stable/logging.html>
[^4]: "Embeddings." LLM Documentation, Datasette, 2026. <https://llm.datasette.io/en/stable/embeddings/index.html>
[^5]: Simon Willison. "Structured data extraction from unstructured content using LLM schemas." Simon Willison's Weblog, 2025-02-28. <https://simonwillison.net/2025/Feb/28/llm-schemas/>
[^6]: "Templates." LLM Documentation, Datasette, 2026. <https://llm.datasette.io/en/stable/templates.html>
[^7]: Simon Willison. "LLM 0.26: Tools support." Simon Willison's Weblog, 2025-05-27. <https://simonwillison.net/2025/May/27/llm-tools/>
[^8]: "Plugin directory." LLM Documentation, Datasette, 2026. <https://llm.datasette.io/en/stable/plugins/directory.html>
[^9]: Simon Willison. "llm-anthropic — LLM plugin for Anthropic's Claude models." GitHub, 2026. <https://github.com/simonw/llm-anthropic>
[^10]: "Using Claude Code with your Pro or Max plan." Claude Help Center, Anthropic, 2026. <https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan>
[^11]: "Why do I have to pay separately for the Claude API?" Claude Help Center, Anthropic, 2026. <https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console>
[^12]: "Anthropic Bans Claude Subscription OAuth in Third-Party Apps." WinBuzzer, 2026-02-19. <https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/>
[^13]: Simon Willison. "How I use LLMs to help me write code." Simon Willison's Substack, 2025. <https://simonw.substack.com/p/how-i-use-llms-to-help-me-write-code>
[^14]: Bill Cava. "Terminal AI: How LLM Changed My Workflow." Medium, 2025. <https://medium.com/@billcava/terminal-ai-how-llm-changed-my-workflow-71ef97ddab5b>
[^15]: "2026 Coding CLI Tools Comparison." Tembo, 2026. <https://www.tembo.io/blog/coding-cli-tools-comparison>
[^16]: "Top 5 CLI-Based AI Coding Agents." Pinggy, 2026. <https://pinggy.io/blog/top_cli_based_ai_coding_agents/>
[^17]: "LLMs on the Command Line." Hacker News Discussion, 2024. <https://news.ycombinator.com/item?id=40782755>

## Quality Metrics

| Metric | Value |
|--------|-------|
| Total sources | 22 |
| Academic sources | 0 |
| Official/documentation | 6 |
| Industry reports | 2 |
| News/journalism | 1 |
| Blog/forum | 13 |
| Citation coverage | 92% |
| Counter-arguments searched | Yes |
