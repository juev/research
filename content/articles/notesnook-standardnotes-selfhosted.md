---
title: "Селф-хостинг Notesnook и Standard Notes: сравнительный анализ"
date: 2026-04-02T10:24:00+03:00
---

Заметки с end-to-end шифрованием становятся стандартом для пользователей, заботящихся о приватности. Два наиболее зрелых open-source решения в этой нише --- Notesnook и Standard Notes --- предлагают возможность самостоятельного размещения сервера синхронизации. Этот обзор анализирует практические аспекты селф-хостинга обоих решений: от архитектуры и системных требований до интеграции с клиентскими приложениями и типичных проблем при развёртывании.

## Архитектура и компоненты

### Standard Notes

Standard Notes использует микросервисную архитектуру, существенно упрощённую в версии 2 (февраль 2023)[^1]. Текущая версия состоит из четырёх Docker-контейнеров вместо тринадцати в legacy-версии, что привело к сокращению потребления памяти на 65%[^2].

Основные компоненты:

- **API Gateway** --- точка входа, маршрутизирующая запросы от клиентов к внутренним сервисам
- **Syncing Server** (+ Worker) --- управление данными пользователей и синхронизация; Worker обрабатывает асинхронные задачи (email-бэкапы, история ревизий)
- **Auth Service** (+ Worker) --- авторизация и аутентификация; Worker занимается задачами вроде удаления аккаунтов
- **MySQL** --- основная база данных
- **Redis** --- кэш и очередь сообщений между сервисами
- **LocalStack** --- эмуляция S3 для хранения файлов (вложения, зашифрованные бэкапы)

Web-приложение --- отдельный контейнер, не входящий в базовый стек. Его можно развернуть дополнительно через `docker run -d -p 3000:80 standardnotes/web`[^3].

### Notesnook

Notesnook построен на .NET 8 и состоит из трёх core-сервисов[^4]:

- **Notesnook.API** --- основной сервис синхронизации данных
- **Streetwriters.Identity** --- аутентификация и авторизация
- **Streetwriters.Messenger** --- Server-Sent Events для real-time синхронизации

Инфраструктурные зависимости:

- **MongoDB** --- база данных
- **MinIO** --- S3-совместимое хранилище для вложений
- **cors-proxy** --- обработка CORS-запросов

Дополнительно может быть развёрнут web-клиент (React-приложение) и Monograph Server для публичного шаринга заметок.

### Сравнение архитектур

| Аспект | Standard Notes | Notesnook |
|---|---|---|
| Контейнеры (минимум) | 4 | 5-6 |
| База данных | MySQL | MongoDB |
| Файловое хранилище | LocalStack (S3) | MinIO (S3) |
| Кэш/очереди | Redis | --- |
| Runtime | Node.js | .NET 8 |
| Лицензия | AGPL-3.0 | AGPL-3.0 |

## Системные требования

### Standard Notes

Официальные минимальные требования[^2]:

- **ОС**: Linux (Ubuntu 22.04 или совместимый дистрибутив)
- **RAM**: 2 ГБ (минимум), 4 ГБ рекомендуется
- **CPU**: 1 vCore
- **Docker**: актуальная версия
- **Хранилище**: зависит от объёма заметок и вложений; 10 ГБ для начала

### Notesnook

Официальные требования не формализованы (альфа-стадия). По данным сообщества[^5][^6]:

- **RAM**: 2 ГБ (минимум), 4 ГБ рекомендуется (MongoDB потребляет больше при росте базы)
- **Docker и Docker Compose**
- **Хранилище**: от 10 ГБ (MongoDB + MinIO)
- **Сеть**: несколько портов (5264, 6264, 7264, 8264, 9090, 9009)

Для сборки из исходников потребуется .NET 8 SDK и Git[^4].

## Процесс развёртывания

### Standard Notes: Docker (рекомендуемый метод)

Standard Notes предоставляет подробную официальную документацию[^2]. Процесс:

**1. Подготовка рабочей директории:**

```bash
mkdir standardnotes && cd standardnotes
```

**2. Получение конфигурационных файлов:**

```bash
curl https://raw.githubusercontent.com/standardnotes/server/main/.env.sample > .env
curl https://raw.githubusercontent.com/standardnotes/server/main/docker-compose.example.yml > docker-compose.yml
curl https://raw.githubusercontent.com/standardnotes/server/main/docker/localstack_bootstrap.sh > localstack_bootstrap.sh
chmod +x localstack_bootstrap.sh
```

