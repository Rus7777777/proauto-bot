"""
PROAUTO BOT v6 - ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ

Исправления:
✅ Сохранение полного текста объявления
✅ Замена ВСЕХ цен (+40000 к каждой)
✅ Поддержка цен с точками: 1.035.000₽
✅ Альбомы - публикация всех фото одной публикацией
✅ HTML гиперссылка для «Написать менеджеру»
✅ Удаление контактов другого канала и текста после строки доставки
"""

import asyncio
import re
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, Update, InputMediaPhoto
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

# КЭШ ДЛЯ ОБРАБОТКИ МЕДИА-ГРУПП
media_groups_cache = {}  # {media_group_id: {photos: [], caption: '', timer: task}}

# ════════════════════════════════════════════════════════════════════
# БАЗЫ ДАННЫХ
# ════════════════════════════════════════════════════════════════════

def load_processed():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_processed(key):
    processed = load_processed()
    processed[str(key)] = datetime.now().isoformat()
    try:
        with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
            json.dump(processed, f, ensure_ascii=False)
    except:
        pass

def is_already_processed(key):
    return str(key) in load_processed()

def load_search_history():
    if os.path.exists(SEARCH_HISTORY_FILE):
        try:
            with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_search_result(key, data):
    history = load_search_history()
    history[key] = data
    try:
        with open(SEARCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False)
    except:
        pass

# ════════════════════════════════════════════════════════════════════
# ОПРЕДЕЛЕНИЕ ИСТОЧНИКА
# ════════════════════════════════════════════════════════════════════

def extract_forward_source(message):
    info = {
        'is_forwarded': False,
        'source_chat_id': None,
        'source_message_id': None,
        'source_chat_username': None,
        'source_chat_title': None,
    }
    
    if not message.forward_from_chat:
        return info
    
    info['is_forwarded'] = True
    info['source_chat_id'] = message.forward_from_chat.id
    info['source_message_id'] = message.forward_from_message_id
    info['source_chat_username'] = message.forward_from_chat.username
    info['source_chat_title'] = message.forward_from_chat.title
    
    return info

def generate_original_link(source_info):
    if not source_info['is_forwarded']:
        return None
    
    msg_id = source_info['source_message_id']
    username = source_info['source_chat_username']
    chat_id = source_info['source_chat_id']
    
    if username:
        return f"https://t.me/{username}/{msg_id}"
    
    if str(chat_id).startswith('-100'):
        chat_id_clean = str(chat_id)[4:]
    else:
        chat_id_clean = str(abs(chat_id))
    
    return f"https://t.me/c/{chat_id_clean}/{msg_id}"

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ТЕКСТА И ЦЕН - ИСПРАВЛЕНО
# ════════════════════════════════════════════════════════════════════

def add_to_price(price_match):
    """Прибавляет +PRICE_ADD к найденной цене"""
    price_str = price_match.group(1)
    
    # Очищаем от пробелов, точек, запятых
    price_clean = re.sub(r'[\s,.]', '', price_str)
    
    try:
        old_price = int(price_clean)
        new_price = old_price + PRICE_ADD
        
        # Форматируем новую цену с точками (как в оригинале)
        new_price_str = f"{new_price:,}".replace(',', '.')
        
        logger.info(f"   💰 Цена: {old_price:,} → {new_price:,}")
        
        return f"{new_price_str}₽"
    except:
        return price_match.group(0)

