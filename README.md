# Research

Коллекция аналитических обзоров по инструментам и технологиям.

Опубликовано на <https://research.evsyukov.org/>

## Локальная разработка

Сайт собирается [Hugo](https://gohugo.io/) (extended, версия закреплена в
`.github/workflows/deploy.yml`):

```bash
hugo server          # предпросмотр на http://localhost:1313/
hugo --minify        # сборка в public/
```

## Структура

- `content/articles/` — статьи, по одному `.md` на статью (YAML front matter:
  `title`, `date` в ISO 8601 с часовым поясом)
- `layouts/`, `assets/` — тема: локальные шаблоны, SCSS и JS, те же, что на
  <https://www.juev.org/>; сторонних тем и git submodule нет
- `hugo.toml` — конфигурация сайта, форматов вывода и подсветки кода
- `static/` — шрифты, иконки, PDF-отчёты

## Ленты

- <https://research.evsyukov.org/atom.xml> — Atom, полный текст статей
- <https://research.evsyukov.org/index.xml> — RSS 2.0, аннотации

Обе ленты объявлены в `<head>` через `<link rel="alternate">`, число записей
задаётся `rssLimit` в `hugo.toml`.

## Деплой

Сайт собирается и публикуется на GitHub Pages при push в ветку `main` через
GitHub Actions.
