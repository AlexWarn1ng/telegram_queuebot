import logging
import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

BOT_TOKEN = "123456789"
MAIN_ADMIN_ID = 123456789
DATA_FILE = "queue_data.json"
MAX_QUEUE_SIZE = 30

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class QueueBot:
    def __init__(self):
        self.app = Application.builder().token(BOT_TOKEN).build()
        self._init_handlers()
        self._ensure_data_file()
        self.scheduled_tasks = {}
        self.waiting_for_queue_name = False  # Флаг ожидания названия очереди

    def _ensure_data_file(self):
        if not os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'w') as f:
                json.dump({
                    "admins": [str(MAIN_ADMIN_ID)],
                    "queues": {},
                    "queue_users": {},
                    "all_users": []
                }, f, indent=2)

    def _load_data(self):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            return {"admins": [], "queues": {}, "queue_users": {}, "all_users": []}

    def _save_data(self, data):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")
            return False

    def _is_admin(self, user_id):
        data = self._load_data()
        return str(user_id) in data.get("admins", []) or user_id == MAIN_ADMIN_ID

    async def _get_username(self, user):
        return user.username or f"{user.first_name or ''} {user.last_name or ''}".strip()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.waiting_for_queue_name = False  # Сбрасываем флаг ожидания
        
        data = self._load_data()
        
        if "all_users" not in data:
            data["all_users"] = []
        if str(user.id) not in data["all_users"]:
            data["all_users"].append(str(user.id))
            self._save_data(data)
        
        buttons = [
            [InlineKeyboardButton("📋 Список очередей", callback_data="list_queues")],
            [InlineKeyboardButton("➕ Присоединиться", callback_data="show_join_menu")],
            [InlineKeyboardButton("➖ Покинуть очередь", callback_data="show_leave_menu")],
        ]
        
        if self._is_admin(user.id):
            buttons.append([InlineKeyboardButton("⚙️ Управление", callback_data="manage_queues")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        if update.message:
            await update.message.reply_text(
                f"👋 Привет, {user.first_name}! Я бот для управления очередями.",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.edit_message_text(
                f"👋 Привет, {user.first_name}! Я бот для управления очередями.",
                reply_markup=reply_markup
            )

    async def manage_queues_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        buttons = [
            [InlineKeyboardButton("📝 Создать очередь", callback_data="create_queue")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")],
        ]
        
        await query.edit_message_text(
            "⚙️ Меню управления очередями:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def create_queue_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        self.waiting_for_queue_name = True  # Устанавливаем флаг ожидания
        await query.edit_message_text("📝 Введите название новой очереди:")

    async def create_queue_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.waiting_for_queue_name:
            await update.message.reply_text("Пожалуйста, используйте команду /start")
            return
            
        self.waiting_for_queue_name = False  
        data = self._load_data()
        user = update.effective_user
        queue_name = update.message.text.strip()
        
        if not queue_name:
            await update.message.reply_text("⛔ Название не может быть пустым")
            return
        
        if queue_name in data["queues"]:
            await update.message.reply_text("⛔ Очередь с таким именем уже существует")
            return
        
        delay_minutes = random.randint(30, 90)
        open_time = datetime.now() + timedelta(minutes=delay_minutes)
        
        data["queues"][queue_name] = {
            "admin_id": user.id,
            "is_active": False,
            "created_at": str(update.message.date),
            "scheduled_open_time": open_time.isoformat()
        }
        
        if not self._save_data(data):
            await update.message.reply_text("⛔ Не удалось создать очередь")
            return
        
        await update.message.reply_text(
            f"⏳ Очередь '{queue_name}' будет открыта через {delay_minutes} минут "
            f"(в {open_time.strftime('%H:%M:%S')})"
        )
        
        for user_id in data["all_users"]:
            try:
                await self.app.bot.send_message(
                    chat_id=user_id,
                    text=f"🚀 Очередь '{queue_name}' будет скоро открыта для записи!\n"
                         f"Вы получите уведомление когда она откроется!"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
        
        self._schedule_queue_opening(queue_name, delay_minutes * 60)
        await self.start(update, context)

    def _schedule_queue_opening(self, queue_name, delay_seconds):
        async def open_queue():
            await asyncio.sleep(delay_seconds)
            
            data = self._load_data()
            if queue_name not in data["queues"]:
                return
                
            data["queues"][queue_name]["is_active"] = True
            data["queues"][queue_name]["opened_at"] = datetime.now().isoformat()
            self._save_data(data)
            
            await self._notify_queue_opened(queue_name)
            
            if queue_name in self.scheduled_tasks:
                del self.scheduled_tasks[queue_name]
        
        task = asyncio.create_task(open_queue())
        self.scheduled_tasks[queue_name] = task

    async def _notify_queue_opened(self, queue_name):
        data = self._load_data()
        if "all_users" not in data:
            return
            
        for user_id in data["all_users"]:
            try:
                await self.app.bot.send_message(
                    chat_id=user_id,
                    text=f"❗Очередь '{queue_name}' открыта для записи! ❗\n"
                         f"❗Перейдите в меню чтобы присоединиться. ❗"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

    async def show_join_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = self._load_data()
        
        active_queues = {
            name: info for name, info in data.get("queues", {}).items() 
            if info.get("is_active", False)
        }
        
        if not active_queues:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="📭 Нет доступных активных очередей"
            )
            await self.start(update, context)
            return
        
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"join_{name}")] 
            for name in active_queues
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        
        await query.edit_message_text(
            "➕ Выберите очередь для присоединения:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def join_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = self._load_data()
        user = query.from_user
        
        queue_name = query.data.split('_')[1]
        queue_info = data.get("queues", {}).get(queue_name)
        
        if not queue_info or not queue_info.get("is_active", False):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⛔ Очередь не найдена или неактивна"
            )
            await self.start(update, context)
            return
        
        queue_users = data.get("queue_users", {}).get(queue_name, [])
        
        if any(str(user.id) == u.get("user_id") for u in queue_users):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="ℹ️ Вы уже в этой очереди"
            )
            await self.start(update, context)
            return
        
        if len(queue_users) >= MAX_QUEUE_SIZE:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"⛔ Очередь заполнена (максимум {MAX_QUEUE_SIZE})"
            )
            await self.start(update, context)
            return
        
        username = await self._get_username(user)
        queue_users.append({
            "user_id": str(user.id),
            "username": username,
            "position": len(queue_users) + 1
        })
        
        data["queue_users"][queue_name] = queue_users
        
        if self._save_data(data):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Вы добавлены в очередь '{queue_name}' на позицию {len(queue_users)}"
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⛔ Ошибка при присоединении к очереди"
            )
        await self.start(update, context)

    async def show_leave_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = self._load_data()
        user = query.from_user
        
        user_queues = []
        for q_name, users in data.get("queue_users", {}).items():
            if any(str(user.id) == u.get("user_id") for u in users):
                if data.get("queues", {}).get(q_name, {}).get("is_active", False):
                    user_queues.append(q_name)
        
        if not user_queues:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="📭 Вы не состоите ни в одной очереди"
            )
            await self.start(update, context)
            return
        
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"leave_{name}")] 
            for name in user_queues
        ]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        
        await query.edit_message_text(
            "➖ Выберите очередь для выхода:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def leave_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = self._load_data()
        user = query.from_user
        
        queue_name = query.data.split('_')[1]
        queue_users = data.get("queue_users", {}).get(queue_name, [])
        
        user_index = next(
            (i for i, u in enumerate(queue_users) if u.get("user_id") == str(user.id)),
            None
        )
        
        if user_index is None:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⛔ Вы не состоите в этой очереди"
            )
            await self.start(update, context)
            return
        
        removed_position = queue_users[user_index]["position"]
        del queue_users[user_index]
        
        for u in queue_users:
            if u["position"] > removed_position:
                u["position"] -= 1
        
        data["queue_users"][queue_name] = queue_users
        
        if self._save_data(data):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Вы вышли из очереди '{queue_name}'"
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⛔ Ошибка при выходе из очереди"
            )
        await self.start(update, context)

    async def list_queues(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        data = self._load_data()
        query = update.callback_query if hasattr(update, 'callback_query') else None
        
        active_queues = {
            name: info for name, info in data.get("queues", {}).items() 
            if info.get("is_active", False)
        }
        
        if not active_queues:
            if query:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="📭 Нет активных очередей"
                )
            else:
                await update.message.reply_text("📭 Нет активных очередей")
            await self.start(update, context)
            return
        
        buttons = []
        for name, info in active_queues.items():
            count = len(data.get("queue_users", {}).get(name, []))
            buttons.append([
                InlineKeyboardButton(
                    f"📌 {name} ({count}/{MAX_QUEUE_SIZE})", 
                    callback_data=f"queue_{name}"
                )
            ])
        
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        text = "📋 Список активных очередей:"
        
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)

    async def show_queue_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = self._load_data()
        
        queue_name = query.data.split('_')[1]
        members = data.get("queue_users", {}).get(queue_name, [])
        
        message = f"👥 Очередь: {queue_name}\n\n" + \
            "\n".join(f"{m['position']}. {m['username']}" for m in members) if members else "📭 Очередь пуста"
        
        buttons = []
        if self._is_admin(query.from_user.id):
            buttons.append([
                InlineKeyboardButton("🔄 Поменять местами", callback_data=f"swap_menu_{queue_name}"),
                InlineKeyboardButton("🗑️ Удалить участника", callback_data=f"remove_menu_{queue_name}")
            ])
            buttons.append([
                InlineKeyboardButton("🔒 Закрыть очередь", callback_data=f"close_{queue_name}")
            ])
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="list_queues")])
        
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def show_swap_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        queue_name = query.data.split('_')[2]
        
        data = self._load_data()
        members = data.get("queue_users", {}).get(queue_name, [])
        
        if len(members) < 2:
            await query.answer("⚠️ Нужно минимум 2 участника для обмена")
            return
        
        buttons = [
            [InlineKeyboardButton(f"{m['position']}. {m['username']}", callback_data=f"swap_first_{queue_name}_{m['user_id']}")]
            for m in members
        ]
        buttons.append([InlineKeyboardButton("❌ Отмена", callback_data=f"queue_{queue_name}")])
        
        await query.edit_message_text(
            "Выберите первого участника для обмена:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def select_second_for_swap(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        _, _, queue_name, first_user_id = query.data.split('_', 3)
        
        data = self._load_data()
        members = data.get("queue_users", {}).get(queue_name, [])
        
        buttons = [
            [InlineKeyboardButton(f"{m['position']}. {m['username']}", callback_data=f"swap_second_{queue_name}_{first_user_id}_{m['user_id']}")]
            for m in members if m['user_id'] != first_user_id
        ]
        buttons.append([InlineKeyboardButton("❌ Отмена", callback_data=f"queue_{queue_name}")])
        
        await query.edit_message_text(
            "Выберите второго участника для обмена:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def process_swap(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        _, _, queue_name, first_user_id, second_user_id = query.data.split('_', 4)
        
        data = self._load_data()
        queue_users = data.get("queue_users", {}).get(queue_name, [])
        
        first_pos = next(u['position'] for u in queue_users if u['user_id'] == first_user_id)
        second_pos = next(u['position'] for u in queue_users if u['user_id'] == second_user_id)
        
        for user in queue_users:
            if user['user_id'] == first_user_id:
                user['position'] = second_pos
            elif user['user_id'] == second_user_id:
                user['position'] = first_pos
        
        data["queue_users"][queue_name] = sorted(queue_users, key=lambda x: x['position'])
        self._save_data(data)
        
        await query.edit_message_text(
            f"✅ Позиции {first_pos} и {second_pos} успешно поменяны местами"
        )
        await self.show_queue_details(update, context)

    async def show_remove_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        queue_name = query.data.split('_')[2]
        
        data = self._load_data()
        members = data.get("queue_users", {}).get(queue_name, [])
        
        buttons = [
            [InlineKeyboardButton(f"{m['position']}. {m['username']}", callback_data=f"remove_user_{queue_name}_{m['user_id']}")]
            for m in members
        ]
        buttons.append([InlineKeyboardButton("❌ Отмена", callback_data=f"queue_{queue_name}")])
        
        await query.edit_message_text(
            "Выберите участника для удаления:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    async def process_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        _, _, queue_name, user_id = query.data.split('_', 3)
        
        data = self._load_data()
        queue_users = data.get("queue_users", {}).get(queue_name, [])
        
        removed_user = next((u for u in queue_users if u['user_id'] == user_id), None)
        if not removed_user:
            await query.answer("⛔ Участник не найден")
            return
        
        removed_position = removed_user['position']
        queue_users = [u for u in queue_users if u['user_id'] != user_id]
        
        for u in queue_users:
            if u['position'] > removed_position:
                u['position'] -= 1
        
        data["queue_users"][queue_name] = queue_users
        self._save_data(data)
        
        await query.edit_message_text(
            f"✅ Участник на позиции {removed_position} удален из очереди"
        )
        await self.show_queue_details(update, context)

    async def close_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        queue_name = query.data.split('_')[1]
        data = self._load_data()
        
        if queue_name in data["queues"]:
            data["queues"][queue_name]["is_active"] = False
            self._save_data(data)
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Очередь '{queue_name}' закрыта"
            )
            await self.start(update, context)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "list_queues":
            await self.list_queues(update, context)
        elif data == "show_join_menu":
            await self.show_join_menu(update, context)
        elif data == "show_leave_menu":
            await self.show_leave_menu(update, context)
        elif data == "manage_queues":
            await self.manage_queues_menu(update, context)
        elif data.startswith("join_"):
            await self.join_queue(update, context)
        elif data.startswith("leave_"):
            await self.leave_queue(update, context)
        elif data.startswith("queue_"):
            await self.show_queue_details(update, context)
        elif data.startswith("swap_menu_"):
            await self.show_swap_menu(update, context)
        elif data.startswith("swap_first_"):
            await self.select_second_for_swap(update, context)
        elif data.startswith("swap_second_"):
            await self.process_swap(update, context)
        elif data.startswith("remove_menu_"):
            await self.show_remove_menu(update, context)
        elif data.startswith("remove_user_"):
            await self.process_remove(update, context)
        elif data == "create_queue":
            await self.create_queue_input(update, context)
        elif data == "back_to_main":
            await self.start(update, context)
        elif data.startswith("close_"):
            await self.close_queue(update, context)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error("Ошибка:", exc_info=context.error)
        if update.callback_query:
            await update.callback_query.answer("⛔ Произошла ошибка")
        await self.start(update, context)

    def _init_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("list_queues", self.list_queues))
        self.app.add_handler(CommandHandler("join_queue", self.show_join_menu))
        self.app.add_handler(CommandHandler("leave_queue", self.show_leave_menu))
        
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.create_queue_process
        ))
        
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        
        self.app.add_error_handler(self.error_handler)

    def run(self):
        logger.info("Бот запускается...")
        self.app.run_polling()

if __name__ == '__main__':
    bot = QueueBot()
    bot.run()
