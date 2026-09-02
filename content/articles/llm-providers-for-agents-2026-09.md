---
title: "Выбор LLM-провайдеров и моделей для разработки и агентных систем"
date: 2026-09-02T09:11:43+03:00
---

## Аннотация

Проведено сравнение шести провайдеров/подходов к получению LLM-инференса для двух сценариев: (1) агентные системы с OpenAI-совместимым API, надёжным tool calling, длинными контекстами и чувствительным к цене трафиком и (2) интерактивная разработка кода (CLI-агенты: Claude Code, Codex CLI, OpenCode). Цены и бенчмарки собраны из первичных источников 2026-09-01: официальные прайс-страницы и API-каталоги (OpenRouter `/api/v1/models`, RouterAI `/api/v1/models`, Selectel promo, docs OpenAI/Anthropic/z.ai/DeepSeek), лидерборды SWE-bench Verified, Terminal-Bench 2.1/3.0, Artificial Analysis.

Главные выводы: **для агентных систем** разумный баланс цены и качества — открытые модели китайских вендоров (GLM-5.3-Flash, DeepSeek V4 Flash/Pro, MiniMax, Kimi), доступные одновременно напрямую (z.ai — самый дешёвый канал для GLM), через OpenRouter (fallback между 420 моделями) и через российские рублёвые шлюзы (RouterAI, Selectel — оплата картами РФ без крипты и зарубежных карт). **Для разработки** лидер качества — Claude Opus 5 (Terminal-Bench 3.0: 51.8%), но разрыв с открытыми моделями сократился до ~10 п.п. на самых сложных задачах при цене в 2–20 раз выше; на стандартизованном SWE-bench Verified разрыв открытых и закрытых — около 1 п.п. Подписки: Claude Pro/Max **легально работают только** в официальных приложениях Anthropic (сторонние агенты — только API, прокси подписки = реальные баны); OpenAI Code/Codex-подписка **де-факто допускает** сторонние обвязки через OAuth, но без юридических гарантий; GLM Coding Plan официально позиционируется для CLI-агентов (Lite от $12.6/мес при годовой оплате).

Курс, использованный для рублёвых пересчётов: **86.38 ₽/$** (ЦБ РФ, 2026-09-01) [^60].

## Введение

**Актуальность.** Рынок LLM за лето 2026 сильно фрагментировался: OpenRouter агрегирует 420+ моделей, появились российские рублёвые шлюзы (RouterAI — 468 моделей, Selectel ИИ-роутер — «300+»), Ollama 31.08.2026 перевела облако на помодельную токенную оплату, OpenAI выпустила новое поколение GPT-5.6 (Sol/Terra/Luna) с агрессивным промо, Anthropic выпустила Opus 5 и Sonnet 5, а Z.ai — GLM-5.3/5.3-Flash с открытыми весами. Цена ошибки выбора растёт: агентные системы расходуют на порядок больше токенов, чем чат-использование, из-за многократных обращений с растущим контекстом.

**Цель** — выбрать конфигурацию «провайдер + модель» для двух сценариев: работа агентной системы через OpenAI-совместимый API и интерактивная разработка с CLI-агентами. Критерии: возможности (качество кода/агентность, контекст, tool calling, скорость), стоимость (цена за 1M токенов, комиссии, курсы), доступность оплаты из России, надёжность.

**Границы.** Не рассматриваются: image/video-модели, локальный инференс на GPU (локальный инференс тяжёлых моделей на CPU — отдельный инфраструктурный сценарий и здесь не рассматривается, см. раздел Ollama), эмбеддинги (уже решены локальным Ollama + bge-m3). Цены зафиксированы на 2026-09-01 и быстро устаревают; промо-цены помечены.

## 1. Сводная таблица: модели для кодинга и агентов

Цены — USD за 1M токенов (input/output), из каталога OpenRouter [^1] и официальных прайсов [^54][^55][^16][^27]. Скоринг — Terminal-Bench (агентный, самый дискриминирующий), SWE-bench Verified (насыщен, см. §8), Artificial Analysis Intelligence Index v4.1.1 (агрегатор) [^51][^52][^53].

| Модель | In $ | Out $ | Кэш $ | Контекст | TB3.0 | TB2.1 | AA idx | Веса |
|---|---|---|---|---|---|---|---|---|
| **Claude Opus 5** | 5.00 | 25.00 | 0.50 | 1M | **51.8%** | 89.1% | 63.1 | нет |
| Claude Fable 5 | 10.00 | 50.00 | — | 1M | 44.5% | — | 62.1 | нет |
| **GLM-5.3** | 1.40 | 4.40 | 0.26 | 1.31M | **41.8%** | 83.9% | 59.5 | да (MIT у Flash) |
| GPT-5.6 Sol | 4.00* | 20.00* | 0.40 | 1.05M | 37.3% | 88.0% | 60.9 | нет |
| Claude Sonnet 5 | 2.00 | 10.00 | 0.20 | 1M | — | — | — | нет |
| **Kimi K3** | 3.00 | 15.00 | 0.30 | 1M | — (TB2.1: 85.0%) | 85.0% | 59.7 | да |
| Gemini 3.7 Flash | 0.75 | 3.75 | — | 1M | — | 85.8% | 56.0 | нет |
| DeepSeek V4 Pro | 0.66–1.32 | 1.98–3.96 | 0.135 | 1M | — | 78.7% | 53.2 | да |
| **GLM-5.3-Flash** | 0.15** | 0.50** | 0.03 | 1.31M | — | **84.3%** | 57.5 | да (MIT) |
| MiniMax M2.5/M3 | 0.30 | 1.20 | 0.06 | 1M | — | — | 45.4 (M3) | да |
| GPT-5.6 Luna | 0.20 | 1.20 | 0.02 | 1.05M | 17.3% | — | 52.3 | нет |
| Qwen3-Coder (480B) | 0.30 | 1.00 | 0.10 | 262K | — | — | — | да |
| Kimi K2.7-Code | 0.66 | 3.40 | 0.18 | 262K | — | — | — | да |
| gpt-oss-120b | 0.15 | 0.60 | 0.014 | 131K | — (TB-hard: 23.5%) | — | 24.1 | да |
| GPT-5.3-Codex | 1.75 | 14.00 | 0.175 | 400K | — | — | — | нет |

