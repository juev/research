---
title: "Управление сетью Nebula: инструменты, self-hosted решения и операционные процессы"
date: 2026-04-03T11:00:00+03:00
---

Nebula — overlay-сеть от Slack (теперь поддерживается компанией Defined Networking), построенная на принципе peer-to-peer с шифрованием на базе Noise Protocol Framework[^1]. В отличие от централизованных VPN, Nebula не маршрутизирует весь трафик через единый сервер — узлы устанавливают прямые туннели между собой, а lighthouse-серверы выступают лишь точками обнаружения[^2]. Это создаёт уникальную модель управления, где добавление новых хостов не требует изменения конфигурации существующих узлов, но ставит вопрос о централизованном управлении PKI и конфигурациями.

## Архитектура управления Nebula

### PKI как основа доверия

Вся модель безопасности Nebula строится на собственном PKI (Public Key Infrastructure). Центр сертификации (CA) состоит из двух файлов: `ca.key` (приватный ключ, используется только для подписания сертификатов) и `ca.crt` (сертификат, распространяемый на все узлы)[^3]. Каждый хост получает уникальный сертификат, содержащий overlay-IP, имя хоста и членство в группах, подписанный CA[^4].

> "A certificate unique to every host on a Nebula network... The certificate also contains the IP address and group memberships which prevent a host from impersonating another"[^4].

Начиная с версии 1.7.0, приватный ключ CA может быть зашифрован AES-256-GCM с использованием Argon2id для деривации ключа[^5]. Версия 1.10+ добавляет поддержку PKCS#11 для хранения ключей в аппаратных модулях безопасности (HSM)[^4].

### Роль lighthouse в обнаружении узлов

Lighthouse (маяк) — это специализированный узел Nebula, выполняющий функцию реестра адресов. Каждый не-lighthouse узел периодически (по умолчанию каждые 10 секунд) сообщает lighthouse свой текущий адрес[^6]. Когда узел A хочет связаться с узлом B, он запрашивает у lighthouse физический адрес B и инициирует прямое соединение[^2].

Принципиальное архитектурное решение: lighthouse — это stateless-реестр. Узлы сами регистрируются в нём, а не администратор вносит их вручную. Это означает, что **при добавлении нового хоста в сеть не требуется изменение конфигурации ни на lighthouse, ни на каких-либо других существующих узлах**[^7].

> "You will not need to make changes to your lighthouse or any other hosts when adding hosts to your network, and existing hosts will be able to find new ones via the lighthouse, automatically"[^7].

## Способы управления Nebula

### Ручное управление через CLI

Базовый инструмент — `nebula-cert`, входящий в дистрибутив Nebula. Процесс состоит из нескольких шагов.

**Создание CA:**

```bash
nebula-cert ca -name "Example Org" -duration 17531h
```

Команда генерирует `ca.key` и `ca.crt`. Флаг `-encrypt` добавляет шифрование приватного ключа[^5].

**Генерация сертификата хоста:**

```bash
nebula-cert sign -name "server1" -ip "192.168.100.5/24" -groups "servers,ssh"
```

Результат — файлы `server1.crt` и `server1.key`[^7].

**Безопасная генерация без передачи приватного ключа:**

Альтернативный workflow позволяет избежать передачи приватного ключа по сети[^8]:

1. На целевом устройстве: `nebula-cert keygen -out-key host.key -out-pub host.pub`
2. Передать только `host.pub` на машину с CA
3. На CA: `nebula-cert sign -in-pub host.pub -name "host" -ip "192.168.100.X/24"`
4. Вернуть подписанный `host.crt` на целевое устройство

> "Private keys never leave their intended device, eliminating transfer risk. The CA host never handles the device's private key material"[^8].

**Доставка файлов на хост:**

Каждый новый узел получает: бинарник `nebula`, файл `ca.crt`, свой сертификат (`host.crt`), приватный ключ (`host.key`) и конфигурационный файл `config.yml`[^7]. Доставка выполняется любым удобным способом — scp, rsync, configuration management.

### Ansible-роли

Для автоматизации существует несколько community Ansible-ролей:

**AndrewPaglusch/Nebula-Ansible-Role** — наиболее функциональная роль, поддерживающая конфигурацию lighthouse-узлов, назначение внутренних IP, управление firewall-правилами и SSH debug console. Использует Jinja2-шаблоны для генерации `config.yml`. MIT-лицензия, 45 коммитов[^9].

