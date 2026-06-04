"""
PROAUTO BOT v9 - ФИНАЛЬНАЯ ВЕРСИЯ

ИСПРАВЛЕНИЯ:
✅ ID публикации ПОД ценой (не сверху)
✅ Удалены баги с пустыми буллетами (•••)
✅ Красивое приветствие с эмодзи
✅ Универсальная обработка ЛЮБЫХ источников
✅ Deep linking: ?start=id_0003 → бот понимает какой авто
✅ Бриф-бот с кнопочным опросником
✅ Калькулятор стоимости
✅ Экспорт текста для площадок (Авито/ВК/Дром)
✅ Уведомления менеджеру о заявках
"""

import asyncio
import re
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import (
    Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, ContextTypes, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ConversationHandler
)
import logging

load_dotenv()

# ════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'proauto_23_bot')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID', '0'))
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME', '@proauto_77')
MANAGER_LINK = os.getenv('MANAGER_LINK', 'https://t.me/rdblm')

OWNER_ID = int(os.getenv('OWNER_ID', '0'))
MANAGER_USER_ID = int(os.getenv('MANAGER_USER_ID', '0'))

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Файлы БД
PUBLICATIONS_DB = 'publications.json'
LEADS_DB = 'leads.json'
USER_STATES_DB = 'user_states.json'
media_groups_cache = {}

# Состояния опросника
BRIEF_STATES = {}  # {user_id: {step: ..., data: {...}}}

# ════════════════════════════════════════════════════════════════════
# ПРАВА ПОЛЬЗОВАТЕЛЕЙ
# ════════════════════════════════════════════════════════════════════

def has_publish_rights(user_id):
    if user_id == OWNER_ID and OWNER_ID != 0:
        return True
    if user_id == MANAGER_USER_ID and MANAGER_USER_ID != 0:
        return True
    return False

# ════════════════════════════════════════════════════════════════════
# БАЗЫ ДАННЫХ
# ════════════════════════════════════════════════════════════════════

def load_db(filename, default=None):
    if default is None:
        default = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    return default

def save_db(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {filename}: {e}")

def get_next_publication_id():
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    db['counter'] = db.get('counter', 0) + 1
    new_id = f"id_{db['counter']:04d}"
    save_db(PUBLICATIONS_DB, db)
    return new_id

def save_publication(pub_id, **kwargs):
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    db['publications'][pub_id] = {
        **kwargs,
        'published_at': datetime.now().isoformat(),
        'expires_at': (datetime.now() + timedelta(days=30)).isoformat()
    }
    save_db(PUBLICATIONS_DB, db)
    logger.info(f"💾 Сохранено {pub_id}")

def find_publication(pub_id):
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    return db['publications'].get(pub_id)

def get_next_lead_id():
    db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
    db['counter'] = db.get('counter', 0) + 1
    new_id = f"lead_{db['counter']:05d}"
    save_db(LEADS_DB, db)
    return new_id

def save_lead(lead_id, data):
    db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
    db['leads'][lead_id] = {
        **data,
        'created_at': datetime.now().isoformat()
    }
    save_db(LEADS_DB, db)

# ════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ЭМОДЗИ
# ════════════════════════════════════════════════════════════════════

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE
)

def remove_all_emojis(text):
    return EMOJI_PATTERN.sub('', text)

# ════════════════════════════════════════════════════════════════════
# МАТЕМАТИКА ЦЕН
# ════════════════════════════════════════════════════════════════════

def calculate_markup(price, currency):
    if currency in ['₽', 'руб', 'RUB']:
        if price >= 30_000_000: return 1_000_000
        elif price >= 25_000_000: return 500_000
        elif price >= 20_000_000: return 350_000
        elif price >= 15_000_000: return 250_000
        elif price >= 10_000_000: return 180_000
        elif price >= 7_000_000: return 100_000
        elif price >= 5_000_000: return 80_000
        else: return 40_000
    elif currency in ['€', '$']:
        return 1_000
    return 0

def format_price_with_dots(price):
    return f"{price:,}".replace(',', '.')

def replace_price(match):
    price_str = match.group(1)
    currency = match.group(2)
    if currency in ['руб', 'RUB']:
        currency = '₽'
    price_clean = re.sub(r'[\s,.\u00a0]', '', price_str)
    try:
        old_price = int(price_clean)
        new_price = old_price + calculate_markup(old_price, currency)
        return f"{format_price_with_dots(new_price)}{currency}"
    except:
        return match.group(0)

# ════════════════════════════════════════════════════════════════════
# ОЧИСТКА ТЕКСТА
# ════════════════════════════════════════════════════════════════════

def remove_old_contacts(text):
    text = re.sub(r'^[\s]*В продаже\s*\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\nВ продаже\s*\n', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'\[@[A-Za-z0-9_]+\]\(https?://t\.me/[A-Za-z0-9_]+\)', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'НАПИСАТЬ МЕНЕДЖЕРУ[\s\S]*?(?=Наши соц сети|$)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Наши соц сети[\s\S]*?$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Нужна цена под ключ до вашего дома\??\s*\n?\s*Пишите в личку!?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Доставка осуществляется во все города РФ\.?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[[^\]]+\]\(https?://[^\)]+\)', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'Whatsapp\s*\+?[\d\s]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Telegram\s*\+?[\d\s]+', '', text, flags=re.IGNORECASE)
    return text

def keep_only_moscow_price(text):
    if not re.search(r'в Москве', text, re.IGNORECASE):
        return text
    text = re.sub(
        r'^.*?(?:Итоговая цена|Цена)[^:\n]*в (?:Уссурийске|Владивостоке)[^:\n]*:[^\n]*\n?',
        '', text, flags=re.IGNORECASE | re.MULTILINE
    )
    return text

# ════════════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ
# ════════════════════════════════════════════════════════════════════

def is_section_header(line):
    headers = ['Комплектация:', 'Состояние:', 'Состояние автомобиля:', 'Опции:']
    return any(h.lower() in line.lower().strip() for h in headers) and len(line) < 50

def is_price_line(line):
    return bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]', line))