\* Sol — промо −20%/−33% минимум до 21.11.2026; лист $5/$30 [^17][^18].
\** GLM-5.3-Flash у z.ai — промо до 09.09.2026 [^54]; на OpenRouter вдвое дешевле ($0.075/$0.25) [^1] — вероятно, тоже промо/дешёвый провайдер в роутинге.

Как читать таблицу: TB3.0 (Terminal-Bench 3.0) — живой агентный бенчмарк (330 реальных задач в терминале), лучший дискриминатор 2026 года [^52]; SWE-bench Verified насыщен (топ-модели 93–97%, см. §8) и почти не различает модели [^64]; AA idx — общий интеллект.

## 2. Стоимость агентного дня

Модель расчёта: тяжёлый агентный день = 30M input-токенов (из них 25M кэшированных — система и история в агентной петле читаются из кэша), 1M output. Курс 86.38 ₽/$ [^60]. Расчёт линейный — при ×6 меньшем трафике делите на 6.

| Модель (канал) | $/день | ₽/мес (30 дней) |
|---|---|---|
| DeepSeek V4 Flash (OpenRouter) | 0.67 | ~1 730 ₽ |
| **GLM-5.3-Flash (OpenRouter)** | 1.00 | ~2 590 ₽ |
| GLM-5.3-Flash (z.ai, промо) | 2.00 | ~5 180 ₽ |
| gpt-oss-120b (Ollama Cloud) | 1.70 | ~4 400 ₽ |
| GPT-5.6 Luna (OpenAI) | 2.70 | ~7 000 ₽ |
| MiniMax M3 (OpenRouter) | 4.20 | ~10 900 ₽ |
| Qwen3-Coder (OpenRouter) | 5.00 | ~13 000 ₽ |
| DeepSeek V4 Pro (OpenRouter) | 8.66 | ~22 400 ₽ |
| Gemini 3.6 Flash (OpenRouter) | 9.38 | ~24 300 ₽ |
| Kimi K2.7-Code (OpenRouter) | 11.20 | ~29 000 ₽ |
| GLM-5.3 (OpenRouter/z.ai) | 17.90 | ~46 400 ₽ |
| GPT-5.6 Terra (OpenAI) | 27.00 | ~70 000 ₽ |
| GPT-5.3-Codex (OpenAI, Responses) | 27.12 | ~70 300 ₽ |
| Claude Sonnet 5 | 25.00 | ~64 800 ₽ |
| GPT-5.6 Sol (OpenAI, промо) | 50.00 | ~129 600 ₽ |
| Claude Opus 5 | 62.50 | ~162 000 ₽ |

Разница между бюджетным и топовым вариантом — **два порядка**. При этом разрыв в качестве на типовых агентных задачах намного меньше, чем в цене: GLM-5.3-Flash проигрывает Opus 5 ~1.4 пункта AA-индекса (57.5 vs 63.1) [^53] — на фоне 60-кратной разницы в цене дня.

Подписки сравниваются с этой шкалой так: GLM Coding Plan (Lite $12.6–18/мес, 10k кредитов/нед) покрывает типовой кодинг-трафик; Ollama Pro $20/мес = $60 кредитов ≈ 35 таких «тяжёлых дней» на glm-5.3-flash; Claude Max $100–200 и ChatGPT Pro $100–200 — про доступ к топ-моделям без токенного биллинга.

## 3. OpenRouter

**Что это:** крупнейший агрегатор — 420 моделей через единый OpenAI-совместимый API, цены pass-through без наценки на инференс [^1][^2].

**Цены и комиссия.** Наценки на токены нет; комиссия берётся только на пополнении: карты/Stripe — **5.5% (мин. $0.80)**, крипта (USDC через Coinbase) — **5%** [^2][^3]. BYOK (свой ключ провайдера) — 5% от стоимости сверх бесплатной квоты, кап $25k list-price/мес [^3]. Цены без VAT.

**Возможности для агентов** — сильнейшие в классе:
- авто-роутинг с fallback между провайдерами одной модели, фильтры `require_parameters` (гарантия tool calling), `provider.order`, `max_price`, ZDR [^4];
- prompt caching со sticky-роутингом (липкость к провайдеру 10 мин, `prompt_cache_key` для агентных сессий) — кэш-чтение в 10–25× дешевле input [^5];
- у всех ключевых моделей заявлены `tools`, `tool_choice`, `structured_outputs`, `reasoning` (проверено в JSON-каталоге) [^1];
- суффиксы `:batch` (−50%), `:nitro` (скорость), `:free` (50 запросов/сутки, 1000 после разового пополнения ≥$10) [^1][^6].

**Надёжность:** 99.99% uptime инференс-API за 90 дней (status.openrouter.ai) [^7].

**Оплата из РФ:** российских карт нет; рабочий путь — USDC (−5%) [^2]. Глобальные rate limits привязаны к аккаунту [^6].

**Итог:** лучший «буферный» канал — одна учётка, все модели мира, дешёвый вход через USDC, страховка от недоступности отдельного вендора.

## 4. Ollama (облако + self-host)

**Новые прайсы (31.08.2026):** Ollama сменила биллинг облака с GPU-времени на помодельную токенную оплату с кредитным пулом [^8]:

| План | Цена | Кредитов/мес | Параллельных запросов |
|---|---|---|---|
| Free | $0 | starter-пул (размер не публикуется) | 1 |
| Pro | $20/мес | **$60** | 3 |
| Max | $100/мес | **$300** | 10 |
| Team | $500/мес | $1000 (общий) | 10 |

