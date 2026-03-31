# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Коллекция аналитических обзоров (research articles) на Hugo + PaperMod theme. Публикуется на <https://research.evsyukov.org/> через GitHub Pages при push в `main`.

## Команды

```bash
# Локальный сервер с live-reload
hugo server

# Сборка статического сайта (output: public/)
hugo --minify
```

## Архитектура

- **content/articles/** — markdown-статьи. Каждая статья — отдельный `.md` файл с YAML frontmatter (title, date с временем в ISO 8601)
- **content/_index.md** — главная страница
- **hugo.toml** — конфигурация: PaperMod theme, markdown-расширения (footnotes, unsafe HTML)
- **themes/PaperMod/** — тема (git submodule)
- **.github/workflows/deploy.yml** — CI: Hugo → deploy на GitHub Pages

## Добавление новой статьи

1. Создать `content/articles/<slug>.md` с frontmatter:

```yaml
---
title: "Название статьи"
date: 2026-03-25T14:30:00+03:00
---
```

Формат даты — ISO 8601 с временем и timezone offset (`+03:00`). Время берётся на момент создания статьи. Это обеспечивает правильную сортировку статей, созданных в один день.

1. Статья автоматически появится в списке на главной странице, отсортированная по дате (новые сверху)
1. Язык контента — русский

## Deep Research

При выполнении `/deep-research` результат сохранять в `content/articles/<slug>.md` с frontmatter (title + date в ISO 8601 с временем). Slug должен отражать тему исследования.

### Структура статьи

- **Без секции Metadata** — не добавлять блок с Date, Research query, Sources, Citation coverage, Mode в начало статьи. Frontmatter (title + date) достаточно.
- **Без секции Источники** — не добавлять заголовок `## Источники`. Footnotes (`[^N]:`) размещаются в конце файла без заголовка — Hugo рендерит их автоматически.
- **Quality Metrics в конце** — таблица `## Quality Metrics` идёт последней секцией перед footnotes.
