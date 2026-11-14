# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Коллекция аналитических обзоров (research articles) на Hugo с локальной темой — те же шаблоны, SCSS и JS, что на <https://www.juev.org/>. Публикуется на <https://research.evsyukov.org/> через GitHub Pages при push в `main`.

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
- **hugo.toml** — конфигурация: формат лент (RSS + Atom), markdown-расширения (footnotes, unsafe HTML), подсветка кода
- **layouts/**, **assets/** — тема: локальные шаблоны, SCSS и JS (порт темы juev.org), сторонних тем и submodule нет
- **layouts/index.atom.xml**, **layouts/index.rss.xml** — ленты `/atom.xml` (полный текст) и `/index.xml` (аннотации)
- **.github/workflows/deploy.yml** — CI: Hugo → deploy на GitHub Pages (fetch-depth: 0 ради `.GitInfo`)

## Добавление новой статьи

1. Создать `content/articles/<slug>.md` с frontmatter:

```yaml
---
title: "Название статьи"
date: 2026-03-25T14:30:00+03:00
---
```

Формат даты — ISO 8601 с временем и timezone offset (`+03:00`). Время берётся **текущее** на момент создания статьи (проверять через `date +%H:%M`). Не выдумывать время — это приводит к датам в будущем. Это обеспечивает правильную сортировку статей, созданных в один день.

1. Статья автоматически появится в архиве `/articles/` по месяцам и в лентах `/atom.xml`, `/index.xml`; на главной показывается только последняя статья
1. Язык контента — русский

## Deep Research

При выполнении `/deep-research` результат сохранять в `content/articles/<slug>.md` с frontmatter (title + date в ISO 8601 с временем). Slug должен отражать тему исследования.

### Структура статьи

- **Без секции Metadata** — не добавлять блок с Date, Research query, Sources, Citation coverage, Mode в начало статьи. Frontmatter (title + date) достаточно.
- **Без отдельных файлов метрик** — не сохранять `<slug>.metrics.json` (или иные sidecar-файлы) рядом со статьёй. В `content/articles/` попадают только сами статьи; посторонние файлы мешают публикации. Метрики пайплайна возвращать только в Result-блоке ответа.
- **Без секции Источники** — не добавлять заголовок `## Источники`. Footnotes (`[^N]:`) размещаются в конце файла без заголовка — Hugo рендерит их автоматически.
- **Quality Metrics в конце** — таблица `## Quality Metrics` идёт последней секцией перед footnotes.

### Обезличивание

- **Домены** — в примерах конфигураций и кода использовать `example.org` и его поддомены (например, `matrix.example.org`). Реальные домены автора или третьих лиц не допускаются.
- **Учётные данные** — токены, пароли, API-ключи в примерах заменять плейсхолдерами (`<your-api-key>`, `sk-...`, `<сгенерировать случайный ключ>`). Реальные значения не допускаются.