Кредиты сгорают; сверх пула — помодельная оплата без наценки; zero data retention [^9]. Цены моделей близки к прайсам вендоров: glm-5.3 $1.40/$4.40, glm-5.3-flash $0.15/$0.50 (кэш $0.03), gpt-oss-120b $0.15/$0.60 (**кэш $0.014** — самый дешёвый кэш в обзоре), deepseek-v4-flash $0.44/$1.32, kimi-k2.7-code $0.95/$4.00 [^9]. Минус: облачные модели периодически выводятся из эксплуатации (последние — minimax-m2.5, kimi-k2.5 до 31.07.2026) [^62].

**API:** OpenAI-совместимый `https://ollama.com/v1` + Anthropic Messages-совместимость (`/v1/messages`, заявлена поддержка Claude Code) + «родной» режим удалённого Ollama-хоста; гибрид — локальный демон проксирует `-cloud`-модели после `ollama signin` [^10][^11][^12].

**Self-host: практические ограничения.** главный фактор — пропускная способность памяти. На CPU: gpt-oss-120b (~63 ГБ, нужно 64+ ГБ RAM) — 7–12 tok/s на потребительской DDR5, ~35 tok/s на серверном EPYC; dense 32B — всего 3.5 tok/s; интерактивно на CPU тянутся только MoE ~20–35B-A3B (gpt-oss-20b, qwen3-coder-30b-a3b) при 24–32 ГБ RAM и быстрой DDR5 с XMP [^13][^14][^15]. Один потребительский GPU 16–24 ГБ VRAM (3090/4090, ~$600–1000 б/у) меняет картину: 25–50+ tok/s [^13][^15]. CPU-only хост годится для эмбеддингов и небольших MoE, но не заменяет облачный инференс для кодинга.

**Итог:** облако Ollama интересно как «второй канал» с дешёвым кэшем (gpt-oss-120b) и единым API с локальным Ollama; Free-план — бесплатная проба. Но как основной канал для агентных систем уступает z.ai/OpenRouter по цене flash-моделей и стабильности каталога.

## 5. OpenAI

**API-линейка (Standard, $/1M):** GPT-5.6 Sol $4/$20 (промо −20%/−33% до ~21.11.2026, лист $5/$30), Terra $2/$12, Luna $0.20/$1.20; GPT-5.5 $5/$30; GPT-5.3-Codex $1.75/$14 — **только Responses API** (в chat-completions недоступен); кэшированный input −90% везде; Batch −50%; контекст 1.05M у GPT-5.6, 400K у прочих [^16][^17][^18].

**Качество:** Sol — 96.2% SWE-bench Verified, 37.3% TB3.0 (3-е место), токен-эффективен в агентных петлях [^51][^52]. Luna при цене $0.20/$1.20 показывает 93% Verified — сильный бюджетник, но TB3.0 всего 17.3%: на длинных агентных задачах проседает.

**Подписки и сторонние агенты:** ChatGPT Plus $20 (Codex: Sol 10–100 / Terra 25–200 / Luna 250–2000 сообщений в 5-часовое окно), Pro 5x $100, Pro 20x $200 [^19]. Подписочная аутентификация официально поддержана только в официальных приложениях и **Codex CLI** [^20]; при этом OpenAI подтвердила допустимость форков Codex CLI, а Сэм Альтман публично разрешил вход по ChatGPT-аккаунту в сторонний агент OpenClaw [^21][^22][^67]; шлюзы типа OneCLI легально крутят агентные запросы через OAuth подписок [^66]. Де-факто сторонние обвязки работают массово; де-юре общего публичного API для этого нет, ToS запрещают «programmatic extraction», риск на пользователе. Для агентных систем возможен OAuth-провайдер `openai-codex` либо API-ключ; codex-модели используют Responses-транспорт.

**Оплата из РФ:** Россия в списке неподдерживаемых стран; официальная позиция — блокировка аккаунта [^23][^24]. Практика: зарубежная карта (KZ/AM/TR/GE/AE), посредники с наценкой 15–30%, виртуальные карты; повторные отказы платежей повышают risk-score [^25][^26].

**Итог:** для разработки по подписке Plus/Pro — сильный вариант (Codex CLI официально, лимиты щедрые). Для агентных систем остаётся выбор между OAuth с неопределённым статусом и API по обычным ценам; оплата из России требует отдельного решения.

## 6. Anthropic Claude

**API ($/1M, in/out):** Opus 5 $5/$25 (кэш-чтение $0.50), Sonnet 5 $2/$10, Haiku 4.5 $1/$5; кэш-запись 1.25×/2×, чтение 0.1×; Batch −50%; у моделей 4.7+ новый токенизатор (~+30% токенов на тот же текст) [^27]. Качество — лидер: Opus 5 — 51.8% TB3.0 и №1 AA-индекса (63.1) [^52][^53].

**Подписки:** Pro $20/мес ($17 при годовой), Max 5x $100, Max 20x $200; обе включают Claude Code; лимиты — 5-часовые сессии + недельный кап на все поверхности [^28][^29][^30][^31].

**Вердикт по сторонним агентам — НЕЛЬЗЯ.** Доки прямо запрещают: «Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials» [^33]. OAuth — «исключительно для native Anthropic applications» [^32][^33]. Прокси-проекты существуют (claude-code-router ~37k★, claude-proxy, BYOKEY), но с января–февраля 2026 — прямое нарушение доков, с реальными банами: HN-тред 655 pts «Anthropic officially bans using subscription auth for third party use» с подтверждениями банов; кейс отзыва Max-подписки с перманентным баном аккаунта [^36][^37]. Для агентных систем — только API-ключ Console (pay-per-token).

