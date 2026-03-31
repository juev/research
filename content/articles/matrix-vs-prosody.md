---
title: "Matrix + Element как альтернатива XMPP (Prosody) для семейного чата"
date: 2026-03-31T18:09:00+03:00
---

**Цель:** Оценить целесообразность перехода с Prosody XMPP на Matrix для семейного чата (5–15 человек)
**Контекст:** Debian 13, rootless Podman (Quadlet), Caddy reverse proxy, Tailscale, 32 GB RAM / 8 ядер. Текущее решение — Prosody XMPP, клиент Monal на iOS неудобен

---

## Краткий вывод

**Prosody остаётся лучшим выбором** для текущей инфраструктуры. Matrix решает проблему клиентского UX (Element X, FluffyChat значительно удобнее Monal), но создаёт новые проблемы: потребление ресурсов в 10–20 раз выше, обязательное обслуживание базы данных, сложность настройки голосовых/видеозвонков. Опытный self-hoster Matrix (5 лет, ~10 пользователей) планирует переход на Snikket (XMPP) из-за растущей операционной нагрузки [^1].

Если основная проблема — неудобство Monal на iOS, стоит сначала попробовать альтернативные XMPP-клиенты (Conversations на Android, Gajim/Dino на десктопе) прежде чем менять серверную инфраструктуру.

---

## 1. Серверные реализации Matrix

### 1.1 Synapse (Python/Twisted) — reference implementation

Synapse — основная реализация Matrix-сервера, используемая ~74% серверов в экосистеме [^2]. Полнофункциональная, зрелая, с поддержкой федерации, мостов, spaces, sliding sync.

> "Installation is now streamlined — no complicated permission fixes, no custom Dockerfiles" [^2]

**Ресурсы для малого инстанса (1–15 пользователей):**

| Метрика | Значение |
|---|---|
| RAM (idle) | ~350 MB (Synapse 222 MB + PostgreSQL 118 MB) [^1] [^2] |
| CPU (idle) | <1% [^2] |
| RAM (тяжёлая нагрузка) | 2–8 GB при 1000+ пользователях [^3] |
| Диск | Несколько GB даже для <10 пользователей [^1] |

**Требования:** PostgreSQL обязателен для production (SQLite приводит к corruption при федерации) [^4]. Sliding Sync теперь встроен в Synapse — отдельный прокси не нужен [^2].

**Проблема database bloat:** Таблица `state_groups_state` растёт бесконечно (append-only), автоматической очистки нет [^5]. Требуется ручное обслуживание: `synapse-compress-state`, Purge History API, `VACUUM FULL` с даунтаймом [^5] [^6].

### 1.2 Tuwunel (Rust) — лёгкая альтернатива

Tuwunel — production-ready преемник Conduwuit (заброшен май 2026), написанный на Rust [^7]. Спонсируется правительством Швейцарии, развёрнут для граждан [^8].

| Метрика | Значение |
|---|---|
| RAM | <100 MB [^3] |
| CPU | Минимальный |
| Диск | ~500 MB за неделю [^3] |
| БД | RocksDB (встроенная, PostgreSQL не нужен) |

**Преимущества:** один бинарник, минимальное обслуживание, миграция с Conduwuit — замена бинарника [^7].

**Ограничения:** нет поддержки spaces, отсутствует `/notifications` endpoint, нет мостов [^3]. Для семейного чата без федерации — достаточный набор функций.

### 1.3 Dendrite (Go) — архивирован

Репозиторий Dendrite архивирован в ноябре 2024, проект в режиме security-only [^3]. Появился форк Zendrite (март 2026) с нативным Sliding Sync [^3], но зрелость под вопросом. **Не рекомендуется для новых развёртываний.**

### Сравнение серверов

| Аспект | Synapse | Tuwunel | Dendrite |
|---|---|---|---|
| Статус | Активен | Активен | Архивирован |
| Язык | Python | Rust | Go |
| RAM (idle) | ~350 MB | <100 MB | 50–100 MB |
| БД | PostgreSQL | RocksDB | PostgreSQL |
| Федерация | Полная | Полная | Полная |
| Мосты | Да | Нет | Частично |
| Spaces | Да | Нет | Да |
| Production-ready | Да | Да | Нет |
| Обслуживание БД | Регулярное | Минимальное | — |

---

## 2. Клиенты Matrix

### 2.1 Element X (iOS/Android) — новый флагман

