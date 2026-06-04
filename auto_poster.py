"""
PROAUTO BOT v10 - ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ

✅ Бесконечных циклов нет
✅ ID идёт с 0004 (правильная нумерация)
✅ ID под ценой
✅ Удаление фраз "Пишите нам" / "Звоните"
✅ Чистая логика брифа (specific_car и custom пути)
✅ Всё работает без глюков
"""

import asyncio
import re
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import (
    Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, ContextTypes, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters
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
media_groups_cache = {}
BRIEF_STATES = {}

# ════════════════════════════════════════════════════════════════════
# ИМПОРТ БАЗЫ АВТО
# ════════════════════════════════════════════════════════════════════

try:
    from car_database import CAR_DATABASE, HASHTAGS, get_brands, get_models, get_generations
except ImportError:
    logger.warning("⚠️ car_database.py не найден. Используем встроенные данные.")
    CAR_DATABASE = {}
    HASHTAGS = {'general': [], 'search_keywords': []}
    def get_brands(): return []
    def get_models(b): return []
    def get_generations(b, m): return []

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
# ФУНКЦИИ БД
# ════════════════════════════════════════════════════════════════════

def load_db(filename, default=None):
    """Загружает БД из файла"""
    if default is None:
        default = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")
            return default
    return default

def save_db(filename, data):
    """Сохраняет БД в файл"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {filename}: {e}")

def get_next_publication_id():
    """Получает следующий ID публикации (id_0001, id_0002...)"""
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    
    # Увеличиваем счётчик
    db['counter'] = db.get('counter', 0) + 1
    new_id = f"id_{db['counter']:04d}"
    
    # ОБЯЗАТЕЛЬНО сохраняем сразу
    save_db(PUBLICATIONS_DB, db)
    
    logger.info(f"🆔 Новый ID: {new_id}")
    return new_id

def save_publication(pub_id, **kwargs):
    """Сохраняет публикацию в БД"""
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    db['publications'][pub_id] = {
        **kwargs,
        'published_at': datetime.now().isoformat(),
        'expires_at': (datetime.now() + timedelta(days=30)).isoformat()
    }
    save_db(PUBLICATIONS_DB, db)
    logger.info(f"💾 {pub_id} сохранён")

def find_publication(pub_id):
    """Ищет публикацию по ID"""
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    return db['publications'].get(pub_id)

def get_next_lead_id():
    """Получает следующий ID заявки"""
    db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
    db['counter'] = db.get('counter', 0) + 1
    new_id = f"lead_{db['counter']:05d}"
    save_db(LEADS_DB, db)
    return new_id

def save_lead(lead_id, data):
    """Сохраняет заявку"""
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
    """Удаляет ВСЕ эмодзи"""
    return EMOJI_PATTERN.sub('', text)

# ════════════════════════════════════════════════════════════════════
# ОЧИСТКА ТЕКСТА ОТ КОНТАКТОВ И ФРАЗ
# ════════════════════════════════════════════════════════════════════

PHRASES_TO_REMOVE = [
    r'пишите\s+(?:нам|в\s+личку|в\s+ди)',
    r'звоните\s+(?:нам|в\s+личку)',
    r'свяжитесь\s+(?:с\s+нами|в\s+личку)',
    r'написать\s+(?:нам|в\s+личку)',
    r'обращайтесь\s+(?:к\s+нам|в\s+личку)',
    r'контакт(?:ы)?:?\s*\+?\d[\d\s\-()]*',
    r'телефон:?\s*\+?\d[\d\s\-()]*',
    r'whatsapp:?\s*\+?\d[\d\s\-()]*',
    r'telegram:?\s*\+?\d[\d\s\-()]*',
]

def remove_old_contacts(text):
    """ИСПРАВЛЕНО: Удаляет контакты и фразы 'Пишите нам'"""
    
    # Удаляем "В продаже" в начале
    text = re.sub(r'^[\s]*В продаже\s*\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\nВ продаже\s*\n', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем фразы типа "Пишите нам", "Звоните", "Свяжитесь"
    for phrase in PHRASES_TO_REMOVE:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    
    # Удаляем @каналы
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    
    # Удаляем ссылки Telegram
    text = re.sub(r'https?://t\.me/[A-Za-z0-9_/?=]+', '', text)
    
    # Удаляем другие ссылки
    text = re.sub(r'https?://[^\s]+', '', text)
    
    # Удаляем markdown ссылки
    text = re.sub(r'\[[^\]]+\]\(https?://[^\)]+\)', '', text)
    
    # Удаляем секцию "Наши соц сети"
    text = re.sub(r'Наши\s+соц\.?сети[\s\S]*?$', '', text, flags=re.IGNORECASE)
    
    # Удаляем "Доставка осуществляется" (заменим своим footer'ом)
    text = re.sub(r'Доставка\s+осуществляется[^\n]*', '', text, flags=re.IGNORECASE)
    
    # Удаляем номера телефонов (отдельные строки)
    text = re.sub(r'^\s*\+?\d[\d\s\-()]{5,}\s*$', '', text, flags=re.MULTILINE)
    
    return text

def keep_only_moscow_price(text):
    """Если есть цена в Москве - удаляем другие города"""
    if not re.search(r'в москве', text, re.IGNORECASE):
        return text
    
    logger.info("   📍 Москва найдена - удаляем другие города")
    
    text = re.sub(
        r'^.*?(?:Итоговая цена|Цена)[^:\n]*в (?:Уссурийске|Владивостоке)[^:\n]*:[^\n]*\n?',
        '',
        text,
        flags=re.IGNORECASE | re.MULTILINE
    )
    return text

# ════════════════════════════════════════════════════════════════════
# МАТЕМАТИКА ЦЕН
# ════════════════════════════════════════════════════════════════════

def calculate_markup(price, currency):
    """Рассчитывает наценку по лестнице"""
    if currency in ['₽', 'руб', 'RUB']:
        if price >= 30_000_000:
            return 1_000_000
        elif price >= 25_000_000:
            return 500_000
        elif price >= 20_000_000:
            return 350_000
        elif price >= 15_000_000:
            return 250_000
        elif price >= 10_000_000:
            return 180_000
        elif price >= 7_000_000:
            return 100_000
        elif price >= 5_000_000:
            return 80_000
        else:
            return 40_000
    elif currency in ['€', '$']:
        return 1_000
    return 0

def format_price_with_dots(price):
    """Форматирует число с точками: 1235000 → 1.235.000"""
    return f"{price:,}".replace(',', '.')

def replace_price(match):
    """Заменяет найденную цену на новую с наценкой"""
    price_str = match.group(1)
    currency = match.group(2)
    
    if currency in ['руб', 'RUB']:
        currency = '₽'
    
    # Удаляем всё кроме цифр
    price_clean = re.sub(r'[\s,.\u00a0]', '', price_str)
    
    try:
        old_price = int(price_clean)
        markup = calculate_markup(old_price, currency)
        new_price = old_price + markup
        return f"{format_price_with_dots(new_price)}{currency}"
    except:
        return match.group(0)

def apply_price_markup(text):
    """Применяет наценку ко всем ценам в тексте"""
    patterns = [
        r'(\d[\d\s.,\u00a0]*\d)\s*(₽|руб|RUB)',
        r'(\d[\d\s.,\u00a0]*\d)\s*(€)',
        r'(\d[\d\s.,\u00a0]*\d)\s*(\$)',
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, replace_price, text)
    
    return text

# ════════════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ ТЕКСТА
# ════════════════════════════════════════════════════════════════════

def is_section_header(line):
    """Проверяет что это заголовок секции"""
    headers = ['Комплектация:', 'Состояние:', 'Состояние автомобиля:', 'Опции:']
    line_clean = line.lower().strip()
    return any(h.lower() in line_clean for h in headers) and len(line) < 50

def is_price_line(line):
    """Проверяет что это строка с ценой"""
    return bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]', line))

def format_characteristics(text):
    """ИСПРАВЛЕНО: Добавляет буллеты, но НЕ создаёт пустые"""
    lines = text.split('\n')
    result_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            result_lines.append('')
            continue
        
        # Уже с буллетом - оставляем
        if stripped.startswith('•') or stripped.startswith('▪'):
            clean = re.sub(r'^[•▪]\s*', '', stripped)
            if clean:  # ТОЛЬКО если есть текст!
                result_lines.append(f'• {clean}')
            continue
        
        # Характеристика "поле: значение"
        if ':' in stripped and not is_section_header(stripped) and not is_price_line(stripped):
            field = stripped.split(':')[0].strip()
            value = stripped.split(':', 1)[1].strip() if ':' in stripped else ''
            if len(field) < 40 and value:  # ВАЖНО: есть поле И значение
                result_lines.append(f'• {stripped}')
                continue
        
        result_lines.append(stripped)
    
    return '\n'.join(result_lines)

def make_section_headers_bold(text):
    """Делает заголовки секций жирными"""
    headers = ['Комплектация:', 'Состояние:', 'Состояние автомобиля:', 'Опции:']
    for header in headers:
        text = re.sub(re.escape(header), f'<b>{header}</b>', text, flags=re.IGNORECASE)
    return text

def make_model_name_bold(text):
    """Делает название модели (первая строка) жирным"""
    lines = text.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith('•') and not stripped.startswith('<b>'):
            lines[i] = f'<b>{stripped}</b>'
            logger.info(f"   📝 Модель: {stripped[:50]}")
            break
    return '\n'.join(lines)

def make_price_lines_bold(text):
    """Делает строки с ценой жирными"""
    pattern = r'^([^\n<]*\d[\d\s.,\u00a0]*\d\s*[₽€$][^\n<]*)$'
    
    def make_bold(match):
        line = match.group(1).strip()
        if not line.startswith('<b>'):
            return f'<b>{line}</b>'
        return line
    
    return re.sub(pattern, make_bold, text, flags=re.MULTILINE)

def fix_spacing(text):
    """Исправляет отступы между секциями"""
    # Убираем 3+ пустых строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Перед заголовками секций только одна пустая строка
    section_headers = ['<b>Комплектация:</b>', '<b>Состояние:</b>', '<b>Состояние автомобиля:</b>']
    for header in section_headers:
        escaped = re.escape(header)
        text = re.sub(rf'\n\n+({escaped})', rf'\n\1', text)
        text = re.sub(rf'({escaped})\n\n+', rf'\1\n', text)
    
    return text.strip()

def determine_footer_type(text):
    """Определяет тип footer'а"""
    text_lower = text.lower()
    
    if 'в москве' in text_lower or 'во владивостоке' in text_lower:
        return 'delivery'
    if '€' in text or '$' in text:
        return 'calculate'
    
    return 'delivery'

def build_footer(footer_type, pub_id, publication_link):
    """ИСПРАВЛЕНО: ID идёт ПОСЛЕ цены в footer'е"""
    
    manager_link = f'<a href="{MANAGER_LINK}?start={pub_id}">«Написать менеджеру»</a> 📞 ✅'
    channel_link = f'<a href="https://t.me/{TARGET_CHANNEL_NAME.replace("@", "")}">{TARGET_CHANNEL_NAME}</a>'
    
    if footer_type == 'delivery':
        footer = (
            f"\n\nДоставка осуществляется во все города РФ\n\n"
            f"По поводу покупки данного автомобиля или подбора:\n"
            f"{manager_link}\n"
            f"(Ответ в течении 1ч)"
        )
    else:
        footer = (
            f"\n\nРассчитаем стоимость до Вашего дома 🏠 ✅\n"
            f"{manager_link}\n"
            f"(Ответ в течении 1ч)"
        )
    
    # ID идёт ПОСЛЕ всего
    if publication_link:
        footer += f"\n\n<a href=\"{publication_link}\">{pub_id}</a>"
    else:
        footer += f"\n\n{pub_id}"
    
    footer += f"\n\n{channel_link}"
    
    return footer

def format_announcement(original_text, pub_id, publication_link):
    """ГЛАВНАЯ функция форматирования"""
    if not original_text:
        return None
    
    logger.info(f"\n🔧 Форматирование {pub_id}")
    
    text = original_text
    
    # ШАГ 1: Удаляем эмодзи
    text = remove_all_emojis(text)
    
    # ШАГ 2: Удаляем контакты и фразы
    text = remove_old_contacts(text)
    
    # ШАГ 3: Применяем наценку
    text = apply_price_markup(text)
    
    # ШАГ 4: Оставляем только Москву если есть
    text = keep_only_moscow_price(text)
    
    # ШАГ 5: Определяем тип footer
    footer_type = determine_footer_type(text)
    
    # ШАГ 6: Форматируем характеристики
    text = format_characteristics(text)
    
    # ШАГ 7: Жирные заголовки
    text = make_section_headers_bold(text)
    
    # ШАГ 8: Жирное название
    text = make_model_name_bold(text)
    
    # ШАГ 9: Жирные цены
    text = make_price_lines_bold(text)
    
    # ШАГ 10: Исправляем отступы
    text = fix_spacing(text)
    
    # ШАГ 11: Собираем финальный текст
    header = "Прямая продажа ✅\n\n"
    footer = build_footer(footer_type, pub_id, publication_link)
    
    final = header + text + footer
    
    logger.info(f"✅ Готово")
    return final
    # ════════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ ОБЪЯВЛЕНИЙ
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text, has_photo):
    """Проверяет валидность объявления"""
    if not has_photo:
        return False, "нет фото"
    
    if not text or len(text) < 20:
        return False, "короткий текст"
    
    # Проверяем наличие цены или ключевых слов
    has_price = bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]|\d[\d\s.,\u00a0]*\d\s*руб', text))
    
    has_keywords = bool(re.search(
        r'BMW|Mercedes|Audi|Toyota|Geely|Kia|Mazda|Volkswagen|Porsche|Rolls-Royce|Honda|Hyundai|'
        r'Volvo|Ford|Nissan|Lamborghini|Ferrari|Bentley|Lexus|Infiniti|Tesla|Chery|Haval|BYD|'
        r'авто|машин|двигател|автомобиль',
        text, re.IGNORECASE
    ))
    
    if has_price or has_keywords:
        return True, "OK"
    
    return False, "не авто"