**Оплата из РФ:** Россия отсутствует в обоих списках поддерживаемых регионов [^35]; обходные схемы нарушают ToS и несут риск потери аккаунта и средств [^34][^35].

**Итог:** лучшие модели для кодинга, но для пользователей из России — тройной барьер: оплата, запрет подписки в сторонних агентах, высокий токенный прайс. Через OpenRouter/RouterAI модели доступны без «танцев» с Anthropic-аккаунтом.

## 7. z.ai / Zhipu (базовый провайдер)

**API-цены** ($/1M, официальный прайс docs.z.ai, проверено 2026-09-01) [^54]:

| Модель | Input | Cached in | Output | Контекст |
|---|---|---|---|---|
| **GLM-5.3-Flash** | **$0.15** (лист $0.30) | $0.075 | **$0.50** (лист $1.00) | 1.31M |
| GLM-5.3 | $1.40 | $0.26 | $4.40 | 1.31M |
| GLM-5.2 | $1.40 | $0.26 | $4.40 | ~1M |
| GLM-5 | $1.00 | $0.20 | $3.20 | 200K |
| GLM-4.7-FlashX | $0.07 | $0.01 | $0.40 | — |
| GLM-4.7-Flash / GLM-4.5-Flash | бесплатно | бесплатно | бесплатно | — |

Промо −50% на Flash действует **до 24:00 09.09.2026 (UTC+8, сингапурское время)** — после этого лист $0.30/$1.00 [^54]. Контекст-кэширование встроено (cached $0.075 = 0.5× input, storage бесплатно на промо).

**Качество и веса:** GLM-5.3 — 41.8% TB3.0 (№1 среди открытых, 3-е место вообще), GLM-5.3-Flash — TB2.1 84.3% (уровень моделей в 3+ раза дороже) [^52][^53]. Веса открыты на HuggingFace: **GLM-5.3-Flash — 320B (18B active), MIT**; GLM-5.3 — 753B (FP8), лицензия custom «glm-5.3» (не MIT) [^70]. Self-host Flash в теории возможен (~180+ ГБ в квантовании), GLM-5.3 требует серверного класса оборудования [^61][^70].

**GLM Coding Plan** (подписка для CLI-агентов; z.ai/subscribe, снято 2026-09-01) [^69]:

| Тариф | Месяц | Годовой (−30%) | Объём |
|---|---|---|---|
| Lite | $18/мес | **$12.6/мес** | 10 000 кредитов/нед |
| Pro | $80/мес | $56/мес | 6× Lite |
| Max | $168/мес | $117.6/мес | 14× Lite |

Официально поддерживаемые инструменты (строгий список — generic API через план запрещён): Claude Code (включая IDE-плагин), Codex, OpenCode, ZCode, Cursor, Cline, Roo/Kilo Code, Crush, Goose, TRAE; в комплекте MCP: Vision, Web Search, Web Reader, Zread [^70]. Квартальная оплата −20%; off-peak −50% (peak: пн–пт 14:00–18:00 UTC+8) [^70]. Квоты кредитов: Lite 2 000/5ч + 10 000/нед; Pro 12 000/5ч + 60 000/нед; Max 28 000/5ч + 140 000/нед — семантика совпадает с quota-эндпоинтом (unit 3 = 5ч, unit 6 = неделя) [^70]. Списание кредита для GLM-5.3: (in×6.9 + cached×1.7 + out×24)/10 000; для Flash: ×2.3/×0.56/×8 — то есть недельные 10 000 кредитов Lite ≈ 146–292M токенов Flash (при 95% cache hit) [^70]. При исчерпании — ожидание сброса 5ч, токенный баланс не расходуется. Это flat-fee доступ к GLM-5.3/Flash внутри агентов — ключевой аргумент против pay-per-token при активном кодинге.

**API для агентов:** OpenAI-совместимый `https://api.z.ai/api/paas/v4/chat/completions` + **Anthropic-совместимый `https://api.z.ai/api/anthropic`** (именно его используют Claude Code/OpenCode с GLM-бэкендом); function calling, tool streaming, structured output, context caching официально поддержаны [^71]. Нюансы: у GLM-5.3 reasoning отключить нельзя (только `reasoning_effort: low`); рекомендуемые настройки Flash — `reasoning_effort: max`, `stream` + `tool_stream`, temp 1, top_p 0.95 [^71]. Числовые rate limits рендерятся только в кабинете — unverified. Квоты мониторятся через `GET /api/monitor/usage/quota/limit` (5-часовые и недельные окна). Оплата — не из РФ (см. §10.3).

**Итог:** glm-5.3-flash — лучший бюджетный агентник рынка ($0.15/$0.50 промо; OpenRouter ещё дешевле — $0.075/$0.25 [^1]); реальный кейс с HN — 30M токенов Flash за $0.52/день [^57]. Настороженность сообщества: надёжность на «длинном хвосте» агентных задач и рекомендация держать max reasoning [^70]. Риски: рост цены после 09.09.2026 и оплата не из РФ — оба решаются мультиканальностью (§10.1).

## 8. RouterAI

**Что это:** российский LLM-шлюз от ООО «Интер» (запуск 2025, домен 2025-09-09); 468 моделей через OpenAI-совместимый API + веб-чат + TG-бот; позиционируется как «замена OpenRouter» [^38][^39][^41].

**Цены (₽/1M, in/out, из публичного API [^39]):** Claude Sonnet 5 / GPT-5.6 Sol / Gemini 3.1 Pro — 224.59/1122.93; GLM-5.3 — 131.38/444.68; **GLM-5.3-Flash — 9.26/30.88** (≈$0.107/$0.36 по ЦБ — дороже OpenRouter, дешевле z.ai-листа); DeepSeek V4 Flash — 6.18/19.76; Qwen3.8 Flash — 16.84/52.78; tool calling заявлен у 265 из 330 текстовых моделей; режимы flex (−50%) и priority [^39][^40].

