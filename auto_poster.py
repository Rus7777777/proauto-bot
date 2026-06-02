"""
PROAUTO BOT v8 - ФИНАЛЬНАЯ ВЕРСИЯ

✅ Удаление эмодзи 🚚 📍 из исходного текста
✅ Новая лестница наценок цены
✅ ID публикаций со ссылками (id_0001)
✅ База данных публикаций с автоочисткой через месяц
✅ Несколько пользователей с правами (владелец + менеджер)
✅ Исправлены отступы и footer
✅ "Рассчитаем стоимость до Вашего дома 🏠 ✅"
"""

import asyncio
import re
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, ContextTypes, MessageHandler, filters
import logging

load_dotenv()

# ════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv('BOT_TOKEN')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID', '0'))
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME', '@proauto_77')
MANAGER_LINK = os.getenv('MANAGER_LINK', 'https://t.me/rdblm')

OWNER_ID = int(os.getenv('OWNER_ID', '0'))
MANAGER_USER_ID = int(os.getenv('MANAGER_USER_ID', '0'))

SOURCE_CHANNELS = [ch.strip() for ch in os.getenv('SOURCE_CHANNELS', 'M_Supercars,autohaykofficial,FRIEND_AUTO1').split(',')]

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Файлы баз данных
PUBLICATIONS_DB = 'publications.json'  # ID → данные публикации
media_groups_cache = {}

# ════════════════════════════════════════════════════════════════════
# ПРАВА ПОЛЬЗОВАТЕЛЕЙ
# ════════════════════════════════════════════════════════════════════

def has_publish_rights(user_id):
    """Может ли пользователь публиковать (владелец или менеджер)"""
    if user_id == OWNER_ID and OWNER_ID != 0:
        return True
    if user_id == MANAGER_USER_ID and MANAGER_USER_ID != 0:
        return True
    return False

# ════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ ПУБЛИКАЦИЙ
# ════════════════════════════════════════════════════════════════════

def load_publications_db():
    """Загружает БД публикаций"""
    if os.path.exists(PUBLICATIONS_DB):
        try:
            with open(PUBLICATIONS_DB, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'counter': 0, 'publications': {}}
    return {'counter': 0, 'publications': {}}

def save_publications_db(db):
    """Сохраняет БД публикаций"""
    try:
        with open(PUBLICATIONS_DB, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения БД: {e}")

def get_next_publication_id():
    """Получает следующий ID публикации (id_0001, id_0002...)"""
    db = load_publications_db()
    db['counter'] = db.get('counter', 0) + 1
    new_id = f"id_{db['counter']:04d}"
    save_publications_db(db)
    return new_id

def save_publication(pub_id, source_link, source_chat_id, source_message_id, 
                     source_username, published_message_id):
    """Сохраняет публикацию в БД"""
    db = load_publications_db()
    
    now = datetime.now()
    expires = now + timedelta(days=30)
    
    db['publications'][pub_id] = {
        'source_link': source_link,
        'source_chat_id': source_chat_id,
        'source_message_id': source_message_id,
        'source_username': source_username,
        'published_message_id': published_message_id,
        'published_at': now.isoformat(),
        'expires_at': expires.isoformat()
    }
    
    save_publications_db(db)
    logger.info(f"💾 Публикация {pub_id} сохранена (истекает: {expires.strftime('%Y-%m-%d')})")

def find_publication_by_id(pub_id):
    """Ищет публикацию по ID"""
    db = load_publications_db()
    return db['publications'].get(pub_id)

def cleanup_old_publications():
    """Удаляет данные публикаций старше 30 дней (оставляет только ссылки)"""
    db = load_publications_db()
    now = datetime.now()
    cleaned_count = 0
    
    for pub_id, pub_data in list(db['publications'].items()):
        try:
            expires = datetime.fromisoformat(pub_data['expires_at'])
            if now > expires:
                # Оставляем только ссылку
                db['publications'][pub_id] = {
                    'source_link': pub_data.get('source_link'),
                    'source_username': pub_data.get('source_username'),
                    'archived': True
                }
                cleaned_count += 1
        except:
            pass
    
    if cleaned_count > 0:
        save_publications_db(db)
        logger.info(f"🧹 Архивировано {cleaned_count} старых публикаций")

# ════════════════════════════════════════════════════════════════════
# УДАЛЕНИЕ ЭМОДЗИ
# ════════════════════════════════════════════════════════════════════

# Полный паттерн для эмодзи
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002700-\U000027BF"  # Dingbats
    "\U000024C2-\U0001F251"
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002600-\U000026FF"  # Misc symbols
    "]+",
    flags=re.UNICODE
)

