# app/bot/keyboards.py — Клавиатуры Telegram-бота

## За что отвечает файл

Все кнопки в боте описаны здесь. В Telegram есть два вида клавиатур:
- **ReplyKeyboard** — кнопки под полем ввода (как обычная клавиатура телефона)
- **InlineKeyboard** — кнопки прямо под сообщением

Каждая функция возвращает готовый объект клавиатуры.

## Код с объяснениями

### Импорты

```python
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
```
Импортируем все типы кнопок и клавиатур из aiogram.

---

### Выбор роли (для новых пользователей)

```python
def role_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨‍🏫 Я тренер", callback_data="role:coach")],
            [InlineKeyboardButton(text="🏃 Я спортсмен", callback_data="role:athlete")],
        ]
    )
```
**InlineKeyboard** под приветственным сообщением. Каждая кнопка в отдельном ряду `[...]`.
- `text` — что видит пользователь
- `callback_data` — что получает бот когда нажата кнопка. Потом в handlers проверяем `F.data == "role:coach"`.

---

### Главное меню спортсмена

```python
def athlete_main_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📋 План"), KeyboardButton(text="📓 Журнал")],
        [KeyboardButton(text="💪 Самочувствие"), KeyboardButton(text="🍎 Питание")],
        [KeyboardButton(text="🔗 Strava"), KeyboardButton(text="💳 Подписка")],
    ]
    if config.WEBAPP_PUBLIC_URL.startswith("https"):
        rows.append([
            KeyboardButton(
                text="📊 Дашборд",
                web_app=WebAppInfo(url=config.WEBAPP_PUBLIC_URL),
            )
        ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
```
**ReplyKeyboard** — остаётся у пользователя под клавиатурой ввода. При нажатии «📋 План» бот получает текстовое сообщение «📋 План».

`web_app=WebAppInfo(url=...)` — специальная кнопка, открывающая наш FastAPI-дашборд прямо внутри Telegram. Доступна только при HTTPS (требование Telegram).

`resize_keyboard=True` — кнопки подстраиваются под размер экрана.

---

### Главное меню тренера

```python
def coach_main_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="👥 Спортсмены"), KeyboardButton(text="⚙️ Настройки бота")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💰 Оплаты")],
        [KeyboardButton(text="📝 Базовая программа"), KeyboardButton(text="📣 Рассылка")],
    ]
    ...
```
Аналогично, но для тренера — другие кнопки.

---

### Настройки тренера (inline)

```python
def coach_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏷 Название", callback_data="set:brand_name")],
            [InlineKeyboardButton(text="🖼 Логотип", callback_data="set:logo_url")],
            ...
            [InlineKeyboardButton(text="🔔 Вкл/выкл опросы", callback_data="set:polls_toggle")],
        ]
    )
```
Inline-кнопки под сообщением настроек. `callback_data="set:brand_name"` — при нажатии в handlers/coach.py сработает обработчик `on_set_field()`.

---

### Шкала оценок 1-10

```python
def scale_kb(prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура 1..10 — для выбора значения в опросе."""
    row1 = [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(text=str(i), callback_data=f"{prefix}:{i}") for i in range(6, 11)]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])
```
Генерируем кнопки 1-10 программно (список comprehension). `prefix` может быть `"fatigue"`, `"sleep"` или `"rpe"` — так в callback_data будет `"fatigue:7"`, `"sleep:8"` и т.д.

---

### Статус тренировки

```python
def training_status_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Выполнено", callback_data="log_status:выполнено"),
            InlineKeyboardButton(text="~ Частично", callback_data="log_status:частично"),
            InlineKeyboardButton(text="⛔ Пропущено", callback_data="log_status:пропущено"),
        ]]
    )
```
Три кнопки в одном ряду.

---

### Подтверждение (да/нет)

```python
def confirm_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"{prefix}:no"),
        ]]
    )
```
Универсальная клавиатура подтверждения. `prefix` позволяет различать для чего именно подтверждение.

## Ключевые термины

- **ReplyKeyboard** — кнопки под полем ввода текста, остаются постоянно.
- **InlineKeyboard** — кнопки под конкретным сообщением.
- **callback_data** — данные, которые бот получает при нажатии inline-кнопки (строка до 64 символов).
- **WebAppInfo** — специальная кнопка для открытия веб-приложения внутри Telegram.
- **List comprehension** — создание списка через `[выражение for i in range]`.