def process_text(original_text):
    """
    ГЛАВНАЯ ФУНКЦИЯ ОБРАБОТКИ ТЕКСТА:
    
    1. Берёт оригинальный текст
    2. Заменяет ВСЕ цены: +40000 к каждой
    3. Удаляет контакты другого канала (@ВРПИ, @CMAYO_Auto и т.д.)
    4. Удаляет лишний текст с ссылками после строки доставки
    5. Добавляет свой footer с гиперссылкой
    """
    
    if not original_text:
        return None
    
    text = original_text
    
    logger.info(f"📝 ОБРАБОТКА ТЕКСТА...")
    
    # ШАГ 1: ЗАМЕНА ВСЕХ ЦЕН (+40000)
    # Ищем числа перед ₽ (могут быть с точками, пробелами, запятыми)
    # Например: "1.035.000₽", "1 035 000 ₽", "1,035,000₽"
    price_pattern = r'(\d[\d\s.,]*\d)\s*₽'
    
    matches_before = re.findall(price_pattern, text)
    logger.info(f"   Найдено цен в тексте: {len(matches_before)}")
    
    text = re.sub(price_pattern, add_to_price, text)
    
    # ШАГ 2: УДАЛЕНИЕ КОНТАКТОВ ДРУГОГО КАНАЛА
    # Удаляем все @username и связанные ссылки
    text = re.sub(r'\[@[A-Za-z0-9_]+\]\(https?://t\.me/[A-Za-z0-9_]+\)', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://t\.me/[A-Za-z0-9_]+', '', text)
    
    # ШАГ 3: УДАЛЕНИЕ ЛИШНИХ ПУСТЫХ СТРОК
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    text = text.strip()
    
    logger.info(f"   ✅ Текст обработан")
    
    return text

def build_footer():
    """
    Создаёт footer с КЛИКАБЕЛЬНОЙ ссылкой «Написать менеджеру»
    Использует HTML формат
    """
    footer = (
        f"\n\n"
        f"По поводу покупки данного автомобиля или подбора:\n"
        f"  <a href=\"{MANAGER_LINK}\">«Написать менеджеру»</a> 📧 📞\n"
        f"(Ответ в течении 1ч)\n\n"
        f"<a href=\"https://t.me/{TARGET_CHANNEL_NAME.replace('@', '')}\">{TARGET_CHANNEL_NAME}</a>"
    )
    return footer

def format_announcement(original_text):
    """
    Финальное форматирование объявления:
    обработанный текст + footer
    """
    processed = process_text(original_text)
    
    if not processed:
        return None
    
    footer = build_footer()
    
    return processed + footer

# ════════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text, has_photo):
    if not has_photo:
        return False, "нет фото"
    
    if not text or len(text) < 20:
        return False, "слишком короткий текст"
    
    # Проверяем наличие цены или ключевых слов
    has_price = bool(re.search(r'\d[\d\s.,]*\d\s*₽', text))
    has_keywords = bool(re.search(r'цена|стоимость|BMW|Mercedes|Audi|Toyota|Geely|Kia|Mazda|авто|машин', text, re.IGNORECASE))
    
    if has_price or has_keywords:
        return True, "OK"
    
    return False, "не похоже на авто"

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА МЕДИА-ГРУПП (АЛЬБОМЫ)
# ════════════════════════════════════════════════════════════════════

async def process_media_group(media_group_id, context):
    """
    Через 3 секунды после первого фото обрабатываем всю группу
    """
    # Ждём пока все фото из альбома придут
    await asyncio.sleep(3)
    
    if media_group_id not in media_groups_cache:
        return
    
    group_data = media_groups_cache[media_group_id]
    photos = group_data['photos']
    caption = group_data['caption']
    chat_id = group_data['chat_id']
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📸 ОБРАБОТКА АЛЬБОМА: {len(photos)} фото")
    logger.info(f"{'='*70}")
    
    if not photos:
        logger.warning("Нет фото в альбоме")
        del media_groups_cache[media_group_id]
        return
    
    # Проверяем валидность
    valid, reason = is_valid_announcement(caption, True)
    if not valid:
        logger.info(f"⏭️ {reason}")
        del media_groups_cache[media_group_id]
        return
    
    # Форматируем текст
    formatted_text = format_announcement(caption)
    
    if not formatted_text:
        logger.info("⏭️ Не удалось обработать текст")
        del media_groups_cache[media_group_id]
        return
    
    # Создаём медиа-группу для отправки
    try:
        media = []
        for i, photo_id in enumerate(photos):
            if i == 0:
                # Первое фото с текстом
                media.append(InputMediaPhoto(
                    media=photo_id,
                    caption=formatted_text,
                    parse_mode='HTML'
                ))
            else:
                media.append(InputMediaPhoto(media=photo_id))
        
        # Публикуем альбом одним сообщением
        await context.bot.send_media_group(
            chat_id=TARGET_GROUP_ID,
            media=media
        )
        
        logger.info(f"✅ Альбом опубликован: {len(photos)} фото")
        logger.info(f"{'='*70}\n")
        
        save_processed(media_group_id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка публикации альбома: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if media_group_id in media_groups_cache:
            del media_groups_cache[media_group_id]

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 1: ОБРАБОТКА ОБЪЯВЛЕНИЯ
# ════════════════════════════════════════════════════════════════════

async def handle_announcement(update, context, source_info):
    """РЕЖИМ 1: Обработка объявления"""
    
    message = update.message
    media_group_id = message.media_group_id
    
    # ВАРИАНТ А: АЛЬБОМ (несколько фото)
    if media_group_id:
        logger.info(f"\n📸 Фото из альбома: {media_group_id}")
        
        # Уже обработан этот альбом?
        if is_already_processed(media_group_id):
            logger.info("Альбом уже обработан")
            return
        
        # Инициализация кэша для группы
        if media_group_id not in media_groups_cache:
            media_groups_cache[media_group_id] = {
                'photos': [],
                'caption': '',
                'chat_id': message.chat_id,
                'source_info': source_info
            }
            
            # Запускаем обработку через 3 секунды
            asyncio.create_task(process_media_group(media_group_id, context))
        
        # Добавляем фото в группу
        if message.photo:
            photo_id = message.photo[-1].file_id
            media_groups_cache[media_group_id]['photos'].append(photo_id)
            logger.info(f"   Добавлено фото #{len(media_groups_cache[media_group_id]['photos'])}")
        
        # Сохраняем caption (только из первого фото)
        if message.caption and not media_groups_cache[media_group_id]['caption']:
            media_groups_cache[media_group_id]['caption'] = message.caption
            logger.info(f"   Caption: {message.caption[:60]}...")
        
        return
    
    # ВАРИАНТ Б: ОДИНОЧНОЕ ФОТО
    msg_id = message.message_id
    
    if is_already_processed(msg_id):
        return
    
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📝 ОБРАБОТКА: одиночное сообщение")
    logger.info(f"{'='*70}")
    
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        logger.info(f"⏭️ {reason}")
        return
    
    formatted = format_announcement(text)
    
    if not formatted:
        return
    
    try:
        if message.photo:
            photo = message.photo[-1]
            await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID,
                photo=photo.file_id,
                caption=formatted,
                parse_mode='HTML'
            )
            logger.info(f"✅ Опубликовано")
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=formatted,
                parse_mode='HTML'
            )
        
        save_processed(msg_id)
        logger.info(f"💾 Сохранено\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 2: ПОИСК ОРИГИНАЛА
# ════════════════════════════════════════════════════════════════════

async def handle_search(update, context, source_info):
    """РЕЖИМ 2: Поиск оригинала"""
    
    message = update.message
    
    logger.info(f"\n🔍 ПОИСК ОРИГИНАЛА")
    
    original_link = generate_original_link(source_info)
    
    if original_link:
        source_name = source_info['source_chat_username'] or source_info['source_chat_title']
        
        response = (
            f"🔗 ОРИГИНАЛЬНОЕ ОБЪЯВЛЕНИЕ\n\n"
            f"Источник: {source_name}\n"
            f"ID: {source_info['source_message_id']}\n\n"
            f"Ссылка:\n{original_link}"
        )
        
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response
        )
        
        logger.info(f"✅ Ссылка отправлена: {original_link}")
    else:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="❌ Не удалось найти оригинал"
        )

