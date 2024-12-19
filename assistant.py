import telebot
import sqlite3
import os
from g4f.client import Client

# Инициализация токена и основных параметров
TOKEN = '8007015559:AAH6S14l-G6H5lImzG3nrje1DWBLmu_o0f0'
bot = telebot.TeleBot(TOKEN)

# Идентификатор группы и тем
GROUP_ID = -1002358776209  # Замените на реальный ID вашей группы
THREADS = {
    "homework": 3,  # ID темы для домашних заданий
    "answers": 77,  # ID темы для ответов на домашние задания
    "news": 6,      # ID темы для новостей
    "chat": 34       # ID темы "Общалочка"
}

# Путь к базе данных
DB_PATH = "bot_database.db"


# --- Функции базы данных ---
def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT
        )
    ''')

    # Таблица заданий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# --- Проверка роли ---
def can_post(user, task_type):
    """Проверка роли пользователя для публикации."""
    if user[0] in ['admin', 'leader']:
        return True
    if task_type == "homework" and user[0] == "homework_writer":
        return True
    if task_type == "news" and user[0] == "news_writer":
        return True
    return False


# --- Авторизация ---
@bot.message_handler(commands=['auth'])
def auth_user(message):
    """Авторизация пользователя."""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверка пользователя в базе
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        bot.reply_to(message, f"Вы уже авторизованы как {user[2]}.")
    else:
        cursor.execute('INSERT INTO users (user_id, username, role) VALUES (?, ?, ?)',
                       (user_id, username, "student"))
        conn.commit()
        bot.reply_to(message, "Вы успешно авторизованы как студент.")
    conn.close()


@bot.message_handler(commands=['set_role'])
def set_role(message):
    """Установка роли пользователя (только администратор)."""
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "Используйте: /set_role <user_id> <role>")
            return

        user_id, role = int(args[1]), args[2]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
        if cursor.rowcount > 0:
            bot.reply_to(message, f"Роль пользователя {user_id} обновлена на {role}.")
        else:
            bot.reply_to(message, f"Пользователь {user_id} не найден.")
        conn.commit()
        conn.close()
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")


# --- Исправление текста ---
@bot.message_handler(commands=['fix_text'])
def fix_text(message):
    """Исправление текста с помощью G4F."""
    content = message.text[len('/fix_text'):].strip()
    if not content:
        bot.reply_to(message, "Добавьте текст для исправления после команды.")
        return

    try:
        client = Client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{'role': 'user', 'content': f'Исправь текст: {content}'}]
        )
        fixed_text = response.choices[0].message.content
        bot.reply_to(message, f"Исправленный текст:\n\n{fixed_text}")
    except Exception as e:
        bot.reply_to(message, f"Ошибка при исправлении текста: {e}")


# --- Обработка домашних заданий ---
@bot.message_handler(func=lambda message: message.chat.id == GROUP_ID and message.message_thread_id == THREADS['homework'])
def analyze_homework(message):
    """Анализ домашнего задания с помощью G4F."""
    content = message.text.strip() if message.text else "Текст не указан."
    photo_id = message.photo[-1].file_id if message.photo else None

    try:
        client = Client()
        task_description = content
        if photo_id:
            task_description += " (с фото, обработка текста возможна отдельно)."

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{'role': 'user', 'content': f'Опиши и реши задание: {task_description}'}]
        )
        answer = response.choices[0].message.content

        # Отправка ответа в тему "Ответы на домашние задания"
        bot.send_message(
            GROUP_ID,
            f"Ответ на домашнее задание:\n\n{answer}",
            message_thread_id=THREADS['answers']
        )
    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке задания: {e}")


# --- Вопросы через /ask ---
@bot.message_handler(commands=['ask'])
def ask_bot(message):
    """Обработка команды /ask для вызова G4F."""
    question = message.text[len('/ask'):].strip()
    if not question:
        bot.reply_to(message, "Добавьте текст вопроса после команды /ask.")
        return

    try:
        client = Client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{'role': 'user', 'content': f'Ответь на вопрос: {question}'}]
        )
        answer = response.choices[0].message.content
        bot.reply_to(message, f"Ответ на ваш вопрос:\n\n{answer}")
    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке вопроса: {e}")


# --- Просмотр списка заданий ---
@bot.message_handler(commands=['view_homework'])
def view_homework(message):
    """Просмотр списка домашних заданий."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT content, timestamp FROM tasks WHERE task_type = "homework" ORDER BY timestamp DESC')
    tasks = cursor.fetchall()
    conn.close()

    if not tasks:
        bot.reply_to(message, "Домашних заданий пока нет.")
        return

    response = "Список домашних заданий:\n\n"
    for task in tasks:
        response += f"- {task[0]} (Добавлено: {task[1]})\n"
    bot.reply_to(message, response)


# --- Список доступных команд ---
@bot.message_handler(commands=['help'])
def help_command(message):
    """Отображение списка команд в зависимости от роли пользователя."""
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверка роли пользователя
    cursor.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    role = user[0] if user else "student"
    commands = {
        "student": [
            "/help - Список доступных команд",
            "/view_homework - Просмотр списка домашних заданий",
            "/fix_text - Исправление текста",
            "/ask - Задать вопрос"
        ],
        "homework_writer": [
            "/add_homework - Добавить домашнее задание",
        ],
        "news_writer": [
            "/add_news - Добавить новость",
        ],
        "leader": [
            "/add_homework - Добавить домашнее задание",
            "/add_news - Добавить новость",
        ],
        "admin": [
            "/set_role - Управление ролями",
            "/add_homework - Добавить домашнее задание",
            "/add_news - Добавить новость",
            "/view_homework - Просмотр домашних заданий",
        ]
    }

    response = "Доступные команды:\n\n" + "\n".join(commands.get(role, []))
    bot.reply_to(message, response)


# --- Запуск бота ---
if __name__ == '__main__':
    init_db()
    bot.polling()
