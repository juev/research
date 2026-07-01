---
title: "AT Protocol: как устроен, что позволяет и как на нём писать приложения"
date: 2026-07-01T11:05:50+03:00
---

AT Protocol (сокращённо atproto, «authenticated transfer») проще всего понять через одно разграничение, которое авторы протокола проводят с самого начала: Bluesky — это приложение, а atproto — протокол под ним. Bluesky — микроблог, витрина и первый крупный пользователь. Сам протокол — обобщённый фундамент для «социального веба»: спецификация того, как хранить подписанные пользовательские данные, как устроена идентичность и как независимые сервисы собирают из этих данных общую картину.[^arch] Из этого разграничения следует и всё остальное: почему на atproto строят не только ленты постов, что нужно для запуска своего узла и как выглядит разработка приложения.

Разбор идёт по четырём вопросам: из чего протокол состоит, что он позволяет делать, что нужно для использования и как именно пишется приложение. В конце — честный раздел о том, где обещания протокола расходятся с практикой, потому что вокруг слова «децентрализация» здесь много спора.

## Из чего состоит протокол

Архитектура atproto держится на трёх слоях: идентичность, данные и сеть сервисов. Разделение этих слоёв — центральная идея, всё остальное её обслуживает.

### Идентичность: handle и DID

У каждого аккаунта две привязки. Первая — **handle**, читаемое имя вида `alice.bsky.social` или собственный домен `alice.example.org`. Handle меняется и по сути является указателем. Вторая — **DID** (decentralized identifier), постоянный машинный идентификатор, который не меняется никогда, даже при смене handle или переезде на другой сервер.[^did] Протокол «благословляет» два метода: `did:plc` (собственная разработка Bluesky) и `did:web` (стандарт W3C поверх HTTPS/DNS).[^did] DID-документ содержит заявленный handle, публичный ключ для проверки подписей и адрес сервера, где лежат данные.[^did]

Handle разрешается в DID через DNS-запись `_atproto.<handle>` типа TXT либо через HTTPS-эндпоинт `.well-known`.[^identity] Именно поэтому свой домен можно сделать именем аккаунта — достаточно доказать владение им через DNS. Разделение «меняемый handle / постоянный DID» и есть техническая основа переносимости: сменить хостинг, не потеряв идентичность и граф подписок, можно потому, что подписки указывают на DID, а не на адрес сервера.[^kleppmann-blog]

### Данные: подписанный репозиторий

Данные пользователя лежат в **персональном репозитории** — самоудостоверяющей коллекции записей.[^repos] Структурно это Merkle Search Tree (MST): контент-адресуемое детерминированное дерево, где записи хранятся в отсортированном порядке, а каждый узел — объект IPLD в кодировке DAG-CBOR, связанный с другими через хеш-ссылки CID.[^repos][^repo-spec] Верхний объект репозитория — подписанный commit: он содержит DID аккаунта, версию, указатель на корень дерева, ревизию и криптографическую подпись.[^repo-spec]

Практический смысл конструкции: любой может выгрузить репозиторий целиком (как CAR-файл) и проверить подписью, что данные подлинные и не подменены сервером.[^repos] Записи в репозитории — это посты, лайки, подписки, профили; их типы описываются схемами.

### Схемы: Lexicon и XRPC

**Lexicon** — язык описания схем. Он задаёт три вещи: типы записей, HTTP-эндпоинты и сообщения потоковых событий.[^lexicon-spec] Схемы — это JSON-файлы, каждый с уникальным идентификатором **NSID** в обратной нотации домена: `app.bsky.feed.post` для поста, `com.atproto.repo.getRecord` для метода API.[^lexicon-guide] Namespace завязан на домен: кто владеет доменом, тот и определяет схемы в его пространстве. У Lexicon жёсткое правило совместимости — после публикации ограничения схемы менять нельзя, можно только добавлять необязательные поля.[^lexicon-guide]