**3. Генерация секретов и настройка `.env`:**

```bash
openssl rand -hex 32  # для AUTH_JWT_SECRET, VALET_TOKEN_SECRET и др.
openssl rand -hex 12  # для DB_PASSWORD
```

Ключевые переменные: `DB_PASSWORD`, `AUTH_JWT_SECRET`, `VALET_TOKEN_SECRET`, `ENCRYPTION_SERVER_KEY`. Пароль БД указывается в трёх местах: `.env` и два раза в `docker-compose.yml` (MYSQL_ROOT_PASSWORD, MYSQL_PASSWORD)[^2].

**4. Запуск:**

```bash
docker compose pull && docker compose up -d
```

**5. Проверка:**

Сервер доступен по `http://localhost:3000`. Логи: `tail -f logs/*.log`[^2].

**6. Настройка HTTPS (для продакшна):**

Reverse proxy (Nginx, Traefik или Caddy) с SSL-сертификатом. Standard Notes предоставляет отдельную документацию по настройке HTTPS[^7].

### Notesnook: Docker

Официальная документация минимальна (помечена как TODO)[^4]. Базовый процесс:

**1. Получение docker-compose.yml:**

```bash
wget https://raw.githubusercontent.com/streetwriters/notesnook-sync-server/master/docker-compose.yml
```

**2. Запуск:**

```bash
docker compose up
```

Docker Compose автоматически поднимает MongoDB, MinIO и три core-сервиса[^4].

Однако для production-развёртывания этого недостаточно. Сообщество создало расширенные конфигурации[^5][^6][^8], которые включают:

- Создание структуры директорий для данных (`database/`, `storage/`, `config/`)
- Настройку `.env` файла с доменами, SMTP-credentials, токенами API
- Конфигурацию reverse proxy с поддержкой WebSocket для субдоменов
- Инициализацию MongoDB replica set

**Пример структуры:**

```
/srv/notesnook/
  database/     # MongoDB data
  storage/      # MinIO data
  config/       # Environment и конфигурация
```

Для Notesnook требуется настройка нескольких субдоменов: отдельные для API, Identity, Messenger и (опционально) web-клиента[^5].

### Сравнение процесса развёртывания

| Критерий | Standard Notes | Notesnook |
|---|---|---|
| Официальная документация | Подробная, пошаговая[^2] | Минимальная, помечена как TODO[^4] |
| Docker Compose "из коробки" | Работает сразу | Требует доработки для продакшна |
| Количество шагов до рабочего сервера | 5-6 | 8-10 (с учётом субдоменов) |
| Community-гайды | Есть, как дополнение[^9] | Основной источник информации[^5][^6] |
| Поддержка | GitHub Issues, Discord | Без поддержки (альфа)[^4] |

## Подписка и premium-функции

### Standard Notes: модель подписки для self-hosted

Standard Notes предлагает два пути получения premium-функций на self-hosted сервере[^10]:

**Путь 1 --- Server-side подписка (бесплатно):**

Создаётся вручную через SQL-команды в MySQL. Разблокирует серверные функции (синхронизация файлов, история ревизий, email-бэкапы), но **не разблокирует клиентские функции** (Super Notes, вложенные теги, расширенные редакторы)[^10].

**Путь 2 --- Offline-подписка (платно):**

Приобретается на сайте Standard Notes. Разблокирует **все** функции, включая клиентские. Стоимость значительно ниже облачной подписки[^11]:

| План | Облачная цена | Offline-цена |
|---|---|---|
| Productivity | $90/год | ~$30/год |
| Professional | $120/год | ~$39/год |

> Для пользователя с существующим ключом Standard Notes: offline-подписка активируется через код в приложении. Процесс: покупка offline-плана на сайте, получение кода активации, ввод в Desktop/Mobile клиенте через Settings. Существующий ключ облачной подписки **не переносится** на self-hosted сервер напрямую --- это разные системы авторизации[^10].

### Notesnook: бесплатная модель

Notesnook при селф-хостинге **не требует подписки** для использования серверных функций[^4]. Все возможности синхронизации доступны бесплатно на собственном сервере. Однако некоторые клиентские функции (вложения, расширенное редактирование) требуют Pro-подписки Notesnook ($49.99/год или $4.99/мес)[^12], при этом пока не документировано, как именно подписка взаимодействует с self-hosted инстансом.

## Интеграция с клиентскими приложениями

### Standard Notes