def format_characteristics(text):
    """ИСПРАВЛЕНО: Не добавляем пустые буллеты"""
    lines = text.split('\n')
    result_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            result_lines.append('')
            continue
        
        # Уже с буллетом - оставляем, но проверяем что есть содержимое
        if stripped.startswith('•') or stripped.startswith('▪') or stripped.startswith('●'):
            clean = re.sub(r'^[•▪●]\s*', '', stripped)
            if clean:  # ВАЖНО: только если есть текст после буллета
                result_lines.append(f'• {clean}')
            continue
        
        # Характеристика "ключ: значение"
        if ':' in stripped and not is_section_header(stripped) and not is_price_line(stripped):
            field_part = stripped.split(':')[0].strip()
            value_part = stripped.split(':', 1)[1].strip() if ':' in stripped else ''
            if len(field_part) < 40 and value_part:  # ВАЖНО: есть и поле и значение
                result_lines.append(f'• {stripped}')
                continue
        
        result_lines.append(stripped)
    
    return '\n'.join(result_lines)

def make_section_headers_bold(text):
    headers = ['Комплектация:', 'Состояние:', 'Состояние автомобиля:', 'Опции:']
    for header in headers:
        text = re.sub(re.escape(header), f'<b>{header}</b>', text, flags=re.IGNORECASE)
    return text

def make_model_name_bold(text):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith('•') and not stripped.startswith('<b>'):
            lines[i] = f'<b>{stripped}</b>'
            break
    return '\n'.join(lines)

def make_price_lines_bold(text):
    pattern = r'^([^\n<]*\d[\d\s.,\u00a0]*\d\s*[₽€$][^\n<]*)$'
    def make_bold(match):
        line = match.group(1).strip()
        if not line.startswith('<b>'):
            return f'<b>{line}</b>'
        return line
    return re.sub(pattern, make_bold, text, flags=re.MULTILINE)

def fix_spacing(text):
    text = re.sub(r'\n{3,}', '\n\n', text)
    section_headers = ['<b>Комплектация:</b>', '<b>Состояние:</b>', '<b>Состояние автомобиля:</b>']
    for header in section_headers:
        escaped = re.escape(header)
        text = re.sub(rf'\n\n+({escaped})', rf'\n\1', text)
        text = re.sub(rf'({escaped})\n\n+', rf'\1\n', text)
    return text.strip()

def apply_price_markup(text):
    patterns = [
        r'(\d[\d\s.,\u00a0]*\d)\s*(₽|руб|RUB)',
        r'(\d[\d\s.,\u00a0]*\d)\s*(€)',
        r'(\d[\d\s.,\u00a0]*\d)\s*(\$)',
    ]
    for pattern in patterns:
        text = re.sub(pattern, replace_price, text)
    return text

def determine_footer_type(text):
    text_lower = text.lower()
    if 'в москве' in text_lower or 'во владивостоке' in text_lower or 'итоговая цена' in text_lower:
        return 'delivery'
    if '€' in text or '$' in text:
        return 'calculate'
    return 'delivery'

def build_footer(footer_type, pub_id, publication_link):
    """ИСПРАВЛЕНО: ID идёт ПОСЛЕ цены, не сверху"""
    
    # Ссылка ID (опционально)
    id_line = ''
    if publication_link:
        id_line = f'\n\n<a href="{publication_link}">{pub_id}</a>'
    else:
        id_line = f'\n\n{pub_id}'
    
    manager_link = f'<a href="{MANAGER_LINK}?start={pub_id}">«Написать менеджеру»</a> 📞 ✅'
    channel_link = f'<a href="https://t.me/{TARGET_CHANNEL_NAME.replace("@", "")}">{TARGET_CHANNEL_NAME}</a>'
    
    if footer_type == 'delivery':
        footer = (
            f"\n\nДоставка осуществляется во все города РФ\n\n"
            f"По поводу покупки данного автомобиля или подбора:\n"
            f"{manager_link}\n"
            f"(Ответ в течении 1ч)"
            f"{id_line}\n\n"
            f"{channel_link}"
        )
    else:
        footer = (
            f"\n\nРассчитаем стоимость до Вашего дома 🏠 ✅\n"
            f"{manager_link}\n"
            f"(Ответ в течении 1ч)"
            f"{id_line}\n\n"
            f"{channel_link}"
        )
    
    return footer

def format_announcement(original_text, pub_id, publication_link):
    if not original_text:
        return None
    
    logger.info(f"🔧 Обработка для {pub_id}")
    
    text = original_text
    text = remove_all_emojis(text)
    text = remove_old_contacts(text)
    text = apply_price_markup(text)
    text = keep_only_moscow_price(text)
    
    footer_type = determine_footer_type(text)
    
    text = format_characteristics(text)
    text = make_section_headers_bold(text)
    text = make_model_name_bold(text)
    text = make_price_lines_bold(text)
    text = fix_spacing(text)
    
    # ИСПРАВЛЕНО: id_XXXX теперь добавляется в footer, не сверху
    header = "Прямая продажа ✅\n\n"
    footer = build_footer(footer_type, pub_id, publication_link)
    
    return header + text + footer
    # ════════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ И ИСТОЧНИК
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text, has_photo):
    if not has_photo:
        return False, "нет фото"
    if not text or len(text) < 20:
        return False, "короткий текст"
    has_price = bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]|\d[\d\s.,\u00a0]*\d\s*руб', text))
    has_keywords = bool(re.search(
        r'BMW|Mercedes|Audi|Toyota|Geely|Kia|Mazda|Volkswagen|Porsche|Rolls-Royce|Honda|Hyundai|Volvo|Ford|Nissan|Lamborghini|Ferrari|Bentley|Lexus|Infiniti|Tesla|авто|машин|двигател',
        text, re.IGNORECASE
    ))
    if has_price or has_keywords:
        return True, "OK"
    return False, "не авто"

def extract_pub_id_from_text(text):
    if not text:
        return None
    match = re.search(r'id_(\d{4})', text)
    if match:
        return f"id_{match.group(1)}"
    return None

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
    if not source_info.get('is_forwarded'):
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

def generate_publication_link(message_id):
    channel = TARGET_CHANNEL_NAME.replace('@', '')
    return f"https://t.me/{channel}/{message_id}"

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА АЛЬБОМОВ
# ════════════════════════════════════════════════════════════════════