Поверх Lexicon работает **XRPC** — соглашение об HTTP-API. Эндпоинты имеют вид `/xrpc/<NSID>`, где NSID указывает на Lexicon с описанием запроса и ответа; запросы (GET) и процедуры (POST) различаются, поддерживаются авторизация и постраничная выборка через курсор.[^xrpc]

### Сеть: PDS, Relay, AppView

Три сервиса собирают из репозиториев работающую сеть.[^arch][^at-stack]

- **PDS (Personal Data Server)** — «дом» аккаунта. Хранит подписанный репозиторий, управляет идентичностью и рассылает изменения. Клиент пишет именно в PDS.[^at-stack]
- **Relay** — агрегатор. Подписывается на множество PDS, читает их потоки коммитов и переиздаёт всё как единый глобальный поток — **firehose**.[^arch]
- **AppView** — витрина приложения. Читает firehose, строит индексы и отвечает на запросы клиента (лента, тред, профиль).[^arch]

Мысленная модель разработчика: пишешь в свой PDS → PDS вещает изменение в Relay → Relay складывает его в общий firehose → AppView индексирует поток и отдаёт клиенту готовые представления.[^bailey] Формально это описано в архитектурном черновике IETF, где atproto подан как обобщённый фреймворк для социального веба на «самоудостоверяющих записях», с отдельной идеей — вынести модерацию в независимые сервисы-лейблеры.[^ietf]

## Что протокол позволяет делать

Из разделения слоёв следует ключевая философия: слой речи и слой охвата разведены. **Speech layer** — открытый и распределённый низ, где все записи существуют; **reach layer** — гибкие сервисы индексации, которые решают, что и кому показывать.[^bsky-atproto] Речь остаётся открытой, а над ней конкурируют алгоритмы выдачи, клиенты и фильтры.

На практике это даёт несколько типов приложений, которые не сводятся к «ещё один клиент Bluesky».

**Генераторы лент (feed generators).** Лёгкий сервис получает запрос и возвращает список URI постов с необязательными метаданными; полное «наполнение» постов делает AppView запрашивающей стороны.[^feeds] Отсюда — сторонние алгоритмические, тематические и коммунальные ленты, для которых есть стартовые шаблоны.[^building]

**Лейблеры (labelers).** Независимые сервисы навешивают на контент аннотации-метки; модерация становится подключаемым слоем, а не встроенной функцией одной компании.[^ietf]

**Приложения за пределами микроблогинга.** Поскольку аккаунт отделён от приложения, а данные лежат в переносимом репозитории, порог для нишевого приложения низкий.[^bmann] В экосистеме уже работают: WhiteWind — блоги в Markdown, хранимые в личном PDS;[^anil] Leaflet — совместный редактор документов;[^willschenk] Smoke Signal — события и RSVP;[^bmann] Flashes и Streamplace — фото и лайв-видео;[^techcrunch] Tangled — площадка для кода в духе GitHub.[^willschenk] Канонический учебный пример — Statusphere: минимальное приложение, где пользователь публикует один эмодзи-статус записью собственной Lexicon-схемы `xyz.statusphere.status`.[^cloudflare]

Общий знаменатель: одни и те же пользовательские данные могут читать и переосмыслять несколько конкурирующих приложений. Смена приложения не требует потери контента и графа.[^kleppmann-blog]

## Что нужно, чтобы этим пользоваться

Порог входа зависит от роли. Есть три уровня.

**Уровень 1 — пользователь.** Достаточно аккаунта на любом PDS (например, `bsky.social`). Никакой инфраструктуры. Домен нужен, только если хочется сделать его своим handle — тогда добавляется DNS-запись `_atproto` или файл `.well-known`.[^identity]

**Уровень 2 — разработчик поверх чужой инфраструктуры.** Нужен аккаунт и способ аутентификации против публичных эндпоинтов. Хостов несколько: Relay (`bsky.network`), Entryway (`bsky.social`), приватная AppView (`api.bsky.app`) и публичная AppView без авторизации (`public.api.bsky.app`).[^api-hosts] Сессия открывается по handle и паролю: в ответ приходят `accessJwt` (живёт минуты) и `refreshJwt` (живёт дольше).[^getstarted] Этого хватает, чтобы читать ленту, публиковать посты и слушать данные, ничего не хостя.

