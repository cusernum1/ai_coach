# app/bot/handlers/payments.py — Оплата подписки

## За что отвечает файл

Реализует полный цикл оплаты через **Telegram Payments**:
1. `/subscribe` → бот отправляет «инвойс» (счёт на оплату)
2. Telegram показывает форму оплаты, пользователь вводит карту
3. Telegram присылает `PreCheckoutQuery` — бот должен подтвердить за 10 секунд
4. После оплаты приходит `SuccessfulPayment` — активируем подписку

## Код с объяснениями

### Запуск оплаты

```python
@router.message(Command("subscribe"))
@router.message(F.text == "💳 Подписка")
async def cmd_subscribe(message: Message, user: User | None, bot: Bot) -> None:
    if not user or user.role != Role.ATHLETE:
        await message.answer("Только для спортсменов.")
        return
    
    async with get_session() as s:
        coach = await get_default_coach(s)
        cfg = await get_coach_config(s, coach.id) if coach else None

    if cfg is None or not config.PAYMENTS_PROVIDER_TOKEN:
        await message.answer("⚠️ Оплата временно недоступна...")
        return
```
Проверяем: есть ли тренер, его настройки, и настроен ли провайдер платежей. Если что-то не так — предупреждаем, не пытаемся отправить инвойс.

```python
    try:
        await send_subscription_invoice(
            bot,
            chat_id=message.chat.id,
            title=cfg.subscription_title,
            description=cfg.subscription_description,
            amount_minor=cfg.subscription_price,
            payload=f"sub:{user.id}:{coach.id}",
        )
    except Exception as e:
        await message.answer(f"Не удалось отправить инвойс: {e}")
```
`payload=f"sub:{user.id}:{coach.id}"` — произвольная строка, которую Telegram вернёт нам при успешной оплате. Кодируем в неё `user_id` и `coach_id` чтобы потом знать кому активировать подписку.

---

### PreCheckoutQuery — подтверждение

```python
@router.pre_checkout_query()
async def on_pre_checkout(pcq: PreCheckoutQuery) -> None:
    ok = pcq.invoice_payload.startswith("sub:") and pcq.total_amount > 0
    await pcq.answer(ok=ok, error_message="Оплата не прошла валидацию" if not ok else None)
```
Telegram обязательно ждёт ответа в течение **10 секунд**. Мы проверяем:
- payload начинается с `"sub:"` — это наш инвойс, не чужой
- сумма больше нуля

`ok=True` → Telegram разрешает провести платёж. `ok=False` — отменяет.

---

### SuccessfulPayment — успешная оплата

```python
@router.message(F.successful_payment)
async def on_successful_payment(message: Message, user: User) -> None:
    sp = message.successful_payment
    if sp is None or user is None:
        return
    
    try:
        _, user_id_str, coach_id_str = sp.invoice_payload.split(":", 2)
        uid = int(user_id_str)
        cid = int(coach_id_str)
    except ValueError:
        uid, cid = user.id, None
```
Распаковываем payload: `"sub:42:1"` → `uid=42`, `cid=1`.

`split(":", 2)` — делим максимум на 3 части: `["sub", "42", "1"]`.

```python
    async with get_session() as s:
        await record_payment(
            s,
            user_id=uid, coach_id=cid,
            amount=sp.total_amount,
            currency=sp.currency,
            title=sp.order_info.name if sp.order_info else "Подписка",
            telegram_charge_id=sp.telegram_payment_charge_id,
            provider_charge_id=sp.provider_payment_charge_id,
        )
        await activate_subscription(s, uid, days=30)

    await message.answer(
        f"✅ Оплата принята: {money(sp.total_amount, sp.currency)}.\n"
        f"Подписка активна на 30 дней. Спасибо!",
        reply_markup=athlete_main_kb(),
    )
```
- `record_payment()` — записываем в таблицу `payments`
- `activate_subscription()` — ставим `subscription_active=True` и `subscription_until = сейчас + 30 дней`
- `telegram_payment_charge_id` — уникальный ID от Telegram (для проверки дубликатов)

## Схема Telegram Payments

```
Пользователь: /subscribe
    ↓
send_invoice() → Telegram показывает форму с ценой
    ↓
Пользователь вводит карту и нажимает "Оплатить"
    ↓
PreCheckoutQuery → бот: ok=True (подтверждаем за 10 сек)
    ↓
Telegram проводит платёж через провайдера (ЮKassa/Stripe)
    ↓
SuccessfulPayment → record_payment() + activate_subscription()
    ↓
"✅ Оплата принята. Подписка на 30 дней!"
```

## Ключевые термины

- **Telegram Payments** — встроенная платёжная система Telegram
- **PreCheckoutQuery** — предзапрос перед оплатой, требует подтверждения в 10 сек
- **SuccessfulPayment** — финальное уведомление об успешном платеже
- **payload** — произвольная строка которую мы передаём при создании инвойса и получаем обратно при оплате
- **provider_token** — токен платёжного провайдера от @BotFather