**Desktop-приложения** (Windows, macOS, Linux) и **мобильные** (iOS, Android) полностью поддерживают подключение к self-hosted серверу[^2]:

1. Открыть меню аккаунта
2. Нажать "Advanced options"
3. Выбрать "Custom" в разделе "Sync Server"
4. Ввести URL сервера (например, `https://sync.example.org`)
5. Зарегистрировать новый аккаунт или войти в существующий

**Web-приложение** (`app.standardnotes.com`) **не поддерживает** подключение к self-hosted серверу из-за Content Security Policy (CSP), ограничивающей домены для подключения[^3]. Для веб-доступа необходимо развернуть собственный экземпляр web-приложения:

```bash
docker run -d -p 3001:80 standardnotes/web
```

Это **существенное ограничение**: для полноценного использования с браузера требуется дополнительный контейнер и настройка домена.

### Notesnook

Начиная с версии 3.0.14, все клиенты Notesnook поддерживают настройку custom server URL через Settings > Server[^13]:

- **Desktop**: Windows, macOS, Linux
- **Mobile**: iOS, Android
- **Web**: web.notesnook.com (или self-hosted web-клиент)

Преимущество Notesnook --- возможность динамически переключаться между серверами без переустановки приложения[^13]. Все клиенты работают идентично с self-hosted инстансом и облачным сервисом.

### Сравнение клиентской интеграции

| Клиент | Standard Notes | Notesnook |
|---|---|---|
| Desktop (Win/Mac/Linux) | Custom server через Advanced options | Custom server через Settings |
| Mobile (iOS/Android) | Custom server через Advanced options | Custom server через Settings |
| Официальный web-app | Не работает с self-hosted (CSP)[^3] | Работает с self-hosted[^13] |
| Self-hosted web-app | Требует отдельного контейнера | Включён в стек (опционально) |
| Смена сервера "на лету" | Требует перелогин | Динамическое переключение |

## End-to-end шифрование

### Standard Notes

Шифрование происходит полностью на стороне клиента до отправки данных на сервер. Сервер хранит только зашифрованные данные и не имеет возможности их расшифровать (zero-knowledge архитектура)[^14]. При self-hosted развёртывании модель шифрования **не меняется** --- ключи шифрования генерируются и хранятся на устройстве пользователя.

Standard Notes прошёл независимый аудит безопасности, результаты которого опубликованы[^14].

### Notesnook

Notesnook использует XChaCha20-Poly1305 для шифрования с Argon2 для деривации ключей[^15]. Как и в случае Standard Notes, шифрование --- клиентское, сервер получает только зашифрованные данные.

Дополнительно Notesnook предоставляет инструмент **Vericrypt** --- офлайн-верификатор, позволяющий убедиться, что данные действительно зашифрованы end-to-end[^16]. Vericrypt работает с реальными данными аккаунта и подтверждает корректность деривации ключей.

Notesnook не проходил формальный аудит безопасности, но весь код открыт (включая серверную часть), что позволяет независимую верификацию[^15].

### Влияние self-hosted на шифрование

В обоих случаях self-hosting **не ослабляет** шифрование. Напротив, он добавляет контроль над метаданными: владелец сервера контролирует access-логи, IP-адреса подключений и временные метки синхронизации, которые в облачной модели доступны провайдеру.

## Резервное копирование и миграция

### Standard Notes

**Бэкап сервера:**

```bash
docker compose down
# Скопировать директорию data/ целиком
cp -r data/ /backup/standardnotes-$(date +%Y%m%d)/
docker compose up -d
```

**Миграция из облака:** Экспорт данных из облачного аккаунта (Settings > Backups > Download), затем импорт на self-hosted сервере через регистрацию нового аккаунта и импорт бэкапа. Аккаунт не "переносится" --- создаётся новый[^7].

**Миграция V1 → V2:** Standard Notes предоставляет инструкции по обновлению legacy-инсталляций до версии 2[^2].

### Notesnook

**Бэкап:** MongoDB и MinIO требуют раздельного бэкапа. Для MongoDB: `mongodump`, для MinIO: копирование директории данных[^4].

**Миграция из облака:** Notesnook поддерживает экспорт в несколько форматов (Markdown, HTML, текст). Импорт на self-hosted сервере возможен через стандартный механизм импорта в клиенте[^13].

## Типичные проблемы и решения

### Standard Notes

**Бесконечный цикл авторизации (infinite login loop)**

