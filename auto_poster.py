"""
╔════════════════════════════════════════════════════════════════════╗
║     PROAUTO BOT v5 - ПОЛНАЯ ВЕРСИЯ                                ║
║     РЕЖИМ 1: Обработка объявлений                                 ║
║     РЕЖИМ 2: Поиск оригиналов по переслному посту                ║
╚════════════════════════════════════════════════════════════════════╝
"""

import re
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
import logging

# ════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════════════════

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID', '0'))
MANAGER_LINK = os.getenv('MANAGER_LINK')
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME')
PRICE_ADD = int(os.getenv('PRICE_ADD', 40000))
SOURCE_CHANNELS = [ch.strip() for ch in os.getenv('SOURCE_CHANNELS', 'M_Supercars,autohaykofficial,FRIEND_AUTO1').split(',')]
MODERATION_GROUP_ID = int(os.getenv('MODERATION_GROUP_ID', '0'))

# ════════════════════════════════════════════════════════════════════
# ЛОГИРОВАНИЕ
# ════════════════════════════════════════════════════════════════════

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════
# ФАЙЛЫ БАЗ ДАННЫХ
# ════════════════════════════════════════════════════════════════════

PROCESSED_FILE = 'processed_posts.json'
SEARCH_HISTORY_FILE = 'search_history.json'
CHAT_INFO_CACHE = 'chat_cache.json'

# ════════════════════════════════════════════════════════════════════
# ФУНКЦИИ БАЗ ДАННЫХ
# ════════════════════════════════════════════════════════════════════

def load_processed():
    """Загружаем обработанные посты"""
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_processed(msg_id):
    """Сохраняем обработанный пост"""
    processed = load_processed()
    processed[str(msg_id)] = datetime.now().isoformat()
    try:
        with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
            json.dump(processed, f, ensure_ascii=False)
    except:
        pass

def is_already_processed(msg_id):
    """Проверяем обработан ли пост"""
    return str(msg_id) in load_processed()

def load_search_history():
    """Загружаем историю поисков"""
    if os.path.exists(SEARCH_HISTORY_FILE):
        try:
            with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_search_result(message_key: str, result_data: dict):
    """Сохраняем результат поиска"""
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
    """Получаем сохранённый результат поиска"""
    history = load_search_history()
    return history.get(message_key, None)

