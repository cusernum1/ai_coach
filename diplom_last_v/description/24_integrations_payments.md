# app/integrations/payments.py — Отправка инвойса Telegram Payments

## За что отвечает файл

Один файл, одна функция. Инкапсулирует вызов `bot.send_invoice()` — отправку счёта на оплату пользователю. Вынесена из handlers в отдельный модуль чтобы handler не знал деталей API оплаты.

## Код с объяснениями

```python
from aiogram import Bot
from aiogram.types import LabeledPrice
```
`LabeledPrice` — специальный объект Telegram для цены: `{"label": "Подписка", "amount": 99900}`.

---

```python
async def send_subscription_invoice(
    bot: Bot,
    *,
    chat_id: int,
    title: str,
    description: str,
    amount_minor: int,
    payload: str,
) -> None:
```
`*` после `bot` — все последующие параметры обязательно именованные (keyword-only). Нельзя вызвать `send_subscription_invoice(bot, 123, "title", ...)` — только `send_subscription_invoice(bot, chat_id=123, ...)`. Защита от ошибок.

```python
    if not config.PAYMENTS_PROVIDER_TOKEN:
        raise RuntimeError(
            "PAYMENTS_PROVIDER_TOKEN не задан в .env — "
            "получите его у @BotFather → Payments → провайдер."
        )
```
Fail-fast: без токена провайдера инвойс не отправить. Падаем с понятным сообщением.

```python
    await bot.send_invoice(
        chat_id=chat_id,
        title=title[:32] or "Подписка",
        description=description[:255] or "Подписка на услуги тренера",
        payload=payload,
        provider_token=config.PAYMENTS_PROVIDER_TOKEN,
        currency=config.PAYMENTS_CURRENCY,
        prices=[LabeledPrice(label=title[:32] or "Подписка", amount=amount_minor)],
        need_email=False,
        need_name=False,
        need_phone_number=False,
        is_flexible=False,
        start_parameter="subscribe",
    )
```
Параметры `bot.send_invoice()`:
- `title[:32]` — Telegram ограничивает название 32 символами
- `description[:255]` — описание до 255 символов
- `payload` — вернётся в `SuccessfulPayment` (кодируем туда `user_id:coach_id`)
- `provider_token` — токен платёжного провайдера
- `currency` — `"RUB"` или `"USD"`
- `prices` — список позиций (у нас одна — подписка)
- `need_email/name/phone` — не запрашиваем лишние данные у пользователя
- `is_flexible=False` — фиксированная цена (не меняется в зависимости от shipping)

## Зачем отдельный файл

Handler (`handlers/payments.py`) должен знать **что** делать (отправить инвойс), но не **как** (какие параметры передать в API Telegram). Это принцип **разделения ответственностей**. Если Telegram изменит API — меняем только этот файл.
