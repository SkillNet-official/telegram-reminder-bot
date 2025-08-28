"""
Telegram Reminder Bot - Бот для напоминаний
Автор: Wlad

Установка зависимостей:
pip install python-telegram-bot apscheduler pytz

Использование:
1. Создайте бота через @BotFather
2. Замените BOT_TOKEN на ваш токен
3. Запустите: python telegram-reminder-bot.py
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import json
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import pytz

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота 
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

class ReminderBot:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.reminders: Dict[str, Dict] = {}
        self.user_timezones: Dict[int, str] = {}
        self.data_file = "reminders.json"
        self.load_data()
        
    def load_data(self):
        """Загрузка сохраненных напоминаний из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.reminders = data.get('reminders', {})
                    self.user_timezones = {int(k): v for k, v in data.get('user_timezones', {}).items()}
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            
    def save_data(self):
        """Сохранение напоминаний в файл"""
        try:
            data = {
                'reminders': self.reminders,
                'user_timezones': {str(k): v for k, v in self.user_timezones.items()}
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")

# Создаем экземпляр бота
bot = ReminderBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = """
🤖 **Бот-напоминалка**

Я помогу вам не забывать важные дела!

**Команды:**
/add - Добавить новое напоминание
/list - Показать все активные напоминания
/delete - Удалить напоминание
/timezone - Установить часовой пояс
/help - Показать эту справку

**Формат добавления напоминания:**
`Дата: 2025-08-29`
`Время: 14:30`
`Текст: Встреча с клиентом`

Я буду напоминать за 1 час и за 30 минут до события! ⏰
    """
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await start(update, context)

async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /add для добавления напоминания"""
    message = """
📅 **Добавление напоминания**

Пожалуйста, отправьте информацию в следующем формате:

```
Дата: ГГГГ-ММ-ДД
Время: ЧЧ:ММ
Текст: Описание напоминания
```

**Пример:**
```
Дата: 2025-08-29
Время: 14:30
Текст: Встреча с врачом
```

Я создам напоминания за 1 час и за 30 минут до события!
    """
    await update.message.reply_text(message, parse_mode='Markdown')

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /list для показа всех напоминаний"""
    user_id = update.effective_user.id
    user_reminders = {k: v for k, v in bot.reminders.items() if v['user_id'] == user_id}
    
    if not user_reminders:
        await update.message.reply_text("📝 У вас пока нет активных напоминаний.")
        return
    
    message = "📋 **Ваши активные напоминания:**\n\n"
    
    for reminder_id, reminder in user_reminders.items():
        dt_str = reminder['datetime_str']
        text = reminder['text']
        message += f"🔹 **{dt_str}** - {text}\n"
        message += f"   ID: `{reminder_id[:8]}...`\n\n"
    
    # Создаем инлайн клавиатуру для удаления
    keyboard = []
    for reminder_id, reminder in list(user_reminders.items())[:10]:  # Ограничиваем 10 напоминаниями
        button_text = f"❌ {reminder['datetime_str'][:16]}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"delete_{reminder_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

async def delete_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку удаления напоминания"""
    query = update.callback_query
    await query.answer()
    
    reminder_id = query.data.replace("delete_", "")
    
    if reminder_id in bot.reminders:
        reminder = bot.reminders[reminder_id]
        # Удаляем задачи из планировщика
        try:
            bot.scheduler.remove_job(f"{reminder_id}_1h")
            bot.scheduler.remove_job(f"{reminder_id}_30m")
        except:
            pass
        
        # Удаляем из словаря
        del bot.reminders[reminder_id]
        bot.save_data()
        
        await query.edit_message_text(f"✅ Напоминание удалено: {reminder['text']}")
    else:
        await query.edit_message_text("❌ Напоминание не найдено.")

async def set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /timezone"""
    message = """
🌍 **Установка часового пояса**

Отправьте ваш часовой пояс в формате:
`Timezone: Europe/Moscow`

**Популярные часовые пояса:**
• `Europe/Moscow` - Москва
• `Europe/Kiev` - Киев
• `Asia/Almaty` - Алматы
• `Asia/Tashkent` - Ташкент
• `UTC` - Всемирное время

Текущий часовой пояс: `{}`
    """.format(bot.user_timezones.get(update.effective_user.id, 'UTC'))
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text
    user_id = update.effective_user.id
    
    try:
        # Проверяем, это ли установка часового пояса
        if text.startswith("Timezone:"):
            timezone_str = text.replace("Timezone:", "").strip()
            try:
                # Проверяем валидность часового пояса
                pytz.timezone(timezone_str)
                bot.user_timezones[user_id] = timezone_str
                bot.save_data()
                await update.message.reply_text(f"✅ Часовой пояс установлен: {timezone_str}")
                return
            except:
                await update.message.reply_text("❌ Неверный формат часового пояса!")
                return
        
        # Парсинг напоминания
        lines = text.strip().split('\n')
        if len(lines) < 3:
            await update.message.reply_text("❌ Неверный формат! Используйте /add для примера.")
            return
        
        date_str = None
        time_str = None
        reminder_text = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("Дата:"):
                date_str = line.replace("Дата:", "").strip()
            elif line.startswith("Время:"):
                time_str = line.replace("Время:", "").strip()
            elif line.startswith("Текст:"):
                reminder_text = line.replace("Текст:", "").strip()
        
        if not all([date_str, time_str, reminder_text]):
            await update.message.reply_text("❌ Не все поля заполнены! Проверьте формат.")
            return
        
        # Создаем datetime объект
        user_tz = pytz.timezone(bot.user_timezones.get(user_id, 'UTC'))
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        dt = user_tz.localize(dt)
        
        # Проверяем, что дата в будущем
        if dt <= datetime.now(user_tz):
            await update.message.reply_text("❌ Время напоминания должно быть в будущем!")
            return
        
        # Создаем уникальный ID
        reminder_id = f"{user_id}_{int(dt.timestamp())}"
        
        # Создаем напоминание
        reminder_data = {
            'user_id': user_id,
            'chat_id': update.effective_chat.id,
            'datetime': dt.isoformat(),
            'datetime_str': dt.strftime("%Y-%m-%d %H:%M"),
            'text': reminder_text,
            'timezone': user_tz.zone
        }
        
        bot.reminders[reminder_id] = reminder_data
        
        # Планируем напоминания
        await schedule_reminders(reminder_id, dt, reminder_text, update.effective_chat.id)
        
        bot.save_data()
        
        await update.message.reply_text(
            f"✅ **Напоминание создано!**\n\n"
            f"📅 **Дата:** {date_str}\n"
            f"⏰ **Время:** {time_str}\n"
            f"📝 **Текст:** {reminder_text}\n\n"
            f"Я напомню вам за 1 час и за 30 минут до события!",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты или времени! Используйте ГГГГ-ММ-ДД и ЧЧ:ММ")
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании напоминания.")

async def schedule_reminders(reminder_id: str, target_datetime: datetime, text: str, chat_id: int):
    """Планирование напоминаний за 1 час и 30 минут"""
    # Напоминание за 1 час
    remind_1h = target_datetime - timedelta(hours=1)
    if remind_1h > datetime.now(target_datetime.tzinfo):
        bot.scheduler.add_job(
            send_reminder,
            DateTrigger(run_date=remind_1h),
            args=[chat_id, f"⏰ **Напоминание через 1 час!**\n\n📝 {text}"],
            id=f"{reminder_id}_1h"
        )
    
    # Напоминание за 30 минут
    remind_30m = target_datetime - timedelta(minutes=30)
    if remind_30m > datetime.now(target_datetime.tzinfo):
        bot.scheduler.add_job(
            send_reminder,
            DateTrigger(run_date=remind_30m),
            args=[chat_id, f"🚨 **Напоминание через 30 минут!**\n\n📝 {text}"],
            id=f"{reminder_id}_30m"
        )

async def send_reminder(chat_id: int, message: str):
    """Отправка напоминания пользователю"""
    try:
        # Получаем текущее приложение из контекста
        from telegram.ext._application import Application
        app = Application.builder().token(BOT_TOKEN).build()
        async with app:
            await app.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")

async def restore_scheduled_jobs():
    """Восстановление запланированных задач после перезапуска"""
    current_time = datetime.now(pytz.UTC)
    
    for reminder_id, reminder in list(bot.reminders.items()):
        try:
            target_dt = datetime.fromisoformat(reminder['datetime'])
            
            # Если время уже прошло, удаляем напоминание
            if target_dt <= current_time:
                del bot.reminders[reminder_id]
                continue
            
            # Восстанавливаем задачи напоминаний
            await schedule_reminders(
                reminder_id, 
                target_dt, 
                reminder['text'], 
                reminder['chat_id']
            )
        except Exception as e:
            logger.error(f"Ошибка восстановления задачи {reminder_id}: {e}")
    
    bot.save_data()

def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_reminder))
    app.add_handler(CommandHandler("list", list_reminders))
    app.add_handler(CommandHandler("timezone", set_timezone))
    
    # Обработчик inline кнопок
    app.add_handler(CallbackQueryHandler(delete_reminder_callback))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем планировщик
    bot.scheduler.start()
    
    # Создаем задачу для восстановления напоминаний
    async def startup():
        await restore_scheduled_jobs()
    
    # Запускаем бота
    print("🤖 Бот запущен!")
    print("📝 Для остановки нажмите Ctrl+C")
    
    # Восстанавливаем задачи при запуске
    asyncio.create_task(startup())
    
    app.run_polling()

if __name__ == '__main__':
    main()
