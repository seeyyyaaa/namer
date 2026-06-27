"""
Telegram-бот для подбора русского имени ребёнку.
Использует aiogram 3.x и FSM для пошагового сбора данных.

Установка зависимостей:
    pip install aiogram==3.x

Запуск:
    python name_bot.py
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ──────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ──────────────────────────────────────────────

# Замените на токен вашего бота, полученный у @BotFather
import os
BOT_TOKEN = "8687678143:AAG2TfC5VD-EnHqIb8Ud91yKE_CS-bmbcqc"

# ──────────────────────────────────────────────
# БАЗА ИМЁН
# Структура: {"имя": {"ends_vowel": True/False}}
# ends_vowel = True  → имя заканчивается на гласную или мягкий знак
# ends_vowel = False → имя заканчивается на твёрдую согласную
# ──────────────────────────────────────────────

ГЛАСНЫЕ = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
ТЯЖЁЛЫЕ_СОГЛАСНЫЕ = set("дкрчДКРЧ")  # согласные, создающие «спотыкание»

NAMES_DB = {
    "male": {
        "Александр": {"ends_vowel": False},
        "Алексей":   {"ends_vowel": False},
        "Андрей":    {"ends_vowel": False},
        "Артём":     {"ends_vowel": False},
        "Арсений":   {"ends_vowel": False},
        "Владимир":  {"ends_vowel": False},
        "Григорий":  {"ends_vowel": False},
        "Даниил":    {"ends_vowel": False},
        "Денис":     {"ends_vowel": False},
        "Дмитрий":   {"ends_vowel": False},
        "Егор":      {"ends_vowel": False},
        "Илья":      {"ends_vowel": True},
        "Кирилл":    {"ends_vowel": False},
        "Максим":    {"ends_vowel": False},
        "Матвей":    {"ends_vowel": False},
        "Михаил":    {"ends_vowel": False},
        "Никита":    {"ends_vowel": True},
        "Николай":   {"ends_vowel": False},
        "Павел":     {"ends_vowel": False},
        "Сергей":    {"ends_vowel": False},
        "Тимур":     {"ends_vowel": False},
        "Фёдор":     {"ends_vowel": False},
        "Филипп":    {"ends_vowel": False},
    },
    "female": {
        "Александра": {"ends_vowel": True},
        "Алина":      {"ends_vowel": True},
        "Алиса":      {"ends_vowel": True},
        "Анастасия":  {"ends_vowel": True},
        "Анна":       {"ends_vowel": True},
        "Валерия":    {"ends_vowel": True},
        "Василиса":   {"ends_vowel": True},
        "Виктория":   {"ends_vowel": True},
        "Дарья":      {"ends_vowel": True},
        "Диана":      {"ends_vowel": True},
        "Екатерина":  {"ends_vowel": True},
        "Елена":      {"ends_vowel": True},
        "Ева":        {"ends_vowel": True},
        "Ксения":     {"ends_vowel": True},
        "Мария":      {"ends_vowel": True},
        "Милана":     {"ends_vowel": True},
        "Надежда":    {"ends_vowel": True},
        "Наталья":    {"ends_vowel": True},
        "Николь":     {"ends_vowel": False},
        "Полина":     {"ends_vowel": True},
        "Светлана":   {"ends_vowel": True},
        "София":      {"ends_vowel": True},
        "Юлия":       {"ends_vowel": True},
    },
}

# ──────────────────────────────────────────────
# FSM: СОСТОЯНИЯ
# ──────────────────────────────────────────────

class NameForm(StatesGroup):
    waiting_surname    = State()  # ожидание фамилии
    waiting_patronymic = State()  # ожидание отчества
    waiting_gender     = State()  # ожидание пола
    waiting_exclusions = State()  # ожидание имён-исключений


# ──────────────────────────────────────────────
# АЛГОРИТМ ПОДБОРА
# ──────────────────────────────────────────────

def pick_names(gender: str, patronymic: str, exclusions: list[str]) -> list[str]:
    """
    Подбирает и ранжирует имена по правилу эвфонии.

    Правило: если отчество начинается на «тяжёлую» согласную (Д, К, Р, Ч),
    имена, оканчивающиеся на гласную/мягкий знак, идут первыми —
    произношение «Илья Дмитриевич» легче, чем «Кирилл Дмитриевич».
    """
    pool = NAMES_DB.get(gender, {})

    # Нормализуем исключения: убираем лишние пробелы, приводим к Title Case
    exclusions_normalized = {e.strip().title() for e in exclusions if e.strip()}

    # Фильтрация: убираем имена-исключения
    filtered = {
        name: attrs
        for name, attrs in pool.items()
        if name not in exclusions_normalized
    }

    # Определяем, начинается ли отчество на «тяжёлую» согласную
    patronymic_first = patronymic[0] if patronymic else ""
    hard_start = patronymic_first in ТЯЖЁЛЫЕ_СОГЛАСНЫЕ

    def sort_key(item):
        name, attrs = item
        # При «тяжёлом» отчестве имена на гласную идут первыми (0), остальные — вторыми (1)
        if hard_start:
            priority = 0 if attrs["ends_vowel"] else 1
        else:
            priority = 0  # без «тяжёлого» отчества — все равнозначны
        return (priority, name)  # вторичная сортировка — алфавит

    sorted_names = [name for name, _ in sorted(filtered.items(), key=sort_key)]
    return sorted_names[:5]  # возвращаем ТОП-5


# ──────────────────────────────────────────────
# КЛАВИАТУРЫ
# ──────────────────────────────────────────────

def kb_gender() -> ReplyKeyboardMarkup:
    """Клавиатура выбора пола."""
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="👦 Мужской"),
            KeyboardButton(text="👧 Женский"),
        ]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def kb_skip() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой «Пропустить»."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустить ➡️")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ──────────────────────────────────────────────
# ХЭНДЛЕРЫ
# ──────────────────────────────────────────────

async def cmd_start(message: Message, state: FSMContext):
    """Точка входа — команда /start."""
    await state.clear()  # сбрасываем прошлое состояние, если было
    await state.set_state(NameForm.waiting_surname)
    await message.answer(
        "👋 Привет! Я помогу подобрать современное русское имя для вашего ребёнка.\n\n"
        "Шаг 1 из 4 — Введите *фамилию* ребёнка:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


async def process_surname(message: Message, state: FSMContext):
    """Сохраняем фамилию, переходим к отчеству."""
    surname = message.text.strip().title()
    if not surname:
        await message.answer("⚠️ Фамилия не может быть пустой. Попробуйте ещё раз:")
        return

    await state.update_data(surname=surname)
    await state.set_state(NameForm.waiting_patronymic)
    await message.answer(
        f"✅ Фамилия: *{surname}*\n\n"
        "Шаг 2 из 4 — Введите *отчество* ребёнка:",
        parse_mode="Markdown",
    )


async def process_patronymic(message: Message, state: FSMContext):
    """Сохраняем отчество, просим выбрать пол."""
    patronymic = message.text.strip().title()
    if not patronymic:
        await message.answer("⚠️ Отчество не может быть пустым. Попробуйте ещё раз:")
        return

    await state.update_data(patronymic=patronymic)
    await state.set_state(NameForm.waiting_gender)
    await message.answer(
        f"✅ Отчество: *{patronymic}*\n\n"
        "Шаг 3 из 4 — Выберите *пол* ребёнка:",
        parse_mode="Markdown",
        reply_markup=kb_gender(),
    )


async def process_gender(message: Message, state: FSMContext):
    """Сохраняем пол, просим ввести исключения."""
    text = message.text.strip()

    # Проверяем, что пользователь нажал именно кнопку
    if text == "👦 Мужской":
        gender = "male"
        gender_label = "👦 Мужской"
    elif text == "👧 Женский":
        gender = "female"
        gender_label = "👧 Женский"
    else:
        # Пользователь ввёл текст вместо нажатия кнопки
        await message.answer(
            "⚠️ Пожалуйста, выберите пол с помощью кнопок ниже 👇",
            reply_markup=kb_gender(),
        )
        return

    await state.update_data(gender=gender)
    await state.set_state(NameForm.waiting_exclusions)
    await message.answer(
        f"✅ Пол: *{gender_label}*\n\n"
        "Шаг 4 из 4 — Введите имена, которые хотите *исключить*, "
        "через запятую (например: `Николай, Дмитрий`).\n\n"
        "Или нажмите «Пропустить ➡️», если исключений нет.",
        parse_mode="Markdown",
        reply_markup=kb_skip(),
    )


async def process_exclusions(message: Message, state: FSMContext):
    """Получаем исключения, запускаем алгоритм и показываем результат."""
    text = message.text.strip()

    # Парсим список исключений (пустой, если пользователь нажал «Пропустить»)
    if text == "Пропустить ➡️" or not text:
        exclusions = []
    else:
        exclusions = [name.strip() for name in text.split(",") if name.strip()]

    # Извлекаем накопленные данные
    data = await state.get_data()
    surname    = data["surname"]
    patronymic = data["patronymic"]
    gender     = data["gender"]

    # Очищаем состояние — диалог завершён
    await state.clear()

    # Запускаем алгоритм подбора
    top_names = pick_names(gender, patronymic, exclusions)

    if not top_names:
        await message.answer(
            "😕 К сожалению, после применения всех исключений не осталось подходящих имён.\n"
            "Попробуйте убрать некоторые исключения. Введите /start, чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Формируем красивый вывод ТОП-5 ФИО
    lines = ["🎉 *ТОП-5 подходящих имён для вашего ребёнка:*\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, name in enumerate(top_names):
        fio = f"{surname} {name} {patronymic}"
        lines.append(f"{medals[i]} ✨ *{fio}*")

    # Поясняем логику, если применялась эвфония
    patronymic_first = patronymic[0] if patronymic else ""
    if patronymic_first in ТЯЖЁЛЫЕ_СОГЛАСНЫЕ:
        lines.append(
            "\n_💡 Имена отсортированы по принципу эвфонии: "
            "первыми идут те, которые лучше звучат вместе с этим отчеством._"
        )

    if exclusions:
        lines.append(f"\n_🚫 Исключены: {', '.join(exclusions)}_")

    lines.append("\n\nℹ️ Чтобы начать подбор заново, введите /start")

    await message.answer(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


# ──────────────────────────────────────────────
# ТОЧКА ВХОДА
# ──────────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # Регистрируем хэндлеры в строгом порядке
    dp.message.register(cmd_start,           CommandStart())
    dp.message.register(process_surname,     NameForm.waiting_surname)
    dp.message.register(process_patronymic,  NameForm.waiting_patronymic)
    dp.message.register(process_gender,      NameForm.waiting_gender)
    dp.message.register(process_exclusions,  NameForm.waiting_exclusions)

    logging.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
