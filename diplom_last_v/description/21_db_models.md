# app/db/models.py — ORM-модели (таблицы базы данных)

## Назначение файла
Описывает структуру БД в виде Python-классов. Каждый класс = таблица. Атрибут с `mapped_column` = колонка.

---

## Построчный разбор

```python
from __future__ import annotations
```
Разрешает аннотации типов с ссылками «вперёд» — `Mapped[Optional["Coach"]]` ссылается на класс `Coach`, который ещё не определён выше.

---

```python
import enum
```
Стандартная библиотека для перечислений. Нужна для класса `Role`.

---

```python
from datetime import date, datetime
```
- `date` — только дата (без времени): `2024-01-15`
- `datetime` — дата + время: `2024-01-15 10:30:00`

---

```python
from typing import Optional
```
`Optional[X]` = `X | None`. Означает что поле может быть `None`.

---

```python
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
```
Типы колонок SQLAlchemy:
- `BigInteger` — 64-битное целое (для Telegram ID, может быть > 2 млрд)
- `Boolean` — булево значение (True/False)
- `Date` — только дата
- `DateTime` — дата и время
- `Enum as SAEnum` — перечисление. Переименовываем `as SAEnum` чтобы не конфликтовать со стандартным `enum`
- `Float` — число с плавающей запятой
- `ForeignKey` — внешний ключ (ссылка на другую таблицу)
- `Integer` — 32-битное целое
- `String` — строка фиксированной длины (`VARCHAR`)
- `Text` — строка неограниченной длины (`TEXT`)
- `UniqueConstraint` — уникальное ограничение на уровне таблицы
- `func` — SQL-функции: `func.now()`, `func.count()`, `func.sum()`

---

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
```
- `Mapped[X]` — аннотация типа для колонок (новый синтаксис SQLAlchemy 2.x)
- `mapped_column(...)` — определяет колонку с параметрами
- `relationship(...)` — определяет связь между таблицами

---

```python
from app.db.database import Base
```
Базовый класс, от которого наследуются все модели.

---

```python
class Role(str, enum.Enum):
```
Класс перечисления. Двойное наследование: `str` (значения — строки) и `enum.Enum`. Строковый enum хранится в БД как строка.

---

```python
    COACH = "coach"
    ATHLETE = "athlete"
    UNKNOWN = "unknown"
```
Три возможных значения. `UNKNOWN` — пользователь только что зарегистрировался, ещё не выбрал роль.

---

```python
class User(Base):
```
Класс модели. Наследуется от `Base` — SQLAlchemy регистрирует его в `Base.metadata`.

---

```python
    __tablename__ = "users"
```
Имя таблицы в БД. Обязательный атрибут для каждой модели.

---

```python
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
```
- `Mapped[int]` — тип Python (целое число)
- `Integer` — тип в БД
- `primary_key=True` — первичный ключ (уникальный идентификатор строки)
- `autoincrement=True` — БД автоматически присваивает следующее число (1, 2, 3...)

---

```python
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
```
- `BigInteger` — 64-bit (Telegram ID может быть очень большим: до ~7 триллионов)
- `unique=True` — два пользователя не могут иметь одинаковый telegram_id
- `index=True` — создаёт индекс в БД для быстрого поиска по этому полю (иначе каждый поиск = полный перебор всей таблицы)
- `nullable=False` — нельзя создать пользователя без telegram_id

---

```python
    username: Mapped[Optional[str]] = mapped_column(String(255))
```
- `Optional[str]` — может быть `None` (у некоторых Telegram-пользователей нет юзернейма)
- `String(255)` — VARCHAR(255), максимум 255 символов

---

```python
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
```
Полное имя из Telegram. Тоже опционально.

---

```python
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, length=16),
        default=Role.UNKNOWN,
        nullable=False,
    )