async def process_media_group(media_group_id, context):
    await asyncio.sleep(3)
    if media_group_id not in media_groups_cache:
        return
    
    group_data = media_groups_cache[media_group_id]
    photos = group_data['photos']
    caption = group_data['caption']
    source_info = group_data['source_info']
    
    logger.info(f"📸 АЛЬБОМ: {len(photos)} фото")
    
    if not photos:
        del media_groups_cache[media_group_id]
        return
    
    valid, reason = is_valid_announcement(caption, True)
    if not valid:
        logger.info(f"⏭️ {reason}")
        del media_groups_cache[media_group_id]
        return
    
    pub_id = get_next_publication_id()
    logger.info(f"🆔 {pub_id}")
    
    source_link = generate_original_link(source_info) if source_info else None
    formatted_text = format_announcement(caption, pub_id, None)
    if not formatted_text:
        del media_groups_cache[media_group_id]
        return
    
    try:
        media = []
        for i, photo_id in enumerate(photos):
            if i == 0:
                media.append(InputMediaPhoto(media=photo_id, caption=formatted_text, parse_mode='HTML'))
            else:
                media.append(InputMediaPhoto(media=photo_id))
        
        sent_messages = await context.bot.send_media_group(
            chat_id=TARGET_GROUP_ID,
            media=media
        )
        
        published_message_id = sent_messages[0].message_id if sent_messages else None
        publication_link = generate_publication_link(published_message_id) if published_message_id else None
        
        # Обновляем caption с правильной ссылкой ID
        if publication_link and sent_messages:
            new_caption = format_announcement(caption, pub_id, publication_link)
            try:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID,
                    message_id=sent_messages[0].message_id,
                    caption=new_caption,
                    parse_mode='HTML'
                )
            except:
                pass
        
        save_publication(
            pub_id,
            source_link=source_link,
            source_chat_id=source_info['source_chat_id'] if source_info else None,
            source_message_id=source_info['source_message_id'] if source_info else None,
            source_username=source_info['source_chat_username'] if source_info else None,
            published_message_id=published_message_id,
            published_chat_id=TARGET_GROUP_ID,
            original_caption=caption
        )
        
        logger.info(f"✅ Альбом {pub_id} опубликован")
        
    except Exception as e:
        logger.error(f"❌ Ошибка альбома: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if media_group_id in media_groups_cache:
            del media_groups_cache[media_group_id]

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ОБЪЯВЛЕНИЙ
# ════════════════════════════════════════════════════════════════════

async def handle_announcement(update, context, source_info):
    message = update.message
    media_group_id = message.media_group_id
    
    if media_group_id:
        if media_group_id not in media_groups_cache:
            media_groups_cache[media_group_id] = {
                'photos': [],
                'caption': '',
                'source_info': source_info
            }
            asyncio.create_task(process_media_group(media_group_id, context))
        
        if message.photo:
            photo_id = message.photo[-1].file_id
            media_groups_cache[media_group_id]['photos'].append(photo_id)
        
        if message.caption and not media_groups_cache[media_group_id]['caption']:
            media_groups_cache[media_group_id]['caption'] = message.caption
        
        return
    
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        logger.info(f"⏭️ {reason}")
        return
    
    pub_id = get_next_publication_id()
    source_link = generate_original_link(source_info) if source_info else None
    formatted = format_announcement(text, pub_id, None)
    
    try:
        if message.photo:
            photo = message.photo[-1]
            sent = await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID,
                photo=photo.file_id,
                caption=formatted,
                parse_mode='HTML'
            )
        else:
            sent = await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=formatted,
                parse_mode='HTML'
            )
        
        published_message_id = sent.message_id
        publication_link = generate_publication_link(published_message_id)
        
        # Обновляем с правильной ссылкой
        new_text = format_announcement(text, pub_id, publication_link)
        try:
            if message.photo:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID,
                    message_id=published_message_id,
                    caption=new_text,
                    parse_mode='HTML'
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=TARGET_GROUP_ID,
                    message_id=published_message_id,
                    text=new_text,
                    parse_mode='HTML'
                )
        except:
            pass
        
        save_publication(
            pub_id,
            source_link=source_link,
            source_chat_id=source_info['source_chat_id'] if source_info else None,
            source_message_id=source_info['source_message_id'] if source_info else None,
            source_username=source_info['source_chat_username'] if source_info else None,
            published_message_id=published_message_id,
            published_chat_id=TARGET_GROUP_ID,
            original_caption=text
        )
        
        logger.info(f"✅ {pub_id} опубликовано")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ════════════════════════════════════════════════════════════════════
# DEEP LINKING & БРИФ-БОТ
# ════════════════════════════════════════════════════════════════════

# Состояния опросника
ASK_INTEREST_TYPE = 'interest_type'
ASK_CITY = 'city'
ASK_BUDGET = 'budget'
ASK_TIMING = 'timing'
ASK_BRAND_GROUP = 'brand_group'
ASK_BRAND = 'brand'
ASK_YEAR = 'year'
ASK_NAME = 'name'
ASK_PHONE = 'phone'
ASK_FINAL = 'final'

CITIES = ['Москва', 'Санкт-Петербург', 'Краснодар', 'Сочи', 'Екатеринбург', 
          'Новосибирск', 'Казань', 'Ростов-на-Дону', 'Нижний Новгород', 'Воронеж']

BUDGET_RANGES = [
    'До 2 млн ₽',
    '2-3 млн ₽',
    '3-5 млн ₽',
    '5-10 млн ₽',
    '10-20 млн ₽',
    'Свыше 20 млн ₽',
]

TIMINGS = [
    'В этом месяце',
    '1-2 месяца',
    '3-6 месяцев',
    'Просто смотрю'
]