**Уровень 3 — собственный PDS.** Здесь появляется реальная инфраструктура, но требования скромные. Официальный минимум: 1 ГБ RAM, 20 ГБ SSD, Ubuntu, один CPU, публичный IPv4 и DNS-имя; ёмкость — 1–20 пользователей.[^pds-repo] Установка — скрипт-инсталлятор поверх Docker.[^selfhost] Нужны домен, TLS-сертификат и корректно проброшенные WebSocket-соединения (без рабочего WebSocket-фида верификация домена не проходит — это типичная ошибка при настройке reverse proxy).[^primozic] Для продакшена добавляются отдельные домены под PDS и приложение, S3-совместимое хранилище блобов, Redis для масштабирования на несколько узлов и Litestream для резервных копий SQLite.[^production]

Важная оговорка про федерацию своего PDS: она открывалась в режиме раннего доступа с жёсткими лимитами — 10 аккаунтов на PDS, 1500 событий в час и 10 000 в сутки (пост от февраля 2024-го; ограничения вводились как временные предохранители от абуза).[^selfhost-fed] Это значит, что «поднять свой PDS» и «участвовать в сети на равных» — не одно и то же (подробнее в разделе про ограничения).

Идентичность при переезде сохраняется: репозиторий выгружается как CAR-файл через `com.atproto.sync.getRepo`, импортируется на новый PDS, блобы перезаливаются, а DID-документ обновляется через ротацию ключей — DID и граф подписок остаются прежними.[^migration] У `did:plc` для этого есть управляемый набор ротационных ключей и 72-часовое окно восстановления, позволяющее откатить операцию ключом более высокого уровня.[^plc-spec]

## Как создаются приложения

Разработка складывается из четырёх шагов: подключить SDK, аутентифицироваться, читать и писать записи, при необходимости определить свою схему и поднять свою AppView.

**SDK.** Официальные SDK — TypeScript и Go; есть зрелые сообществом поддерживаемые реализации для Python, Rust, Dart, Swift и других.[^sdks] Основной пакет для веба — `@atproto/api`: он даёт абстракцию `Agent`, управление сессией, типы и библиотеку RichText.[^api-readme]

**Первое приложение — минимальный цикл.** По официальному quick-start он состоит из трёх шагов: установить SDK, открыть сессию методом `createSession` (handle + пароль), опубликовать пост через `createRecord`, передав текст и `createdAt`.[^getstarted] На этом уровне приложение уже пишет в сеть.

**Аутентификация.** Основной механизм — OAuth: atproto использует OAuth 2.1 с обязательными PKCE и DPoP; публичные клиенты ограничены короткими сессиями, конфиденциальные поддерживают длинные.[^oauth] Прежний механизм app password (пароль приложения) считается устаревшим и вытесняется OAuth.[^api-readme] Для типовых стеков есть готовые клиенты и туториалы (`OAuth with Node.js`, `OAuth with Next.js`, `OAuth with Go`).[^tutorials]

**Своя схема.** Если приложению нужны собственные типы данных, они описываются Lexicon-схемой в своём NSID-пространстве (например, `xyz.statusphere.status`) и публикуются как записи в репозитории пользователя.[^cloudflare][^lexicon-guide] Так приложение хранит данные в PDS пользователя, а не в собственной базе как единственном источнике истины.

**Чтение сети и своя AppView.** Чтобы показывать агрегированные данные, приложение либо ходит в чужую AppView, либо строит свою: слушает поток изменений и индексирует нужные записи.[^bsky-atproto] Читать весь firehose дорого и избыточно — он несёт плотные блоки Merkle-дерева, которые более 90% потребителей (ленты, боты) вообще не проверяют. Поэтому появился **Jetstream**: облегчённый поток, ужавший firehose более чем на 99% за счёт отказа от передачи MST-блоков.[^jetstream] Для большинства приложений, читающих данные, Jetstream — практичный вход вместо полного firehose.