def extract_pub_id_from_text(text):
    """Извлекает ID публикации из текста (id_0001)"""
    if not text:
        return None
    match = re.search(r'id_(\d{4})', text)
    if match:
        return f"id_{match.group(1)}"
    return None

# ════════════════════════════════════════════════════════════════════
# ИНФОРМАЦИЯ ОБ ИСТОЧНИКЕ
# ════════════════════════════════════════════════════════════════════

def extract_forward_source(message):
    """Извлекает информацию об источнике переслания"""
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
    """Генерирует ссылку на оригинальное объявление"""
    if not source_info.get('is_forwarded'):
        return None
    
    msg_id = source_info['source_message_id']
    username = source_info['source_chat_username']
    chat_id = source_info['source_chat_id']
    
    # Если есть username - используем его
    if username:
        return f"https://t.me/{username}/{msg_id}"
    
    # Если приватный чат - используем ID
    if str(chat_id).startswith('-100'):
        chat_id_clean = str(chat_id)[4:]
    else:
        chat_id_clean = str(abs(chat_id))
    
    return f"https://t.me/c/{chat_id_clean}/{msg_id}"

def generate_publication_link(message_id):
    """Генерирует ссылку на нашу публикацию в @proauto_77"""
    channel = TARGET_CHANNEL_NAME.replace('@', '')
    return f"https://t.me/{channel}/{message_id}"

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА АЛЬБОМОВ (несколько фото)
# ════════════════════════════════════════════════════════════════════