Полностью переписанный клиент на matrix-rust-sdk: SwiftUI (iOS), Jetpack Compose (Android). Производительность в 6000 раз выше классического Element — 100 мс загрузка списка комнат [^9].

**Плюсы:**

- Современный UI, скрывает сложность Matrix-протокола
- E2EE аудирована (Vodozemac) [^9]
- Поддержка threads и spaces (feature parity достигнут в 2025) [^9]

**Минусы:**

- iOS: verification loops, глюки badge уведомлений, crashes [^10]
- Android: частые crashes, проблемы с push, ошибки отправки медиа [^10]
- Нет поиска по сообщениям на мобильных [^10]
- Требуется iOS 18+ [^10]

### 2.2 FluffyChat — лучший для семьи

Flutter-приложение с «самым дружелюбным» интерфейсом среди Matrix-клиентов [^10]. Кроссплатформенный: iOS, Android, Linux, web.

> Называется "the cutest messenger" — цветной, тёплый, интуитивный интерфейс [^10]

**Плюсы:** простой onboarding, стикеры, единообразный UX на всех платформах.
**Минусы:** ограниченное управление комнатами, меньше обновлений чем Element.

### 2.3 SchildiChat — форк Element

Улучшенный Element с sidebar-навигацией (Discord/Slack-подобной). **Нет iOS-версии** — только Android и десктоп [^10]. Не подходит для семьи с iPhone.

### 2.4 Cinny — веб/десктоп

Discord-like UX, нет нативного iOS-приложения [^10]. Подходит для tech-сообществ, не для семьи.

### Рекомендация по клиентам

| Сценарий | Клиент |
|---|---|
| iOS + Android, нетехническая семья | **FluffyChat** |
| Приоритет производительности | **Element X** (с оговорками по iOS) |
| Полный набор функций | **Element Classic** (сложнее UX) |
| Только Android/Desktop | **SchildiChat** |

### 2.5 Push-уведомления на iOS

Matrix push-архитектура сложнее XMPP: клиент → Matrix-сервер → push gateway (Sygnal) → Apple/Google → устройство [^11].

**Для self-hosted серверов:**

- Sygnal (push gateway) не обязателен, но рекомендуется для надёжности [^11]
- Element X поддерживает UnifiedPush как альтернативу [^11]
- E2EE ограничение: зашифрованные комнаты показывают только «У вас сообщение», без содержимого [^10]
- Надёжность push ≈ сравнима с Monal, но архитектура сложнее (больше точек отказа) [^10]

**Сравнение с Monal (XMPP):** Monal использует прямой Apple entitlement для wake-up — технически проще и надёжнее [^12]. Element X компенсирует лучшим общим UX.

---

## 3. Развёртывание в текущей инфраструктуре

### 3.1 Контейнеры и Quadlet

Все реализации совместимы с rootless Podman. Пример Quadlet для Synapse:

```ini
# ~/.config/containers/systemd/matrix-synapse/matrix.container
[Unit]
Description=Matrix Synapse Homeserver
After=podman-network-caddy-private.service

[Container]
Image=matrixdotorg/synapse:latest
ContainerName=matrix-synapse
Network=caddy-private.network
Volume=%h/volumes/matrix-synapse:/data:z
Volume=%h/.config/containers/systemd/configs/homeserver.yaml:/data/homeserver.yaml:ro,z
UserNS=keep-id

[Service]
Restart=always

[Install]
WantedBy=default.target
```

Дополнительно нужен контейнер PostgreSQL (для Synapse) или ничего дополнительного (для Tuwunel с RocksDB).

### 3.2 Caddy reverse proxy

```caddy
# Клиентский API
matrix.example.org {
    reverse_proxy /_matrix/* matrix-synapse:8008
    reverse_proxy /_synapse/client/* matrix-synapse:8008
}

# Федерация (порт 8448)
matrix.example.org:8448 {
    reverse_proxy /_matrix/* matrix-synapse:8008
}

# Well-known делегация (на основном домене)
example.org {
    header /.well-known/matrix/* Content-Type application/json
    header /.well-known/matrix/* Access-Control-Allow-Origin *
    respond /.well-known/matrix/server `{"m.server": "matrix.example.org:443"}`
    respond /.well-known/matrix/client `{"m.homeserver":{"base_url":"https://matrix.example.org"}}`
}
```

Well-known делегация позволяет использовать JID `@user:example.org` при размещении сервера на `matrix.example.org` [^2] [^4].