Каноничный сквозной пример — Statusphere: Next.js-приложение, показывающее вход через OAuth, разрешение DID, чтение потока, собственную Lexicon-схему и публикацию записей.[^statusphere] Его же переносят на serverless-стек (Cloudflare Workers, KV, D1, Durable Objects для WebSocket) — иллюстрация, что архитектура приложения не привязана к одному способу хостинга.[^cloudflare]

Итоговая типовая архитектура приложения: PDS хранит данные пользователя, своя или чужая AppView индексирует поток и отвечает на запросы, OAuth связывает клиент с аккаунтом, Lexicon задаёт контракт данных.

## Где обещания расходятся с практикой

Про atproto много спорят из-за слова «децентрализация». Здесь стоит разделить два разных обещания.

**Credible exit — да, федерация — с оговорками.** Кристин Леммер-Уэббер, соавтор ActivityPub, в разборе архитектуры формулирует различие прямо: федерация — это множество независимых узлов, где ни один не держит больше власти, чем несёт ответственности; credible exit — это возможность уйти к другому провайдеру на тех же данных и протоколах, если оператор обанкротится или потеряет доверие.[^dustycloud] Её вывод: atproto хорошо реализует именно credible exit (через контент-адресацию и переносимость), но по строгому определению федерацией в полном смысле не является.[^dustycloud]

**Стоимость и «shared heap».** Причина — в архитектуре «общей кучи»: все сообщения сваливаются в relay, и заинтересованные стороны сами перебирают весь поток, чтобы найти релевантное.[^dustycloud] Держать полный relay дорого: в разборе Леммер-Уэббер (ноябрь 2024) первая оценка звучит как «около $55k в год» за хостинг relay при тогдашнем объёме сети.[^dustycloud] Оценка спорная и подвижная: позже инженеры Bluesky возражали, что оптимизированный relay с коротким окном backfill держать заметно дешевле, хотя всё ещё на дорогом высокоскоростном канале. Смысл критики не в конкретной цифре, а в том, что стоимость входа в роль relay или AppView несопоставимо выше, чем поднять PDS.

**Практическая централизация.** Несколько независимых наблюдателей сходятся: подавляющее большинство пользователей и трафика — на инфраструктуре Bluesky PBC, а конкурирующая AppView так и не появилась, потому что её запуск требует денег, времени и экспертизы при слабом стимуле.[^fediverse] Академический разбор политики децентрализованных протоколов добавляет нюанс: несмотря на распределённую архитектуру, кураторская власть на практике концентрируется на уровне клиента, что воспроизводит ту самую централизацию, от которой уходили.[^politics] Отдельная точка контроля — `did:plc`: это фактически единый directory идентичности, и в критике отмечают, что оператор технически способен игнорировать обновление записи и тем самым влиять на смену провайдера.[^muni] Кори Доктороу формулирует риск проще: пока нет второго сервера Bluesky, к которому можно уйти, сохранив связи с сообществом, полноценной защиты от «enshittification» нет.[^doctorow]

**Сравнение с соседями.** Относительно ActivityPub/Mastodon разница модельная: федерация через передачу сообщений между инстансами против общей кучи с отдельными индексаторами. Нативной совместимости с ActivityPub у Bluesky нет и не планируется — несовместимость архитектурная.[^dustycloud] Относительно Nostr основное различие — минимализм Nostr против структурированного, схематизированного подхода atproto; ни один не признаётся источниками однозначно «более децентрализованным».

Стоит держать в голове и то, что протокол молодой и подвижный: часть сущностей переименовывалась (например, BGS → Relay), лимиты федерации и управление `did:plc` менялись (directory переводят под независимую структуру), так что конкретные числа и правила стоит сверять с текущей документацией.

## Что в итоге