def remove_all_emojis(text):
    """Удаляет ВСЕ эмодзи из текста"""
    return EMOJI_PATTERN.sub('', text)

# ════════════════════════════════════════════════════════════════════
# МАТЕМАТИКА ЦЕН - НОВАЯ ЛЕСТНИЦА
# ════════════════════════════════════════════════════════════════════

def calculate_markup(price, currency):
    """Рассчитывает наценку по новой логике"""
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
            return 40_000  # до 5млн
    elif currency == '€':
        return 1_000
    elif currency == '$':
        return 1_000
    return 0

def calculate_new_price(old_price, currency):
    """Возвращает новую цену с наценкой"""
    return old_price + calculate_markup(old_price, currency)

def format_price_with_dots(price):
    """Форматирует число с точками: 1235000 → 1.235.000"""
    return f"{price:,}".replace(',', '.')

def replace_price_in_text(match):
    """Заменяет найденную цену на новую"""
    price_str = match.group(1)
    currency = match.group(2)
    
    if currency in ['руб', 'RUB']:
        currency = '₽'
    
    price_clean = re.sub(r'[\s,.\u00a0]', '', price_str)
    
    try:
        old_price = int(price_clean)
        new_price = calculate_new_price(old_price, currency)
        markup = new_price - old_price
        
        # Форматируем
        if currency == '₽':
            new_price_str = format_price_with_dots(new_price)
        else:
            new_price_str = format_price_with_dots(new_price)
        
        logger.info(f"   💰 {format_price_with_dots(old_price)}{currency} +{format_price_with_dots(markup)}{currency} = {new_price_str}{currency}")
        
        return f"{new_price_str}{currency}"
    except:
        return match.group(0)

# ════════════════════════════════════════════════════════════════════
# ОЧИСТКА ТЕКСТА
# ════════════════════════════════════════════════════════════════════

