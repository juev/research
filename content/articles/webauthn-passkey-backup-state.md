---
title: "WebAuthn Level 3: что сервер знает о синхронизируемом passkey и чего не знает"
date: 2026-11-25T09:51:00+03:00
description: "BE, BS, signCount и attestation позволяют строить политику для passkeys, но не раскрывают инвентарь устройств и не гарантируют восстановление аккаунта."
showToc: true
tocOpen: true
---

## Аннотация

Синхронизируемый passkey не превращается на сервере в список телефонов и компьютеров пользователя. Relying party видит credential ID, публичный ключ и подписанные authenticator data; среди них есть флаги backup eligibility (`BE`), backup state (`BS`) и счётчик `signCount`. Они полезны для политики допуска и оценки риска, но не отвечают, сколько копий ключа существует, на каких устройствах они находятся и сможет ли владелец восстановить доступ.

В обзоре разобраны WebAuthn Level 3 — W3C Recommendation от 25 августа 2026 года, — NIST SP 800-63B-4, документация Google, Microsoft, Apple, SimpleWebAuthn и исследования синхронизируемых credentials. Отдельно рассмотрены Signal API, attestation и противоречие в руководстве Google, которое смешивает `BE` с текущим состоянием резервной копии. Данные на 2026-11-25; собственные interoperability-тесты браузеров и passkey providers не проводились.

## Введение: credential не равен устройству

WebAuthn Level 3 стал W3C Recommendation 25 августа 2026 года и закрепил модель, в которой дальнейшие новые возможности разрабатываются уже в Level 4. Для relying party (RP) это повод зафиксировать точную семантику полей, а не полагаться на бытовое определение «синхронизируемого ключа».[^1][^2]

При регистрации сервер получает и сохраняет как минимум `credentialId`, публичный ключ, `signCount`, `backupEligible` и `backupState`; при аутентификации он проверяет challenge, origin, `rpIdHash`, флаги присутствия и верификации пользователя, затем подпись сохранённым публичным ключом. Это доказывает владение соответствующим закрытым ключом в рамках конкретной церемонии, но не создаёт учётной записи для каждого физического устройства.[^1][^4][^5]

Такое разделение принципиально: Google прямо описывает возможность существования одного закрытого ключа на нескольких устройствах через synchronization и backup. Следовательно, повторный вход с тем же credential ID может означать другое устройство, а новое устройство не обязано порождать новую строку в базе RP.[^3]

## BE и BS: два независимых утверждения

`authenticatorData` начинается с 32-байтового `rpIdHash`, одного байта flags и четырёхбайтового беззнакового big-endian `signCount`; минимальная длина структуры — 37 байтов. В байте flags `BE` занимает бит 3 (`0x08`), а `BS` — бит 4 (`0x10`). Оба значения приходят внутри подписанных authenticator data, поэтому RP должен разбирать их после проверки церемонии, а не принимать самостоятельные boolean-поля от клиента.[^1]

**Backup eligibility — постоянное свойство credential.** Authenticator определяет его при создании: `BE=1` означает multi-device credential, который разрешено резервировать, а после регистрации значение меняться не должно. Если RP использует backup state в бизнес-логике или политике, при последующих входах сервер сверяет текущий `BE` с сохранённым `backupEligible`; несовпадение — ошибка проверки, а не повод молча изменить тип credential.[^1]

**Backup state — текущее наблюдение.** `BS=1` означает, что managing authenticator считает credential резервированным в момент операции. Значение может меняться между регистрацией и аутентификацией; спецификация требует обновить сохранённый `backupState` после успешных проверок. Если authenticator не уверен в состоянии или подозревает проблему с копией, он не должен устанавливать `BS`.[^1]

Допустимы три сочетания: `BE=0, BS=0` — device-bound credential; `BE=1, BS=0` — копирование разрешено, но сейчас резервная копия не подтверждена; `BE=1, BS=1` — копирование разрешено и текущее состояние отмечено как backed up. Сочетание `BE=0, BS=1` противоречиво: алгоритм аутентификации предписывает проверить, что при сброшенном `BE` сброшен и `BS`.[^1]