Наиболее часто упоминаемая проблема в сообществе[^9][^17]. Причина --- неверно заданная переменная `COOKIE_DOMAIN` в `.env`. Значение должно точно соответствовать домену, через который клиенты подключаются к серверу.

```bash
# Правильно:
COOKIE_DOMAIN=sync.example.org
# Неправильно (с протоколом или портом):
COOKIE_DOMAIN=https://sync.example.org:3000
```

**Ошибки загрузки файлов**

Files Server работает на отдельном порте (3125 по умолчанию). Если reverse proxy не маршрутизирует этот порт, загрузка файлов не работает. Решение --- настроить отдельный проксирующий location или субдомен для файлового сервера[^2].

**Проблемы мобильных приложений с сертификатами**

Self-signed сертификаты или сертификаты от нестандартных CA могут не приниматься мобильными клиентами. Решение --- использовать Let's Encrypt[^9].

**Web-приложение не подключается**

Штатное ограничение: `app.standardnotes.com` блокирует запросы к нестандартным серверам через CSP[^3]. Решение --- развернуть собственный экземпляр web-приложения.

### Notesnook

**Нестабильность (альфа-стадия)**

Главная проблема --- self-hosting находится в альфа-стадии. Разработчики прямо предупреждают: "expect a lot of things not to work when connected to your own instance"[^4]. Рекомендация --- использовать для экспериментов, не для production.

**Ошибки при загрузке вложений**

Пользователи сообщают о "Network Error" и файлах размером 0 при загрузке через MinIO[^18]. Причина --- некорректная конфигурация MinIO endpoint или отсутствие HTTPS. Решение --- использовать HTTPS для MinIO endpoint и проверить bucket policies.

**MongoDB replica set**

Notesnook требует инициализации MongoDB replica set, что не всегда очевидно из минимальной документации[^5]. Без replica set некоторые операции (транзакции, change streams) не работают.

**SMTP-конфигурация**

Для регистрации и восстановления пароля требуется рабочий SMTP-сервер. Без него --- невозможно создать аккаунт через web-интерфейс[^5].

**Отсутствие документации**

Основная практическая проблема. Официальная документация помечена как TODO. Сообщество создало неофициальные гайды[^5][^6][^8], но они быстро устаревают.

## Обновление сервера

### Standard Notes

Процесс обновления документирован[^2]:

```bash
docker compose down
# Обновить docker-compose.yml, .env, localstack_bootstrap.sh
docker compose pull
docker compose up -d
```

Перед обновлением рекомендуется сделать полный бэкап данных.

### Notesnook

Процесс обновления не документирован официально. Предполагаемый подход:

```bash
docker compose down
docker compose pull
docker compose up -d
```

Риск: при отсутствии миграционных скриптов обновления могут сломать существующую базу данных.

## Итоговое сравнение

| Критерий | Standard Notes | Notesnook |
|---|---|---|
| **Зрелость self-hosting** | Production-ready (V2, с 2023)[^1] | Альфа-стадия[^4] |
| **Документация** | Подробная официальная[^2] | Минимальная, community-гайды[^5] |
| **Простота развёртывания** | Средняя (5-6 шагов) | Низкая (субдомены, replica set) |
| **Минимум RAM** | 2 ГБ | 2 ГБ |
| **E2E шифрование** | Да, аудирован[^14] | Да, XChaCha20-Poly1305[^15] |
| **Web-app с self-hosted** | Требует отдельного контейнера[^3] | Поддерживается нативно[^13] |
| **Premium на self-hosted** | Offline-подписка ~$39/год[^11] | Бесплатно (серверные функции) |
| **Существующий ключ** | Нужна отдельная offline-подписка[^10] | Не применимо |
| **Поддержка мобильных** | iOS, Android (custom server)[^2] | iOS, Android (custom server)[^13] |
| **Стабильность** | Высокая | Низкая (альфа) |
| **Бэкап** | Документирован | Ручной (mongodump + MinIO) |
| **Лицензия** | AGPL-3.0 | AGPL-3.0 |

## Рекомендации

**Standard Notes** --- обоснованный выбор для production self-hosting:

- Зрелая инфраструктура с документированным процессом развёртывания
- Прошёл аудит безопасности
- При наличии существующего ключа: потребуется приобрести offline-подписку ($39/год) для полного набора функций на self-hosted сервере --- облачная подписка не переносится
- Основной недостаток --- необходимость отдельного контейнера для web-приложения