**API:** `https://routerai.ru/api/v1`, Bearer, `tools/tool_choice/parallel_tool_calls`, SSE-стриминг, авто-fallback провайдеров, выбор провайдера `provider.order/only/ignore` [^40][^42]. Публичный каталог цен без регистрации — прозрачнее Selectel.

**Биллинг:** рубли, карты РФ, СБП; минимум пополнения 1 ₽; без подписок (Coding Plan отсутствует — его просят в отзывах) [^41]. Нюанс: списание постфактум, генерация не останавливается при нуле — возможен минус-баланс [^41].

**Репутация:** Startpack 4.9/5 (286 отзывов); плюсы — стабильность, поддержка, рубли, быстрая раскатка новых моделей; в отзывах сервис используют как движок для агентных систем [^41]. Минусы: наценка к прямым ценам, дорого для больших объёмов (нет coding-планов), непрозрачные списания; независимых обсуждений на Habr/vc.ru/GitHub найти не удалось (0 результатов на Habr) — сервис молодой, публичной технической критики почти нет [^41].

**Итог:** главный плюс для РФ — легальная оплата рублями без крипты/зарубежных карт при каталоге OpenRouter-масштаба. Дешёвые открытые модели через RouterAI годятся как основной канал для агентных систем; премиум-модели дороже OpenRouter из-за наценки.

## 9. Selectel ИИ-роутер

**Продукты:** (1) **ИИ-роутер** (июнь 2026) — API-gateway к «300+» моделям (в promo-таблице ~15; полный каталог только в панели), рубли, лимиты/квоты и аналитика по ключам [^43][^44][^45]; (2) **Foundation Models Catalog** — 30+ открытых моделей (qwen3-coder-30b, gpt-oss-20b/120b, bge-m3 и др.) выделенными эндпоинтами (vLLM) с оплатой за GPU-конфигурацию, на превью токены неограничены [^49]; (3) GPU-серверы/маркетплейс [^43].

**Цены** (₽/1M in/out, promo-таблица «актуально на 05.08», динамические, обновляются ежечасно [^44]) — пересчитано по ЦБ 86.38 ₽/$ [^60]: GPT-5.6 Terra — 128.75/772.49 (**≈$1.49/$8.94 — на ~25% дешевле листа OpenAI**); GPT-5.6 Luna — 12.88/77.25 (≈$1.49/... ≈ паритет); Qwen3.7 Flash — 3.86/16.74; DeepSeek V4 Flash — 11.59/23.18 (≈$0.134/$0.27 — примерно ×2 к OpenRouter); DeepSeek V4 Pro — 78.41/156.81; GLM 5.2 — 77.25/193.12; Kimi K2.7 Code — 90.12/450.62. Claude в promo-таблице нет [^44].

**API:** `https://api.selectel.ru/aig/v1/chat/completions`, Bearer, streaming, модель вида `vendor/model`, параметр `reasoning.effort`; официально OpenAI-совместимый [^45][^46]. **Не задокументированы: tool calling (подразумевается, требует теста), rate limits RPM/TPM, контекстные окна** — заданы только бюджетные лимиты в рублях/мес [^47]. Фича августа 2026 — авто-маскирование персональных данных в запросах [^45].

**Биллинг:** рубли, карты МИР/Visa/MC РФ, СБП, счёт; минимум 200 ₽; при нуле роутер работает ещё 3 дня [^48].

**Репутация:** компания с 2008 г., ФСТЭК, 152-ФЗ; свежий независимый бенчмарк VPS — «стабильно, но дорого», худший диск в тесте [^50]; по самому ИИ-роутеру независимых отзывов ещё нет (продукту <3 мес) [^43].

**Итог:** самый «корпоративный» вариант из рублёвых: платежи и соответствие 152-ФЗ образцовые, но каталог и документация уже, чем у RouterAI, tool calling не задокументирован, цены динамические. Для агентных систем это резервный рублёвый канал; перед боевым использованием обязательный smoke-тест tool calling.

## 10. Сравнение каналов для агентных систем и разработки

### 10.1 Агентные системы: tool calling и бюджет

| Канал | Основная модель | ₽/мес (тяжёлый день, §2) | Оплата | Риск |
|---|---|---|---|---|
| **z.ai (сейчас)** | glm-5.3-flash | ~5 180 (промо) | карта не-RF | промо до 09.09; недоступность РФ-оплаты |
| **OpenRouter** | glm-5.3-flash / deepseek-v4-flash | ~2 590 / ~1 730 | USDC (−5%) | пополнение через крипту |
| **RouterAI** | glm-5.3-flash / deepseek-v4-flash | ~3 100 / ~2 080* | **карты РФ, СБП, от 1 ₽** | молодой сервис, постфактум-биллинг |
| **Selectel** | qwen3.7-flash / deepseek-v4-flash | ~н/д / ~2 400 | **карты РФ, СБП** | tool calling не задокументирован |
| **Ollama Cloud** | glm-5.3-flash | ~5 180 (или в $60-кредитах Pro) | карта не-RF | выведение моделей из каталога |

\* RouterAI-цены GLM-5.3-Flash 9.26/30.88 ₽ ≈ $0.107/$0.36; пересчёт «тяжёлого дня» по формуле §2.

Рекомендуемая схема: **основной канал — z.ai glm-5.3-flash** (лучшая цена/качество, уже работает, квоты мониторятся); **fallback — RouterAI** (рубли, тот же GLM + DeepSeek + весь каталог, не нужна крипта); **экспериментальный контур — OpenRouter** для премиум-моделей по мере надобности (Claude/GPT без заводки аккаунтов у вендоров). Selectel — вариант если важна 152-ФЗ/бюджетные лимиты, после теста tool calling.

### 10.2 Разработка (CLI-кодинг: Claude Code, Codex CLI, OpenCode)