def load_chat_cache():
    """Загружаем кэш информации о чатах"""
    if os.path.exists(CHAT_INFO_CACHE):
        try:
            with open(CHAT_INFO_CACHE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_chat_info(chat_id: int, chat_info: dict):
    """Сохраняем информацию о чате в кэш"""
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
# ФУНКЦИИ ОПРЕДЕЛЕНИЯ ИСТОЧНИКА
# ════════════════════════════════════════════════════════════════════

def extract_forward_source(message):
    """Извлекаем информацию об оригинальном сообщении"""
    
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
    """Генерируем прямую ссылку на оригинальное сообщение"""
    
    if not source_info['is_forwarded']:
        return None
    
    message_id = source_info['source_message_id']
    chat_id = source_info['source_chat_id']
    username = source_info['source_chat_username']
    
    try:
        if username:
            link = f"https://t.me/{username}/{message_id}"
            logger.info(f"✅ Ссылка на ПУБЛИЧНЫЙ канал: {link}")
            return link
        
        if str(chat_id).startswith('-100'):
            chat_id_for_link = str(chat_id)[4:]
        else:
            chat_id_for_link = str(abs(chat_id))
        
        link = f"https://t.me/c/{chat_id_for_link}/{message_id}"
        logger.info(f"✅ Ссылка на ПРИВАТНУЮ группу: {link}")
        return link
    
    except Exception as e:
        logger.error(f"❌ Ошибка генерации ссылки: {e}")
        return None

# ════════════════════════════════════════════════════════════════════
# ФУНКЦИИ ВАЛИДАЦИИ И ОБРАБОТКИ ОБЪЯВЛЕНИЙ
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text: str, has_photo: bool) -> tuple:
    """Проверяем это ли объявление об авто"""
    
    if not has_photo:
        return False, "нет фото"
    
    if not text:
        return True, "OK (только фото)"
    
    text_lower = text.lower()
    
    # Триггеры цены
    price_triggers = [
        r'цена',
        r'стоимость',
        r'сумма',
        r'€',
        r'₽',
        r'\d{3}\s*\d{3}',
    ]
    
    has_price = any(re.search(t, text_lower, re.IGNORECASE) for t in price_triggers)
    
    # Марки авто
    auto_brands = [
        r'BMW|Audi|Mercedes|Toyota|Volkswagen|Ford|Kia|Mazda|Honda|Hyundai',
        r'Volvo|Skoda|LADA|Chevrolet|Renault|Peugeot|Nissan|Subaru|Mitsubishi',
        r'Porsche|Ferrari|Lamborghini|Bugatti|Rolls|Bentley|Maserati|Jaguar',
        r'Chrysler|Dodge|Jeep|GMC|Cadillac|Lincoln|Tesla|Lucid|Isuzu',
    ]
    
    has_brand = any(re.search(b, text, re.IGNORECASE) for b in auto_brands)
    
    # Слова об авто
    auto_words = [
        r'авто\b',
        r'машин',
        r'автомобиль',
        r'кроссовер',
        r'седан',
        r'хэтчбэк',
        r'минивэн',
        r'пикап',
        r'внедорожник',
        r'двигател',
        r'пробег',
        r'комплектаци',
        r'состояни',
        r'коллекция',
        r'VIN',
    ]
    
    has_auto_word = any(re.search(w, text_lower, re.IGNORECASE) for w in auto_words)
    
    if has_photo and (has_price or has_brand or has_auto_word):
        return True, "OK"
    
    if has_photo and not text:
        return True, "OK (фото)"
    
    return False, "не похоже на авто"

def extract_price(text: str):
    """Извлекаем цену"""
    pattern = r'([\d\s,]+)\s*₽'
    matches = re.findall(pattern, text)
    if matches:
        try:
            return int(matches[-1].replace(' ', '').replace(',', ''))
        except:
            return None
    return None

def clean_text(text: str) -> str:
    """Очищаем текст от старых контактов"""
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'\n\n+', '\n', text)
    return text.strip()

def format_text(original_text: str, price: int) -> str:
    """
    ФОРМИРУЕТ НОВОЕ ОБЪЯВЛЕНИЕ
    
    1. Очищает от старых контактов
    2. Меняет цену (добавляет наценку)
    3. Добавляет новые контакты
    """
    cleaned = clean_text(original_text)
    new_price = price + PRICE_ADD
    
    # Заменяем цену в тексте
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
    
    # Добавляем новый контактный блок
    footer = f"\n\nПо поводу покупки или подбора:\n[«Написать менеджеру»]({MANAGER_LINK}) 📧📞\n\n{TARGET_CHANNEL_NAME}"
    
    return cleaned + footer

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 1: ОБРАБОТКА И ПУБЛИКАЦИЯ ОБЪЯВЛЕНИЙ
# ════════════════════════════════════════════════════════════════════