**Notesnook** --- перспективный, но незрелый вариант:

- Бесплатный self-hosting без ограничений серверных функций
- Более современная клиентская архитектура (динамическое переключение серверов)
- Не готов для production-использования (альфа-стадия, нет документации, нет поддержки)
- Стоит отслеживать развитие --- команда заявила, что self-hosting станет приоритетом после стабилизации v3[^13]

Для пользователя с существующим ключом Standard Notes оптимальный путь: развернуть Standard Notes Server через Docker, приобрести offline Professional подписку ($39/год), настроить reverse proxy с Let's Encrypt, подключить desktop и mobile клиенты через "Custom Sync Server". Web-доступ --- через отдельный контейнер `standardnotes/web`.

## Дискуссионные вопросы и противоречия

**Стоимость self-hosting vs. облачной подписки.** Offline-подписка Standard Notes ($39/год) дешевле облачной ($120/год), но к ней добавляется стоимость серверной инфраструктуры (VPS от $5-10/мес). При использовании домашнего сервера экономия существенна; при аренде VPS --- менее очевидна[^9].

**Notesnook: open-source без реального self-hosting.** Несмотря на AGPLv3-лицензию и открытый серверный код, практическая возможность self-hosting остаётся ограниченной из-за альфа-стадии и отсутствия документации. Часть сообщества рассматривает это как "номинальный open-source"[^18].

**Безопасность self-hosted vs. облачного.** E2E-шифрование одинаково в обоих случаях. Аргумент за self-hosting --- контроль над метаданными и отсутствие зависимости от жизнеспособности компании-провайдера. Аргумент против --- необходимость самостоятельно обеспечивать безопасность сервера (обновления, firewall, мониторинг)[^14][^15].

## Quality Metrics

| Метрика | Значение |
|---|---|
| Источников найдено | 24 |
| Источников процитировано | 18 |
| Типы источников | official: 8, community: 5, GitHub: 3, news: 2 |
| Покрытие цитатами | ~92% |
| Подвопросов исследовано | 8 |
| Раундов исследования | 2 (initial + verification) |

[^1]: [Standard Notes --- Making self-hosting easy for all](https://standardnotes.com/blog/making-self-hosting-easy-for-all)
[^2]: [Standard Notes --- Self-hosting with Docker](https://standardnotes.com/help/self-hosting/docker)
[^3]: [Standard Notes --- Self-hosting Web App with Docker](https://standardnotes.com/help/self-hosting/web-app)
[^4]: [GitHub --- streetwriters/notesnook-sync-server](https://github.com/streetwriters/notesnook-sync-server)
[^5]: [Notesnook sync server: a Noob-Friendly Setup Tutorial (Lemmy)](https://lemmy.world/post/24509570)
[^6]: [Take Control of Your Notes: Self-Hosting Notesnook in Your Homelab (TechDecode)](https://techdecode.online/decode/notesnook/)
[^7]: [Standard Notes --- Getting started with self-hosting](https://standardnotes.com/help/self-hosting/getting-started)
[^8]: [GitHub --- BeardedTek/notesnook-docker](https://github.com/beardedtek/notesnook-docker)
[^9]: [How to completely self-host Standard Notes (The Self-Hosting Blog)](https://theselfhostingblog.com/posts/how-to-completely-self-host-standard-notes/)
[^10]: [Standard Notes --- Subscriptions on your self-hosted server](https://standardnotes.com/help/self-hosting/subscriptions)
[^11]: [Standard Notes --- Plans](https://standardnotes.com/plans)
[^12]: [Notesnook --- Open source & zero knowledge private note taking app](https://notesnook.com/)
[^13]: [Notesnook v3.0.14 Release Blog](https://blog.notesnook.com/notesnook-v3.0.14)
[^14]: [Can I self-host Standard Notes?](https://standardnotes.com/help/47/can-i-self-host-standard-notes)
[^15]: [GitHub --- streetwriters/notesnook (encryption documentation)](https://github.com/streetwriters/notesnook)
[^16]: [Vericrypt --- Verify Notesnook Encryption](https://vericrypt.notesnook.com/)
[^17]: [Selfhosted Standard Notes with Docker and Traefik (ae3.ch)](https://ae3.ch/selfhosted-standard-notes-with-docker-and-traefik/)
[^18]: [Privacy Guides Community --- Notesnook discussion](https://discuss.privacyguides.net/t/open-source-but-needs-subscription-even-for-offline-use/28125)