При этом backed up шире, чем «лежит в облаке». Определение W3C включает peer-to-peer и cloud sync, синхронизацию по локальной сети и ручные import/export. Поэтому из `BS=1` нельзя вывести название провайдера, регион хранения, число копий, наличие шифрования или факт успешного тестового восстановления.[^1]

### Документационная ловушка

Руководство Google по server-side registration, обновлённое 16 ноября 2026 года, предлагает определять поле `backed_up` по флагу `BE`. Это смешивает разрешение на резервирование с его текущим состоянием и противоречит нормативному различию W3C: для `backed_up` нужен `BS`, тогда как `BE` следует хранить отдельно как `backup_eligible`.[^1][^4]

Практический ориентир подтверждает такое прочтение. В SimpleWebAuthn 13.3.1 `parseBackupFlags()` присваивает `credentialBackedUp = bs`, а `credentialDeviceType = multiDevice` выводит из `be`; комбинация single-device и backed-up вызывает `InvalidBackupFlags`. При аутентификации библиотека возвращает новые `credentialDeviceType` и `credentialBackedUp`, поэтому приложению следует обновлять не только counter, но и backup state в собственной записи.[^8][^9]

## signCount: детектор аномалии, а не счётчик устройств

Счётчик подписи задуман как дополнительный сигнал для обнаружения клонированного authenticator. Если authenticator не поддерживает эту возможность, он оставляет `signCount` равным нулю. Когда новое или сохранённое значение отлично от нуля, RP сравнивает их: рост счётчика валиден, а значение меньше либо равное сохранённому — сигнал, но не доказательство клона.[^1]

У негативного результата есть штатные объяснения: две копии закрытого ключа используются параллельно, authenticator неисправен или RP обработал ответы не в порядке их создания. Вопрос #2172 в репозитории W3C показывает простую гонку: ответ с более новым `C2` обработан раньше старого `C1`, после чего `C1` выглядит подозрительно. Спецификация оставляет выбор между risk scoring, обновлением счётчика и отказом от входа за политикой RP.[^1][^10]

Нулевой `signCount` ничего не говорит ни о числе устройств, ни об отсутствии злоупотреблений. SimpleWebAuthn приводит Touch ID на macOS как пример authenticator, который может всегда возвращать ноль; Unit 42 в исследовании Google Password Manager на Windows также сообщает о постоянном счётчике в синхронизируемой системе. Это наблюдения над конкретными реализациями, а не универсальное свойство всех passkeys.[^17][^20]

Поэтому корректные выводы узки: «counter не поддерживается», «counter вырос» или «наблюдение требует дополнительной оценки риска». Некорректные — «пользователь вошёл с третьего устройства», «клон доказан» и «ноль исключает копирование». Даже монотонный счётчик идентифицирует последовательность assertions для credential, а не физический экземпляр устройства.[^1][^20]

## Attestation и AAGUID: происхождение на регистрации

Attestation отвечает на другой вопрос: может ли RP доверять заявленным свойствам authenticator при создании credential. При `attestation: "direct"` или `"enterprise"` клиент передаёт AAGUID и attestation statement без изменений; при `"none"` attestation statement заменяется пустым `fmt: "none"`, кроме особого случая self attestation. Ненулевой AAGUID в Level 3 сам по себе не доказывает проверенное происхождение устройства.[^1]

FIDO Metadata Service помогает сопоставить AAGUID с подписанными метаданными: производителем, моделью, сертификацией, возможностями и статусом доверия. Это основа allowlist или denylist для управляемой среды, но не телеметрия текущих устройств пользователя. Attestation относится к регистрационному authenticator; последующее использование синхронизированного credential на другом устройстве не создаёт новой аттестации этого устройства для RP.[^1][^11]

Доступность таких сигналов зависит от среды. Microsoft для synced passkeys в Entra указывает отсутствие attestation и рекомендует device-bound варианты администраторам и привилегированным пользователям. Это документированное ограничение конкретного deployment, а не основание объявить attestation невозможной для любого синхронизируемого credential.[^12]

NIST SP 800-63B-4 занимает более различённую позицию. Syncable authenticators могут применяться на AAL2 при выполнении требований к encrypted sync fabric, AAL2-equivalent доступу, локальным операциям с ключом и контролю жизненного цикла; для AAL3 они запрещены, потому что синхронизация предполагает экспортируемость закрытого ключа. Для публичных сервисов NIST не рекомендует делать отсутствие attestation блокером, а `BE` и `BS` разрешает использовать в политике.[^6][^7]