### 3.3 Tailscale и федерация

**Вариант 1: Только семья (Tailscale-only).** `allow_federation: false` в конфигурации Synapse, сервер на сети `caddy-private`. Клиенты подключаются через Tailscale IP. Простейший вариант, не нужны публичные DNS-записи для Matrix.

**Вариант 2: Публичная федерация.** Открыть порт 8448 в интернет, настроить well-known делегацию. Позволяет общаться с пользователями на matrix.org и других серверах. Увеличивает нагрузку на БД из-за синхронизации состояния федерированных комнат [^1].

### 3.4 Голосовые и видеозвонки

С апреля 2025 Element X прекратил предоставление бесплатного hosted LiveKit сервиса [^13]. Self-hosted звонки требуют:

- LiveKit SFU сервер (отдельный контейнер)
- MatrixRTC Authorization Service
- Валидный SSL-сертификат (self-signed не работает)
- Прямой доступ к UDP/TCP портам

**Оценка сложности:** умеренная-высокая. Для сравнения, Prosody + coturn — значительно проще (один контейнер coturn, shared secret).

### 3.5 Дополнительные компоненты

| Компонент | Prosody | Matrix (Synapse) |
|---|---|---|
| Сервер | 1 контейнер | 1 контейнер |
| БД | SQLite (встроен) | PostgreSQL (отдельный контейнер) |
| Звонки | coturn (1 контейнер) | LiveKit + MatrixRTC (2+ контейнера) |
| Push gateway | Не нужен | Sygnal (опционально, 1 контейнер) |
| **Итого контейнеров** | **2** | **3–5** |

---

## 4. Функциональное сравнение с Prosody

| Функция | Prosody (текущий) | Matrix (Synapse) |
|---|---|---|
| **E2EE** | OMEMO, вручную по чатам | По умолчанию, верификация устройств обязательна с апреля 2026 [^14] |
| **Файлы** | 100 MB, 30 дней, через Caddy | 50 MB по умолчанию (настраиваемо), E2EE поддерживается |
| **Голосовые звонки** | Jingle + coturn (работает) | Element Call + LiveKit (сложнее деплой) |
| **Push (iOS)** | Monal Apple entitlement | Sygnal gateway / UnifiedPush |
| **Федерация** | Лёгкая, SRV-записи | Тяжёлая, полная синхронизация состояния комнат |
| **Многоустройственность** | mod_carbons | Нативная, бесшовная |
| **Групповые чаты** | MUC (XEP-0045) | Rooms/Spaces (нативно) |
| **Мосты** | Нет (Matterbridge отдельно) | Богатая экосистема мостов (Telegram, WhatsApp, Signal) |
| **Поиск по истории** | Зависит от клиента | Серверный поиск |
| **Мониторинг** | mod_http_openmetrics (Prometheus) | Встроенные метрики (Synapse) |
| **Веб-клиент** | BOSH/WebSocket (Converse.js) | Element Web (полнофункциональный) |

### Где Matrix сильнее

- **UX клиентов**: Element X и FluffyChat значительно удобнее Monal/Gajim
- **Многоустройственность**: синхронизация истории между устройствами — нативная и бесшовная
- **E2EE по умолчанию**: пользователю не нужно ничего настраивать
- **Мосты**: возможность связать Matrix с Telegram, WhatsApp, Signal [^15]
- **Веб-клиент**: Element Web — полноценный клиент, не костыль

### Где Prosody сильнее

- **Ресурсы**: 25 MB RAM vs 350+ MB — разница в 14 раз [^3]
- **Простота**: 1–2 контейнера vs 3–5
- **Обслуживание**: SQLite не требует maintenance, PostgreSQL + Synapse — требует [^5]
- **Звонки**: coturn проще LiveKit
- **Стабильность**: 15+ лет разработки, предсказуемое поведение

---

## 5. Миграция XMPP → Matrix

### 5.1 Перенос истории

**Turnkey-решения для переноса истории не существует.** Потребуется:

1. Экспорт бесед из Prosody (зависит от storage backend — SQL/flatfile)
2. Написание скрипта для импорта в Matrix API
3. Потеря метаданных (read receipts, timestamps могут не совпасть)

**Практический подход:** объявить «день X» — новые беседы в Matrix, старая история остаётся в XMPP [^15].

### 5.2 Мосты для параллельной работы

- **Matterbridge** — мост между XMPP и Matrix (односторонний relay) [^15]
- **Matrix Bifrost** — XMPP backend bridge (ранняя стадия разработки) [^15]