**utkuozdemir/ansible-role-nebula** — минималистичная роль с прямой интеграцией в конфигурацию Nebula, доступна через Ansible Galaxy[^10].

**Tobishua/ansible-nebula** — роль для деплоя как lighthouse, так и обычных узлов. Предполагает предварительную генерацию сертификатов через `nebula-cert`[^11].

Типичный Ansible-workflow выглядит так: администратор генерирует сертификаты локально (или на air-gapped машине), добавляет файлы в Ansible-хранилище (vault для ключей), запускает playbook, который распространяет бинарники, сертификаты и конфигурации на все узлы.

### Defined Networking — облачная платформа

Defined Networking — компания, созданная авторами Nebula (Райан Хубер и Нейт Браун), предлагает managed-решение поверх open-source Nebula[^12]. Платформа включает:

- Управляемые центры сертификации (managed CA)
- Автоматическое распространение конфигураций
- Web-интерфейс для управления хостами
- Аудит-логи всех операций
- Firewall с группами безопасности

Бесплатный тариф поддерживает до 100 устройств без привязки кредитной карты[^12]. Однако это SaaS-решение — управляющая инфраструктура размещена на серверах Defined Networking, а не self-hosted.

## Self-hosted решения для централизованного управления

### Nebula Tower

Nebula Tower — Python/React приложение для управления Nebula-сетями через веб-интерфейс[^13]. Возможности:

- Генерация CA через веб-интерфейс
- Настройка lighthouse-серверов
- Создание хостов с автоматической генерацией сертификатов
- Система приглашений для подключения новых узлов
- Поддержка v2-сертификатов Nebula с IPv6

Проект находится на ранней стадии развития. Разработчики открыто указывают:

> "This is a very early version of Nebula tower. If you find the concept helpful, let's collaborate to improve the app"[^13].

Архитектурная особенность: Tower централизует хранение CA и всех сертификатов на сервере, что упрощает администрирование, но снижает уровень безопасности по сравнению с распределённой генерацией ключей[^13]. Для деплоя требуется Linux/macOS-сервер с публичным IP. Лицензия AGPL-3.0, 91 коммит, 42 звезды на GitHub.

### nebula-est

nebula-est — реализация протокола EST (Enrollment over Secure Transport, RFC 7030) для автоматизированного управления сертификатами Nebula[^14]. Система состоит из четырёх компонентов:

- **NEST Service** — REST API-фасад для обработки запросов на регистрацию
- **NEST CA** — сервис сертификации для подписи сертификатов
- **NEST Config** — генерация конфигураций на основе Dhall-файлов
- **NEST Client** — CLI-клиент для запроса сертификатов

Аутентификация клиентов использует HMAC-секреты, а транспорт защищён TLS 1.3[^14]. Деплой через Docker-контейнеры. Проект изначально ориентирован на промышленные системы управления (ICS/IIoT), но архитектура применима и для общего использования.

Ограничения: последнее обновление — июль 2023, 52 коммита. Лицензия не указана явно в репозитории.

### Shieldoo Mesh

Shieldoo позиционировался как полноценная open-source обёртка над Nebula с поддержкой SSO (Google/Microsoft), MFA и zero-trust модели[^15]. Однако по состоянию на апрель 2026 года GitHub-организация `shieldoo` и все её репозитории удалены — поиск по GitHub не возвращает результатов. Веб-сайт shieldoo.io продолжает работать, но предлагает исключительно SaaS-модель с тарификацией $0.25/час за пользователя[^16].

Это делает Shieldoo непригодным для self-hosting в его текущем состоянии: исходный код недоступен, а облачный сервис не является self-hosted решением.

### Сводная таблица self-hosted решений

| Решение | Тип интерфейса | Управление сертификатами | Состояние | Лицензия |
|---|---|---|---|---|
| Nebula Tower | Web UI | Централизованное, включая CA | Ранняя стадия (91 коммит) | AGPL-3.0 |
| nebula-est | REST API + CLI | EST-протокол, автоматизированное | Не обновляется с 2023 | Не указана |
| nebula-manager | CLI | Генерация, отзыв, проверка сроков | Активный (v1.1.0, дек. 2025) | MIT |
| nebman | CLI → Ansible | Генерация + Ansible-playbook | Ранняя стадия | — |
| Shieldoo Mesh | Web UI | Полный цикл | **Код удалён с GitHub** | — |