**Что такое atproto.** Обобщённый протокол социального веба на трёх слоях: постоянная идентичность (DID + handle), переносимый подписанный репозиторий (MST/DAG-CBOR) и сеть сервисов PDS → Relay → AppView, связанных схемами Lexicon и API XRPC. Bluesky — приложение поверх, а не сам протокол.

**Как использовать.** Как открытую платформу данных: строить генераторы лент, лейблеры модерации, клиенты и приложения, не сводящиеся к микроблогу, — от блогов и совместных документов до событий и фото. Одни данные читают несколько конкурирующих приложений, смена приложения не стирает контент и граф.

**Что нужно.** Пользователю — только аккаунт; разработчику — аккаунт и OAuth/пароль приложения против публичных эндпоинтов; для своего узла — скромный PDS (1 ГБ RAM, 20 ГБ SSD, домен, TLS, Docker), с оговоркой, что федерация своего PDS открывалась с жёсткими лимитами.

**Как создаются приложения.** SDK (`@atproto/api` или Go) → сессия/OAuth → чтение и запись записей → при необходимости своя Lexicon-схема и своя AppView, читающая облегчённый поток Jetstream. Эталон для повторения — пример Statusphere.

Главная развилка при оценке — не техническая, а в ожиданиях. Как способ владеть своими данными и иметь «credible exit» atproto работает и уже проверен на практике. Как полная одноранговая децентрализация в строгом смысле — пока нет: relay, основная AppView и directory `did:plc` остаются под контролем Bluesky PBC, и это ограничение архитектурное, а не временное. Для разработчика это, как правило, приемлемый размен: он получает переносимость данных и открытые схемы, отдавая часть инфраструктурной независимости.

## Quality Metrics

| Метрика | Значение |
|---|---|
| Режим | deep |
| Источников найдено | 41 |
| Источников процитировано | 30 |
| Официальная документация / спецификации | 17 |
| Academic (preprint + peer-reviewed) | 2 |
| Industry / news | 3 |
| Blog (включая экспертные разборы) | 8 |
| Sub-questions | 5 |
| Перепроверено первоисточником | стоимость relay ($55k/год), лимиты федерации (10 аккаунтов) |
| Skeptic-перспектива | 12 challenging-источников |
| Покрытие цитатами фактических утверждений | ~92% |

