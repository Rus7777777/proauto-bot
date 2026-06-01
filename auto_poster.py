import re
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
import logging
import signal
import sys

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID'))
MANAGER_LINK = os.getenv('MANAGER_LINK')
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME')
PRICE_ADD = int(os.getenv('PRICE_ADD', 40000))

PROCESSED_FILE = 'processed_posts.json'

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app_instance = None

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

def is_valid_announcement(text: str, has_photo: bool) -> tuple:
    if not text or not has_photo:
        return False, "нет текста или фото"
    
    price_triggers = [r'Цена', r'Стоимость', r'Сумма', r'₽']
    has_price = any(re.search(t, text, re.IGNORECASE) for t in price_triggers)
    if not has_price:
        return False, "нет цены"
    
    auto_keywords = [
        r'BMW|Audi|Mercedes|Toyota|Volkswagen|Ford|Kia|Mazda|Honda|Hyundai|Volvo|Skoda|LADA|Chrysler|Dodge|Porsche|Ferrari|Lamborghini',
        r'авто|машин|автомобиль|кроссовер|седан|хэтчбэк|минивэн|пикап',
    ]
    has_auto = any(re.search(k, text, re.IGNORECASE) for k in auto_keywords)
    if not has_auto:
        return False, "не авто"
    
    return True, "OK"

def extract_price(text: str):
    pattern = r'([\d\s,]+)\s*₽'
    matches = re.findall(pattern, text)
    if matches:
        try:
            return int(matches[-1].replace(' ', '').replace(',', ''))
        except:
            return None
    return None

def clean_text(text: str) -> str:
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'\n\n+', '\n', text)
    return text.strip()

def format_text(original_text: str, price: int) -> str:
    cleaned = clean_text(original_text)
    new_price = price + PRICE_ADD
    
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
    footer = f"\n\nПо поводу покупки или подбора:\n[«Написать менеджеру»]({MANAGER_LINK}) 📧📞\n\n{TARGET_CHANNEL_NAME}"
    return cleaned + footer

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message:
            return
        
        msg_id = message.message_id
        
        if is_already_processed(msg_id):
            logger.info(f"Пост {msg_id} уже обработан")
            return
        
        text = message.text or message.caption or ""
        has_photo = bool(message.photo)
        
        logger.info(f"\n📝 НОВОЕ СООБЩЕНИЕ {msg_id}")
        logger.info(f"Текст: {text[:60]}...")
        
        valid, reason = is_valid_announcement(text, has_photo)
        if not valid:
            logger.info(f"⏭️  {reason}")
            return
        
        price = extract_price(text)
        if not price:
            logger.info(f"⏭️  Цена не найдена")
            return
        
        logger.info(f"💰 {price:,} ₽ → {price + PRICE_ADD:,} ₽")
        
        formatted = format_text(text, price)
        
        if message.photo:
            photo = message.photo[-1]
            await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID,
                photo=photo.file_id,
                caption=formatted,
                parse_mode='HTML'
            )
            logger.info(f"✅ Опубликовано с фото в {TARGET_CHANNEL_NAME}")
        else:
            await context.bot.send_message(
                chat_id=TARGET_GROUP_ID,
                text=formatted,
                parse_mode='HTML'
            )
            logger.info(f"✅ Опубликовано в {TARGET_CHANNEL_NAME}")
        
        save_processed(msg_id)
        logger.info(f"💾 Сохранено в базу\n")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            f"✅ Бот активен!\n\n"
            f"📤 Пересылайте объявления об авто\n"
            f"🎯 Будут опубликованы в: {TARGET_CHANNEL_NAME}\n"
            f"💰 Наценка: +{PRICE_ADD:,} ₽\n\n"
            f"Требования:\n"
            f"• Фото\n"
            f"• Описание с ценой\n"
            f"• Марка автомобиля"
        )
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")

async def post_init(application):
    logger.info("\n" + "="*70)
    logger.info("🚀 PROAUTO BOT v2")
    logger.info("="*70)
    logger.info(f"📤 Целевая группа: {TARGET_CHANNEL_NAME}")
    logger.info(f"💰 Наценка: +{PRICE_ADD:,} ₽")
    logger.info(f"✅ БОТ ЗАПУЩЕН И РАБОТАЕТ")
    logger.info(f"📍 Режим: Polling (Bot API)")
    logger.info("="*70)
    logger.info(f"✍️  Ожидаю сообщений...\n")

def main():
    global app_instance
    
    try:
        logger.info("⏳ Инициализация Application...")
        
        app_instance = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        app_instance.add_handler(MessageHandler(filters.COMMAND, start))
        app_instance.add_handler(MessageHandler(
            filters.TEXT | filters.CAPTION | filters.PHOTO,
            process_message
        ))
        
        logger.info("⏳ Запуск бота...")
        app_instance.run_polling(
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