BRAND_GROUPS = {
    '🇩🇪 Немецкие': ['BMW', 'Mercedes-Benz', 'Audi', 'Volkswagen', 'Porsche'],
    '🇯🇵 Японские': ['Toyota', 'Lexus', 'Honda', 'Nissan', 'Mazda', 'Subaru', 'Infiniti'],
    '🇰🇷 Корейские': ['Kia', 'Hyundai', 'Genesis', 'SsangYong'],
    '🇨🇳 Китайские': ['Geely', 'Lixiang', 'Zeekr', 'NIO', 'BYD', 'Haval', 'Tank'],
    '🇺🇸 Американские': ['Ford', 'Chevrolet', 'Tesla', 'Cadillac', 'Dodge', 'Jeep'],
    '🇪🇺 Премиум EU': ['Ferrari', 'Lamborghini', 'Bentley', 'Rolls-Royce', 'Maserati', 'Aston Martin'],
    '⚡ Электромобили': ['Tesla', 'Zeekr', 'BYD', 'NIO', 'Lucid', 'Rivian'],
}

YEARS = ['2024-2025', '2022-2023', '2020-2021', '2017-2019', 'Старше 2017']

def get_user_state(user_id):
    if user_id not in BRIEF_STATES:
        BRIEF_STATES[user_id] = {'step': None, 'data': {}}
    return BRIEF_STATES[user_id]

def clear_user_state(user_id):
    if user_id in BRIEF_STATES:
        del BRIEF_STATES[user_id]

