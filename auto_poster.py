"""
PROAUTO BOT v5.1 - ИСПРАВЛЕННАЯ ВЕРСИЯ
"""

import re
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
import logging

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID', '0'))
MANAGER_LINK = os.getenv('MANAGER_LINK')
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME')
PRICE_ADD = int(os.getenv('PRICE_ADD', 40000))
SOURCE_CHANNELS = [ch.strip() for ch in os.getenv('SOURCE_CHANNELS', 'M_Supercars,autohaykofficial,FRIEND_AUTO1').split(',')]
MODERATION_GROUP_ID = int(os.getenv('MODERATION_GROUP_ID', '0'))

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PROCESSED_FILE = 'processed_posts.json'
SEARCH_HISTORY_FILE = 'search_history.json'
CHAT_INFO_CACHE = 'chat_cache.json'

# ════════════════════════════════════════════════════════════════════
# БД ФУНКЦИИ
# ════════════════════════════════════════════════════════════════════

def load_processed():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_processed(msg_id):
    processed = load_processed()
    processed[str(msg_id)] = datetime.now().isoformat()
    try:
        with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
            json.dump(processed, f, ensure_ascii=False)
    except:
        pass

def is_already_processed(msg_id):
    return str(msg_id) in load_processed()

def load_search_history():
    if os.path.exists(SEARCH_HISTORY_FILE):
        try:
            with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_search_result(message_key: str, result_data: dict):
    history = load_search_history()
    history[message_key] = {
        'source_chat_id': result_data.get('source_chat_id'),
        'source_message_id': result_data.get('source_message_id'),
        'source_chat_username': result_data.get('source_chat_username'),
        'source_chat_title': result_data.get('source_chat_title'),
        'original_link': result_data.get('original_link'),
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(SEARCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except:
        pass

def get_search_result(message_key: str):
    history = load_search_history()
    return history.get(message_key, None)

def load_chat_cache():
    if os.path.exists(CHAT_INFO_CACHE):
        try:
            with open(CHAT_INFO_CACHE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_chat_info(chat_id: int, chat_info: dict):
    cache = load_chat_cache()
    cache[str(chat_id)] = {
        'username': chat_info.get('username'),
        'title': chat_info.get('title'),
        'is_private': chat_info.get('is_private'),
        'timestamp': datetime.now().isoformat()
    }
    try:
        with open(CHAT_INFO_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except:
        pass

# ════════════════════════════════════════════════════════════════════
# ИСТОЧНИК
# ════════════════════════════════════════════════════════════════════

def extract_forward_source(message):
    source_info = {
        'is_forwarded': False,
        'source_chat_id': None,
        'source_message_id': None,
        'source_chat_username': None,
        'source_chat_title': None,
        'is_private_chat': False,
    }
    
    if not message.forward_from_chat:
        return source_info
    
    source_info['is_forwarded'] = True
    source_info['source_chat_id'] = message.forward_from_chat.id
    source_info['source_message_id'] = message.forward_from_message_id
    source_info['source_chat_username'] = message.forward_from_chat.username
    source_info['source_chat_title'] = message.forward_from_chat.title
    source_info['is_private_chat'] = str(message.forward_from_chat.id).startswith('-100')
    
    return source_info

def generate_original_link(source_info: dict) -> str:
    if not source_info['is_forwarded']:
        return None
    
    message_id = source_info['source_message_id']
    chat_id = source_info['source_chat_id']
    username = source_info['source_chat_username']
    
    try:
        if username:
            link = f"https://t.me/{username}/{message_id}"
            logger.info(f"✅ Ссылка: {link}")
            return link
        
        if str(chat_id).startswith('-100'):
            chat_id_for_link = str(chat_id)[4:]
        else:
            chat_id_for_link = str(abs(chat_id))
        
        link = f"https://t.me/c/{chat_id_for_link}/{message_id}"
        logger.info(f"✅ Ссылка: {link}")
        return link
    
    except Exception as e:
        logger.error(f"❌ Ошибка ссылки: {e}")
        return None

# ════════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ И ОБРАБОТКА
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text: str, has_photo: bool) -> tuple:
    """УПРОЩЁННАЯ ПРОВЕРКА - НЕ ТРЕБУЕТ ПОЛНЫЙ ТЕКСТ"""
    
    if not has_photo:
        return False, "нет фото"
    
    # Если нет текста (только форвард фото) - ПРИНИМАЕМ
    if not text or text == "...":
        return True, "OK (форвард)"
    
    text_lower = text.lower()
    
    # Любое из этих слов - уже достаточно
    keywords = [
        r'цена',
        r'стоимость', 
        r'BMW|Mercedes|Audi|Toyota|Ford|Kia|Mazda|Honda',
        r'авто',
        r'машин',
        r'автомобиль',
        r'₽|€',
    ]
    
    has_keyword = any(re.search(k, text_lower, re.IGNORECASE) for k in keywords)
    
    if has_photo and has_keyword:
        return True, "OK"
    
    if has_photo:
        return True, "OK (фото)"
    
    return False, "нет фото"

def extract_price(text: str):
    """ИЗВЛЕЧЕНИЕ ЦЕНЫ - С РЕЗЕРВНЫМИ ВАРИАНТАМИ"""
    
    if not text or text == "...":
        return None
    
    # Поиск цены с рублём
    pattern = r'([\d\s,]+)\s*₽'
    matches = re.findall(pattern, text)
    
    if matches:
        try:
            return int(matches[-1].replace(' ', '').replace(',', ''))
        except:
            return None
    
    # Поиск просто больших чисел (3000000, 5 000 000 и т.д.)
    pattern2 = r'(\d[\d\s]*\d)'
    matches2 = re.findall(pattern2, text)
    
    if matches2:
        for m in reversed(matches2):
            num_str = m.replace(' ', '')
            try:
                num = int(num_str)
                if num > 500000 and num < 100000000:  # Вероятная цена авто
                    return num
            except:
                pass
    
    return None

def clean_text(text: str) -> str:
    """ОЧИСТКА ТЕКСТА"""
    if not text or text == "...":
        return ""
    
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'\n\n+', '\n', text)
    return text.strip()

def format_text(original_text: str, price: int) -> str:
    """
    ФОРМАТИРОВАНИЕ ОБЪЯВЛЕНИЯ
    
    Исправлено: HTML вместо Markdown
    """
    if not original_text or original_text == "...":
        original_text = f"Автомобиль {price:,} рублей"
    
    cleaned = clean_text(original_text)
    new_price = price + PRICE_ADD
    
    # Заменяем цену
    pattern = r'([\d\s,]+)\s*₽'
    def replace_price(m):
        try:
            old = int(m.group(1).replace(' ', '').replace(',', ''))
            if abs(old - price) < 200000:
                return f"{new_price:,} ₽".replace(',', ' ')
        except:
            pass
        return m.group(0)
    
    cleaned = re.sub(pattern, replace_price, cleaned)
    
    # ИСПРАВЛЕННЫЙ FOOTER - БЕЗ MARKDOWN
    footer = f"\n\nПо поводу покупки или подбора:\nМенеджер: {MANAGER_LINK}\nВремя ответа: ~1ч\n\n{TARGET_CHANNEL_NAME}"
    
    return cleaned + footer

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 1: ОБРАБОТКА
# ════════════════════════════════════════════════════════════════════

async def handle_announcement_processing(update: Update, context: ContextTypes.DEFAULT_TYPE, source_info: dict):
    """РЕЖИМ 1: ОБРАБОТКА И ПУБЛИКАЦИЯ"""
    
    message = update.message
    msg_id = message.message_id
    
    if is_already_processed(msg_id):
        logger.info(f"Пост {msg_id} уже обработан")
        return
    
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📝 РЕЖИМ 1: ОБРАБОТКА")
    logger.info(f"{'='*70}")
    logger.info(f"📍 Источник: {source_info['source_chat_username'] or source_info['source_chat_title']}")
    
    # Проверяем валидность
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        logger.info(f"⏭️  {reason}")
        return
    
    # Извлекаем цену
    price = extract_price(text)
    if not price:
        logger.info(f"⏭️  Цена не найдена, используем дефолт")
        price = 3000000  # Дефолт для форвардов без текста
    
    logger.info(f"💰 Цена: {price:,} ₽ → {price + PRICE_ADD:,} ₽")
    
    # Форматируем
    formatted = format_text(text, price)
    
    # Публикуем
    try:
        if message.photo:
            photo = message.photo[-1]
            await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID,
                photo=photo.file_id,
                caption=formatted
            )
            logger.info(f"✅ Опубликовано в {TARGET_CHANNEL_NAME}")
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=formatted
            )
            logger.info(f"✅ Опубликовано")
        
        save_processed(msg_id)
        logger.info(f"💾 Сохранено\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 2: ПОИСК ОРИГИНАЛА
# ════════════════════════════════════════════════════════════════════

async def handle_original_search(update: Update, context: ContextTypes.DEFAULT_TYPE, source_info: dict):
    """РЕЖИМ 2: ПОИСК ОРИГИНАЛА"""
    
    message = update.message
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🔍 РЕЖИМ 2: ПОИСК")
    logger.info(f"{'='*70}")
    logger.info(f"📍 Источник: {source_info['source_chat_username'] or source_info['source_chat_title']}")
    
    cache_key = f"{source_info['source_chat_id']}_{source_info['source_message_id']}"
    cached_result = get_search_result(cache_key)
    
    if cached_result:
        logger.info(f"💾 Из кэша")
        original_link = cached_result['original_link']
    else:
        logger.info(f"🔍 Генерируем...")
        
        original_link = generate_original_link(source_info)
        
        if original_link:
            save_search_result(cache_key, {
                'source_chat_id': source_info['source_chat_id'],
                'source_message_id': source_info['source_message_id'],
                'source_chat_username': source_info['source_chat_username'],
                'source_chat_title': source_info['source_chat_title'],
                'original_link': original_link
            })
            
            save_chat_info(source_info['source_chat_id'], {
                'username': source_info['source_chat_username'],
                'title': source_info['source_chat_title'],
                'is_private': source_info['is_private_chat']
            })
    
    # ИСПРАВЛЕННЫЙ ОТВЕТ - БЕЗ MARKDOWN ОШИБОК
    if original_link:
        source_name = source_info['source_chat_username'] or source_info['source_chat_title']
        
        response_text = (
            f"🔗 ОРИГИНАЛЬНОЕ ОБЪЯВЛЕНИЕ\n\n"
            f"Источник: {source_name}\n"
            f"ID сообщения: {source_info['source_message_id']}\n\n"
            f"Ссылка:\n{original_link}\n\n"
            f"Нажми чтобы посмотреть оригинальное объявление"
        )
        
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response_text
        )
        
        logger.info(f"✅ Ссылка отправлена\n")
    else:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="Ошибка при генерации ссылки"
        )
        logger.error(f"❌ Ошибка\n")