def remove_old_contacts(text):
    """Удаляет старые контакты, ссылки, соц.сети"""
    
    # Удаляем "В продаже" в начале (из autohaykofficial)
    text = re.sub(r'^[\s]*В продаже\s*\n', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\nВ продаже\s*\n', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем строки с упоминаниями каналов
    text = re.sub(r'\[@[A-Za-z0-9_]+\]\(https?://t\.me/[A-Za-z0-9_]+\)', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    
    # Удаляем секцию "НАПИСАТЬ МЕНЕДЖЕРУ" и все ниже
    text = re.sub(
        r'НАПИСАТЬ МЕНЕДЖЕРУ[\s\S]*?(?=Наши соц сети|$)',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем секцию "Наши соц сети"
    text = re.sub(r'Наши соц сети[\s\S]*?$', '', text, flags=re.IGNORECASE)
    
    # Удаляем "Нужна цена под ключ..."
    text = re.sub(
        r'Нужна цена под ключ до вашего дома\??\s*\n?\s*Пишите в личку!?',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем "Доставка осуществляется во все города РФ" (заменим своим footer'ом)
    text = re.sub(
        r'Доставка осуществляется во все города РФ\.?',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем оставшиеся ссылки
    text = re.sub(r'\[[^\]]+\]\(https?://[^\)]+\)', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'Whatsapp\s*\+?[\d\s]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Telegram\s*\+?[\d\s]+', '', text, flags=re.IGNORECASE)
    
    return text

def keep_only_moscow_price(text):
    """Если есть цена в Москве - удаляем другие города"""
    if not re.search(r'в Москве', text, re.IGNORECASE):
        return text
    
    logger.info("   📍 Найдена цена в Москве - удаляем другие города")
    
    # Удаляем строки с другими городами
    text = re.sub(
        r'^.*?(?:Итоговая цена|Цена)[^:\n]*в (?:Уссурийске|Владивостоке)[^:\n]*:[^\n]*\n?',
        '',
        text,
        flags=re.IGNORECASE | re.MULTILINE
    )
    
    return text

# ════════════════════════════════════════════════════════════════════
# ФОРМАТИРОВАНИЕ
# ════════════════════════════════════════════════════════════════════

def is_section_header(line):
    """Является ли строка заголовком секции"""
    headers = ['Комплектация:', 'Состояние:', 'Состояние автомобиля:', 'Опции:']
    line_clean = line.lower().strip()
    return any(h.lower() in line_clean for h in headers) and len(line) < 50

def is_price_line(line):
    """Является ли строка строкой с ценой"""
    return bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]', line))

def format_characteristics(text):
    """Добавляет буллеты • к строкам характеристик"""
    
    lines = text.split('\n')
    result_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            result_lines.append('')
            continue
        
        # Уже с буллетом
        if stripped.startswith('•') or stripped.startswith('▪') or stripped.startswith('●'):
            clean = re.sub(r'^[•▪●]\s*', '', stripped)
            result_lines.append(f'• {clean}')
            continue
        
        # ✅ галочка - заменяем на буллет
        if stripped.startswith('✅'):
            clean = re.sub(r'^✅\s*', '', stripped)
            result_lines.append(f'• {clean}')
            continue
        
        # Характеристика "ключ: значение"
        if ':' in stripped and not is_section_header(stripped) and not is_price_line(stripped):
            # Проверяем что это не "Год", "Пробег" и т.д. - короткое имя поля
            field_part = stripped.split(':')[0].strip()
            if len(field_part) < 40:
                result_lines.append(f'• {stripped}')
                continue
        
        result_lines.append(stripped)
    
    return '\n'.join(result_lines)

def make_section_headers_bold(text):
    """Делает заголовки секций жирными"""
    headers = ['Комплектация:', 'Состояние:', 'Состояние автомобиля:', 'Опции:']
    
    for header in headers:
        pattern = re.escape(header)
        replacement = f'<b>{header}</b>'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text

def make_model_name_bold(text):
    """Делает название модели (первая значимая строка) жирной"""
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if not stripped:
            continue
        
        if not stripped.startswith('•') and not stripped.startswith('<b>'):
            lines[i] = f'<b>{stripped}</b>'
            logger.info(f"   📝 Модель жирным: {stripped[:40]}...")
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
    """Исправляет отступы:
    - Над "Комплектация:", "Состояние:" - убираем пустые строки сверху
    - Одна пустая строка между секциями
    """
    
    # Заменяем 3+ переноса на 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Перед заголовками секций должна быть ОДНА пустая строка
    # Заменяем "\n\n<b>Комплектация:</b>" → "\n<b>Комплектация:</b>"
    # Нет - наоборот: исключаем лишний \n перед заголовком
    
    # Перед "Комплектация:" и "Состояние:" - только 1 \n (то есть прямо на следующей строке)
    section_headers = ['<b>Комплектация:</b>', '<b>Состояние:</b>', '<b>Состояние автомобиля:</b>']
    
    for header in section_headers:
        # \n\n перед заголовком → \n
        escaped = re.escape(header)
        text = re.sub(rf'\n\n+({escaped})', rf'\n\1', text)
    
    # После заголовков "Комплектация:", "Состояние:" не должно быть пустой строки
    for header in section_headers:
        escaped = re.escape(header)
        text = re.sub(rf'({escaped})\n\n+', rf'\1\n', text)
    
    # Очищаем пустые строки в начале и конце
    text = text.strip()
    
    return text

def apply_price_markup(text):
    """Применяет наценку ко всем ценам"""
    patterns = [
        (r'(\d[\d\s.,\u00a0]*\d)\s*(₽|руб|RUB)', None),
        (r'(\d[\d\s.,\u00a0]*\d)\s*(€)', None),
        (r'(\d[\d\s.,\u00a0]*\d)\s*(\$)', None),
    ]
    
    for pattern, _ in patterns:
        text = re.sub(pattern, replace_price_in_text, text)
    
    return text

def determine_footer_type(text):
    """
    Определяет тип footer'а:
    - 'delivery' - есть "Цена в Москве" или "Владивостоке" → доставка
    - 'calculate' - евро/доллары/нет города → рассчитаем стоимость
    """
    text_lower = text.lower()
    
    if 'в москве' in text_lower or 'во владивостоке' in text_lower or 'итоговая цена' in text_lower:
        return 'delivery'
    
    if '€' in text or '$' in text:
        return 'calculate'
    
    if 'до вашего города' in text_lower or 'до вашего дома' in text_lower:
        return 'calculate'
    
    return 'delivery'

def build_footer(footer_type, pub_id, publication_link):
    """Создаёт footer"""
    
    # ID публикации - первая строка (сделаем потом)
    
    # Footer
    manager_link = f'<a href="{MANAGER_LINK}">«Написать менеджеру»</a> 📞 ✅'
    channel_link = f'<a href="https://t.me/{TARGET_CHANNEL_NAME.replace("@", "")}">{TARGET_CHANNEL_NAME}</a>'
    
    if footer_type == 'delivery':
        footer = (
            f"\n\nДоставка осуществляется во все города РФ\n\n"
            f"По поводу покупки данного автомобиля или подбора:\n"
            f"{manager_link}\n"
            f"(Ответ в течении 1ч)\n\n"
            f"{channel_link}"
        )
    else:
        footer = (
            f"\n\nРассчитаем стоимость до Вашего дома 🏠 ✅\n"
            f"{manager_link}\n"
            f"(Ответ в течении 1ч)\n\n"
            f"{channel_link}"
        )
    
    return footer

# ════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ
# ════════════════════════════════════════════════════════════════════

def format_announcement(original_text, pub_id, publication_link):
    """ГЛАВНАЯ ФУНКЦИЯ ФОРМАТИРОВАНИЯ"""
    if not original_text:
        return None
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🔧 ОБРАБОТКА ТЕКСТА для {pub_id}")
    logger.info(f"{'='*70}")
    
    text = original_text
    
    # ШАГ 1: Удаляем ВСЕ эмодзи из исходного текста
    logger.info(f"🧹 Шаг 1: Удаление эмодзи...")
    text = remove_all_emojis(text)
    
    # ШАГ 2: Удаляем старые контакты
    logger.info(f"🧹 Шаг 2: Удаление контактов...")
    text = remove_old_contacts(text)
    
    # ШАГ 3: Применяем наценку
    logger.info(f"💰 Шаг 3: Наценка...")
    text = apply_price_markup(text)
    
    # ШАГ 4: Оставляем только Москву
    text = keep_only_moscow_price(text)
    
    # ШАГ 5: Определяем тип footer'а
    footer_type = determine_footer_type(text)
    logger.info(f"📌 Footer type: {footer_type}")
    
    # ШАГ 6: Буллеты для характеристик
    text = format_characteristics(text)
    
    # ШАГ 7: Жирные заголовки секций
    text = make_section_headers_bold(text)
    
    # ШАГ 8: Жирное название модели
    text = make_model_name_bold(text)
    
    # ШАГ 9: Жирные цены
    text = make_price_lines_bold(text)
    
    # ШАГ 10: Исправляем отступы
    text = fix_spacing(text)
    
    # ШАГ 11: Собираем финальный текст
    # ID публикации - первая строка как кликабельная ссылка
    if publication_link:
        id_line = f'<a href="{publication_link}">{pub_id}</a>'
    else:
        id_line = pub_id
    
    header = f"{id_line}\n\nПрямая продажа ✅\n\n"
    footer = build_footer(footer_type, pub_id, publication_link)
    
    final = header + text + footer
    
    logger.info(f"✅ ТЕКСТ ГОТОВ")
    logger.info(f"{'='*70}\n")
    
    return final

# ════════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ И ПОИСК ID В ТЕКСТЕ
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text, has_photo):
    if not has_photo:
        return False, "нет фото"
    
    if not text or len(text) < 20:
        return False, "короткий текст"
    
    has_price = bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]|\d[\d\s.,\u00a0]*\d\s*руб', text))
    has_keywords = bool(re.search(
        r'BMW|Mercedes|Audi|Toyota|Geely|Kia|Mazda|Volkswagen|Porsche|Rolls-Royce|Honda|Hyundai|Volvo|Ford|Nissan|Lamborghini|Ferrari|Bentley|Lexus|Infiniti|авто|машин|двигател',
        text, re.IGNORECASE
    ))
    
    if has_price or has_keywords:
        return True, "OK"
    
    return False, "не авто"

def extract_pub_id_from_text(text):
    """Извлекает ID публикации из текста (id_0001 и т.д.)"""
    if not text:
        return None
    
    match = re.search(r'id_(\d{4})', text)
    if match:
        return f"id_{match.group(1)}"
    return None

# ════════════════════════════════════════════════════════════════════
# ИСТОЧНИК
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

def generate_publication_link(message_id):
    """Генерирует ссылку на нашу публикацию в @proauto_77"""
    channel = TARGET_CHANNEL_NAME.replace('@', '')
    return f"https://t.me/{channel}/{message_id}"

# ════════════════════════════════════════════════════════════════════
# ОБРАБОТКА АЛЬБОМОВ
# ════════════════════════════════════════════════════════════════════

async def process_media_group(media_group_id, context):
    """Обрабатывает альбом"""
    await asyncio.sleep(3)
    
    if media_group_id not in media_groups_cache:
        return
    
    group_data = media_groups_cache[media_group_id]
    photos = group_data['photos']
    caption = group_data['caption']
    source_info = group_data['source_info']
    
    logger.info(f"\n📸 АЛЬБОМ: {len(photos)} фото")
    
    if not photos:
        del media_groups_cache[media_group_id]
        return
    
    valid, reason = is_valid_announcement(caption, True)
    if not valid:
        logger.info(f"⏭️ {reason}")
        del media_groups_cache[media_group_id]
        return
    
    # Получаем ID и ссылку
    pub_id = get_next_publication_id()
    logger.info(f"🆔 ID: {pub_id}")
    
    # Источник
    source_link = generate_original_link(source_info)
    
    # Сначала публикуем БЕЗ ID ссылки (нужно знать message_id)
    formatted_text = format_announcement(caption, pub_id, None)
    if not formatted_text:
        del media_groups_cache[media_group_id]
        return
    
    try:
        media = []
        for i, photo_id in enumerate(photos):
            if i == 0:
                media.append(InputMediaPhoto(
                    media=photo_id,
                    caption=formatted_text,
                    parse_mode='HTML'
                ))
            else:
                media.append(InputMediaPhoto(media=photo_id))
        
        sent_messages = await context.bot.send_media_group(
            chat_id=TARGET_GROUP_ID,
            media=media
        )
        
        # Получаем ID опубликованного сообщения
        published_message_id = sent_messages[0].message_id if sent_messages else None
        publication_link = generate_publication_link(published_message_id) if published_message_id else None
        
        logger.info(f"✅ Альбом опубликован, msg_id: {published_message_id}")
        
        # ПЕРЕРЕДАКТИРУЕМ caption с правильной ссылкой ID
        if publication_link and sent_messages:
            new_caption = format_announcement(caption, pub_id, publication_link)
            try:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID,
                    message_id=sent_messages[0].message_id,
                    caption=new_caption,
                    parse_mode='HTML'
                )
                logger.info(f"✅ Caption обновлён с ссылкой ID")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось обновить caption: {e}")
        
        # Сохраняем в БД
        save_publication(
            pub_id=pub_id,
            source_link=source_link,
            source_chat_id=source_info['source_chat_id'],
            source_message_id=source_info['source_message_id'],
            source_username=source_info['source_chat_username'],
            published_message_id=published_message_id
        )
        
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
    """Обработка объявления"""
    message = update.message
    media_group_id = message.media_group_id
    
    # Альбом
    if media_group_id:
        if media_group_id not in media_groups_cache:
            media_groups_cache[media_group_id] = {
                'photos': [],
                'caption': '',
                'chat_id': message.chat_id,
                'source_info': source_info
            }
            asyncio.create_task(process_media_group(media_group_id, context))
        
        if message.photo:
            photo_id = message.photo[-1].file_id
            media_groups_cache[media_group_id]['photos'].append(photo_id)
        
        if message.caption and not media_groups_cache[media_group_id]['caption']:
            media_groups_cache[media_group_id]['caption'] = message.caption
        
        return
    
    # Одиночное сообщение
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        logger.info(f"⏭️ {reason}")
        return
    
    pub_id = get_next_publication_id()
    logger.info(f"🆔 ID: {pub_id}")
    
    source_link = generate_original_link(source_info) if source_info else None
    
    formatted = format_announcement(text, pub_id, None)
    if not formatted:
        return
    
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
            pub_id=pub_id,
            source_link=source_link,
            source_chat_id=source_info['source_chat_id'] if source_info else None,
            source_message_id=source_info['source_message_id'] if source_info else None,
            source_username=source_info['source_chat_username'] if source_info else None,
            published_message_id=published_message_id
        )
        
        logger.info(f"✅ Опубликовано {pub_id}\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════
# ПОИСК ПО ID
# ════════════════════════════════════════════════════════════════════

async def handle_id_search(update, context, pub_id):
    """Поиск оригинала по ID публикации"""
    message = update.message
    
    publication = find_publication_by_id(pub_id)
    
    if not publication:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"❌ Публикация {pub_id} не найдена в базе"
        )
        return
    
    source_link = publication.get('source_link')
    source_username = publication.get('source_username', 'Неизвестный')
    
    response = (
        f"🔗 <b>ПУБЛИКАЦИЯ {pub_id}</b>\n\n"
        f"Источник: <code>{source_username}</code>\n\n"
        f"<b>Ссылка на оригинал:</b>\n"
        f"{source_link}\n\n"
        f"<i>Нажми чтобы перейти к оригинальному объявлению</i>"
    )
    
    await context.bot.send_message(
        chat_id=message.chat_id,
        text=response,
        parse_mode='HTML',
        disable_web_page_preview=False
    )
    
    logger.info(f"✅ Найден оригинал для {pub_id}: {source_link}")

# ════════════════════════════════════════════════════════════════════
# ПОИСК ПО ПЕРЕСЛНОМУ СООБЩЕНИЮ
# ════════════════════════════════════════════════════════════════════

async def handle_search_by_forward(update, context, source_info):
    """Поиск оригинала по переслному сообщению"""
    message = update.message
    
    original_link = generate_original_link(source_info)
    
    if original_link:
        source_name = source_info['source_chat_username'] or source_info['source_chat_title']
        
        response = (
            f"🔗 <b>ОРИГИНАЛЬНОЕ ОБЪЯВЛЕНИЕ</b>\n\n"
            f"Источник: <code>{source_name}</code>\n\n"
            f"<b>Ссылка:</b>\n"
            f"{original_link}"
        )
        
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response,
            parse_mode='HTML'
        )
        
        logger.info(f"✅ Ссылка: {original_link}")