## Три разных восстановления

**Восстановление ключа у провайдера.** Apple сообщает, что passkeys в iCloud Keychain синхронизируются между устройствами и защищены end-to-end encryption; Google описывает восстановление ключей шифрования через screen lock существующего устройства и защищённый online backup. Эти механизмы повышают доступность, но их внутреннее состояние не передаётся RP в `BE` или `BS`.[^3][^13]

**Восстановление аккаунта провайдера.** Даже наличие резервной копии не доказывает, что пользователь помнит PIN, сохранил доступ к recovery factor, может пройти device enrollment или не потерял сам аккаунт провайдера. Сравнительное исследование Büttner и Gruschka поэтому концентрирует существенную часть безопасности synced passkeys в passkey provider; это аналитическая модель, а не измеренная вероятность lockout.[^18]

**Восстановление аккаунта у RP.** WebAuthn не определяет, как сервис восстановит доступ, если credential недоступен. OWASP рекомендует несколько authenticators, одноразовые recovery codes или соразмерную риску identity recovery, уведомления и защиту слабейшего recovery route. Следовательно, `BS=1` — аргумент в пользу доступности, но недостаточное основание автоматически удалить пароль или последний независимый recovery method.[^14]

Это различие имеет практическое следствие: сервер может наблюдать успешную подпись и не наблюдать ни пробную потерю всех устройств, ни способность владельца открыть sync fabric, ни качество собственной процедуры восстановления. Гарантия «пользователь не потеряет аккаунт» требует отдельного lifecycle-дизайна и тестирования, а не одного флага.[^6][^14]

## Signal API: согласование состояния, не инвентаризация

Level 3 добавляет `signalUnknownCredential()`, `signalAllAcceptedCredentials()` и `signalCurrentUserDetails()`. Первый метод сообщает, что RP не распознал credential ID; второй передаёт полный список принимаемых IDs для аутентифицированного пользователя; третий обновляет отображаемые имя и user handle. Они помогают credential provider скрыть удалённые passkeys и устранить рассинхронизацию с сервером.[^1][^15]

`signalUnknownCredential()` не требует полного списка credentials и user handle, чтобы не раскрывать их неаутентифицированному вызывающему. `signalAllAcceptedCredentials()`, наоборот, должен содержать полный snapshot: отсутствующий ID может быть скрыт или удалён, поэтому неполный список опасен. Authenticator может быть отключён в момент вызова, и W3C предлагает повторять сигнал периодически, например при входе.[^1][^15]

Поддержку нельзя считать одновременно универсальной. В WPT snapshot от 26 июня 2026 года `signal-all-accepted-credentials` дал 8/8 subtests в Chrome и Edge, 4/8 в Safari preview и 0/8 в Firefox; `signal-current-user-details` — соответственно 4/4, 4/4, 1/4 и 0/4. Это ограниченный тестовый snapshot, а не рейтинг безопасности passkey providers.[^16]

Главное ограничение остаётся прежним: Signal API синхронизирует представление о lifecycle credential, а не сообщает, на скольких устройствах существует ключ. Он также не заменяет серверный revoke и не восстанавливает аккаунт пользователя.[^14][^15]

## Что показывают свежие атаки

В 2026 году Unit 42 описала три Pass-ta-key сценария для Google Password Manager в Chrome на Windows с TPM. Исходным условием было уже выполняющееся на устройстве вредоносное ПО; исследователи использовали device trust, onboarding и recovery, а не взлом криптографии WebAuthn. В одном из сценариев корректная подпись получалась без ожидаемого пользовательского взаимодействия, а другой затрагивал извлечение key material из процесса Chrome.[^17]

Для темы наблюдаемости вывод ограниченный: валидная assertion подтверждает криптографическую церемонию, но не отсутствие endpoint compromise. RP не должен превращать `BS`, `UV`, AAGUID или `signCount` в универсальный индикатор безопасности устройства; нужны строгая проверка требуемого `UV`, защита enrollment/recovery и независимые risk signals. Результаты Unit 42 относятся к исследованной конфигурации и не доказывают уязвимость каждого provider.[^14][^17]