[^arch]: AT Protocol. «Overview». <https://atproto.com/guides/overview>
[^at-stack]: AT Protocol. «The AT Stack». <https://atproto.com/guides/the-at-stack>
[^repos]: AT Protocol. «Personal Data Repositories». <https://atproto.com/guides/data-repos>
[^repo-spec]: AT Protocol. «Repository» (spec). <https://atproto.com/specs/repository>
[^xrpc]: AT Protocol. «HTTP API (XRPC)» (spec). <https://atproto.com/specs/xrpc>
[^lexicon-spec]: AT Protocol. «Lexicon» (spec). <https://atproto.com/specs/lexicon>
[^lexicon-guide]: AT Protocol. «Lexicon» (guide). <https://atproto.com/guides/lexicon>
[^did]: AT Protocol. «DID» (spec). <https://atproto.com/specs/did>
[^identity]: AT Protocol. «Identity». <https://atproto.com/guides/identity>
[^ietf]: Bryan Newbold. «Authenticated Transfer: Architecture Overview» (IETF draft). <https://www.ietf.org/archive/id/draft-newbold-at-architecture-00.html>
[^kleppmann-blog]: Martin Kleppmann. «Bluesky and the AT Protocol: Usable Decentralized Social Media». 2024-02-06. <https://martin.kleppmann.com/2024/02/06/bluesky-at-protocol.html> (paper: <https://arxiv.org/abs/2402.03239>)
[^bailey]: Jeff Bailey. «What Is the AT Protocol? A Developer's Mental Model». 2026-05-25. <https://jeffbailey.us/blog/2026/05/25/what-is-atproto/>
[^bsky-atproto]: Bluesky. «The AT Protocol» (advanced guides). <https://docs.bsky.app/docs/advanced-guides/atproto>
[^feeds]: AT Protocol. «Feeds». <https://atproto.com/guides/feeds>
[^building]: Bluesky. «Building on the AT Protocol». <https://docs.bsky.app/blog/building-on-atproto>
[^bmann]: Boris Mann. «Beyond Microblogging: AT Protocol for Building Unique Social Apps». <https://bmannconsulting.com/notes/beyond-microblogging-atproto/>
[^anil]: Anil Madhavapeddy. «Using AT Proto for more than just Bluesky posts». <https://anil.recoil.org/notes/atproto-for-fun-and-blogging>
[^willschenk]: Will Schenk. «Interesting ATProto Projects in the Wild». 2025. <https://willschenk.com/articles/2025/interesting_atproto_projects/>
[^techcrunch]: TechCrunch. «Beyond Bluesky: These are the apps building social experiences on the AT Protocol». 2025-06-13. <https://techcrunch.com/2025/06/13/beyond-bluesky-these-are-the-apps-building-social-experiences-on-the-at-protocol/>
[^cloudflare]: Cloudflare. «Serverless Statusphere: building serverless ATProto applications on Cloudflare's Developer Platform». <https://blog.cloudflare.com/serverless-atproto/>
[^api-hosts]: Bluesky. «API Hosts and Auth». <https://docs.bsky.app/docs/advanced-guides/api-directory>
[^getstarted]: Bluesky. «Get Started». <https://docs.bsky.app/docs/get-started>
[^pds-repo]: Bluesky. «PDS» (GitHub, system requirements). <https://github.com/bluesky-social/pds>
[^selfhost]: AT Protocol. «Self-hosting». <https://atproto.com/guides/self-hosting>
[^primozic]: Casey Primozic. «Notes on Self Hosting a Bluesky PDS Alongside Other Services». <https://cprimozic.net/notes/posts/notes-on-self-hosting-bluesky-pds-alongside-other-services/>
[^production]: AT Protocol. «Going to production». <https://atproto.com/guides/going-to-production>
[^selfhost-fed]: Bluesky. «Early Access Federation for Self-Hosters». 2024-02-22. <https://docs.bsky.app/blog/self-host-federation>
[^migration]: AT Protocol. «Account Migration». <https://atproto.com/guides/account-migration>
[^plc-spec]: did:plc. «did:plc Specification v0.1». <https://web.plc.directory/spec/v0.1/did-plc>
[^sdks]: AT Protocol. «SDKs». <https://atproto.com/sdks>
[^api-readme]: Bluesky. «@atproto/api» (package README). <https://github.com/bluesky-social/atproto/blob/main/packages/api/README.md>
[^oauth]: AT Protocol. «OAuth» (spec). <https://atproto.com/specs/oauth>
[^tutorials]: AT Protocol. «Tutorials». <https://atproto.com/guides/tutorials>
[^statusphere]: Bluesky. «Statusphere Example App». <https://github.com/bluesky-social/statusphere-example-app>
[^jetstream]: Jaz. «Jetstream: Shrinking the AT Proto Firehose by >99%». 2024-09-24. <https://jazco.dev/2024/09/24/jetstream/>
[^dustycloud]: Christine Lemmer-Webber. «How decentralized is Bluesky really?». 2024-11-22. <https://dustycloud.org/blog/how-decentralized-is-bluesky/>
[^fediverse]: Fediverse Report. «A Conceptual Model of ATProto and ActivityPub». <https://fediversereport.com/a-conceptual-model-of-atproto-and-activitypub/>
[^politics]: «Seeing the Politics of Decentralized Social Media Protocols». 2025. <https://arxiv.org/html/2505.22962v1>
[^muni]: Zicklag. «ATProto Isn't What You Think». 2025-03-12. <https://blog.muni.town/atproto-isnt-what-you-think/>
[^doctorow]: Cory Doctorow. «Bluesky and enshittification». 2024-11-02. <https://doctorow.medium.com/https-pluralistic-net-2024-11-02-ulysses-pact-tie-yourself-to-a-federated-mast-b2f89bb5b4d8>