async def handle_announcement_processing(update: Update, context: ContextTypes.DEFAULT_TYPE, source_info: dict):
    """
    РЕЖИМ 1: Обработка объявления из источника
    
    1. Проверяет валидность
    2. Извлекает цену
    3. Переделывает текст
    4. Добавляет контакты
    5. Публикует в целевую группу
    """
    
    message = update.message
    msg_id = message.message_id
    
    if is_already_processed(msg_id):
        logger.info(f"Пост {msg_id} уже обработан, пропускаем")
        return
    
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📝 РЕЖИМ 1: ОБРАБОТКА ОБЪЯВЛЕНИЯ")
    logger.info(f"{'='*70}")
    logger.info(f"📍 Источник: {source_info['source_chat_username'] or source_info['source_chat_title']}")
    logger.info(f"Текст: {text[:60]}...")
    
    # Проверяем валидность
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        logger.info(f"⏭️  {reason}")
        return
    
    # Извлекаем цену
    price = extract_price(text)
    if not price:
        logger.info(f"⏭️  Цена не найдена")
        return
    
    logger.info(f"💰 Цена: {price:,} ₽ → {price + PRICE_ADD:,} ₽")
    
    # Форматируем текст
    formatted = format_text(text, price)
    
    logger.info(f"📝 Текст переделан")
    logger.info(f"✍️  Добавлены контакты: {MANAGER_LINK}")
    
    # Публикуем в целевую группу
    try:
        if message.photo:
            photo = message.photo[-1]
            await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID,
                photo=photo.file_id,
                caption=formatted,
                parse_mode='HTML'
            )
            logger.info(f"✅ Опубликовано с ФОТО в {TARGET_CHANNEL_NAME}")
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=formatted,
                parse_mode='HTML'
            )
            logger.info(f"✅ Опубликовано (текст) в {TARGET_CHANNEL_NAME}")
        
        save_processed(msg_id)
        logger.info(f"💾 Сохранено в базу")
        logger.info(f"{'='*70}\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка публикации: {e}")
        logger.info(f"{'='*70}\n")

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 2: ПОИСК ОРИГИНАЛА ПО ПЕРЕСЛНОМУ СООБЩЕНИЮ
# ════════════════════════════════════════════════════════════════════

async def handle_original_search(update: Update, context: ContextTypes.DEFAULT_TYPE, source_info: dict):
    """
    РЕЖИМ 2: Поиск оригинального объявления
    
    1. Анализирует переслное сообщение
    2. Определяет откуда оно
    3. Генерирует ссылку
    4. Отправляет менеджеру
    """
    
    message = update.message
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🔍 РЕЖИМ 2: ПОИСК ОРИГИНАЛА")
    logger.info(f"{'='*70}")
    logger.info(f"📍 Источник: {source_info['source_chat_username'] or source_info['source_chat_title']}")
    logger.info(f"📌 ID сообщения: {source_info['source_message_id']}")
    
    # Проверяем кэш
    cache_key = f"{source_info['source_chat_id']}_{source_info['source_message_id']}"
    cached_result = get_search_result(cache_key)
    
    if cached_result:
        logger.info(f"💾 Результат найден в кэше")
        original_link = cached_result['original_link']
    else:
        logger.info(f"🔍 Генерируем ссылку...")
        
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
    
    # Отправляем результат
    if original_link:
        source_name = source_info['source_chat_username'] or source_info['source_chat_title']
        
        response_text = (
            f"🔗 *ОРИГИНАЛЬНОЕ ОБЪЯВЛЕНИЕ*\n\n"
            f"📍 Источник: `{source_name}`\n"
            f"💬 ID: `{source_info['source_message_id']}`\n\n"
            f"*🔗 ССЫЛКА:*\n"
            f"{original_link}\n\n"
            f"_Нажми чтобы посмотреть оригинальное объявление_"
        )
        
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Ссылка отправлена менеджеру")
        logger.info(f"🔗 {original_link}")
        logger.info(f"{'='*70}\n")
    else:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="❌ Ошибка при генерации ссылки",
            parse_mode='Markdown'
        )
        logger.error(f"❌ Не удалось сгенерировать ссылку")
        logger.info(f"{'='*70}\n")