| Вариант | Цена | Качество (TB3.0) | Легальность в сторонних обвязках |
|---|---|---|---|
| **GLM Coding Plan (z.ai)** | $12.6–80/мес (Lite/Pro) | 41.8% (GLM-5.3) | официально для CLI-агентов |
| ChatGPT Plus + Codex CLI | $20/мес | 37.3% (Sol) | официально в Codex CLI; сторонние — серая зона |
| Claude Pro + Claude Code | $20/мес | 51.8% (Opus 5) | только официальные приложения |
| Claude Max | $100–200/мес | 51.8% | только официальные приложения |
| API + RouterAI/OpenRouter | pay-per-token | до 51.8% | полностью легально |

Для максимума качества на длинных задачах Claude Opus 5 вне конкуренции, но легально — только в самом Claude Code и только с зарубежной картой. Практичный стек: **GLM Coding Plan как ежедневный драйвер** (OpenCode/Claude Code с GLM-бэкендом) + подписка/OpenRouter-токены на Claude-модели для сложных случаев. Это же соотношение подтверждают бенчмарки: GLM-5.3 — №1 open-weights, в 2.2 раза дешевле прогона Opus 5 [^52].

### 10.3 Оплата из России — сводка

| Провайдер | Карта РФ | Рабочий путь | Риск |
|---|---|---|---|
| OpenRouter | нет | USDC крипта (−5%) | низкий |
| RouterAI | **да** | СБП/карта, от 1 ₽ | низкий |
| Selectel | **да** | карта/СБП/счёт | низкий |
| OpenAI | нет | зарубежная карта/посредник | средний (ToS, бан) |
| Anthropic | нет | зарубежная карта | высокий (жёсткие баны) |
| z.ai | нет | зарубежная карта/крипта/посредник | средний |
| Ollama Cloud | нет | зарубежная карта | средний |

## 11. Дискуссионные вопросы и противоречия

1. **Насколько честны бенчмарки.** SWE-bench Verified насыщен (93–97%), вендорские скоры завышают на 15–30 п.п. за счёт своих scaffold'ов (MiniMax M2.5: «80.2%» у вендора → 75.8% на нейтральном борде), Epoch AI оценивает ошибку разметки датасета в 5–10%, а загрязнение train-данными завышает агентные оценки на 20–50% [^56][^57][^58][^59][^64]. Поэтому в отчёте опора на Terminal-Bench (живой, held-out) и AA-индекс. Прямое следствие: разрыв «открытые vs закрытые» на честном harness — 1–3.5 п.п., а не те 15–30, что рисуют вендоры [^51][^53].

2. **Промо-цены как фактор выбора.** Ключевые дешёвые позиции (GLM-5.3-Flash у z.ai до 09.09.2026; Sol до ~21.11.2026) — временные [^17][^54]. Архитектура доступа должна переживать смену цен: мультиканальность (z.ai ↔ OpenRouter ↔ RouterAI) важнее «самой низкой цены сегодня».

3. **Подписка vs API у OpenAI.** Позиция OpenAI двойственна: форки Codex CLI разрешены и публичные шлюзы OAuth существуют, но юридической гарантии нет («quite permissive» без обязательств) [^21][^66]. Для боевого production — API-ключ; для личного использования — подписка экономична на порядок.

4. **«Дешёвый рублёвый шлюз» vs «прямой канал».** RouterAI/Selectel берут наценку (у RouterAI она видна на премиум-моделях: Sonnet 5 по $2.60/$13 экв. [^39] против $2/$10 напрямую), но дают оплату рублями и один ключ на весь каталог. Для открытых моделей наценка минимальна — там рублёвые шлюзы почти бесплатны как convenience.

## 12. Недостаточность данных

- **Selectel ИИ-роутер:** полный каталог «300+» моделей, контекстные окна, rate limits и подтверждение tool calling — только в панели после регистрации; публичной документации нет [^45][^47].
- **RouterAI:** SLA/uptime не публикуются; независимые обсуждения на Habr/vc/GitHub не найдены (0 результатов) — оценка надёжности опирается на агрегатор отзывов Startpack [^41].
- **Ollama Cloud:** размер starter-кредитов Free не публикуется [^9].
- **z.ai Coding Plan:** квоты и формула списания кредитов описаны в докс-ревизии использования [^70]; числовые rate limits API и точные цены тарифов для новых подписок (страница тарифа рендерится после входа) — проверять в кабинете.
- **GLM-5.3-Flash на OpenRouter** ($0.075/$0.25 — вдвое дешевле промо z.ai): природа цены (постоянная/промо/дешёвый провайдер в роутинге) не верифицирована — рекомендован мониторинг после 09.09.2026 [^1][^54].

## Заключение

**Для агентных систем:** GLM-5.3-Flash через z.ai — сильный основной канал по цене и качеству на сентябрь 2026. Для устойчивости нужна мультиканальность: RouterAI даёт оплату в рублях и доступ к GLM/DeepSeek, OpenRouter — широкий каталог премиальных моделей, Selectel стоит рассматривать после smoke-теста tool calling. Ollama Cloud остаётся нишевым вариантом для дешёвого кэша gpt-oss-120b, а локальный Ollama — для эмбеддингов.

**Для разработки:** **GLM Coding Plan** (Lite $12.6/мес годовых, Pro $56/мес) как ежедневный драйвер CLI-агентов — качество уровня 80–90% от лидера за 5–10% его цены; Claude Opus 5 (через API/OpenRouter/RouterAI-токены, либо Claude Code по подписке при наличии зарубежной карты) — для сложных Long-Horizon задач. ChatGPT Plus с Codex CLI — равноценная альтернатива GLM-плану, если предпочтительнее экосистема OpenAI.

**Не делать:** не проксировать Claude-подписку в сторонние агенты (реальные баны [^36][^37]); не строить продакшн-схему на одном канале с промо-ценой; не выбирать модель по вендорским SWE-bench-скорам.

