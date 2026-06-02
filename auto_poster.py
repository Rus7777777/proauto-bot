"""
PROAUTO BOT v7 - ФИНАЛЬНАЯ ВЕРСИЯ
✅ Защита: только владелец публикует
✅ Универсальная обработка всех форматов
✅ Жирный шрифт, эмодзи, кликабельные ссылки
✅ Альбомы из нескольких фото
✅ Умная математика цен (₽/€/$)
✅ Приветствие клиентов как менеджер
"""

import asyncio
import re
import json
import os
from datetime import datetime
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
MANAGER_LINK = os.getenv('MANAGER_LINK', 'https://t.me/rdblm')
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME', '@proauto_77')
PRICE_ADD_RUB = int(os.getenv('PRICE_ADD', 40000))
PRICE_ADD_RUB_BIG = 1000000  # +1млн если цена > 30млн
PRICE_ADD_EUR = 1000
PRICE_ADD_USD = 1000
SOURCE_CHANNELS = [ch.strip() for ch in os.getenv('SOURCE_CHANNELS', 'M_Supercars,autohaykofficial,FRIEND_AUTO1').split(',')]
OWNER_ID = int(os.getenv('OWNER_ID', '0'))

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PROCESSED_FILE = 'processed_posts.json'
media_groups_cache = {}

# ════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
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

# ════════════════════════════════════════════════════════════════════
# ПРОВЕРКА ВЛАДЕЛЬЦА
# ════════════════════════════════════════════════════════════════════

def is_owner(user_id):
    """Проверяет является ли пользователь владельцем"""
    if OWNER_ID == 0:
        logger.warning("OWNER_ID не настроен!")
        return False
    return user_id == OWNER_ID

# ════════════════════════════════════════════════════════════════════
# МАТЕМАТИКА ЦЕН
# ════════════════════════════════════════════════════════════════════

def calculate_new_price(old_price, currency):
    """Считаем новую цену с наценкой"""
    if currency in ['₽', 'руб', 'RUB']:
        if old_price >= 30_000_000:
            return old_price + PRICE_ADD_RUB_BIG  # +1млн
        else:
            return old_price + PRICE_ADD_RUB  # +40k
    elif currency == '€':
        return old_price + PRICE_ADD_EUR  # +1000€
    elif currency == '$':
        return old_price + PRICE_ADD_USD  # +1000$
    return old_price

def format_price_with_dots(price):
    """Форматирует число с точками: 1235000 → 1.235.000"""
    return f"{price:,}".replace(',', '.')

def replace_price_in_text(match):
    """Заменяет найденную цену на новую"""
    price_str = match.group(1)
    currency = match.group(2) if len(match.groups()) >= 2 else '₽'
    
    # Нормализуем валюту
    if currency in ['руб', 'RUB']:
        currency = '₽'
    
    # Очищаем число
    price_clean = re.sub(r'[\s,.\u00a0]', '', price_str)
    
    try:
        old_price = int(price_clean)
        new_price = calculate_new_price(old_price, currency)
        new_price_str = format_price_with_dots(new_price)
        
        logger.info(f"   💰 {old_price:,}{currency} → {new_price:,}{currency}")
        
        return f"{new_price_str}{currency}"
    except:
        return match.group(0)

# ════════════════════════════════════════════════════════════════════
# ОСНОВНАЯ ОБРАБОТКА ТЕКСТА - УНИВЕРСАЛЬНАЯ
# ════════════════════════════════════════════════════════════════════