# ════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК
# ════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ГЛАВНЫЙ ОБРАБОТЧИК"""
    
    try:
        message = update.message
        
        if not message:
            return
        
        source_info = extract_forward_source(message)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📨 НОВОЕ СООБЩЕНИЕ")
        logger.info(f"{'='*70}")
        
        if source_info['is_forwarded']:
            source_username = source_info['source_chat_username']
            
            logger.info(f"✅ ПЕРЕСЛАНО")
            logger.info(f"📍 Из: {source_username or source_info['source_chat_title']}")
            
            # Из источника → ОБРАБОТКА
            if source_username and source_username in SOURCE_CHANNELS:
                logger.info(f"✅ Источник (@{source_username})")
                await handle_announcement_processing(update, context, source_info)
            
            # Иначе → ПОИСК
            else:
                logger.info(f"📍 Другой источник")
                await handle_original_search(update, context, source_info)
        
        else:
            logger.info(f"⚠️  Не переслано")
            
            help_text = (
                f"Бот готов работать\n\n"
                f"1. Пересли объявление - обработаю и опубликую\n"
                f"2. Пересли запрос - найду оригинал"
            )
            
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=help_text
            )
    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════
# /START - ИСПРАВЛЕНА ОШИБКА MARKDOWN
# ════════════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - БЕЗ MARKDOWN ОШИБОК"""
    try:
        start_text = (
            f"PROAUTO BOT v5.1\n\n"
            f"ФУНКЦИИ:\n"
            f"1. Обработка объявлений\n"
            f"2. Поиск оригиналов\n\n"
            f"Пересли объявление - я его обработаю"
        )
        
        await update.message.reply_text(start_text)
    except Exception as e:
        logger.error(f"Ошибка /start: {e}")

# ════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════════════

async def post_init(application):
    """Инициализация"""
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v5.1 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"BOT: @proauto_23_bot")
    logger.info(f"Менеджер: {MANAGER_LINK}")
    logger.info(f"Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"Наценка: +{PRICE_ADD:,} рублей")
    logger.info(f"Источники: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"")
    logger.info(f"✅ ГОТОВО")
    logger.info(f"{'='*70}")
    logger.info(f"Ожидаю сообщений...\n")

def main():
    """Запуск"""
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        app.add_handler(MessageHandler(filters.COMMAND, start_command))
        app.add_handler(MessageHandler(
            filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO,
            handle_message
        ))
        
        app.run_polling(
            allowed_updates=['message'],
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=30,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30
        )
        
    except Exception as e:
        logger.error(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