# ════════════════════════════════════════════════════════════════════
# КЛИЕНТСКОЕ ОБРАЩЕНИЕ
# ════════════════════════════════════════════════════════════════════

async def handle_customer_inquiry(update, context):
    """Ответ клиенту (не владельцу)"""
    message = update.message
    user = message.from_user
    
    logger.info(f"\n📞 КЛИЕНТ: @{user.username} (ID: {user.id})")
    
    response = (
        f"Здравствуйте! 👋\n\n"
        f"Я представляю компанию <b>ProAuto</b> — мы профессионально занимаемся "
        f"подбором и доставкой автомобилей по всей России и СНГ.\n\n"
        f"<b>Наши преимущества:</b>\n"
        f"• Прозрачные цены без скрытых платежей ✅\n"
        f"• Подбор автомобиля под любой бюджет\n"
        f"• Доставка во все города РФ\n"
        f"• Полное юридическое сопровождение\n"
        f"• Гарантия качества каждого авто\n\n"
        f"<b>Что Вас интересует?</b> Расскажите о Вашем запросе, "
        f"и наш менеджер подберёт лучший вариант лично для Вас!\n\n"
        f"📞 Связь с менеджером напрямую:\n"
        f'<a href="{MANAGER_LINK}">«Написать менеджеру»</a> 📞 ✅\n'
        f"(Ответ в течении 1 часа)\n\n"
        f"Наш канал с актуальными предложениями:\n"
        f'<a href="https://t.me/{TARGET_CHANNEL_NAME.replace("@", "")}">{TARGET_CHANNEL_NAME}</a>'
    )
    
    try:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        logger.info(f"✅ Ответ клиенту")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК
# ════════════════════════════════════════════════════════════════════

async def handle_message(update, context):
    try:
        message = update.message
        if not message:
            return
        
        user_id = message.from_user.id
        has_rights = has_publish_rights(user_id)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📨 От ID:{user_id} (Права: {has_rights})")
        logger.info(f"{'='*70}")
        
        # ВЛАДЕЛЕЦ/МЕНЕДЖЕР
        if has_rights:
            source_info = extract_forward_source(message)
            text = message.text or message.caption or ""
            
            # Проверяем есть ли ID публикации в тексте
            existing_id = extract_pub_id_from_text(text)
            
            if existing_id:
                logger.info(f"🔎 Найден ID {existing_id} - ищем оригинал")
                await handle_id_search(update, context, existing_id)
                return
            
            # Если переслано
            if source_info['is_forwarded']:
                username = source_info['source_chat_username']
                logger.info(f"📍 Переслано из: @{username or 'private'}")
                
                if username and username in SOURCE_CHANNELS:
                    logger.info(f"→ ОБРАБОТКА И ПУБЛИКАЦИЯ")
                    await handle_announcement(update, context, source_info)
                else:
                    logger.info(f"→ ПОИСК ОРИГИНАЛА")
                    await handle_search_by_forward(update, context, source_info)
            else:
                # Не переслано - может быть свой текст
                if message.photo:
                    logger.info(f"→ Обработка собственного объявления")
                    await handle_announcement(update, context, None)
        
        # КЛИЕНТ
        else:
            await handle_customer_inquiry(update, context)
    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def start_command(update, context):
    try:
        user_id = update.message.from_user.id
        
        if has_publish_rights(user_id):
            text = (
                f"🚀 <b>PROAUTO BOT v8</b>\n\n"
                f"Готов к работе. Пересылай объявления."
            )
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            await handle_customer_inquiry(update, context)
    except Exception as e:
        logger.error(f"Ошибка /start: {e}")

# ════════════════════════════════════════════════════════════════════
# ЗАПУСК
# ════════════════════════════════════════════════════════════════════

async def post_init(application):
    # Запускаем очистку старых публикаций
    cleanup_old_publications()
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v8 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"BOT: @proauto_23_bot")
    logger.info(f"Владелец: {OWNER_ID}")
    logger.info(f"Менеджер: {MANAGER_USER_ID}")
    logger.info(f"Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"Источники: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"\nЛестница наценок (₽):")
    logger.info(f"  < 5млн: +40,000")
    logger.info(f"  5-7млн: +80,000")
    logger.info(f"  7-10млн: +100,000")
    logger.info(f"  10-15млн: +180,000")
    logger.info(f"  15-20млн: +250,000")
    logger.info(f"  20-25млн: +350,000")
    logger.info(f"  25-30млн: +500,000")
    logger.info(f"  30+млн: +1,000,000")
    logger.info(f"\nЕвро/Доллары: +1,000")
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
            timeout=30
        )
    except Exception as e:
        logger.error(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