# ════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК
# ════════════════════════════════════════════════════════════════════

async def handle_message(update, context):
    try:
        message = update.message
        
        if not message:
            return
        
        source_info = extract_forward_source(message)
        
        if source_info['is_forwarded']:
            username = source_info['source_chat_username']
            
            logger.info(f"📨 Переслано из: @{username or source_info['source_chat_title']}")
            
            # Из источника → ОБРАБОТКА
            if username and username in SOURCE_CHANNELS:
                logger.info(f"→ РЕЖИМ ОБРАБОТКИ")
                await handle_announcement(update, context, source_info)
            else:
                logger.info(f"→ РЕЖИМ ПОИСКА")
                await handle_search(update, context, source_info)
        else:
            help_text = (
                "Бот готов!\n\n"
                "1. Пересли объявление из источника - обработаю\n"
                "2. Пересли запрос - найду оригинал"
            )
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=help_text
            )
    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def start_command(update, context):
    try:
        await update.message.reply_text(
            "PROAUTO BOT v6\n\n"
            "Пересылай объявления - я их обработаю\n"
            "Добавлю наценку, поменяю контакты\n"
            "Опубликую в группе"
        )
    except Exception as e:
        logger.error(f"Ошибка /start: {e}")

async def post_init(application):
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v6 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"BOT: @proauto_23_bot")
    logger.info(f"Менеджер: {MANAGER_LINK}")
    logger.info(f"Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"Наценка: +{PRICE_ADD:,} ₽")
    logger.info(f"Источники: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"{'='*70}")
    logger.info(f"✅ ГОТОВО\n")

def main():
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