## Практическая политика RP

Ниже — рекомендуемая модель, а не нормативный алгоритм W3C. Она сочетает обязательные проверки протокола с решениями, которые сервис выбирает по своему риску.[^1][^6][^14]

```text
CredentialRecord:
  id, userHandle, publicKey, algorithm
  backupEligible             # записать из BE один раз
  backupState                # обновлять из BS после успешной проверки
  signCount                  # обновлять по правилам библиотеки
  uvInitialized, transports
  attestation/AAGUID         # если политика их использует
  createdAt, lastUsedAt      # метаданные RP, не свойства WebAuthn

На каждой аутентификации:
  проверить challenge, origin, rpIdHash, владельца credential и подпись
  проверить UP; при userVerification=required проверить UV
  отклонить BE=0, BS=1
  проверить неизменность backupEligible
  оценить signCount как risk signal
  только после остальных проверок обновить backupState и signCount
```

Для публичного сервиса разумно принимать synced и device-bound passkeys, требовать `UV` там, где passkey заменяет MFA, хранить несколько credentials на аккаунт и не блокировать вход только из-за `BS=0` или нулевого счётчика. Изменение `BS`, аномалия counter и новый enrollment должны попадать в журнал риска, но не становиться самостоятельным доказательством взлома.[^6][^14][^20]

Для управляемой среды политика может отклонять `BE=1` или требовать device-bound credential и проверенную attestation через MDS. Для NIST AAL3 syncable authenticator неприменим в принципе, тогда как на AAL2 нужны дополнительные контроли sync fabric и device enrollment. Это решения assurance policy, а не способ получить более точный список устройств.[^6][^7][^11][^19]

## Противоречия и недостаточность данных

Главное противоречие находится не в криптографии, а в документации: Google связывает `backed_up` с `BE`, W3C и SimpleWebAuthn — с `BS`. До исправления руководства серверной команде следует опираться на Recommendation и проверять mapping в версии используемой библиотеки, а не копировать название поля из примера схемы.[^1][^4][^8]

Второе противоречие касается attestation. Microsoft описывает её отсутствие для synced passkeys в своём deployment, NIST допускает отсутствие attestation в публичных приложениях, а Yubico считает attestation сильнейшим сигналом для high-assurance RP. Это позиции для разных threat models: interoperability consumer-сервиса нельзя без оговорок переносить на управляемый enterprise.[^6][^12][^19]

Не найдено независимых измерений точности `BS` и ложных срабатываний `signCount` по репрезентативному наборе passkey providers. WPT измеряет поддержку browser API, vendor docs описывают заявленное поведение, а Unit 42 исследует конкретную атаку; ни один источник не даёт процента устройств, которые RP способен правильно распознать. Поэтому численной «надёжности инвентаризации» здесь нет — и сама такая метрика была бы неверной постановкой задачи.[^1][^16][^17]

## Заключение

Сервер знает, что владелец credential прошёл конкретную WebAuthn-церемонию, разрешено ли резервировать ключ и считает ли текущий authenticator его резервированным. При поддержке счётчика он видит ещё один сигнал аномалии, а при attestation — сведения о происхождении authenticator на регистрации. Этого достаточно для осмысленной политики, но недостаточно для инвентаря устройств.[^1][^11]

`BE` отвечает на «можно ли копировать», `BS` — «считается ли сейчас скопированным», `signCount` — «есть ли аномалия в последовательности assertions». Ни одно поле не отвечает на «сколько устройств», «какие именно», «здоровы ли они» и «восстановит ли пользователь аккаунт». Последний вопрос решается независимыми credentials, защищённым enrollment и recovery-процессом RP.[^6][^14]

## Quality Metrics

| Metric | Value |
|--------|-------|
| Sources found | 52 |
| Sources read | 31 |
| Sources cited | 20 |
| Academic sources | 1 |
| Official/documentation | 18 |
| Industry reports | 1 |
| News/journalism | 0 |
| Blog/forum | 0 |
| Citation coverage | 90% |
| Counter-arguments searched | Yes |
| Research rounds | 3 |
| Questions emerged | 8 |
| Questions resolved | 7 |
| Questions insufficient data | 1 |

