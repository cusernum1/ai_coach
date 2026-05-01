# app/bot/handlers/agent_chat.py — Свободный диалог с ИИ

## За что отвечает файл

Это «catch-all» обработчик — ловит **любое текстовое сообщение**, которое не попало ни в один другой handler. Именно он отвечает за диалог спортсмена с ИИ-тренером.

Поэтому в `handlers/__init__.py` он регистрируется **последним**.

## Код с объяснениями

### In-memory история диалогов

```python
_HISTORY: Dict[int, Deque[dict]] = defaultdict(lambda: deque(maxlen=config.CHAT_MEMORY_SIZE * 2))
```
Словарь для хранения истории чатов: `chat_id → очередь сообщений`.

- `Dict[int, Deque[dict]]` — тип: словарь от int (chat_id) к очереди словарей
- `defaultdict(lambda: deque(...))` — автоматически создаёт новую очередь для нового chat_id
- `deque(maxlen=...)` — очередь с ограниченным размером. При добавлении нового элемента когда очередь полна — старый **автоматически удаляется**
- `CHAT_MEMORY_SIZE * 2` — храним N пар user+assistant сообщений (6 × 2 = 12 элементов)

Это **оперативная память диалога**. При перезапуске бота история теряется.

---

### Обработчик любого текста

```python
@router.message()
async def on_free_text(message: Message, user: User | None) -> None:
```
`@router.message()` без фильтров — срабатывает на **всё**. Но поскольку зарегистрирован последним — до него доходят только сообщения, которые не обработали другие handlers.

```python
    if not message.text:
        return
```
Игнорируем нетекстовые сообщения (фото, стикеры, голосовые).

```python
    if user is None:
        await message.answer("Сначала /start.")
        return

    if user.role != Role.ATHLETE or user.athlete is None or not user.athlete.sport:
        await message.answer("Сначала заполни анкету (/start) — и задавай вопросы.")
        return
```
Агент доступен только спортсменам с заполненной анкетой (нужен вид спорта для контекста).

---

### Получение настроек тренера

```python
    athlete = user.athlete
    async with get_session() as s:
        brand, base_program = await get_coach_brand(s, athlete.coach_id)
```
Вместо того чтобы вручную проверять `coach_id` и `cfg` — делегируем это в вспомогательную функцию `get_coach_brand()` из `repo.py`.

- `get_coach_brand(session, coach_id)` — возвращает кортеж `(brand_name, base_program)`
- Если тренер не найден или `coach_id = None` → возвращает дефолт `("AI Coach", None)`
- Это убирает дублирование кода: одна функция вместо трёх if-проверок в каждом handler

`brand` и `base_program` потом встраиваются в system-prompt LLM.

---

### Индикатор «думаю»

```python
    thinking = await message.answer("💭 думаю…")
```
Сначала отправляем заглушку — пользователь сразу видит что бот обрабатывает запрос (LLM может отвечать 2-5 секунд).

---

### История диалога

```python
    history = list(_HISTORY[message.chat.id])
    history.append({"role": "user", "content": text})
```
Берём накопленную историю и добавляем текущее сообщение. Передаём в `run_agent()` как контекст.

---

### Вызов агента

```python
    response = await run_agent(
        text,
        athlete={
            "name": athlete.name,
            "age": athlete.age,
            "sport": athlete.sport,
            "level": athlete.level,
            "goal": athlete.goal,
            "sessions_per_week": athlete.sessions_per_week,
        },
        chat_history=history,
        brand_name=brand,
        base_program=base_program,
    )
```
Передаём: текст вопроса, профиль спортсмена, историю чата, имя бренда, базовую программу.

---

### Сохранение истории

```python
    _HISTORY[message.chat.id].append({"role": "user", "content": text})
    _HISTORY[message.chat.id].append({"role": "assistant", "content": response})
```
Добавляем в историю и вопрос, и ответ (для контекста следующего сообщения).

---

### Удаление заглушки и отправка ответа

```python
    try:
        await thinking.delete()
    except Exception:
        pass

    for part in chunk_text(response):
        await message.answer(part)
```
Удаляем «💭 думаю…». `try/except` — на случай если сообщение уже удалено или прошло время.

Разбиваем ответ на куски (может быть длинным) и отправляем по частям.

## Ключевые концепции

- **catch-all handler** — ловит всё что не поймали раньше. Регистрируется последним!
- **`defaultdict`** — словарь, автоматически создающий значение по умолчанию для нового ключа
- **`deque(maxlen=N)`** — очередь с ограниченным размером, старые элементы выбрасываются автоматически
- **In-memory history** — история в оперативной памяти (не в БД), теряется при перезапуске
- **«💭 думаю…»** — UX-паттерн для долгих операций