```
- `SAEnum(Role, native_enum=False, length=16)` — хранить как строку, не как PostgreSQL ENUM тип. `native_enum=False` обеспечивает совместимость с SQLite.
- `default=Role.UNKNOWN` — новый пользователь получает роль UNKNOWN
- `nullable=False` — роль обязательна

---

```python
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```
- `server_default=func.now()` — **база данных** автоматически ставит текущее время при INSERT. `server_default` (не `default`) — работает на уровне SQL, надёжнее.

---

```python
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```
- `onupdate=func.now()` — автоматически обновляет время при каждом UPDATE этой строки

---

```python
    coach: Mapped[Optional["Coach"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
```
Связь «один к одному» с моделью `Coach`:
- `Optional["Coach"]` — в кавычках потому что `Coach` ещё не определён (прямая ссылка)
- `back_populates="user"` — обратная связь: у `Coach` тоже есть атрибут `user`, они связаны
- `uselist=False` — один объект, не список (один пользователь = один тренер)
- `cascade="all, delete-orphan"` — при удалении `User` автоматически удаляется и `Coach`

---

```python
    athlete: Mapped[Optional["Athlete"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    strava_token: Mapped[Optional["StravaToken"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
```
Аналогичные связи один-к-одному с `Athlete` и `StravaToken`.

---

```python
class Coach(Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
```
- `ForeignKey("users.id", ondelete="CASCADE")` — колонка ссылается на `id` таблицы `users`. При удалении строки из `users` — строка из `coaches` тоже удалится (`CASCADE`).
- `unique=True` — один пользователь не может быть двумя тренерами

---

```python
    display_name: Mapped[str] = mapped_column(String(255), default="Тренер")
```
Отображаемое имя тренера. `default` (не `server_default`) — значение устанавливается на уровне Python, до передачи в БД.

---

```python
    user: Mapped[User] = relationship(back_populates="coach")
    athletes: Mapped[list["Athlete"]] = relationship(back_populates="coach")
    config: Mapped[Optional["CoachConfig"]] = relationship(
        back_populates="coach", uselist=False, cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="coach")
```
Связи тренера:
- `user` — обратная ссылка на пользователя
- `athletes` — список спортсменов (один-ко-многим)
- `config` — настройки бота (один-к-одному)
- `payments` — список платежей

---

```python
class CoachConfig(Base):
    __tablename__ = "coach_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(
        ForeignKey("coaches.id", ondelete="CASCADE"), unique=True
    )
```
Один тренер — одна конфигурация.

---

```python
    brand_name: Mapped[str] = mapped_column(String(255), default="AI Coach")
```
Название бота тренера. По умолчанию "AI Coach".

---

```python
    base_program: Mapped[str] = mapped_column(
        Text, default="Базовая программа: 3 тренировки в неделю..."
    )
```
`Text` (не `String`) — неограниченная длина. Базовая программа может быть длинным текстом.

---

```python
    subscription_price: Mapped[int] = mapped_column(Integer, default=100000)  # 1000 руб
```
Хранится в **копейках** — целое число. 100000 копеек = 1000 рублей. Telegram Payments требует минимальные единицы валюты.

---

```python
    daily_poll_time: Mapped[str] = mapped_column(String(5), default="08:00")
```
Время опроса в формате `"HH:MM"`. `String(5)` — ровно 5 символов достаточно.

---

```python
    polls_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```
Флаг: включены ли ежедневные опросы. Тренер может выключить через настройки.

---

```python
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```
Время последнего изменения настроек.

---

```python
class Athlete(Base):
    __tablename__ = "athletes"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    coach_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("coaches.id", ondelete="SET NULL"), nullable=True, index=True
    )
```
- `Optional[int]` — может быть `None` (новый спортсмен ещё не привязан к тренеру)
- `ondelete="SET NULL"` — при удалении тренера, у его спортсменов `coach_id` становится `NULL` (не удаляем спортсменов!)
- `index=True` — частый запрос: «все спортсмены тренера X». Индекс ускоряет.

---

```python
    name: Mapped[str] = mapped_column(String(255))
    age: Mapped[Optional[int]] = mapped_column(Integer)
    sport: Mapped[Optional[str]] = mapped_column(String(64))
    level: Mapped[Optional[str]] = mapped_column(String(64))
    goal: Mapped[Optional[str]] = mapped_column(String(255))
    sessions_per_week: Mapped[Optional[int]] = mapped_column(Integer)
```
Поля анкеты спортсмена. Все `Optional` — заполняются постепенно в процессе онбординга.

---

```python
    subscription_active: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
```
Подписка. `subscription_until` — до какого числа активна. `Optional` — может быть `None` если подписки не было.

---

```python
class TrainingLog(Base):
    log_date: Mapped[date] = mapped_column(Date)
```
`Date` (без времени) — нам важна только дата тренировки, не точное время.

---

```python
    status: Mapped[str] = mapped_column(String(32))
```
`String(32)` — достаточно для «выполнено», «частично», «пропущено».

---

```python
    rpe: Mapped[int] = mapped_column(Integer, default=0)
```
RPE 0-10. `default=0` — при создании без RPE (напр. из Strava без субъективной оценки).

---

```python
    source: Mapped[str] = mapped_column(String(32), default="manual")
    external_id: Mapped[Optional[str]] = mapped_column(String(64))
```
`source` — откуда запись: `"manual"` или `"strava"`. `external_id` — ID активности в Strava API.

---

```python
class Payment(Base):
    telegram_charge_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
```
`unique=True` — один платёж не может быть записан дважды. Защита от дублирования при повторном событии от Telegram.

---

```python
class StravaToken(Base):
    expires_at: Mapped[int] = mapped_column(Integer)
```
Unix timestamp истечения access_token. Хранится как целое число секунд.

---

```python
    __table_args__ = (UniqueConstraint("user_id", name="uq_strava_tokens_user"),)
```
`__table_args__` — дополнительные ограничения на уровне таблицы. `UniqueConstraint` на `user_id` — у каждого пользователя только один Strava-токен. Аналогично `unique=True` на колонке, но здесь как именованное ограничение (можно по имени найти в схеме).