# ════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК
# ════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ГЛАВНЫЙ ОБРАБОТЧИК - ВЫБИРАЕТ РЕЖИМ"""
    
    try:
        message = update.message
        
        if not message:
            return
        
        source_info = extract_forward_source(message)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📨 НОВОЕ СООБЩЕНИЕ")
        logger.info(f"{'='*70}")
        
        # ════════════════════════════════════════════════════════════════
        # ЕСЛИ ПЕРЕСЛАНО - ОПРЕДЕЛЯЕМ ИЗ КАКОЙ ГРУППЫ
        # ════════════════════════════════════════════════════════════════
        
        if source_info['is_forwarded']:
            source_username = source_info['source_chat_username']
            
            logger.info(f"✅ Сообщение ПЕРЕСЛАНО")
            logger.info(f"📍 Из: {source_username or source_info['source_chat_title']}")
            
            # ВАРИАНТ 1: Из группы-источника → ОБРАБОТКА
            if source_username and source_username in SOURCE_CHANNELS:
                logger.info(f"✅ Это источник (@{source_username}) → РЕЖИМ ОБРАБОТКИ")
                await handle_announcement_processing(update, context, source_info)
            
            # ВАРИАНТ 2: Из группы модерации → ПОИСК ОРИГИНАЛА
            elif MODERATION_GROUP_ID != 0 and source_info['source_chat_id'] == MODERATION_GROUP_ID:
                logger.info(f"✅ Это группа модерации → РЕЖИМ ПОИСКА")
                await handle_original_search(update, context, source_info)
            
            # ВАРИАНТ 3: Из других источников → ПОИСК ОРИГИНАЛА
            else:
                logger.info(f"📍 Другой источник → РЕЖИМ ПОИСКА")
                await handle_original_search(update, context, source_info)
        
        # ════════════════════════════════════════════════════════════════
        # ЕСЛИ НЕ ПЕРЕСЛАНО - СПРАВКА
        # ════════════════════════════════════════════════════════════════
        
        else:
            logger.info(f"⚠️  Не переслано → Справка")
            
            help_text = (
                f"ℹ️ *КАК ПОЛЬЗОВАТЬСЯ*\n\n"
                f"*РЕЖИМ 1: Обработка объявлений*\n"
                f"Пересли объявление сюда\n"
                f"↓\n"
                f"Бот переделает текст + цену + контакты\n"
                f"↓\n"
                f"Опубликует в {TARGET_CHANNEL_NAME}\n\n"
                f"*РЕЖИМ 2: Поиск оригиналов*\n"
                f"Менеджер пересылает запрос из модерации\n"
                f"↓\n"
                f"Бот находит и отправляет ссылку на оригинал"
            )
            
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=help_text,
                parse_mode='Markdown'
            )
    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════
# КОМАНДА /START
# ════════════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    try:
        start_text = (
            f"🚀 *PROAUTO BOT v5*\n\n"
            f"*ПОЛНЫЙ ФУНКЦИОНАЛ:*\n\n"
            f"*1️⃣ ОБРАБОТКА ОБЪЯВЛЕНИЙ*\n"
            f"Переслай объявление\n"
            f"Бот переделает текст, цену, контакты\n"
            f"Опубликует в {TARGET_CHANNEL_NAME}\n\n"
            f"*2️⃣ ПОИСК ОРИГИНАЛОВ*\n"
            f"Пересли запрос менеджера\n"
            f"Бот найдет оригинал\n"
            f"Отправит ссылку\n\n"
            f"✅ Готово к работе!"
        )
        
        await update.message.reply_text(start_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")

# ════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════════════

async def post_init(application):
    """Инициализация"""
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v5 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"📱 @proauto_23_bot")
    logger.info(f"👨‍💼 Менеджер: {MANAGER_LINK}")
    logger.info(f"📋 Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"💰 Наценка: +{PRICE_ADD:,} ₽")
    logger.info(f"📊 Источники: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"")
    logger.info(f"✅ ДВА РЕЖИМА РАБОТАЮТ")
    logger.info(f"{'='*70}")
    logger.info(f"⏳ Ожидаю сообщений...\n")

def main():
    """Запуск"""
    try:
        logger.info("⏳ Инициализация...")
        
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        app.add_handler(MessageHandler(filters.COMMAND, start_command))
        app.add_handler(MessageHandler(
            filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO,
            handle_message
        ))
        
        logger.info("✅ Инициализировано\n")
        
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
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