[^1]: W3C. "Web Authentication: An API for accessing Public Key Credentials Level 3." W3C Recommendation, 25 August 2026. https://www.w3.org/TR/2026/REC-webauthn-3-20260825/
[^2]: W3C. "Web Authentication: An API for accessing Public Key Credentials Level 3 is now a W3C Recommendation." W3C News, 25 August 2026. https://www.w3.org/news/2026/web-authentication-an-api-for-accessing-public-key-credentials-level-3-is-now-a-w3c-recommendation/
[^3]: Arnar Birgisson. "Security of Passkeys in the Google Password Manager." Google Security Blog, 12 October 2022. https://security.googleblog.com/2022/10/SecurityofPasskeysintheGooglePasswordManager.html
[^4]: Google for Developers. "Server-side passkey registration." Web guides, updated 16 November 2026. https://developers.google.com/identity/passkeys/developer-guides/server-registration?hl=en
[^5]: Google for Developers. "Server-side passkey authentication." Web guides, updated 27 October 2026. https://developers.google.com/identity/passkeys/developer-guides/server-authentication?hl=en
[^6]: NIST. "Syncable Authenticators." SP 800-63B-4, July 2025. https://pages.nist.gov/800-63-4/sp800-63b/syncable/
[^7]: NIST. "Authentication Assurance Levels." SP 800-63B-4, July 2025. https://pages.nist.gov/800-63-4/sp800-63b/aal/
[^8]: MasterKale. "parseBackupFlags.ts." SimpleWebAuthn, tag v13.3.1, 2026. https://github.com/MasterKale/SimpleWebAuthn/blob/v13.3.1/packages/server/src/helpers/parseBackupFlags.ts
[^9]: MasterKale. "verifyAuthenticationResponse.ts." SimpleWebAuthn, tag v13.3.1, 2026. https://github.com/MasterKale/SimpleWebAuthn/blob/v13.3.1/packages/server/src/authentication/verifyAuthenticationResponse.ts
[^10]: W3C Web Authentication Working Group. "Should race condition be added as a reason for a signature counter not increasing? #2172." GitHub, 1 October 2024. https://github.com/w3c/webauthn/issues/2172
[^11]: FIDO Alliance. "FIDO Metadata Service (MDS) Overview." FIDO Alliance. https://fidoalliance.org/metadata/
[^12]: Microsoft. "Enable synced passkeys in Microsoft Entra ID." Microsoft Learn. https://learn.microsoft.com/en-us/entra/identity/authentication/how-to-synced-passkeys
[^13]: Apple. "Passkeys." Apple Developer. https://developer.apple.com/passkeys/
[^14]: OWASP. "Passkey Security Cheat Sheet." OWASP Cheat Sheet Series. https://cheatsheetseries.owasp.org/cheatsheets/Passkey_Security_Cheat_Sheet.html
[^15]: Google Chrome Developers. "Keep passkeys consistent with credentials on your server with the Signal API." Chrome for Developers, updated 12 November 2024. https://developer.chrome.com/docs/identity/webauthn-signal-api?hl=en
[^16]: W3C. "web-platform-tests dashboard snapshot for /webauthn/." WPT snapshot, 26 June 2026. https://www.w3.org/2026/06/wpt-webauthn-2026-06-26.html
[^17]: Palo Alto Networks Unit 42. "Pass the Passkey: A Novel Attack Surface in Passwordless Authentication." Unit 42, 2026. https://unit42.paloaltonetworks.com/passwordless-authentication-security-risks/
[^18]: Andre Büttner, Nils Gruschka. "Device-Bound vs. Synced Credentials: A Comparative Evaluation of Passkey Authentication." ICISSP 2025 author version; arXiv:2501.07380, 13 January 2025. https://arxiv.org/html/2501.07380v1
[^19]: Yubico. "High assurance passkey relying party." Passkey relying party implementation guidance. https://developers.yubico.com/Passkeys/Passkey_relying_party_implementation_guidance/High_assurance_passkey_relying_party.html
[^20]: SimpleWebAuthn. "@simplewebauthn/server." SimpleWebAuthn Documentation. https://simplewebauthn.dev/docs/packages/server/