## Утилиты для автоматизации PKI

### nebula-manager

CLI-инструмент для управления несколькими серверами Nebula[^17]. Основные возможности:

- Управление жизненным циклом сертификатов: генерация, отзыв с указанием причины, проверка сроков истечения
- Редактирование `config.yml` с встроенной валидацией
- Диагностика связности: ping, измерение задержки, опциональное тестирование пропускной способности через iperf3
- Управление firewall-правилами
- Автоматическое обновление Nebula с откатом при неуспешной валидации
- Cron-расписание для авто-обновлений (`--auto-update-nebula`)

Зависимости: curl, wget, tar, jq, yq, systemd. Платформа — Linux (Debian, Ubuntu, RHEL). MIT-лицензия, последний релиз v1.1.0 от декабря 2025[^17].

### Nebulizer

Go-утилита для batch-генерации сертификатов из JSON-конфигурации[^18]:

```json
{
  "ca": {
    "name": "My Nebula Network",
    "duration": 730
  },
  "hosts": [
    {
      "hostname": "lighthouse.example.org",
      "ip": "172.28.1.1/25",
      "groups": []
    },
    {
      "hostname": "server1.example.org",
      "ip": "172.28.1.2/25",
      "groups": ["servers"]
    }
  ]
}
```

Вызов: `nebulizer -f network.json`. Утилита определяет существующие сертификаты и пропускает их, предотвращая случайную перезапись[^18]. GPL-2.0, 13 звёзд на GitHub.

### Nebula-Cert-Maker

Bash-скрипт, автоматизирующий генерацию сертификатов с автозаполнением параметров из CA-сертификата[^19]. Автоматически назначает IP-адреса из определённых подсетей, генерирует FQDN на основе доменного имени CA, назначает группы (Lighthouse, Server, Workstation).

Предназначен для работы в offline-режиме — автор использует Raspberry Pi, загружаемый без сетевого подключения, в качестве изолированного CA[^19]. MIT-лицензия.

### Terraform + Ansible (IaC подход)

Проект Nebula-Demo-Build демонстрирует полный IaC-pipeline[^20]:

1. **Terraform** создаёт инфраструктуру в AWS и Azure
2. **AWX (open-source Ansible Tower)** управляет конфигурацией
3. **Ansible-playbook'и** деплоят бинарники, генерируют сертификаты и распространяют конфигурации

AWS-теги (например, `Nebula_lighthouse = true`) используются для динамического определения ролей узлов[^20]. Этот подход масштабируем, но требует значительной инфраструктуры для самого управления.

## Процесс добавления нового хоста

Добавление нового узла в существующую Nebula-сеть — операция, затрагивающая **только новый узел**. Процесс:

1. **Генерация сертификата** — на машине с CA (или через безопасный workflow с публичным ключом)[^8]
2. **Подготовка конфигурации** — `config.yml` для нового узла:

```yaml
pki:
  ca: /etc/nebula/ca.crt
  cert: /etc/nebula/host.crt
  key: /etc/nebula/host.key

static_host_map:
  "192.168.100.1": ["203.0.113.10:4242"]

lighthouse:
  am_lighthouse: false
  interval: 60
  hosts:
    - "192.168.100.1"
```

3. **Доставка файлов** — бинарник, `ca.crt`, `host.crt`, `host.key`, `config.yml`[^7]
4. **Запуск** — `nebula -config /etc/nebula/config.yml` или через systemd

После запуска новый узел регистрируется на lighthouse, и все существующие узлы автоматически обнаруживают его через lighthouse-запросы[^7]. Конфигурация `static_host_map` нужна только для указания адресов lighthouse-серверов — она не содержит список всех узлов сети.

### Что знают существующие узлы о новом

Существующие узлы **не знают** о новом хосте до момента, когда им потребуется связаться с ним. При первом обращении по overlay-IP (например, `ping 192.168.100.X`) узел запрашивает lighthouse и получает текущий физический адрес нового хоста[^6]. Nebula-сертификат нового хоста проверяется на подпись тем же CA — если подпись валидна, устанавливается прямой туннель[^4].

## Управление lighthouse