def remove_old_contacts(text):
    """Удаляет старые контакты, ссылки, соц.сети"""
    
    # Удаляем строки с упоминаниями каналов
    text = re.sub(r'\[@[A-Za-z0-9_]+\]\(https?://t\.me/[A-Za-z0-9_]+\)', '', text)
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    
    # Удаляем секцию "НАПИСАТЬ МЕНЕДЖЕРУ" и все ниже неё (телефоны, whatsapp)
    text = re.sub(
        r'НАПИСАТЬ МЕНЕДЖЕРУ[\s\S]*?(?=Наши соц сети|$)',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем секцию "Наши соц сети" и все ссылки ниже
    text = re.sub(
        r'Наши соц сети[\s\S]*?$',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем "Нужна цена под ключ до вашего дома? Пишите в личку!"
    text = re.sub(
        r'Нужна цена под ключ до вашего дома\??\s*\n?\s*Пишите в личку!?',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем "Доставка осуществляется..." (заменим своим footer'ом)
    text = re.sub(
        r'[🚚📦]?\s*Доставка осуществляется во все города РФ\.?',
        '',
        text,
        flags=re.IGNORECASE
    )
    
    # Удаляем оставшиеся ссылки на сайты и соцсети
    text = re.sub(r'\[[^\]]+\]\(https?://[^\)]+\)', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'Whatsapp\s*\+?[\d\s]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Telegram\s*\+?[\d\s]+', '', text, flags=re.IGNORECASE)
    
    return text

def keep_only_moscow_price(text):
    """
    Если в тексте есть несколько цен с указанием городов,
    оставляем только цену для Москвы
    """
    # Ищем все строки с ценой и городом
    moscow_pattern = r'(Цена[^:]*в Москве[^:]*:|Итоговая цена в Москве:)[\s\S]*?(\d[\d\s.,\u00a0]*\d\s*[₽€$])'
    other_pattern = r'(Итоговая цена в Уссурийске|Цена[^:]*в (?:Уссурийске|Владивостоке)[^:]*):[\s\S]*?\d[\d\s.,\u00a0]*\d\s*[₽€$]'
    
    # Если есть цена в Москве, удаляем цены в других городах
    if re.search(r'в Москве', text, re.IGNORECASE):
        text = re.sub(other_pattern, '', text, flags=re.IGNORECASE)
        logger.info("   📍 Найдена цена в Москве - удаляем другие города")
    
    return text

def format_characteristics(text):
    """Форматирует характеристики с буллетами •"""
    
    lines = text.split('\n')
    result_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            result_lines.append('')
            continue
        
        # Уже есть буллет - оставляем
        if stripped.startswith('•') or stripped.startswith('▪') or stripped.startswith('●'):
            # Нормализуем буллет
            clean = re.sub(r'^[•▪●]\s*', '', stripped)
            result_lines.append(f'• {clean}')
            continue
        
        # Зеленая галочка ✅ - удаляем и ставим буллет
        if stripped.startswith('✅'):
            clean = re.sub(r'^✅\s*', '', stripped)
            result_lines.append(f'• {clean}')
            continue
        
        # Строки с "характеристика: значение" - добавляем буллет
        # Но НЕ заголовки секций и НЕ цены
        if ':' in stripped and not is_section_header(stripped) and not is_price_line(stripped):
            # Это характеристика
            result_lines.append(f'• {stripped}')
            continue
        
        # Остальное оставляем как есть
        result_lines.append(stripped)
    
    return '\n'.join(result_lines)

def is_section_header(line):
    """Является ли строка заголовком секции"""
    headers = [
        'Комплектация:',
        'Состояние:',
        'Состояние автомобиля:',
        'Опции:',
        'Дополнительно:',
        'Особенности:',
    ]
    line_lower = line.lower().strip()
    return any(h.lower() in line_lower for h in headers) and len(line) < 50

def is_price_line(line):
    """Является ли строка строкой с ценой"""
    return bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]', line)) or 'цена' in line.lower()

def make_section_headers_bold(text):
    """Делает заголовки секций жирными (HTML)"""
    headers = [
        'Комплектация:',
        'Состояние:',
        'Состояние автомобиля:',
        'Опции:',
        'Дополнительно:',
    ]
    
    for header in headers:
        # Заменяем заголовок на жирный
        pattern = re.escape(header)
        replacement = f'<b>{header}</b>'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text

def make_model_name_bold(text):
    """Делает первую значимую строку (название модели) жирной"""
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Пропускаем "Прямая продажа", пустые строки и заголовки
        if not stripped or stripped.startswith('Прямая продажа'):
            continue
        
        # Это первая значимая строка - делаем её жирной
        if not stripped.startswith('•') and not stripped.startswith('<b>'):
            lines[i] = f'<b>{stripped}</b>'
            logger.info(f"   📝 Модель жирным: {stripped[:40]}...")
            break
    
    return '\n'.join(lines)

def make_price_lines_bold(text):
    """Делает строки с ценой жирными"""
    # Паттерн: строка содержащая цену
    pattern = r'^([^\n]*\d[\d\s.,\u00a0]*\d\s*[₽€$][^\n]*)$'
    
    def make_bold(match):
        line = match.group(1).strip()
        if not line.startswith('<b>'):
            return f'<b>{line}</b>'
        return line
    
    return re.sub(pattern, make_bold, text, flags=re.MULTILINE)

def apply_price_markup(text):
    """Применяет наценку ко всем ценам в тексте"""
    
    # Паттерны для разных валют
    patterns = [
        # Рубли: 1.035.000₽, 1 035 000 ₽, 1,035,000 руб
        (r'(\d[\d\s.,\u00a0]*\d)\s*(₽|руб|RUB)', '₽'),
        # Евро: 180.000€, 535000 €
        (r'(\d[\d\s.,\u00a0]*\d)\s*(€)', '€'),
        # Доллары: 50.000$, $50000
        (r'(\d[\d\s.,\u00a0]*\d)\s*(\$)', '$'),
    ]
    
    for pattern, default_currency in patterns:
        text = re.sub(pattern, replace_price_in_text, text)
    
    return text

def clean_extra_spaces(text):
    """Очищает лишние пустые строки и пробелы"""
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    text = text.strip()
    return text

def determine_price_format(text):
    """
    Определяет какой использовать footer:
    - "Цена под ключ во Владивостоке" → "Доставка осуществляется во все города РФ"
    - "Под ключ до вашего города" → "Расчитаем стоимость под ключ до вашего дома"
    - С указанием цены в Москве → "Расчитаем стоимость под ключ до вашего дома"
    - Цена в евро/долларах → "Расчитаем стоимость под ключ до вашего дома"
    """
    text_lower = text.lower()
    
    # Если есть "под ключ во Владивостоке" - оставляем доставку
    if 'под ключ во владивосток' in text_lower or 'итоговая цена в москве' in text_lower:
        return 'delivery'  # 🚚 Доставка осуществляется во все города РФ
    
    # Если "до вашего города" или евро/доллары - расчитаем стоимость
    return 'calculate'  # Расчитаем стоимость под ключ до вашего дома

def build_footer(format_type):
    """Создаёт footer в зависимости от типа объявления"""
    
    manager_link = f'<a href="{MANAGER_LINK}">«Написать менеджеру»</a> 📧 📞'
    channel_link = f'<a href="https://t.me/{TARGET_CHANNEL_NAME.replace("@", "")}">{TARGET_CHANNEL_NAME}</a>'
    
    if format_type == 'delivery':
        # Для постов с "Цена в Москве" или "Владивостоке"
        footer = (
            f"\n\n"
            f"🚚 Доставка осуществляется во все города РФ\n\n"
            f"По поводу покупки данного автомобиля или подбора:\n"
            f"  {manager_link}\n"
            f"  (Ответ в течении 1ч)\n\n"
            f"  {channel_link}"
        )
    else:
        # Для постов без указания города/в евро
        footer = (
            f"\n\n"
            f"Расчитаем стоимость под ключ до вашего дома 🏠✅\n"
            f"{manager_link}\n"
            f"  (Ответ в течении 1ч)\n\n"
            f"  {channel_link}"
        )
    
    return footer

def format_announcement(original_text):
    """
    ГЛАВНАЯ ФУНКЦИЯ ОБРАБОТКИ
    Применяет все правила и форматы
    """
    if not original_text:
        return None
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🔧 НАЧАЛО ОБРАБОТКИ ТЕКСТА")
    logger.info(f"{'='*70}")
    logger.info(f"📥 Исходный текст ({len(original_text)} симв)")
    
    text = original_text
    
    # ШАГ 1: Удаляем старые контакты
    logger.info(f"🧹 Шаг 1: Удаление контактов...")
    text = remove_old_contacts(text)
    
    # ШАГ 2: Применяем наценку к ценам
    logger.info(f"💰 Шаг 2: Применение наценки...")
    text = apply_price_markup(text)
    
    # ШАГ 3: Оставляем только цену для Москвы (если есть)
    logger.info(f"📍 Шаг 3: Фильтрация по Москве...")
    text = keep_only_moscow_price(text)
    
    # ШАГ 4: Форматируем характеристики с буллетами
    logger.info(f"📝 Шаг 4: Форматирование буллетов...")
    text = format_characteristics(text)
    
    # ШАГ 5: Очищаем лишние пробелы
    logger.info(f"🧼 Шаг 5: Очистка пробелов...")
    text = clean_extra_spaces(text)
    
    # ШАГ 6: Определяем тип footer'а ДО форматирования (текст ещё в простом виде)
    format_type = determine_price_format(text)
    logger.info(f"📌 Тип footer: {format_type}")
    
    # ШАГ 7: Делаем заголовки секций жирными
    logger.info(f"📌 Шаг 7: Жирные заголовки секций...")
    text = make_section_headers_bold(text)
    
    # ШАГ 8: Делаем название модели жирным
    logger.info(f"📌 Шаг 8: Жирное название модели...")
    text = make_model_name_bold(text)
    
    # ШАГ 9: Делаем строки с ценой жирными
    logger.info(f"📌 Шаг 9: Жирные цены...")
    text = make_price_lines_bold(text)
    
    # ШАГ 10: Добавляем "Прямая продажа ✅" в начало
    final = f"Прямая продажа ✅\n\n{text}"
    
    # ШАГ 11: Добавляем footer
    final += build_footer(format_type)
    
    logger.info(f"✅ ТЕКСТ ОБРАБОТАН")
    logger.info(f"{'='*70}\n")
    
    return final

# ════════════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ
# ════════════════════════════════════════════════════════════════════

def is_valid_announcement(text, has_photo):
    if not has_photo:
        return False, "нет фото"
    
    if not text or len(text) < 20:
        return False, "короткий текст"
    
    # Должна быть цена или ключевые слова авто
    has_price = bool(re.search(r'\d[\d\s.,\u00a0]*\d\s*[₽€$]|\d[\d\s.,\u00a0]*\d\s*руб', text))
    has_keywords = bool(re.search(
        r'BMW|Mercedes|Audi|Toyota|Geely|Kia|Mazda|Volkswagen|Porsche|Rolls-Royce|Honda|Hyundai|Volvo|Ford|Nissan|Lamborghini|Ferrari|Bentley|авто|машин|двигател',
        text, re.IGNORECASE
    ))
    
    if has_price or has_keywords:
        return True, "OK"
    
    return False, "не авто"

# ════════════════════════════════════════════════════════════════════
# ИСТОЧНИК СООБЩЕНИЯ
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
# ОБРАБОТКА МЕДИА-ГРУПП (АЛЬБОМЫ)
# ════════════════════════════════════════════════════════════════════

async def process_media_group(media_group_id, context):
    """Обрабатывает альбом через 3 секунды"""
    await asyncio.sleep(3)
    
    if media_group_id not in media_groups_cache:
        return
    
    group_data = media_groups_cache[media_group_id]
    photos = group_data['photos']
    caption = group_data['caption']
    
    logger.info(f"\n📸 АЛЬБОМ: {len(photos)} фото")
    
    if not photos:
        del media_groups_cache[media_group_id]
        return
    
    valid, reason = is_valid_announcement(caption, True)
    if not valid:
        logger.info(f"⏭️ {reason}")
        del media_groups_cache[media_group_id]
        return
    
    formatted_text = format_announcement(caption)
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
        
        await context.bot.send_media_group(
            chat_id=TARGET_GROUP_ID,
            media=media
        )
        
        logger.info(f"✅ Альбом опубликован\n")
        save_processed(media_group_id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка альбома: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if media_group_id in media_groups_cache:
            del media_groups_cache[media_group_id]

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 1: ОБРАБОТКА ОБЪЯВЛЕНИЯ (только для владельца)
# ════════════════════════════════════════════════════════════════════

async def handle_announcement(update, context):
    message = update.message
    media_group_id = message.media_group_id
    
    # Альбом
    if media_group_id:
        if is_already_processed(media_group_id):
            return
        
        if media_group_id not in media_groups_cache:
            media_groups_cache[media_group_id] = {
                'photos': [],
                'caption': '',
                'chat_id': message.chat_id,
            }
            asyncio.create_task(process_media_group(media_group_id, context))
        
        if message.photo:
            photo_id = message.photo[-1].file_id
            media_groups_cache[media_group_id]['photos'].append(photo_id)
        
        if message.caption and not media_groups_cache[media_group_id]['caption']:
            media_groups_cache[media_group_id]['caption'] = message.caption
        
        return
    
    # Одиночное сообщение
    msg_id = message.message_id
    if is_already_processed(msg_id):
        return
    
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    
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
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=formatted,
                parse_mode='HTML'
            )
        
        save_processed(msg_id)
        logger.info(f"✅ Опубликовано\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 2: ПОИСК ОРИГИНАЛА (только для владельца)
# ════════════════════════════════════════════════════════════════════

async def handle_search(update, context, source_info):
    message = update.message
    
    original_link = generate_original_link(source_info)
    
    if original_link:
        source_name = source_info['source_chat_username'] or source_info['source_chat_title']
        
        response = (
            f"🔗 <b>ОРИГИНАЛЬНОЕ ОБЪЯВЛЕНИЕ</b>\n\n"
            f"Источник: {source_name}\n"
            f"ID: {source_info['source_message_id']}\n\n"
            f"Ссылка:\n{original_link}"
        )
        
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=response,
            parse_mode='HTML'
        )
        
        logger.info(f"✅ Ссылка отправлена: {original_link}")
    else:
        await context.bot.send_message(chat_id=message.chat_id, text="❌ Ошибка")

# ════════════════════════════════════════════════════════════════════
# РЕЖИМ 3: КЛИЕНТСКОЕ ОБРАЩЕНИЕ (для НЕ-владельцев)
# ════════════════════════════════════════════════════════════════════

async def handle_customer_inquiry(update, context):
    """Обработка обращения от КЛИЕНТА (не владельца)"""
    
    message = update.message
    user = message.from_user
    
    logger.info(f"\n📞 КЛИЕНТСКОЕ ОБРАЩЕНИЕ от @{user.username} (ID: {user.id})")
    
    response = (
        f"Здравствуйте! 👋\n\n"
        f"Я представляю компанию <b>ProAuto</b> — мы профессионально занимаемся "
        f"подбором и доставкой автомобилей по всей России и СНГ.\n\n"
        f"<b>Наши преимущества:</b>\n"
        f"• ✅ Прозрачные цены без скрытых платежей\n"
        f"• 🚗 Подбор автомобиля под любой бюджет\n"
        f"• 📦 Доставка во все города РФ\n"
        f"• 📋 Полное юридическое сопровождение\n"
        f"• 🛡 Гарантия качества каждого авто\n\n"
        f"<b>Что Вас интересует?</b> Расскажите о Вашем запросе, "
        f"и наш менеджер подберёт лучший вариант лично для Вас!\n\n"
        f"📞 Связь с менеджером напрямую:\n"
        f'<a href="{MANAGER_LINK}">«Написать менеджеру»</a> 📧 📞\n'
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
        logger.info(f"✅ Ответ клиенту отправлен")
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
        user_is_owner = is_owner(user_id)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📨 СООБЩЕНИЕ от ID:{user_id} (Владелец: {user_is_owner})")
        logger.info(f"{'='*70}")
        
        source_info = extract_forward_source(message)
        
        # ════════════════════════════════════════════════════════════════
        # ВЛАДЕЛЕЦ - обработка и публикация
        # ════════════════════════════════════════════════════════════════
        if user_is_owner:
            if source_info['is_forwarded']:
                username = source_info['source_chat_username']
                logger.info(f"📍 Переслано из: @{username or source_info['source_chat_title']}")
                
                if username and username in SOURCE_CHANNELS:
                    logger.info(f"→ РЕЖИМ ОБРАБОТКИ")
                    await handle_announcement(update, context)
                else:
                    logger.info(f"→ РЕЖИМ ПОИСКА")
                    await handle_search(update, context, source_info)
            else:
                # Обычный текст от владельца - возможно тестирует
                # Обработаем как объявление
                await handle_announcement(update, context)
        
        # ════════════════════════════════════════════════════════════════
        # КЛИЕНТ - презентация компании
        # ════════════════════════════════════════════════════════════════
        else:
            await handle_customer_inquiry(update, context)
    
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════════════
# /START
# ════════════════════════════════════════════════════════════════════

async def start_command(update, context):
    try:
        user_id = update.message.from_user.id
        
        if is_owner(user_id):
            # Владелец
            text = (
                f"🚀 <b>PROAUTO BOT v7</b>\n\n"
                f"<b>Режимы работы:</b>\n\n"
                f"1️⃣ <b>Обработка объявлений</b>\n"
                f"Пересылай объявления из источников\n"
                f"@M_Supercars, @autohaykofficial, @FRIEND_AUTO1\n\n"
                f"2️⃣ <b>Поиск оригинала</b>\n"
                f"Пересли запрос из любой группы\n"
                f"Получишь прямую ссылку\n\n"
                f"✅ Готово к работе"
            )
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            # Клиент
            await handle_customer_inquiry(update, context)
    except Exception as e:
        logger.error(f"Ошибка /start: {e}")

# ════════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════════════

async def post_init(application):
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 PROAUTO BOT v7 - ЗАПУСК")
    logger.info(f"{'='*70}")
    logger.info(f"BOT: @proauto_23_bot")
    logger.info(f"Владелец ID: {OWNER_ID}")
    logger.info(f"Менеджер: {MANAGER_LINK}")
    logger.info(f"Группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"Наценка ₽: +{PRICE_ADD_RUB:,} (если < 30млн)")
    logger.info(f"Наценка ₽: +{PRICE_ADD_RUB_BIG:,} (если ≥ 30млн)")
    logger.info(f"Наценка €: +{PRICE_ADD_EUR:,}")
    logger.info(f"Наценка $: +{PRICE_ADD_USD:,}")
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
            timeout=30
        )
        
    except Exception as e:
        logger.error(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