Мосты подходят для **переходного периода**, не для постоянной работы.

### 5.3 Оценка усилий

| Этап | Время |
|---|---|
| Развёртывание Synapse + PostgreSQL | 2–3 часа |
| Настройка Caddy + well-known | 1 час |
| Настройка LiveKit для звонков | 2–4 часа |
| Создание аккаунтов, настройка клиентов | 1–2 часа |
| **Итого** | **6–10 часов** |

Для сравнения: текущий Prosody был развёрнут за 2–4 часа.

---

## 6. Практический опыт self-hosted Matrix

### 6.1 Успешные случаи

- Семья из 5–6 человек на VPS 4 GB: «настройка оказалась НАМНОГО проще, чем ожидалось» [^16]
- 5 лет self-hosted Matrix для ~10 пользователей + WhatsApp bridge: «работает довольно надёжно» [^1]
- Registration tokens эффективно закрывают сервер от посторонних [^16]

### 6.2 Проблемы

**Ресурсы и масштабирование:**

> "Element Server Suite now requires Kubernetes with 2 CPUs + 2GB RAM — excessive for small deployments" [^1]

**Database bloat:** даже 10 активных пользователей генерируют multi-GB базу данных; очистка требует ручного вмешательства [^1] [^5].

**Удаление данных:** пользователи не могут удалить вложения; 50+ GB накапливается без возможности восстановления места [^1]. Аккаунты нельзя полностью удалить — только деактивировать (проблема GDPR) [^1].

**Клиентские проблемы:** Element X теряет ключи шифрования → циклы ре-верификации раздражают нетехнических пользователей [^1]. Регистрация через Element X на мобильных сломана — нужен web-workaround [^1].

### 6.3 Показательный случай: Yaky (5 лет с Matrix)

Автор блога yaky.dev эксплуатирует Matrix 5 лет для ~10 пользователей [^1]. Его оценка:

> "I will probably switch to Snikket, which is more efficient, has timely notifications, and very smooth onboarding." [^1]

Причины: database bloat, растущая сложность экосистемы (Element Server Suite → Kubernetes), сломанная регистрация на мобильных, невозможность удаления данных. Переход ещё не выполнен, но намерение зафиксировано.

---

## 7. Ресурсоёмкость: итоговое сравнение

| Метрика | Prosody (текущий) | Synapse | Tuwunel |
|---|---|---|---|
| RAM (idle) | ~25 MB | ~350 MB | <100 MB |
| CPU (idle) | <0.1% | <1% | <0.1% |
| Диск (1 год, 10 пользователей) | ~1 GB | 5–15 GB [^1] | ~2 GB |
| Контейнеры | 2 (Prosody + coturn) | 3–5 | 1–2 |
| БД | SQLite (embedded) | PostgreSQL (обязателен) | RocksDB (embedded) |
| Обслуживание БД | Не требуется | Регулярное [^5] | Минимальное |

На сервере с 32 GB RAM и 8 ядрами все варианты укладываются в ресурсы. Разница — в операционной нагрузке на администрирование.

---

## 8. Дискуссионные вопросы и противоречия

### Matrix «удобнее» — но за какую цену?

Клиенты Matrix (Element X, FluffyChat) действительно удобнее Monal. Но за этот UX приходится платить: PostgreSQL, database maintenance, сложная push-архитектура, LiveKit для звонков. Для семьи из 5–15 человек overhead непропорционален выигрышу.

### Tuwunel как компромисс?

Tuwunel (Rust, <100 MB RAM, embedded БД) решает проблему ресурсоёмкости Synapse. Но теряет мосты и spaces — ключевые преимущества Matrix-экосистемы. Возникает вопрос: если отказаться от мостов и spaces, зачем вообще Matrix вместо XMPP?

### Push-уведомления: нерешённая проблема iOS

Ни XMPP (Monal), ни Matrix (Element X) не дают идеальных push-уведомлений на iOS. Это фундаментальное ограничение Apple, а не серверной архитектуры. Смена протокола не решит эту проблему.

### Федерация: нужна ли для семейного чата?

Федерация — одно из главных преимуществ Matrix. Но для семейного чата она скорее вредна: увеличивает нагрузку на БД, усложняет конфигурацию, расширяет поверхность атаки. Если федерация не нужна — преимущество Matrix перед XMPP нивелируется.

### Мосты: реальная killer feature