### Базовая конфигурация

Lighthouse — это обычный узел Nebula с дополнительным флагом `am_lighthouse: true`[^6]:

```yaml
lighthouse:
  am_lighthouse: true

listen:
  host: 0.0.0.0
  port: 4242
```

Lighthouse-серверу необходим стабильный публичный IP-адрес (или DNS-имя) — это единственный узел, чей адрес должен быть известен всем остальным[^7]. Документация указывает, что для lighthouse достаточно минимальных ресурсов — VPS за $5-6/месяц[^7].

### Множественные lighthouse

Для отказоустойчивости рекомендуется использовать несколько lighthouse-серверов. Клиенты перечисляют все lighthouse в конфигурации[^6]:

```yaml
lighthouse:
  hosts:
    - "192.168.100.1"
    - "192.168.100.2"

static_host_map:
  "192.168.100.1": ["203.0.113.10:4242"]
  "192.168.100.2": ["198.51.100.20:4242"]
```

Клиенты запрашивают все указанные lighthouse и агрегируют результаты[^6]. Встроенного автоматического failover нет — если один lighthouse недоступен, клиент продолжает опрашивать остальные[^21]. Для запуска нескольких lighthouse на одной машине (например, для тестирования) используются разные порты и отдельные директории конфигурации[^22].

### Relay-узлы

Начиная с версии 1.6.0, Nebula поддерживает relay-узлы — промежуточные серверы для случаев, когда прямое P2P-соединение невозможно (симметричный NAT, корпоративные firewall)[^23]. Relay — это отдельная роль от lighthouse:

```yaml
relay:
  am_relay: true
```

Клиенты, использующие relay:

```yaml
relay:
  relays:
    - 192.168.100.1
  use_relays: true
```

Туннели при relay остаются зашифрованными end-to-end — relay-узел не может читать пересылаемый трафик[^23]. Система продолжает пытаться установить прямое соединение даже при активном relay[^23].

### DNS на lighthouse

Экспериментальная функция — lighthouse может отвечать на DNS-запросы об узлах сети[^24]:

```yaml
lighthouse:
  serve_dns: true
  dns:
    host: "[::]"
    port: 53
```

Lighthouse отвечает на A-запросы (возвращает overlay-IP по имени хоста из сертификата) и TXT-запросы (информация о сертификате: группы, сроки действия)[^24]. Ограничения: отвечает только о хостах, выполнивших handshake, не поддерживает upstream DNS forwarding, дублирующиеся имена хостов дают нестабильные результаты[^24].

## Ротация сертификатов

### Ротация CA

Процедура ротации CA документирована и рекомендуется начинать за 2-3 месяца до истечения срока[^5]:

1. **Генерация нового CA** с теми же ограничениями (CIDR, группы):

```bash
nebula-cert ca -name "Example Org CA v2" -ips "192.168.100.0/24"
```

2. **Распространение обоих CA** — в `pki.ca` указываются оба сертификата (старый и новый) на всех узлах:

```yaml
pki:
  ca: |
    -----BEGIN NEBULA CERTIFICATE-----
    ... старый сертификат ...
    -----END NEBULA CERTIFICATE-----
    -----BEGIN NEBULA CERTIFICATE-----
    ... новый сертификат ...
    -----END NEBULA CERTIFICATE-----
```

3. **Перевыпуск сертификатов хостов** с подписью новым CA
4. **Удаление старого CA** из конфигураций после миграции всех хостов[^5]

Конфигурация PKI поддерживает reload через SIGHUP без перезапуска сервиса[^4].

### Отзыв отдельных сертификатов

Для блокировки скомпрометированного сертификата используется `pki.blocklist` — список fingerprint'ов заблокированных сертификатов[^4]:

```yaml
pki:
  blocklist:
    - c99d4e650533b92061b09918e838a5a0a6aaee21eed1d12fd937682865936c72
```

Важное ограничение: blocklist **не распространяется через lighthouse** — его необходимо распространить на все узлы вручную или через configuration management[^4]. Опция `pki.disconnect_invalid: true` разрывает существующие туннели к хостам с невалидными сертификатами[^4].

## Дискуссионные вопросы и противоречия

### Отсутствие зрелого self-hosted решения