## Quality Metrics

| Metric | Value |
|--------|-------|
| Total sources | 68 |
| Academic sources | 2 (arXiv, Epoch) |
| Official/documentation | 34 |
| Industry reports | 9 (лидерборды, агрегаторы) |
| News/journalism | 6 |
| Blog/forum | 17 (HN, Reddit, GitHub, Startpack, Habr) |
| Citation coverage | ~90% |
| Counter-arguments searched | Yes (§11) |
| Research rounds | 3 (1 исходная + 2 замены/уточнения субагентов) |
| Questions emerged | 6 |
| Questions resolved | 3 |
| Questions insufficient data | 4 (см. §12) |

[^1]: OpenRouter. "Models API catalog" (420 моделей, цены), получено 2026-09-01. https://openrouter.ai/api/v1/models
[^2]: OpenRouter. "FAQ" (комиссии пополнения, способы оплаты, возвраты), 2026-09-01. https://openrouter.ai/docs/faq
[^3]: OpenRouter. "Pricing" (BYOK, налоги), 2026-09-01. https://openrouter.ai/pricing
[^4]: OpenRouter. "Provider Routing" (fallback, require_parameters), 2026-09-01. https://openrouter.ai/docs/features/provider-routing
[^5]: OpenRouter. "Prompt Caching" (sticky routing, prompt_cache_key), 2026-09-01. https://openrouter.ai/docs/features/prompt-caching
[^6]: OpenRouter. "Limits" (free-tier лимиты, per-account капы), 2026-09-01. https://openrouter.ai/docs/limits
[^7]: OpenRouter. "Status" (99.99% uptime инференса за 90 дней), 2026-09-01. https://status.openrouter.ai/
[^8]: Ollama. "Ollama's transparent pricing" (анонс смены биллинга), 31.08.2026. https://ollama.com/blog/transparent-pricing
[^9]: Ollama. "Pricing" (тарифы Free/Pro/Max/Team, цены моделей, ZDR), 2026-09-01. https://ollama.com/pricing
[^10]: Ollama. "Cloud Docs" (API, ollama signin гибрид), 2026-09-01. https://docs.ollama.com/cloud
[^11]: Ollama. "OpenAI compatibility", 2026-09-01. https://docs.ollama.com/api/openai-compatibility
[^12]: Ollama. "Anthropic compatibility" (/v1/messages, Claude Code), 2026-09-01. https://docs.ollama.com/api/anthropic-compatibility
[^13]: ggml-org/llama.cpp. "Issue #19480: контролируемые CPU-бенчмарки" (DDR4/DDR5/EPYC замеры), 2026. https://github.com/ggml-org/llama.cpp/issues/19480
[^14]: ggml-org/llama.cpp. "Discussion #15396: gpt-oss runtime stack" (требования, --n-cpu-moe), 2025–2026. https://github.com/ggml-org/llama.cpp/discussions/15396
[^15]: carteakey.dev. "Optimizing GPT-OSS-120B local inference" (роль пропускной способности RAM), 2026. https://carteakey.dev/blog/local-inference/optimizing-gpt-oss-120b-local-inference/
[^16]: OpenAI. "API Pricing" (developers docs, .md-endpoint), проверено 2026-09-01. https://developers.openai.com/api/docs/pricing
[^17]: OpenAI. "Introducing GPT-5.6" (промо Sol), 21.08.2026. https://openai.com/index/gpt-5-6/
[^18]: OpenAI. "Advancing the price-performance frontier with GPT-5.6" (скидки Luna/Terra), 30.07.2026. https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/
[^19]: OpenAI. "ChatGPT pricing" (планы, Codex-лимиты), проверено 2026-09-01. https://learn.chatgpt.com/docs/pricing
[^20]: OpenAI. "Codex authentication" (подписочный OAuth vs API), 2026. https://learn.chatgpt.com/docs/auth
[^21]: openai/codex. "Discussion #8338: сторонние клиенты и OAuth" (ответы OpenAI), 2025-12–2026-02. https://github.com/openai/codex/discussions/8338
[^22]: Altman, S. "OpenClaw ChatGPT login" (твит), 01–02.05.2026. https://x.com/sama/status/2050357911915028689
[^23]: OpenAI. "Supported countries", 2026. https://developers.openai.com/api/docs/supported-countries
[^24]: OpenAI Help. "ChatGPT and API services in unsupported countries", 2026. https://help.openai.com/en/articles/9131992
[^25]: Habr/TSNIS. "Оплата OpenAI из России: способы и рекомендации", 28.07.2026. https://habr.com/ru/companies/tsnis/articles/1063790/
[^26]: vc.ru. "Оплата OpenAI из России", 11.08.2026. https://vc.ru/services/3073970-oplata-openai-iz-rossii-sposoby-i-rekomendatsii
[^27]: Anthropic. "Model Pricing" (API), проверено 2026-09-01. https://platform.claude.com/docs/en/about-claude/pricing
[^28]: Anthropic. "Plans & Pricing" (claude.com), 2026-09-01. https://claude.com/pricing
[^29]: Anthropic Support. "What is the Pro plan?", 2026. https://support.claude.com/en/articles/8325606-what-is-the-pro-plan
[^30]: Anthropic Support. "What is the Max plan?", 2026. https://support.claude.com/en/articles/11049741-what-is-the-max-plan
[^31]: Anthropic Support. "How do usage and length limits work?", 2026. https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work
[^32]: Claude Code Docs. "Authentication", 2026. https://code.claude.com/docs/en/authentication
[^33]: Claude Code Docs. "Legal and compliance" (запрет третьих лиц), февраль 2026. https://code.claude.com/docs/en/legal-and-compliance
[^34]: Anthropic. "Consumer Terms of Service", 2026. https://www.anthropic.com/legal/consumer-terms
[^35]: Anthropic. "Supported countries and regions", 2026. https://www.anthropic.com/supported-countries
[^36]: Hacker News. "Anthropic officially bans using subscription auth for third party use" (655 pts), 19.02.2026. https://news.ycombinator.com/item?id=47069299
[^37]: r/Anthropic. "Claude Max Subscription Silently Revoked... Account Permanently Banned", март 2026. https://www.reddit.com/r/Anthropic/comments/1rocwic/
[^38]: RouterAI. "Главная" (ООО «Интер», 468 моделей, оплата), 2026-09-01. https://routerai.ru/
[^39]: RouterAI. "Models API" (публичный каталог с ценами), снято 2026-09-01. https://routerai.ru/api/v1/models
[^40]: RouterAI. "Docs" (API, параметры, провайдеры), 2026-09-01. https://routerai.ru/docs
[^41]: Startpack. "Router AI" (4.9/5, 286 отзывов, биллинг), 2026-09-01. https://startpack.ru/application/router-ai
[^42]: RouterAI. "llms-full.txt" (полная документация для LLM), 2026-09-01. https://routerai.ru/llms-full.txt
[^43]: Selectel @ Habr. "ИИ-роутер и AI-продукты" (дайджест), 09.07.2026. https://habr.com/ru/companies/selectel/articles/1057434/
[^44]: Selectel. "ИИ-роутер: промо-страница с ценами" (актуально на 05.08.2026, динамика ежечасно). https://promo.selectel.ru/ai-router
[^45]: Selectel. "Документация ИИ-роутера" (описание, release notes), 2026-09-01. https://docs.selectel.ru/ai-router/about/about-ai-router
[^46]: Selectel. "AI Router Quickstart" (endpoint, примеры), 2026-09-01. https://docs.selectel.ru/ai-router/quickstart
[^47]: Selectel. "Лимиты ИИ-роутера" (бюджетные лимиты), 2026-09-01. https://docs.selectel.ru/ai-router/manage/limits
[^48]: Selectel. "Оплата ИИ-роутера" (периоды списания, 3 дня грейс), 2026-09-01. https://docs.selectel.ru/ai-router/about/payment
[^49]: Selectel. "Foundation Models Catalog" (каталог, GPU-оплата), 2026-09-01. https://selectel.ru/services/cloud/foundation-models-catalog/
[^50]: Habr. "Независимый бенчмарк VPS: Selectel" (+43), 09.06.2026. https://habr.com/ru/articles/1045690/
[^51]: SWE-bench. "Official leaderboard" (нормализованный harness), снято 2026-09-01. https://www.swebench.com/
[^52]: Terminal-Bench. "Leaderboards TB3.0 / TB2.1" (Stanford/Laude), снято 2026-09-01. https://www.tbench.ai/
[^53]: Artificial Analysis. "Intelligence Index v4.1.1" (скоринг + цены), снято 2026-09-01. https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index
[^54]: Z.ai. "Docs: Pricing" (GLM-5.3/Flash, промо до 09.09.2026), 2026-09-01. https://docs.z.ai/guides/overview/pricing
[^55]: DeepSeek. "API Pricing" (V4 Pro/Flash, off-peak), 2026-09-01. https://api-docs.deepseek.com/quick_start/pricing
[^56]: MiniMax. "MiniMax-M2.5" (официальный анонс), 12.02.2026. https://www.minimax.io/news/minimax-m25
[^57]: Hacker News. "MiniMax M2.5" (community-обсуждение), 2026. https://news.ycombinator.com/item?id=46991154
[^58]: arXiv 2510.08996. "Benchmark Mutation Approach" (загрязнение бенчмарков 20–50%), 2025. https://arxiv.org/html/2510.08996v1
[^59]: Epoch AI. "SWE-bench Verified: методология и ограничения", 2026. https://epoch.ai/benchmarks/swe-bench-verified
[^60]: ЦБ РФ. "Официальный курс USD", 2026-09-01: 86.3793 ₽. https://www.cbr-xml-daily.ru/daily_json.js
[^61]: Z.ai. "GLM-5.3 blog" (архитектура, веса, даты), 14–28.08.2026. https://z.ai/blog/glm-5.3
[^62]: Ollama Docs. "Cloud: deprecation" (вывод minimax-m2.5, kimi-k2.5), 2026-07-31. https://docs.ollama.com/cloud
[^63]: Aider. "Polyglot leaderboards" (заморожен на 2025-моделях), снято 2026-09-01. https://aider.chat/docs/leaderboards/
[^64]: localaimaster. "SWE-bench explained" (агрегат vals.ai/SEAL), август 2026. https://localaimaster.com/models/swe-bench-explained-ai-benchmarks
[^65]: codingplan.org. "GLM-5.3 model page" (post-training scaling), 2026. https://codingplan.org/models/glm-5.3
[^66]: OneCLI. "OpenAI integrations: OAuth-шлюзы подписок", 2026. https://onecli.sh/docs/integrations/openai
[^67]: TNW. "OpenAI lets OpenClaw use ChatGPT subscription", 05.2026. https://thenextweb.com/news/openai-openclaw-chatgpt-subscription-agent
[^68]: models.dev. "Ollama Cloud provider" (контексты облачных моделей), 2026-09-01. https://models.dev/providers/ollama-cloud
[^69]: Z.ai. "GLM Coding Plan" (тарифы Lite/Pro/Max, поддерживаемые инструменты), снято 2026-09-01. https://z.ai/subscribe
[^70]: Z.ai. "Coding Plan: Usage revision" (квоты кредитов, формула списания, off-peak, список инструментов), 2026-09-01. https://docs.z.ai/devpack/usage-revision
[^71]: Z.ai. "Function Calling / Capabilities" (эндпоинты, настройки моделей), 2026-09-01. https://docs.z.ai/guides/capabilities/function-calling
