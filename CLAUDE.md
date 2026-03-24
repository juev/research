# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

Коллекция аналитических обзоров (research articles) на MkDocs + Material theme. Публикуется на <https://research.evsyukov.org/> через GitHub Pages при push в `main`.

## Команды

```bash
# Установка зависимостей
pip install -r requirements.txt

# Локальный сервер с live-reload
mkdocs serve

# Сборка статического сайта (output: site/)
mkdocs build
```

## Архитектура

- **docs/** — markdown-статьи. Каждая статья — отдельный `.md` файл с H1-заголовком
- **docs/index.md** — главная страница, использует Jinja-макрос `{{ article_list() }}` для автогенерации списка статей
- **main.py** — mkdocs-macros-plugin модуль: функция `define_env` регистрирует макрос `article_list()`, который сканирует `docs/` и формирует список ссылок из H1-заголовков файлов
- **mkdocs.yml** — конфигурация: Material theme, плагины (search, awesome-nav, macros), markdown-расширения
- **.github/workflows/deploy.yml** — CI: Python 3.12, `pip install` → `mkdocs build` → deploy на GitHub Pages

## Добавление новой статьи

1. Создать `docs/<slug>.md` с H1-заголовком (`# Название`)
2. Статья автоматически появится в навигации (awesome-nav) и на главной странице (макрос `article_list()`)
3. Язык контента — русский

## Deep Research

При выполнении `/deep-research` результат сохранять в `docs/<slug>.md`, а не в корне репозитория. Slug должен отражать тему исследования (например, `docs/api-gateway-comparison.md`).