async def start_brief_for_specific_car(update, context, pub_id):
    """Старт брифа для конкретного авто (deep link)"""
    publication = find_publication(pub_id)
    
    if publication:
        # Берём название из оригинального текста (первая строка после "Прямая продажа")
        original = publication.get('original_caption', '')
        # Извлекаем название модели
        lines = original.split('\n')
        car_name = "выбранный автомобиль"
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('•') and len(stripped) < 100:
                car_name = stripped
                break
    else:
        car_name = "автомобиль"
    
    user_id = update.effective_user.id
    BRIEF_STATES[user_id] = {
        'step': ASK_INTEREST_TYPE,
        'data': {
            'pub_id': pub_id,
            'car_name': car_name,
            'source': 'deep_link'
        }
    }
    
    text = (
        f"Здравствуйте! 👋\n\n"
        f"🚗 <b>Видим что интересует:</b>\n\n"
        f"{car_name} ({pub_id})\n\n"
        f"Хотите оформить заявку?"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, интересует этот авто", callback_data=f"brief_yes_{pub_id}")],
        [InlineKeyboardButton("🟦 Нет, индивидуальный заказ", callback_data="brief_custom")],
        [InlineKeyboardButton("❓ У меня другой вопрос", callback_data="brief_question")],
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def start_general_brief(update, context):
    """Старт общего брифа (без deep link)"""
    user_id = update.effective_user.id
    BRIEF_STATES[user_id] = {
        'step': ASK_INTEREST_TYPE,
        'data': {'source': 'direct'}
    }
    
    text = (
        f"Здравствуйте! 👋\n\n"
        f"Я представляю компанию <b>ProAuto</b> — мы профессионально занимаемся "
        f"подбором и доставкой автомобилей по всей России и СНГ.\n\n"
        f"<b>Наши преимущества:</b>\n"
        f"• Прозрачные цены без скрытых платежей ✅\n"
        f"• 🚗 Подбор автомобиля под любой бюджет\n"
        f"• 📦 Доставка во все города РФ\n"
        f"• 📋 Полное юридическое сопровождение\n"
        f"• 🛡 Гарантия качества каждого авто\n\n"
        f"<b>Что Вас интересует?</b>"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Подобрать автомобиль", callback_data="brief_custom")],
        [InlineKeyboardButton("📋 Посмотреть каталог", url=f"https://t.me/{TARGET_CHANNEL_NAME.replace('@', '')}")],
        [InlineKeyboardButton("❓ Задать вопрос", callback_data="brief_question")],
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

async def ask_city(update, context):
    """Шаг: выбор города доставки"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state['step'] = ASK_CITY
    
    keyboard = []
    row = []
    for i, city in enumerate(CITIES):
        row.append(InlineKeyboardButton(city, callback_data=f"city_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✍️ Другой город", callback_data="city_other")])
    
    text = "🏙 <b>В какой город нужна доставка?</b>"
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def ask_timing(update, context):
    """Шаг: сроки покупки"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state['step'] = ASK_TIMING
    
    keyboard = [[InlineKeyboardButton(t, callback_data=f"timing_{i}")] for i, t in enumerate(TIMINGS)]
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏰ <b>Когда планируете покупку?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def ask_brand_group(update, context):
    """Шаг: группа марок"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state['step'] = ASK_BRAND_GROUP
    
    keyboard = [[InlineKeyboardButton(g, callback_data=f"bgroup_{i}")] 
                for i, g in enumerate(BRAND_GROUPS.keys())]
    keyboard.append([InlineKeyboardButton("🤔 Любая марка", callback_data="bgroup_any")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="🚗 <b>Какие марки Вас интересуют?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def ask_brand(update, context, group_idx):
    """Шаг: конкретная марка"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state['step'] = ASK_BRAND
    
    group_name = list(BRAND_GROUPS.keys())[group_idx]
    brands = BRAND_GROUPS[group_name]
    
    keyboard = []
    row = []
    for i, brand in enumerate(brands):
        row.append(InlineKeyboardButton(brand, callback_data=f"brand_{group_idx}_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_groups")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"<b>{group_name}</b>\n\nВыберите марку:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def ask_budget(update, context):
    """Шаг: бюджет"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state['step'] = ASK_BUDGET
    
    keyboard = [[InlineKeyboardButton(b, callback_data=f"budget_{i}")] for i, b in enumerate(BUDGET_RANGES)]
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="💰 <b>Ваш бюджет (под ключ)?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def ask_year(update, context):
    """Шаг: год выпуска"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state['step'] = ASK_YEAR
    
    keyboard = [[InlineKeyboardButton(y, callback_data=f"year_{i}")] for i, y in enumerate(YEARS)]
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="📅 <b>Какой год выпуска?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def finalize_brief(update, context):
    """Финализация заявки"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    data = state['data']
    user = update.effective_user
    
    lead_id = get_next_lead_id()
    
    lead_data = {
        'user_id': user_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        **data
    }
    
    save_lead(lead_id, lead_data)
    
    # Сообщение клиенту
    client_text = (
        f"✅ <b>Спасибо! Ваша заявка №{lead_id} принята</b>\n\n"
        f"📞 Менеджер свяжется с Вами в течение <b>1 часа</b>\n\n"
        f"А пока можете посмотреть актуальные предложения:\n"
        f"{TARGET_CHANNEL_NAME}"
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=client_text,
        parse_mode='HTML'
    )
    
    # Уведомление менеджеру
    await notify_manager(context, lead_id, lead_data)
    
    clear_user_state(user_id)

async def notify_manager(context, lead_id, lead_data):
    """Отправка заявки менеджеру"""
    if not MANAGER_USER_ID and not OWNER_ID:
        return
    
    text = f"🆕 <b>НОВАЯ ЗАЯВКА {lead_id}</b>\n\n"
    text += f"👤 Клиент: "
    if lead_data.get('username'):
        text += f"@{lead_data['username']} "
    text += f"({lead_data.get('first_name', '')} {lead_data.get('last_name', '')})\n"
    text += f"🆔 User ID: <code>{lead_data['user_id']}</code>\n\n"
    
    if lead_data.get('pub_id'):
        text += f"🚗 <b>Интересует:</b>\n"
        text += f"{lead_data.get('car_name', '')}\n"
        text += f"ID: {lead_data['pub_id']}\n\n"
    
    text += f"📋 <b>Бриф:</b>\n"
    if lead_data.get('city'):
        text += f"• Город: {lead_data['city']}\n"
    if lead_data.get('timing'):
        text += f"• Срок: {lead_data['timing']}\n"
    if lead_data.get('brand'):
        text += f"• Марка: {lead_data['brand']}\n"
    if lead_data.get('year'):
        text += f"• Год: {lead_data['year']}\n"
    if lead_data.get('budget'):
        text += f"• Бюджет: {lead_data['budget']}\n"
    
    text += f"\n💬 <a href='tg://user?id={lead_data['user_id']}'>Открыть чат с клиентом</a>"
    
    # Отправляем владельцу и менеджеру
    for recipient_id in [OWNER_ID, MANAGER_USER_ID]:
        if recipient_id != 0:
            try:
                await context.bot.send_message(
                    chat_id=recipient_id,
                    text=text,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить {recipient_id}: {e}")

# ════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER (обработка кнопок)
# ════════════════════════════════════════════════════════════════════

async def button_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    state = get_user_state(user_id)
    
    # Интерес к конкретному авто
    if data.startswith("brief_yes_"):
        pub_id = data.replace("brief_yes_", "")
        state['data']['pub_id'] = pub_id
        state['data']['interest_type'] = 'specific_car'
        await query.edit_message_text("✅ Отлично! Уточним пару деталей:")
        await ask_city(update, context)
        return
    
    # Индивидуальный заказ
    if data == "brief_custom":
        state['data']['interest_type'] = 'custom'
        await query.edit_message_text("🔍 Подберём идеальное авто для Вас!")
        await ask_brand_group(update, context)
        return
    
    # Вопрос
    if data == "brief_question":
        state['data']['interest_type'] = 'question'
        await query.edit_message_text(
            "💬 <b>Напишите Ваш вопрос менеджеру:</b>\n\n"
            f"📞 <a href='{MANAGER_LINK}'>«Написать менеджеру»</a> 📞 ✅\n"
            f"(Ответ в течении 1ч)",
            parse_mode='HTML'
        )
        clear_user_state(user_id)
        return
    
    # Город
    if data.startswith("city_"):
        if data == "city_other":
            state['data']['city'] = 'Другой (уточнить с менеджером)'
        else:
            idx = int(data.replace("city_", ""))
            state['data']['city'] = CITIES[idx]
        await query.edit_message_text(f"🏙 Город: <b>{state['data']['city']}</b>", parse_mode='HTML')
        
        if state['data'].get('interest_type') == 'specific_car':
            await ask_timing(update, context)
        else:
            await ask_year(update, context)
        return
    
    # Срок
    if data.startswith("timing_"):
        idx = int(data.replace("timing_", ""))
        state['data']['timing'] = TIMINGS[idx]
        await query.edit_message_text(f"⏰ Срок: <b>{state['data']['timing']}</b>", parse_mode='HTML')
        
        if state['data'].get('interest_type') == 'specific_car':
            await finalize_brief(update, context)
        else:
            await ask_budget(update, context)
        return
    
    # Группа марок
    if data.startswith("bgroup_"):
        if data == "bgroup_any":
            state['data']['brand'] = 'Любая (уточнить)'
            await query.edit_message_text("🚗 Марка: <b>Любая</b>", parse_mode='HTML')
            await ask_year(update, context)
            return
        idx = int(data.replace("bgroup_", ""))
        state['data']['brand_group_idx'] = idx
        await ask_brand(update, context, idx)
        return
    
    # Конкретная марка
    if data.startswith("brand_"):
        parts = data.split("_")
        group_idx = int(parts[1])
        brand_idx = int(parts[2])
        group_name = list(BRAND_GROUPS.keys())[group_idx]
        brand = BRAND_GROUPS[group_name][brand_idx]
        state['data']['brand'] = brand
        await query.edit_message_text(f"🚗 Марка: <b>{brand}</b>", parse_mode='HTML')
        await ask_year(update, context)
        return
    
    # Назад к группам
    if data == "back_to_groups":
        await ask_brand_group(update, context)
        return
    
    # Год
    if data.startswith("year_"):
        idx = int(data.replace("year_", ""))
        state['data']['year'] = YEARS[idx]
        await query.edit_message_text(f"📅 Год: <b>{state['data']['year']}</b>", parse_mode='HTML')
        await ask_budget(update, context)
        return
    
    # Бюджет
    if data.startswith("budget_"):
        idx = int(data.replace("budget_", ""))
        state['data']['budget'] = BUDGET_RANGES[idx]
        await query.edit_message_text(f"💰 Бюджет: <b>{state['data']['budget']}</b>", parse_mode='HTML')
        await ask_city(update, context)
        return

# ════════════════════════════════════════════════════════════════════
# КАЛЬКУЛЯТОР СТОИМОСТИ
# ════════════════════════════════════════════════════════════════════

async def calculator_command(update, context):
    """Команда /calculator - калькулятор стоимости"""
    text = (
        f"🧮 <b>КАЛЬКУЛЯТОР СТОИМОСТИ АВТО</b>\n\n"
        f"Подберите примерную цену под ключ:\n"
        f"(окончательная цена — после консультации с менеджером)\n\n"
        f"Из какой страны планируете заказывать?"
    )
    
    keyboard = [
        [InlineKeyboardButton("🇰🇷 Корея", callback_data="calc_country_korea")],
        [InlineKeyboardButton("🇯🇵 Япония", callback_data="calc_country_japan")],
        [InlineKeyboardButton("🇩🇪 Германия", callback_data="calc_country_germany")],
        [InlineKeyboardButton("🇨🇳 Китай", callback_data="calc_country_china")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="calc_country_usa")],
        [InlineKeyboardButton("📞 Связаться с менеджером", url=MANAGER_LINK)],
    ]
    
    await update.message.reply_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

# ════════════════════════════════════════════════════════════════════
# /START - DEEP LINKING
# ════════════════════════════════════════════════════════════════════

async def start_command(update, context):
    user_id = update.effective_user.id
    
    # Проверяем deep link параметр
    args = context.args
    
    if args:
        param = args[0]
        
        # Если параметр - это ID публикации (id_0003)
        if param.startswith('id_'):
            await start_brief_for_specific_car(update, context, param)
            return
        
        # UTM-метки (utm_avito, utm_vk и т.д.)
        if param.startswith('utm_'):
            source = param.replace('utm_', '')
            logger.info(f"📊 UTM: {source} от user {user_id}")
            # Сохраняем источник в state
            state = get_user_state(user_id)
            state['data']['utm_source'] = source
    
    # Если владелец
    if has_publish_rights(user_id):
        text = (
            f"🚀 <b>PROAUTO BOT v9 — Админ-панель</b>\n\n"
            f"Возможности:\n"
            f"• 📤 Пересылай объявления — публикую в {TARGET_CHANNEL_NAME}\n"
            f"• 🔎 Пересылай свой пост с id_XXXX — найду оригинал\n"
            f"• 📊 /stats — статистика\n"
            f"• 📋 /leads — последние заявки\n"
            f"• 📤 /export — экспорт текстов для площадок"
        )
        await update.message.reply_text(text, parse_mode='HTML')
    else:
        # Обычный клиент — общий бриф
        await start_general_brief(update, context)
        # ════════════════════════════════════════════════════════════════════
# СТАТИСТИКА И ЗАЯВКИ
# ════════════════════════════════════════════════════════════════════

async def stats_command(update, context):
    """Команда /stats - статистика"""
    user_id = update.effective_user.id
    if not has_publish_rights(user_id):
        return
    
    pubs_db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    leads_db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
    
    total_pubs = pubs_db.get('counter', 0)
    total_leads = leads_db.get('counter', 0)
    
    # Статистика за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    
    recent_pubs = 0
    for pub in pubs_db['publications'].values():
        try:
            pub_date = datetime.fromisoformat(pub.get('published_at', ''))
            if pub_date > week_ago:
                recent_pubs += 1
        except:
            pass
    
    recent_leads = 0
    leads_by_source = {}
    for lead in leads_db['leads'].values():
        try:
            lead_date = datetime.fromisoformat(lead.get('created_at', ''))
            if lead_date > week_ago:
                recent_leads += 1
                src = lead.get('utm_source', lead.get('source', 'direct'))
                leads_by_source[src] = leads_by_source.get(src, 0) + 1
        except:
            pass
    
    text = (
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"📢 <b>Публикации:</b>\n"
        f"• Всего: {total_pubs}\n"
        f"• За 7 дней: {recent_pubs}\n\n"
        f"📋 <b>Заявки:</b>\n"
        f"• Всего: {total_leads}\n"
        f"• За 7 дней: {recent_leads}\n\n"
    )
    
    if leads_by_source:
        text += f"📈 <b>Источники (7 дней):</b>\n"
        for source, count in sorted(leads_by_source.items(), key=lambda x: -x[1]):
            text += f"• {source}: {count}\n"
    
    text += f"\n💡 Подробнее: /leads"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def leads_command(update, context):
    """Команда /leads - последние заявки"""
    user_id = update.effective_user.id
    if not has_publish_rights(user_id):
        return
    
    leads_db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
    
    if not leads_db['leads']:
        await update.message.reply_text("📋 Заявок пока нет")
        return
    
    # Берём последние 10
    leads_list = list(leads_db['leads'].items())
    leads_list.sort(key=lambda x: x[1].get('created_at', ''), reverse=True)
    last_leads = leads_list[:10]
    
    text = f"📋 <b>ПОСЛЕДНИЕ ЗАЯВКИ ({len(last_leads)} из {leads_db['counter']})</b>\n\n"
    
    for lead_id, lead in last_leads:
        try:
            created = datetime.fromisoformat(lead.get('created_at', ''))
            date_str = created.strftime('%d.%m %H:%M')
        except:
            date_str = "?"
        
        username = lead.get('username', '?')
        first_name = lead.get('first_name', '')
        
        text += f"<b>{lead_id}</b> | {date_str}\n"
        text += f"👤 @{username} ({first_name})\n"
        
        if lead.get('pub_id'):
            text += f"🚗 {lead.get('car_name', 'авто')[:40]}\n"
        elif lead.get('brand'):
            text += f"🔍 {lead.get('brand', '')} {lead.get('year', '')}\n"
        
        if lead.get('city'):
            text += f"🏙 {lead['city']}\n"
        if lead.get('budget'):
            text += f"💰 {lead['budget']}\n"
        
        text += "━━━━━━━━━━\n"
    
    await update.message.reply_text(text, parse_mode='HTML')

# ════════════════════════════════════════════════════════════════════
# ЭКСПОРТ ДЛЯ ПЛОЩАДОК (Авито/ВК/Дром)
# ════════════════════════════════════════════════════════════════════

async def export_command(update, context):
    """Команда /export — экспорт текстов для разных площадок"""
    user_id = update.effective_user.id
    if not has_publish_rights(user_id):
        return
    
    text = (
        f"📤 <b>ЭКСПОРТ ДЛЯ ПЛОЩАДОК</b>\n\n"
        f"Перешли мне ID публикации в формате:\n"
        f"<code>/export id_0001</code>\n\n"
        f"Получишь текст для:\n"
        f"• 🟢 Авито (раздел Услуги)\n"
        f"• 🟦 ВКонтакте (Маркет)\n"
        f"• 🟡 Дром\n"
        f"• 📋 Авто.ру\n\n"
        f"💡 Тексты оптимизированы под SEO ключевые слова"
    )
    
    args = context.args
    if not args:
        await update.message.reply_text(text, parse_mode='HTML')
        return
    
    pub_id = args[0]
    publication = find_publication(pub_id)
    
    if not publication:
        await update.message.reply_text(f"❌ Публикация {pub_id} не найдена")
        return
    
    original = publication.get('original_caption', '')
    if not original:
        await update.message.reply_text(f"❌ Нет исходного текста для {pub_id}")
        return
    
    # Генерируем варианты
    avito_text = generate_avito_text(original, pub_id, publication)
    vk_text = generate_vk_text(original, pub_id, publication)
    drom_text = generate_drom_text(original, pub_id, publication)
    autoru_text = generate_autoru_text(original, pub_id, publication)
    
    # Отправляем по очереди
    await update.message.reply_text(
        f"📤 <b>ЭКСПОРТ {pub_id}</b>\n\n"
        f"Сейчас пришлю 4 версии текста:\n"
        f"1️⃣ Авито\n"
        f"2️⃣ ВКонтакте\n"
        f"3️⃣ Дром\n"
        f"4️⃣ Авто.ру",
        parse_mode='HTML'
    )
    
    await update.message.reply_text(f"🟢 <b>АВИТО (Услуги):</b>\n\n<code>{avito_text}</code>", parse_mode='HTML')
    await update.message.reply_text(f"🟦 <b>ВКОНТАКТЕ:</b>\n\n<code>{vk_text}</code>", parse_mode='HTML')
    await update.message.reply_text(f"🟡 <b>ДРОМ:</b>\n\n<code>{drom_text}</code>", parse_mode='HTML')
    await update.message.reply_text(f"📋 <b>АВТО.РУ:</b>\n\n<code>{autoru_text}</code>", parse_mode='HTML')

def extract_car_info(original_text):
    """Извлекает основную информацию об авто"""
    info = {
        'name': '',
        'year': '',
        'mileage': '',
        'engine': '',
        'price_rub': None,
        'description_lines': []
    }
    
    cleaned = remove_all_emojis(original_text)
    cleaned = remove_old_contacts(cleaned)
    lines = cleaned.split('\n')
    
    # Название - первая значимая строка
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('•'):
            info['name'] = stripped[:80]
            break
    
    # Парсим характеристики
    for line in lines:
        line_lower = line.lower()
        if 'год' in line_lower and ':' in line:
            info['year'] = line.split(':', 1)[1].strip()[:20]
        elif 'пробег' in line_lower and ':' in line:
            info['mileage'] = line.split(':', 1)[1].strip()[:30]
        elif 'двигател' in line_lower and ':' in line:
            info['engine'] = line.split(':', 1)[1].strip()[:50]
    
    # Цена в рублях
    price_match = re.search(r'(\d[\d\s.,]*\d)\s*(?:₽|руб)', cleaned)
    if price_match:
        try:
            info['price_rub'] = int(re.sub(r'[\s,.]', '', price_match.group(1)))
        except:
            pass
    
    return info

def generate_avito_text(original_text, pub_id, publication):
    """Текст для Авито (раздел Услуги — пригон автомобиля)"""
    info = extract_car_info(original_text)
    name = info.get('name', 'автомобиля')
    
    # Применяем наценку
    formatted_original = apply_price_markup(remove_old_contacts(remove_all_emojis(original_text)))
    
    text = (
        f"🚗 Подбор и доставка под заказ: {name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Профессионально подберём и доставим автомобиль из Кореи, Японии, Германии, Китая и США.\n\n"
        f"📋 ХАРАКТЕРИСТИКИ КОНКРЕТНОГО ВАРИАНТА:\n\n"
        f"{formatted_original}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ ЧТО ВКЛЮЧЕНО:\n"
        f"• Подбор автомобиля по Вашим параметрам\n"
        f"• Проверка истории и состояния\n"
        f"• Полное оформление документов\n"
        f"• Растаможка под ключ\n"
        f"• Доставка в Ваш город\n"
        f"• Гарантия чистоты сделки\n\n"
        f"📞 СВЯЗЬ:\n"
        f"Telegram: t.me/{BOT_USERNAME}?start={pub_id}\n"
        f"Менеджер: {MANAGER_LINK}\n\n"
        f"🔑 КЛЮЧЕВЫЕ СЛОВА:\n"
        f"авто под заказ, пригон автомобиля, авто из Кореи, авто из Японии, "
        f"автомобиль с пробегом, авто на заказ Москва, доставка авто РФ, "
        f"подбор автомобиля, импорт авто, растаможка"
    )
    return text

def generate_vk_text(original_text, pub_id, publication):
    """Текст для ВК (Маркет / стена)"""
    info = extract_car_info(original_text)
    formatted = apply_price_markup(remove_old_contacts(remove_all_emojis(original_text)))
    
    text = (
        f"🚗 {info.get('name', 'Автомобиль под заказ')}\n\n"
        f"{formatted}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💼 ProAuto — подбор и доставка автомобилей по России и СНГ\n\n"
        f"✅ Прозрачные цены\n"
        f"✅ Полное юридическое сопровождение\n"
        f"✅ Доставка в любой город РФ\n"
        f"✅ Гарантия качества\n\n"
        f"📞 Связаться с менеджером:\n"
        f"Telegram: t.me/{BOT_USERNAME}?start={pub_id}\n\n"
        f"#автоподзаказ #авто #автомобиль #автоизкореи #автоизяпонии #автоизгермании "
        f"#пригонавто #автонапрокат #купитьавто #автосалон"
    )
    return text

def generate_drom_text(original_text, pub_id, publication):
    """Текст для Дром"""
    info = extract_car_info(original_text)
    formatted = apply_price_markup(remove_old_contacts(remove_all_emojis(original_text)))
    
    text = (
        f"Услуга подбора и доставки: {info.get('name', 'автомобиля')}\n\n"
        f"{formatted}\n\n"
        f"---\n"
        f"Поможем подобрать и привезти любой автомобиль:\n"
        f"• Корея, Япония, Германия, Китай, США\n"
        f"• Доставка во все города РФ\n"
        f"• Растаможка под ключ\n"
        f"• Юридическое сопровождение\n\n"
        f"Связь: t.me/{BOT_USERNAME}?start={pub_id}\n"
        f"Менеджер: {MANAGER_LINK}"
    )
    return text

def generate_autoru_text(original_text, pub_id, publication):
    """Текст для Авто.ру"""
    info = extract_car_info(original_text)
    formatted = apply_price_markup(remove_old_contacts(remove_all_emojis(original_text)))
    
    text = (
        f"{info.get('name', 'Автомобиль')} — под заказ\n\n"
        f"{formatted}\n\n"
        f"Услуги подбора и доставки:\n"
        f"— Проверка истории\n"
        f"— Растаможка\n"
        f"— Юр. оформление\n"
        f"— Доставка в любой город\n\n"
        f"Telegram: t.me/{BOT_USERNAME}?start={pub_id}\n"
        f"Связь с менеджером: {MANAGER_LINK}"
    )
    return text

# ════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════════════

async def handle_message(update, context):
    try:
        message = update.message
        if not message:
            return
        
        user_id = message.from_user.id
        has_rights = has_publish_rights(user_id)
        text = message.text or message.caption or ""
        
        logger.info(f"📨 От ID:{user_id} (Права: {has_rights})")
        
        # Проверяем активный опросник
        state = get_user_state(user_id)
        if state.get('step') and not has_rights:
            # Пользователь в процессе опросника — игнорируем обычные сообщения
            await message.reply_text(
                "ℹ️ Используйте кнопки выше для продолжения опроса"
            )
            return
        
        # ═══ ВЛАДЕЛЕЦ / МЕНЕДЖЕР ═══
        if has_rights:
            source_info = extract_forward_source(message)
            
            # Проверяем есть ли ID публикации в тексте
            existing_id = extract_pub_id_from_text(text)
            
            if existing_id:
                # Ищем оригинал
                publication = find_publication(existing_id)
                if publication:
                    source_link = publication.get('source_link', 'нет ссылки')
                    source_name = publication.get('source_username', 'неизвестно')
                    response = (
                        f"🔗 <b>ПУБЛИКАЦИЯ {existing_id}</b>\n\n"
                        f"Источник: <code>{source_name}</code>\n\n"
                        f"<b>Оригинал:</b>\n{source_link}"
                    )
                    await context.bot.send_message(
                        chat_id=message.chat_id,
                        text=response,
                        parse_mode='HTML'
                    )
                else:
                    await message.reply_text(f"❌ {existing_id} не найдено")
                return
            
            # Если переслано из канала
            if source_info['is_forwarded']:
                await handle_announcement(update, context, source_info)
            elif message.photo:
                # Свой текст с фото
                await handle_announcement(update, context, None)
            else:
                await message.reply_text(
                    "ℹ️ Пересылай объявления из каналов или используй команды:\n"
                    "/stats — статистика\n"
                    "/leads — заявки\n"
                    "/export id_XXXX — экспорт для площадок"
                )
        
        # ═══ КЛИЕНТ ═══
        else:
            # Если уже в брифе — игнорируем (обработка через кнопки)
            if state.get('step'):
                return
            
            # Запускаем общий бриф
            await start_general_brief(update, context)
    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════
# ОЧИСТКА СТАРЫХ ДАННЫХ
# ════════════════════════════════════════════════════════════════════

def cleanup_old_publications():
    """Архивируем публикации старше 30 дней"""
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    now = datetime.now()
    cleaned = 0
    
    for pub_id, pub in list(db['publications'].items()):
        try:
            expires = datetime.fromisoformat(pub.get('expires_at', ''))
            if now > expires and not pub.get('archived'):
                # Оставляем только ссылку
                db['publications'][pub_id] = {
                    'source_link': pub.get('source_link'),
                    'source_username': pub.get('source_username'),
                    'archived': True,
                    'archived_at': now.isoformat()
                }
                cleaned += 1
        except:
            pass
    
    if cleaned > 0:
        save_db(PUBLICATIONS_DB, db)
        logger.info(f"🧹 Архивировано {cleaned} публикаций")

# ════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК
# ════════════════════════════════════════════════════════════════════

async def post_init(application):
    """Действия при запуске"""
    cleanup_old_publications()
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v9 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"BOT: @{BOT_USERNAME}")
    logger.info(f"Владелец ID: {OWNER_ID}")
    logger.info(f"Менеджер ID: {MANAGER_USER_ID}")
    logger.info(f"Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"{'='*70}")
    logger.info(f"\n💰 ЛЕСТНИЦА НАЦЕНОК (₽):")
    logger.info(f"  < 5 млн: +40,000")
    logger.info(f"  5-7 млн: +80,000")
    logger.info(f"  7-10 млн: +100,000")
    logger.info(f"  10-15 млн: +180,000")
    logger.info(f"  15-20 млн: +250,000")
    logger.info(f"  20-25 млн: +350,000")
    logger.info(f"  25-30 млн: +500,000")
    logger.info(f"  30+ млн: +1,000,000")
    logger.info(f"  EUR/USD: +1,000")
    logger.info(f"\n{'='*70}")
    logger.info(f"✅ ГОТОВО К РАБОТЕ\n")

def main():
    """Запуск бота"""
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        # Команды
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("leads", leads_command))
        app.add_handler(CommandHandler("export", export_command))
        app.add_handler(CommandHandler("calculator", calculator_command))
        
        # Callback кнопки
        app.add_handler(CallbackQueryHandler(button_callback))
        
        # Все остальные сообщения
        app.add_handler(MessageHandler(
            filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO,
            handle_message
        ))
        
        # Запуск
        app.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=30
        )
    except Exception as e:
        logger.error(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