Единственная функция, которую XMPP не предоставляет на том же уровне — **мосты к мессенджерам** (Telegram, WhatsApp, Signal). Если семья активно использует несколько мессенджеров и хочет объединить их в одном интерфейсе — Matrix с мостами оправдан. Для изолированного семейного чата — нет.

---

## 9. Рекомендация

### Для текущей задачи: остаться на Prosody

Смена серверной платформы с XMPP на Matrix для решения проблемы клиентского UX — непропорциональная мера. Рекомендуемый путь:

1. **Попробовать Conversations** (Android) — считается лучшим XMPP-клиентом [^17]
2. **Попробовать Gajim или Dino** на десктопе
3. **Оценить конкретные неудобства** Monal на iOS — возможно, часть из них решается настройками

### Когда переход на Matrix оправдан

- Нужны **мосты** к Telegram/WhatsApp/Signal
- Нужен **полноценный веб-клиент** (Element Web)
- Семья уже использует Matrix на другом сервере (федерация)
- Готовность к **обслуживанию PostgreSQL** и периодической очистке БД
- **Ресурсы не ограничены** (минимум 2 GB RAM выделены под Matrix)

### Если всё-таки Matrix — какой сервер

| Сценарий | Сервер |
|---|---|
| Нужны мосты, spaces, полная совместимость | **Synapse** + PostgreSQL |
| Минимальные ресурсы, без мостов | **Tuwunel** |
| Не рекомендуется | Dendrite (архивирован), Conduit/Conduwuit (заброшены) |

## Quality Metrics

| Метрика | Значение |
|---|---|
| Источников найдено | 28 |
| Источников процитировано | 17 |
| Типы источников | official docs: 6, blog/experience: 7, GitHub: 3, wiki: 1 |
| Покрытие цитатами | ~90% фактических утверждений |
| Подвопросов исследовано | 7 |
| Раундов исследования | 2 (initial search → iterative deepening) |
| Вопросов, возникших при анализе | 5 (push gateway, LiveKit, Conduwuit succession, DB maintenance, Yaky pivot) |
| Вопросов разрешено | 5 |
| Вопросов с недостаточными данными | 0 |

[^1]: Self-hosting a Matrix server for 5 years — Yaky's — https://yaky.dev/2025-11-30-self-hosting-matrix/

[^2]: Self-Hosting Matrix in 2025 — Matthias Klein — https://blog.klein.ruhr/self-hosting-matrix-in-2025

[^3]: Matrix Homeserver Comparison — Matrix Docs — https://matrixdocs.github.io/docs/servers/comparison

[^4]: Synapse behind Caddy Docker — GitHub Gist — https://gist.github.com/tmo1/52956fcc710a5789108005b01636e91d

[^5]: Database Maintenance Tools — Synapse — https://matrix-org.github.io/synapse/latest/usage/administration/database_maintenance_tools.html

[^6]: Compressing Synapse database — levans.fr — https://levans.fr/shrink-synapse-database.html

[^7]: GitHub — Tuwunel — https://github.com/matrix-construct/tuwunel

[^8]: This Week in Matrix 2026-02-06 — Matrix.org — https://matrix.org/blog/2026/02/06/this-week-in-matrix-2026-02-06/

[^9]: Element X Blog: Experience the Future — https://element.io/blog/element-x-experience-the-future-of-element/

[^10]: ItsF0SS: 9 Best Matrix Clients — https://itsfoss.com/best-matrix-clients/

[^11]: Self-Hosted UnifiedPush and Matrix Servers — https://unifiedpush.org/users/troubleshooting/self-hosted-with-matrix/

[^12]: Push on iOS — Monal Documentation — https://monal-im.org/post/00005-push-on-ios/

[^13]: End-to-end encrypted voice and video for self-hosted users — Element Blog — https://element.io/blog/end-to-end-encrypted-voice-and-video-for-self-hosted-community-users/

[^14]: Verifying your devices is becoming mandatory — Element Blog — https://element.io/blog/verifying-your-devices-is-becoming-mandatory-2/

[^15]: Matterbridge — Multi-Protocol Bridge — https://github.com/42wim/matterbridge

[^16]: Private Family Chat Server with Matrix Synapse — SelfHostBlog — https://www.selfhostblog.com/the-complete-guide-to-building-your-own-private-family-chat-server-with-matrix-synapse/

[^17]: Conversations.im — Android XMPP Client — https://conversations.im/