async def process_media_group(media_group_id, context):
    """Обрабатывает альбом из нескольких фото"""
    await asyncio.sleep(3)
    
    if media_group_id not in media_groups_cache:
        return
    
    group_data = media_groups_cache[media_group_id]
    photos = group_data['photos']
    caption = group_data['caption']
    source_info = group_data['source_info']
    
    logger.info(f"📸 Альбом: {len(photos)} фото")
    
    if not photos:
        del media_groups_cache[media_group_id]
        return
    
    # Валидируем
    valid, reason = is_valid_announcement(caption, True)
    if not valid:
        logger.info(f"⏭️ {reason}")
        del media_groups_cache[media_group_id]
        return
    
    # Генерируем ID
    pub_id = get_next_publication_id()
    source_link = generate_original_link(source_info) if source_info else None
    
    # Форматируем текст БЕЗ ссылки (узнаём ID поста позже)
    formatted_text = format_announcement(caption, pub_id, None)
    if not formatted_text:
        del media_groups_cache[media_group_id]
        return
    
    try:
        # Собираем альбом
        media = []
        for i, photo_id in enumerate(photos):
            if i == 0:
                media.append(InputMediaPhoto(media=photo_id, caption=formatted_text, parse_mode='HTML'))
            else:
                media.append(InputMediaPhoto(media=photo_id))
        
        # Публикуем в группу
        sent_messages = await context.bot.send_media_group(
            chat_id=TARGET_GROUP_ID,
            media=media
        )
        
        published_message_id = sent_messages[0].message_id if sent_messages else None
        publication_link = generate_publication_link(published_message_id) if published_message_id else None
        
        logger.info(f"✅ Альбом опубликован, msg_id: {published_message_id}")
        
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
                logger.info(f"✅ Caption обновлён с ссылкой")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось обновить caption: {e}")
        
        # Сохраняем в БД
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
        
    except Exception as e:
        logger.error(f"❌ Ошибка альбома: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    finally:
        if media_group_id in media_groups_cache:
            del media_groups_cache[media_group_id]

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ОДИНОЧНЫХ ОБЪЯВЛЕНИЙ
# ════════════════════════════════════════════════════════════════════

async def handle_announcement(update, context, source_info):
    """Обрабатывает объявление (с альбомами или одиночное)"""
    message = update.message
    media_group_id = message.media_group_id
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    # ───────────────────────────────────────────
    # АЛЬБОМ - собираем и обрабатываем через 3 сек
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
    
    # ───────────────────────────────────────────
    # ОДИНОЧНОЕ СООБЩЕНИЕ
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        logger.info(f"⏭️ {reason}")
        return
    
    pub_id = get_next_publication_id()
    source_link = generate_original_link(source_info) if source_info else None
    
    formatted = format_announcement(text, pub_id, None)
    if not formatted:
        return
    
    try:
        # Отправляем фото или текст
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
        
        # Обновляем с правильной ссылкой ID
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
        
        # Сохраняем в БД
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
        import traceback
        logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЕ МЕНЕДЖЕРУ
# ════════════════════════════════════════════════════════════════════

async def notify_manager(context, lead_id, lead_data):
    """Отправляет заявку менеджеру в ЛС"""
    if not MANAGER_USER_ID and not OWNER_ID:
        return
    
    text = f"🆕 <b>ЗАЯВКА {lead_id}</b>\n\n"
    
    # Клиент
    if lead_data.get('username'):
        text += f"👤 @{lead_data['username']} "
    text += f"({lead_data.get('first_name', '')} {lead_data.get('last_name', '')})\n"
    text += f"🆔 User ID: <code>{lead_data['user_id']}</code>\n\n"
    
    # Авто (если конкретное)
    if lead_data.get('pub_id'):
        text += f"🚗 <b>Интересует:</b> {lead_data.get('car_name', '')}\n"
        text += f"({lead_data['pub_id']})\n\n"
    
    # Детали заявки
    text += f"📋 <b>Параметры:</b>\n"
    if lead_data.get('brand'):
        text += f"• Марка: {lead_data['brand']}\n"
    if lead_data.get('model'):
        text += f"• Модель: {lead_data['model']}\n"
    if lead_data.get('generation'):
        text += f"• Поколение: {lead_data['generation']}\n"
    if lead_data.get('city'):
        text += f"• Город: {lead_data['city']}\n"
    if lead_data.get('timing'):
        text += f"• Срок: {lead_data['timing']}\n"
    
    # Контакт
    text += f"\n💬 <a href='tg://user?id={lead_data['user_id']}'>Написать клиенту</a>"
    
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
                logger.error(f"⚠️ Не удалось уведомить {recipient_id}: {e}")

# ════════════════════════════════════════════════════════════════════
# DEEP LINKING И СТАРТ БРИФА
# ════════════════════════════════════════════════════════════════════

CITIES = ['Москва', 'Санкт-Петербург', 'Краснодар', 'Сочи', 'Екатеринбург', 
          'Новосибирск', 'Казань', 'Ростов-на-Дону', 'Нижний Новгород', 'Воронеж']

TIMINGS = ['В этом месяце', '1-2 месяца', '3-6 месяцев', 'Просто смотрю']

BRAND_GROUPS = {
    '🇩🇪 Немецкие': ['BMW', 'Mercedes-Benz', 'Audi', 'Volkswagen', 'Porsche'],
    '🇯🇵 Японские': ['Toyota', 'Honda', 'Nissan', 'Mazda', 'Lexus', 'Subaru'],
    '🇰🇷 Корейские': ['Kia', 'Hyundai', 'Genesis'],
    '🇨🇳 Китайские': ['Geely', 'Haval', 'BYD', 'Chery'],
    '🇺🇸 Американские': ['Tesla', 'Ford', 'Chevrolet'],
    '⚡ Премиум': ['Ferrari', 'Lamborghini', 'Bentley', 'Rolls-Royce'],
}

# Состояния опросника
SPECIFIC_ASK_CITY = 'specific_ask_city'
SPECIFIC_ASK_TIMING = 'specific_ask_timing'
SPECIFIC_FINALIZE = 'specific_finalize'

CUSTOM_ASK_BRAND_GROUP = 'custom_ask_brand_group'
CUSTOM_ASK_BRAND = 'custom_ask_brand'
CUSTOM_ASK_MODEL = 'custom_ask_model'
CUSTOM_ASK_GENERATION = 'custom_ask_generation'
CUSTOM_ASK_TIMING = 'custom_ask_timing'
CUSTOM_ASK_CITY = 'custom_ask_city'
CUSTOM_FINALIZE = 'custom_finalize'

def get_user_state(user_id):
    """Получает состояние пользователя"""
    if user_id not in BRIEF_STATES:
        BRIEF_STATES[user_id] = {'step': None, 'data': {}}
    return BRIEF_STATES[user_id]

def clear_user_state(user_id):
    """Очищает состояние пользователя"""
    if user_id in BRIEF_STATES:
        del BRIEF_STATES[user_id]
        # ════════════════════════════════════════════════════════════════════
# ФУНКЦИИ БРИФА: КОНКРЕТНОЕ АВТО (SPECIFIC_CAR ПУТЬ)
# ════════════════════════════════════════════════════════════════════

async def specific_ask_city(update, context, user_id):
    """Шаг 1: Город доставки (для конкретного авто)"""
    state = get_user_state(user_id)
    state['step'] = SPECIFIC_ASK_CITY
    
    keyboard = []
    row = []
    for i, city in enumerate(CITIES):
        row.append(InlineKeyboardButton(city, callback_data=f"specific_city_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✍️ Другой город", callback_data="specific_city_other")])
    
    text = "🏙 <b>В какой город нужна доставка?</b>"
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def specific_ask_timing(update, context, user_id):
    """Шаг 2: Сроки покупки (для конкретного авто)"""
    state = get_user_state(user_id)
    state['step'] = SPECIFIC_ASK_TIMING
    
    keyboard = [[InlineKeyboardButton(t, callback_data=f"specific_timing_{i}")] 
                for i, t in enumerate(TIMINGS)]
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏰ <b>Когда планируете покупку?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def specific_finalize(update, context, user_id):
    """Завершение: Сохранение заявки (для конкретного авто)"""
    state = get_user_state(user_id)
    data = state['data']
    user = update.effective_user
    
    lead_id = get_next_lead_id()
    
    lead_data = {
        'user_id': user_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'pub_id': data.get('pub_id'),
        'car_name': data.get('car_name'),
        'city': data.get('city'),
        'timing': data.get('timing'),
        'interest_type': 'specific_car'
    }
    
    save_lead(lead_id, lead_data)
    
    # Сообщение клиенту
    client_text = (
        f"✅ <b>Спасибо! Ваша заявка #{lead_id} принята</b>\n\n"
        f"🚗 <b>Интересует:</b> {data.get('car_name', 'автомобиль')}\n"
        f"📍 <b>Доставка в:</b> {data.get('city', '?')}\n"
        f"⏰ <b>Срок:</b> {data.get('timing', '?')}\n\n"
        f"📞 Менеджер свяжется с Вами в течение <b>1 часа</b>\n\n"
        f"Благодарим за доверие к ProAuto ✅\n\n"
        f"Наш канал с актуальными предложениями:\n"
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

# ════════════════════════════════════════════════════════════════════
# ФУНКЦИИ БРИФА: ИНДИВИДУАЛЬНЫЙ ЗАКАЗ (CUSTOM ПУТЬ)
# ════════════════════════════════════════════════════════════════════

async def custom_ask_brand_group(update, context, user_id):
    """Шаг 1: Группа марок"""
    state = get_user_state(user_id)
    state['step'] = CUSTOM_ASK_BRAND_GROUP
    
    keyboard = [[InlineKeyboardButton(g, callback_data=f"custom_bgroup_{i}")] 
                for i, g in enumerate(BRAND_GROUPS.keys())]
    keyboard.append([InlineKeyboardButton("🤔 Любая марка", callback_data="custom_bgroup_any")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="🚗 <b>Какие марки Вас интересуют?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def custom_ask_brand(update, context, user_id, group_idx):
    """Шаг 2: Конкретная марка"""
    state = get_user_state(user_id)
    state['step'] = CUSTOM_ASK_BRAND
    state['data']['brand_group_idx'] = group_idx
    
    group_name = list(BRAND_GROUPS.keys())[group_idx]
    brands = BRAND_GROUPS[group_name]
    
    keyboard = []
    row = []
    for i, brand in enumerate(brands):
        row.append(InlineKeyboardButton(brand, callback_data=f"custom_brand_{group_idx}_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="custom_back_to_groups")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"<b>{group_name}</b>\n\nВыберите марку:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def custom_ask_model(update, context, user_id):
    """Шаг 3: Модель"""
    state = get_user_state(user_id)
    state['step'] = CUSTOM_ASK_MODEL
    
    brand = state['data'].get('brand')
    if not brand or brand == 'Любая':
        state['data']['model'] = 'Любая'
        await custom_ask_generation(update, context, user_id)
        return
    
    models = get_models(brand)
    
    if not models:
        logger.warning(f"⚠️ Нет моделей для {brand}")
        state['data']['model'] = 'Не указана'
        await custom_ask_generation(update, context, user_id)
        return
    
    keyboard = []
    row = []
    for i, model in enumerate(models):
        row.append(InlineKeyboardButton(model, callback_data=f"custom_model_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="custom_back_to_brands")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"<b>{brand}</b>\n\nВыберите модель:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def custom_ask_generation(update, context, user_id):
    """Шаг 4: Поколение"""
    state = get_user_state(user_id)
    state['step'] = CUSTOM_ASK_GENERATION
    
    brand = state['data'].get('brand')
    model = state['data'].get('model')
    
    if not brand or not model or brand == 'Любая' or model == 'Любая':
        state['data']['generation'] = 'Любое'
        await custom_ask_timing(update, context, user_id)
        return
    
    generations = get_generations(brand, model)
    
    if not generations:
        logger.warning(f"⚠️ Нет поколений для {brand} {model}")
        state['data']['generation'] = 'Не указано'
        await custom_ask_timing(update, context, user_id)
        return
    
    keyboard = []
    for i, gen in enumerate(generations):
        keyboard.append([InlineKeyboardButton(gen, callback_data=f"custom_gen_{i}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="custom_back_to_models")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"<b>{brand} {model}</b>\n\nВыберите поколение:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def custom_ask_timing(update, context, user_id):
    """Шаг 5: Сроки покупки"""
    state = get_user_state(user_id)
    state['step'] = CUSTOM_ASK_TIMING
    
    keyboard = [[InlineKeyboardButton(t, callback_data=f"custom_timing_{i}")] 
                for i, t in enumerate(TIMINGS)]
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="⏰ <b>Когда планируете покупку?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def custom_ask_city(update, context, user_id):
    """Шаг 6: Город доставки"""
    state = get_user_state(user_id)
    state['step'] = CUSTOM_ASK_CITY
    
    keyboard = []
    row = []
    for i, city in enumerate(CITIES):
        row.append(InlineKeyboardButton(city, callback_data=f"custom_city_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✍️ Другой город", callback_data="custom_city_other")])
    
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text="🏙 <b>В какой город нужна доставка?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def custom_finalize(update, context, user_id):
    """Завершение: Сохранение заявки (для индивидуального заказа)"""
    state = get_user_state(user_id)
    data = state['data']
    user = update.effective_user
    
    lead_id = get_next_lead_id()
    
    lead_data = {
        'user_id': user_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'brand': data.get('brand'),
        'model': data.get('model'),
        'generation': data.get('generation'),
        'timing': data.get('timing'),
        'city': data.get('city'),
        'interest_type': 'custom'
    }
    
    save_lead(lead_id, lead_data)
    
    # Формируем название авто
    car_info = f"{data.get('brand', '')} {data.get('model', '')}".strip()
    if data.get('generation') and data.get('generation') != 'Любое':
        car_info += f" ({data['generation']})"
    if not car_info or car_info.strip() == '':
        car_info = "выбранный автомобиль"
    
    # Сообщение клиенту
    client_text = (
        f"✅ <b>Спасибо! Ваша заявка #{lead_id} принята</b>\n\n"
        f"🚗 <b>Подбираем:</b> {car_info}\n"
        f"📍 <b>Доставка в:</b> {data.get('city', '?')}\n"
        f"⏰ <b>Срок:</b> {data.get('timing', '?')}\n\n"
        f"📞 Менеджер свяжется с Вами в течение <b>1 часа</b>\n\n"
        f"Благодарим за доверие к ProAuto ✅\n\n"
        f"Наш канал с актуальными предложениями:\n"
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

# ════════════════════════════════════════════════════════════════════
# СТАРТ БРИФА ДЛЯ КОНКРЕТНОГО АВТО (DEEP LINK)
# ════════════════════════════════════════════════════════════════════

async def start_brief_for_specific_car(update, context, pub_id):
    """Старт брифа для конкретного авто (из deep link)"""
    publication = find_publication(pub_id)
    
    if publication:
        original = publication.get('original_caption', '')
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
    state = get_user_state(user_id)
    
    state['step'] = SPECIFIC_ASK_CITY
    state['data'] = {
        'pub_id': pub_id,
        'car_name': car_name,
        'source': 'deep_link',
        'interest_type': 'specific_car'
    }
    
    text = (
        f"🚗 <b>Видим что интересует:</b>\n\n"
        f"{car_name} ({pub_id})\n\n"
        f"✅ Отлично! Уточним пару деталей:"
    )
    
    keyboard = []
    row = []
    for i, city in enumerate(CITIES):
        row.append(InlineKeyboardButton(city, callback_data=f"specific_city_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✍️ Другой город", callback_data="specific_city_other")])
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

# ════════════════════════════════════════════════════════════════════
# ОБЩИЙ БРИФ (БЕЗ DEEP LINK)
# ════════════════════════════════════════════════════════════════════

async def start_general_brief(update, context):
    """Старт общего брифа (для клиента без deep link)"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    state['step'] = CUSTOM_ASK_BRAND_GROUP
    state['data'] = {'source': 'direct', 'interest_type': 'custom'}
    
    text = (
        f"Здравствуйте! 👋\n\n"
        f"Я представляю компанию <b>ProAuto</b> — мы профессионально занимаемся "
        f"подбором и доставкой автомобилей по всей России и СНГ.\n\n"
        f"<b>Наши преимущества:</b>\n"
        f"• Прозрачные цены без скрытых платежей ✅\n"
        f"• Подбор автомобиля под любой бюджет\n"
        f"• Доставка во все города РФ\n"
        f"• Полное юридическое сопровождение\n"
        f"• Гарантия качества каждого авто\n\n"
        f"<b>Какие марки Вас интересуют?</b>"
    )
    
    keyboard = [[InlineKeyboardButton(g, callback_data=f"custom_bgroup_{i}")] 
                for i, g in enumerate(BRAND_GROUPS.keys())]
    keyboard.append([InlineKeyboardButton("🤔 Любая марка", callback_data="custom_bgroup_any")])
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        disable_web_page_preview=True
    )
    # ════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER - ОБРАБОТКА КНОПОК (ИСПРАВЛЕННЫЙ БЕЗ ЦИКЛОВ)
# ════════════════════════════════════════════════════════════════════

async def button_callback(update, context):
    """Главный обработчик всех нажатий кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    state = get_user_state(user_id)
    
    logger.info(f"🔘 Кнопка от {user_id}: {data[:30]}")
    
    # ═══════════════════════════════════════════════════════════════════
    # ПУТЬ 1: КОНКРЕТНОЕ АВТО (SPECIFIC_CAR)
    # ═══════════════════════════════════════════════════════════════════
    
    # Начало: клиент выбрал "Да, интересует этот авто"
    if data.startswith("brief_yes_"):
        pub_id = data.replace("brief_yes_", "")
        await start_brief_for_specific_car(update, context, pub_id)
        return
    
    # Шаг 1: Выбор города (SPECIFIC)
    if data.startswith("specific_city_"):
        if data == "specific_city_other":
            state['data']['city'] = 'Другой (уточнить с менеджером)'
        else:
            try:
                idx = int(data.replace("specific_city_", ""))
                state['data']['city'] = CITIES[idx]
            except:
                state['data']['city'] = 'Неизвестно'
        
        logger.info(f"   🏙 Город: {state['data']['city']}")
        
        await query.edit_message_text(
            f"🏙 Город: <b>{state['data']['city']}</b>\n\n⏰ Когда планируете покупку?",
            parse_mode='HTML'
        )
        
        # ПЕРЕХОД: спрашиваем срок
        await specific_ask_timing(update, context, user_id)
        return
    
    # Шаг 2: Выбор сроков (SPECIFIC) → ФИНАЛИЗАЦИЯ
    if data.startswith("specific_timing_"):
        try:
            idx = int(data.replace("specific_timing_", ""))
            state['data']['timing'] = TIMINGS[idx]
        except:
            state['data']['timing'] = 'Не указано'
        
        logger.info(f"   ⏰ Срок: {state['data']['timing']}")
        
        await query.edit_message_text(
            f"⏰ Срок: <b>{state['data']['timing']}</b>\n\n✅ Спасибо за ответы!",
            parse_mode='HTML'
        )
        
        # ФИНАЛИЗАЦИЯ - сохраняем заявку
        await specific_finalize(update, context, user_id)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # ПУТЬ 2: ИНДИВИДУАЛЬНЫЙ ЗАКАЗ (CUSTOM)
    # ═══════════════════════════════════════════════════════════════════
    
    # Начало: клиент выбрал "Индивидуальный заказ"
    if data == "brief_custom":
        state['step'] = CUSTOM_ASK_BRAND_GROUP
        state['data'] = {'source': 'direct', 'interest_type': 'custom'}
        
        await query.edit_message_text("🔍 Подберём идеальное авто для Вас!")
        
        # ПЕРЕХОД: спрашиваем группу марок
        await custom_ask_brand_group(update, context, user_id)
        return
    
    # Шаг 1: Выбор группы марок (CUSTOM)
    if data.startswith("custom_bgroup_"):
        if data == "custom_bgroup_any":
            state['data']['brand'] = 'Любая'
            state['data']['model'] = 'Любая'
            state['data']['generation'] = 'Любое'
            
            logger.info(f"   🚗 Марка: Любая")
            
            await query.edit_message_text("🚗 Марка: <b>Любая</b>\n\n⏰ Когда планируете покупку?")
            
            # ПЕРЕХОД: сразу спрашиваем сроки (пропускаем марку/модель/поколение)
            await custom_ask_timing(update, context, user_id)
            return
        
        try:
            group_idx = int(data.replace("custom_bgroup_", ""))
        except:
            return
        
        logger.info(f"   📁 Группа марок: {list(BRAND_GROUPS.keys())[group_idx]}")
        
        # ПЕРЕХОД: спрашиваем конкретную марку
        await custom_ask_brand(update, context, user_id, group_idx)
        return
    
    # Шаг 2: Выбор конкретной марки (CUSTOM)
    if data.startswith("custom_brand_"):
        try:
            parts = data.split("_")
            group_idx = int(parts[2])
            brand_idx = int(parts[3])
            
            group_name = list(BRAND_GROUPS.keys())[group_idx]
            brand = BRAND_GROUPS[group_name][brand_idx]
            
            state['data']['brand'] = brand
            state['data']['brand_group'] = group_name
            
            logger.info(f"   🏷 Марка: {brand}")
            
            await query.edit_message_text(f"✅ Марка: <b>{brand}</b>\n\nВыбираем модель...")
        except Exception as e:
            logger.error(f"Ошибка выбора марки: {e}")
            return
        
        # ПЕРЕХОД: спрашиваем модель
        await custom_ask_model(update, context, user_id)
        return
    
    # Шаг 3: Выбор модели (CUSTOM)
    if data.startswith("custom_model_"):
        try:
            idx = int(data.replace("custom_model_", ""))
            brand = state['data'].get('brand')
            
            if not brand:
                logger.error("Нет марки в state")
                return
            
            models = get_models(brand)
            if idx >= len(models):
                logger.error(f"Индекс модели выходит за границы: {idx}")
                return
            
            model = models[idx]
            state['data']['model'] = model
            
            logger.info(f"   📋 Модель: {model}")
            
            await query.edit_message_text(f"✅ Модель: <b>{model}</b>\n\nВыбираем поколение...")
        except Exception as e:
            logger.error(f"Ошибка выбора модели: {e}")
            return
        
        # ПЕРЕХОД: спрашиваем поколение
        await custom_ask_generation(update, context, user_id)
        return
    
    # Шаг 4: Выбор поколения (CUSTOM)
    if data.startswith("custom_gen_"):
        try:
            idx = int(data.replace("custom_gen_", ""))
            brand = state['data'].get('brand')
            model = state['data'].get('model')
            
            if not brand or not model:
                logger.error("Нет марки или модели в state")
                return
            
            generations = get_generations(brand, model)
            if idx >= len(generations):
                logger.error(f"Индекс поколения выходит за границы: {idx}")
                return
            
            generation = generations[idx]
            state['data']['generation'] = generation
            
            logger.info(f"   👶 Поколение: {generation}")
            
            await query.edit_message_text(f"✅ Поколение: <b>{generation}</b>\n\n⏰ Сроки покупки...")
        except Exception as e:
            logger.error(f"Ошибка выбора поколения: {e}")
            return
        
        # ПЕРЕХОД: спрашиваем сроки
        await custom_ask_timing(update, context, user_id)
        return
    
    # Шаг 5: Выбор сроков (CUSTOM)
    if data.startswith("custom_timing_"):
        try:
            idx = int(data.replace("custom_timing_", ""))
            state['data']['timing'] = TIMINGS[idx]
        except:
            state['data']['timing'] = 'Не указано'
        
        logger.info(f"   ⏰ Срок: {state['data']['timing']}")
        
        await query.edit_message_text(
            f"⏰ Срок: <b>{state['data']['timing']}</b>\n\n🏙 Выбираем город доставки...",
            parse_mode='HTML'
        )
        
        # ПЕРЕХОД: спрашиваем город
        await custom_ask_city(update, context, user_id)
        return
    
    # Шаг 6: Выбор города (CUSTOM) → ФИНАЛИЗАЦИЯ
    if data.startswith("custom_city_"):
        if data == "custom_city_other":
            state['data']['city'] = 'Другой (уточнить с менеджером)'
        else:
            try:
                idx = int(data.replace("custom_city_", ""))
                state['data']['city'] = CITIES[idx]
            except:
                state['data']['city'] = 'Неизвестно'
        
        logger.info(f"   🏙 Город: {state['data']['city']}")
        
        await query.edit_message_text(
            f"🏙 Город: <b>{state['data']['city']}</b>\n\n✅ Спасибо за ответы!",
            parse_mode='HTML'
        )
        
        # ФИНАЛИЗАЦИЯ - сохраняем заявку
        await custom_finalize(update, context, user_id)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # НАВИГАЦИЯ "НАЗАД"
    # ═══════════════════════════════════════════════════════════════════
    
    # Назад к группам марок
    if data == "custom_back_to_groups":
        logger.info("   ⬅️ Назад: к группам марок")
        await custom_ask_brand_group(update, context, user_id)
        return
    
    # Назад к маркам
    if data == "custom_back_to_brands":
        logger.info("   ⬅️ Назад: к маркам")
        group_idx = state['data'].get('brand_group_idx', 0)
        await custom_ask_brand(update, context, user_id, group_idx)
        return
    
    # Назад к моделям
    if data == "custom_back_to_models":
        logger.info("   ⬅️ Назад: к моделям")
        await custom_ask_model(update, context, user_id)
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # ВОПРОС (ДРУГОЕ)
    # ═══════════════════════════════════════════════════════════════════
    
    if data == "brief_question":
        logger.info("   ❓ Клиент выбрал: У меня другой вопрос")
        
        state['data']['interest_type'] = 'question'
        
        await query.edit_message_text(
            f"💬 <b>Напишите Ваш вопрос менеджеру:</b>\n\n"
            f"📞 <a href='{MANAGER_LINK}'>«Написать менеджеру»</a> 📞 ✅\n"
            f"(Ответ в течении 1ч)",
            parse_mode='HTML'
        )
        
        clear_user_state(user_id)
        return
    
    logger.warning(f"⚠️ Неизвестная кнопка: {data}")
    # ════════════════════════════════════════════════════════════════════
# КОМАНДА /START (DEEP LINKING)
# ════════════════════════════════════════════════════════════════════

async def start_command(update, context):
    """Команда /start с поддержкой deep linking"""
    user_id = update.effective_user.id
    args = context.args
    
    logger.info(f"👤 /start от ID:{user_id}, args: {args}")
    
    # Проверяем deep link параметр
    if args:
        param = args[0]
        
        # ID публикации (id_0001, id_0002...)
        if param.startswith('id_'):
            logger.info(f"🔗 Deep link: {param}")
            await start_brief_for_specific_car(update, context, param)
            return
        
        # UTM-метки
        if param.startswith('utm_'):
            source = param.replace('utm_', '')
            logger.info(f"📊 UTM источник: {source}")
            state = get_user_state(user_id)
            state['data']['utm_source'] = source
    
    # ───────────────────────────────────────────
    # ВЛАДЕЛЕЦ / МЕНЕДЖЕР
    if has_publish_rights(user_id):
        text = (
            f"🚀 <b>PROAUTO BOT v10 — Админ-панель</b>\n\n"
            f"<b>Команды:</b>\n"
            f"• 📤 Пересылай объявления → публикую в {TARGET_CHANNEL_NAME}\n"
            f"• 🔎 /export id_XXXX → текст для Авито/ВК/Дром\n"
            f"• 📊 /stats → статистика\n"
            f"• 📋 /leads → последние заявки\n\n"
            f"<b>Для клиентов:</b>\n"
            f"• 📱 Пересылай мне объявления → они переходят в бриф\n"
            f"• 🔗 Ссылка из поста → открывает бриф для конкретного авто"
        )
        await update.message.reply_text(text, parse_mode='HTML')
    
    # ───────────────────────────────────────────
    # КЛИЕНТ
    else:
        await start_general_brief(update, context)

# ════════════════════════════════════════════════════════════════════
# КОМАНДА /STATS
# ════════════════════════════════════════════════════════════════════

async def stats_command(update, context):
    """Статистика публикаций и заявок"""
    user_id = update.effective_user.id
    
    if not has_publish_rights(user_id):
        await update.message.reply_text("❌ Нет прав")
        return
    
    pubs_db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    leads_db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
    
    total_pubs = pubs_db.get('counter', 0)
    total_leads = leads_db.get('counter', 0)
    
    # Статистика за 7 дней
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
    for lead in leads_db['leads'].values():
        try:
            lead_date = datetime.fromisoformat(lead.get('created_at', ''))
            if lead_date > week_ago:
                recent_leads += 1
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
        f"📈 Конверсия: {round(recent_leads / max(recent_pubs, 1) * 100, 1)}% (заявки/публикации)"
    )
    
    await update.message.reply_text(text, parse_mode='HTML')

# ════════════════════════════════════════════════════════════════════
# КОМАНДА /LEADS
# ════════════════════════════════════════════════════════════════════

async def leads_command(update, context):
    """Последние заявки"""
    user_id = update.effective_user.id
    
    if not has_publish_rights(user_id):
        await update.message.reply_text("❌ Нет прав")
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
            text += f"🔍 {lead.get('brand', '')} {lead.get('model', '')}\n"
        
        if lead.get('city'):
            text += f"🏙 {lead['city']}\n"
        if lead.get('timing'):
            text += f"⏰ {lead['timing']}\n"
        
        text += "━━━━━━━━━━\n"
    
    # Telegram ограничивает сообщение на 4096 символов
    if len(text) > 4000:
        text = text[:3950] + "\n\n... (сокращено)"
    
    await update.message.reply_text(text, parse_mode='HTML')

# ════════════════════════════════════════════════════════════════════
# КОМАНДА /EXPORT (экспорт текстов для площадок)
# ════════════════════════════════════════════════════════════════════

async def export_command(update, context):
    """Экспорт текста для Авито/ВК/Дром"""
    user_id = update.effective_user.id
    
    if not has_publish_rights(user_id):
        await update.message.reply_text("❌ Нет прав")
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "📤 <b>Экспорт текстов для площадок</b>\n\n"
            "Используй: <code>/export id_0001</code>\n\n"
            "Получишь текст для:\n"
            "• Авито (раздел Услуги)\n"
            "• ВКонтакте\n"
            "• Дром\n"
            "• Авто.ру",
            parse_mode='HTML'
        )
        return
    
    pub_id = args[0]
    publication = find_publication(pub_id)
    
    if not publication:
        await update.message.reply_text(f"❌ {pub_id} не найдено")
        return
    
    original = publication.get('original_caption', '')
    if not original:
        await update.message.reply_text(f"❌ Нет текста для {pub_id}")
        return
    
    # Очищаем текст
    cleaned = remove_all_emojis(original)
    cleaned = remove_old_contacts(cleaned)
    cleaned = apply_price_markup(cleaned)
    
    # ───────────────────────────────────────────
    # АВИТО
    avito_text = (
        f"🚗 Подбор и доставка автомобиля под заказ\n\n"
        f"{cleaned}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ ЧТО ВКЛЮЧЕНО:\n"
        f"• Подбор по параметрам\n"
        f"• Проверка состояния\n"
        f"• Оформление документов\n"
        f"• Растаможка под ключ\n"
        f"• Доставка в ваш город\n"
        f"• Гарантия чистоты сделки\n\n"
        f"📞 Telegram: t.me/{BOT_USERNAME}?start={pub_id}\n"
        f"Менеджер: {MANAGER_LINK}\n\n"
        f"🔑 КЛЮЧИ:\n"
        f"авто под заказ, пригон автомобиля, авто из кореи, авто из японии, "
        f"подбор автомобиля, доставка авто, растаможка, импорт авто"
    )
    
    # ───────────────────────────────────────────
    # ВК
    vk_text = (
        f"🚗 Подбор и доставка автомобилей\n\n"
        f"{cleaned}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💼 ProAuto — подбор авто по России и СНГ\n\n"
        f"✅ Прозрачные цены\n"
        f"✅ Юридическое сопровождение\n"
        f"✅ Доставка в любой город\n"
        f"✅ Гарантия\n\n"
        f"📞 Telegram: t.me/{BOT_USERNAME}?start={pub_id}\n\n"
        f"#авто #автомобиль #автоподзаказ #пригонавто #авточастно"
    )
    
    # ───────────────────────────────────────────
    # ДРОМ
    drom_text = (
        f"Услуга подбора и доставки автомобиля\n\n"
        f"{cleaned}\n\n"
        f"Поможем с подбором:\n"
        f"✅ Из Кореи, Японии, Германии, Китая, США\n"
        f"✅ Доставка по РФ\n"
        f"✅ Растаможка\n"
        f"✅ Юр. оформление\n\n"
        f"Telegram: t.me/{BOT_USERNAME}?start={pub_id}\n"
        f"Менеджер: {MANAGER_LINK}"
    )
    
    # Отправляем текстом (не превышает лимит)
    message_text = (
        f"📤 <b>ЭКСПОРТ {pub_id}</b>\n\n"
        f"Выбери площадку ниже и скопируй текст:\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🟢 АВИТО:\n"
        f"<code>{avito_text[:500]}...</code>\n\n"
        f"🟦 ВКОНТАКТЕ:\n"
        f"<code>{vk_text[:500]}...</code>\n\n"
        f"🟡 ДРОМ:\n"
        f"<code>{drom_text[:500]}...</code>"
    )
    
    await update.message.reply_text(message_text, parse_mode='HTML')
    
    # Отправляем полные тексты в отдельных сообщениях
    await update.message.reply_text(
        f"🟢 <b>АВИТО (полный текст):</b>\n\n<code>{avito_text}</code>",
        parse_mode='HTML'
    )
    
    await update.message.reply_text(
        f"🟦 <b>ВКОНТАКТЕ (полный текст):</b>\n\n<code>{vk_text}</code>",
        parse_mode='HTML'
    )
    
    await update.message.reply_text(
        f"🟡 <b>ДРОМ (полный текст):</b>\n\n<code>{drom_text}</code>",
        parse_mode='HTML'
    )

# ════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════════════

async def handle_message(update, context):
    """Обработка всех текстовых сообщений и фото"""
    try:
        message = update.message
        if not message:
            return
        
        user_id = message.from_user.id
        has_rights = has_publish_rights(user_id)
        text = message.text or message.caption or ""
        
        logger.info(f"📨 От {user_id} (права: {has_rights})")
        
        # ───────────────────────────────────────────
        # ВЛАДЕЛЕЦ / МЕНЕДЖЕР
        if has_rights:
            source_info = extract_forward_source(message)
            
            # Проверяем есть ли ID публикации в тексте
            existing_id = extract_pub_id_from_text(text)
            
            if existing_id:
                # Ищем оригинал
                publication = find_publication(existing_id)
                if publication:
                    source_link = publication.get('source_link', 'нет')
                    source_name = publication.get('source_username', 'неизвестно')
                    response = (
                        f"🔗 <b>{existing_id}</b>\n\n"
                        f"Источник: <code>{source_name}</code>\n\n"
                        f"<b>Оригинал:</b>\n{source_link}"
                    )
                    await message.reply_text(response, parse_mode='HTML')
                else:
                    await message.reply_text(f"❌ {existing_id} не найдено")
                return
            
            # Если переслано из канала/группы
            if source_info['is_forwarded']:
                username = source_info['source_chat_username']
                logger.info(f"📍 От @{username or 'приватная группа'}")
                
                # Обработка как объявление
                await handle_announcement(update, context, source_info)
            
            # Или свой текст с фото
            elif message.photo:
                logger.info(f"📷 Свой текст с фото")
                await handle_announcement(update, context, None)
            
            # Иначе - информация
            else:
                await message.reply_text(
                    "ℹ️ <b>Что я умею:</b>\n\n"
                    "📤 Пересылай объявления → публикую\n"
                    "📸 Отправляй фото + текст → публикую\n"
                    "🔎 Пересылай пост с id_XXXX → ищу оригинал\n\n"
                    "<b>Команды:</b>\n"
                    "/stats — статистика\n"
                    "/leads — заявки\n"
                    "/export id_XXXX — текст для площадок",
                    parse_mode='HTML'
                )
        
        # ───────────────────────────────────────────
        # КЛИЕНТ
        else:
            state = get_user_state(user_id)
            
            # Если уже в брифе - игнорируем (обработка только через кнопки)
            if state.get('step'):
                await message.reply_text(
                    "ℹ️ Используйте кнопки выше для продолжения опроса"
                )
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
    """Архивирует публикации старше 30 дней"""
    db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
    now = datetime.now()
    cleaned = 0
    
    for pub_id, pub in list(db['publications'].items()):
        try:
            expires = datetime.fromisoformat(pub.get('expires_at', ''))
            if now > expires and not pub.get('archived'):
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
        logger.info(f"🧹 Архивировано {cleaned} старых публикаций")
        # ════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ И ЗАПУСК
# ════════════════════════════════════════════════════════════════════

async def post_init(application):
    """Действия при старте бота"""
    cleanup_old_publications()
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v10 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"BOT: @{BOT_USERNAME}")
    logger.info(f"Владелец: {OWNER_ID}")
    logger.info(f"Менеджер: {MANAGER_USER_ID}")
    logger.info(f"Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"Менеджер ссылка: {MANAGER_LINK}")
    logger.info(f"{'='*70}")
    logger.info(f"\n💰 ЛЕСТНИЦА НАЦЕНОК:")
    logger.info(f"  < 5 млн: +40,000₽")
    logger.info(f"  5-7 млн: +80,000₽")
    logger.info(f"  7-10 млн: +100,000₽")
    logger.info(f"  10-15 млн: +180,000₽")
    logger.info(f"  15-20 млн: +250,000₽")
    logger.info(f"  20-25 млн: +350,000₽")
    logger.info(f"  25-30 млн: +500,000₽")
    logger.info(f"  30+ млн: +1,000,000₽")
    logger.info(f"  EUR/USD: +1,000")
    logger.info(f"\n{'='*70}")
    
    # Проверяем БД авто
    if CAR_DATABASE:
        brands_count = len(CAR_DATABASE)
        logger.info(f"📚 БД Автомобилей загружена: {brands_count} марок")
    else:
        logger.warning(f"⚠️ БД Автомобилей НЕ загружена! Используем встроенные данные.")
    
    logger.info(f"✅ БОТ ГОТОВ К РАБОТЕ\n")

def main():
    """Главная функция запуска бота"""
    try:
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        # Регистрируем команды
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("leads", leads_command))
        app.add_handler(CommandHandler("export", export_command))
        
        # Обработчик кнопок (callback)
        app.add_handler(CallbackQueryHandler(button_callback))
        
        # Обработчик всех остальных сообщений (текст, фото, видео)
        app.add_handler(MessageHandler(
            filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO,
            handle_message
        ))
        
        logger.info("🔗 Все обработчики подключены")
        logger.info("⏳ Запуск polling...\n")
        
        # Запуск polling
        app.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=30
        )
    
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