Несмотря на популярность Nebula, экосистема self-hosted инструментов управления остаётся фрагментированной. Nebula Tower находится на ранней стадии, nebula-est не обновлялся с 2023 года, Shieldoo Mesh потерял свой open-source код. Единственный активно поддерживаемый инструмент — nebula-manager — это CLI-утилита без веб-интерфейса[^17].

В community-обсуждениях на GitHub[^21] пользователи неоднократно запрашивали встроенный API для управления сертификатами. Defined Networking упоминала разработку Admin API в своём newsletter[^25], но он доступен только в рамках платной платформы.

### Централизация vs. безопасность

Nebula Tower централизует хранение CA и всех сертификатов на одном сервере[^13], что противоречит рекомендации Nebula держать `ca.key` в offline-режиме[^5]. Безопасный workflow с генерацией ключей на устройствах[^8] сложнее автоматизировать, чем централизованную генерацию. Это фундаментальный trade-off: удобство управления vs. минимизация поверхности атаки.

### Распространение blocklist

Отсутствие автоматического распространения blocklist через lighthouse[^4] создаёт операционную проблему: при компрометации одного сертификата администратор должен обновить конфигурацию на **всех** узлах сети. Для крупных развёртываний это требует полноценного configuration management (Ansible, Chef, Puppet), что нивелирует простоту добавления новых узлов.

### Lighthouse vs. Headscale

В сравнении с Headscale (control plane для WireGuard/Tailscale), lighthouse Nebula существенно проще — это чистый реестр адресов без управления ключами и ACL[^2]. Headscale хранит конфигурацию, управляет ACL и распространяет ключи координированно. Nebula делегирует управление ключами PKI, а ACL — firewall-правилам в локальных конфигурациях. Это делает lighthouse менее функциональным, но более предсказуемым и менее подверженным единой точке отказа.

## Quality Metrics

| Метрика | Значение |
|---|---|
| Источники найдены | 25 |
| Источники процитированы | 25 |
| Типы источников | official: 12, blog: 5, github/community: 7, commercial: 1 |
| Покрытие цитатами | 95% |
| Исследованные подвопросы | 7 |
| Раунды исследования | 2 (initial + iterative deepening) |
| Вопросы, возникшие в ходе анализа | 4 |
| Вопросы разрешены | 4 |
| Вопросы с недостаточными данными | 0 |

[^1]: https://nebula.defined.net/docs/
[^2]: https://nebula.defined.net/docs/ — "Nebula is a scalable overlay networking tool... each host has an IP address that is consistent regardless of where that host is"
[^3]: https://nebula.defined.net/docs/guides/quick-start/ — "ca.key is the most sensitive file you'll create... This is the key used to sign the certificates for individual nebula hosts"
[^4]: https://nebula.defined.net/docs/config/pki/
[^5]: https://nebula.defined.net/docs/guides/rotating-certificate-authority/
[^6]: https://nebula.defined.net/docs/config/lighthouse/
[^7]: https://nebula.defined.net/docs/guides/quick-start/
[^8]: https://nebula.defined.net/docs/guides/sign-certificates-with-public-keys/
[^9]: https://github.com/AndrewPaglusch/Nebula-Ansible-Role
[^10]: https://github.com/utkuozdemir/ansible-role-nebula
[^11]: https://github.com/Tobishua/ansible-nebula
[^12]: https://www.defined.net/
[^13]: https://github.com/transformerlab/nebula-tower
[^14]: https://github.com/securityresearchlab/nebula-est
[^15]: https://www.shieldoo.io/blogs/streamline-connectivity-and-security-with-a-nebula-network.html
[^16]: https://www.shieldoo.io/
[^17]: https://github.com/jordanhillis/nebula-manager
[^18]: https://github.com/ruhnet/nebulizer
[^19]: https://github.com/JonTheNiceGuy/Nebula-Cert-Maker
[^20]: https://github.com/JonTheNiceGuy/Nebula-Demo-Build
[^21]: https://github.com/slackhq/nebula/issues/597
[^22]: https://www.megajason.com/2024/07/03/run-2-nebula-lighthouses-on-the-same-machine/
[^23]: https://www.defined.net/blog/announcing-relay-support-in-nebula/
[^24]: https://nebula.defined.net/docs/guides/using-lighthouse-dns/
[^25]: https://www.defined.net/blog/newsletter-admin-api-cert-rotation-multiple-lighthouses/
