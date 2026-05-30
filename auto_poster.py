import asyncio
import re
import json
import os
from datetime import datetime
from telethon import TelegramClient, events
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

# Telethon (для мониторинга каналов)
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')

# Bot API (для отправки в группу)
BOT_TOKEN = os.getenv('BOT_TOKEN')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID'))

# Параметры
MANAGER_LINK = os.getenv('MANAGER_LINK')
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME')
PRICE_ADD = int(os.getenv('PRICE_ADD', 40000))
SOURCE_CHANNELS = [ch.strip() for ch in os.getenv('SOURCE_CHANNELS').split(',')]

PROCESSED_FILE = 'processed_posts.json'

# Клиенты
client = TelegramClient('session_name', API_ID, API_HASH)
bot = Bot(token=BOT_TOKEN)

# ============================================
# ФУНКЦИИ ОБРАБОТКИ
# ============================================

def load_processed_posts():
    """Загружаем обработанные посты"""
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_processed_post(channel, msg_id):
    """Сохраняем обработанный пост"""
    processed = load_processed_posts()
    key = f"{channel}_{msg_id}"
    processed[key] = datetime.now().isoformat()
    with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

def is_already_processed(channel, msg_id):
    """Проверяем был ли обработан"""
    processed = load_processed_posts()
    key = f"{channel}_{msg_id}"
    return key in processed

def is_valid_announcement(text: str) -> bool:
    """Проверяем это ли объявление об авто"""
    if not text:
        return False
    
    # Триггеры для определения объявления
    price_triggers = [
        r'Цена под ключ',
        r'Цена\s*:',
        r'Цена\s*\(',
        r'Под ключ',
        r'Итоговая цена',
        r'Цена\s*во',
        r'Цена на',
        r'Стоимость',
    ]
    
    has_price = any(re.search(trigger, text, re.IGNORECASE) for trigger in price_triggers)
    
    # Проверяем что это не реклама услуг, а объявление об авто
    is_auto_related = any(re.search(pattern, text, re.IGNORECASE) for pattern in [
        r'BMW|Audi|Mercedes|Toyota|Volkswagen|Ford|Kia|Mazda|Honda|Hyundai|Volvo|Skoda|LADA',
        r'авто|машин|автомобиль|кроссовер|седан|хэтчбэк|внедорожник',
    ])
    
    return has_price and is_auto_related

def extract_price(text: str) -> int or None:
    """Извлекаем цену"""
    price_pattern = r'([\d\s,]+)\s*₽'
    matches = re.findall(price_pattern, text)
    
    if matches:
        price_str = matches[-1].replace(' ', '').replace(',', '')
        try:
            return int(price_str)
        except:
            return None
    return None

def clean_text(text: str) -> str:
    """Очищаем от старых контактов"""
    # Удаляем ссылки на другие каналы
    text = re.sub(r'@[A-Za-z0-9_]{1,32}', '', text)
    # Удаляем ссылки на других менеджеров
    text = re.sub(r'\[«[^»]+»\]\(https://t\.me/[A-Za-z0-9_]+\)', '', text)
    # Удаляем повторяющиеся пробелы
    text = re.sub(r'\n\n+', '\n', text)
    return text.strip()

def format_to_standard(original_text: str, extracted_price: int) -> str:
    """Форматируем в стандартный вид"""
    cleaned = clean_text(original_text)
    new_price = extracted_price + PRICE_ADD
    
    # Заменяем цену
    price_pattern = r'([\d\s,]+)\s*₽'
    
    def replace_price(match):
        old_price_str = match.group(1)
        try:
            old_price = int(old_price_str.replace(' ', '').replace(',', ''))
            if abs(old_price - extracted_price) < 100000:
                return f"{new_price:,} ₽".replace(',', ' ')
        except:
            pass
        return match.group(0)
    
    cleaned = re.sub(price_pattern, replace_price, cleaned)
    
    # ИСПРАВЛЕННЫЙ контактный блок с эмодзи в правильном порядке
    contact_block = f"""
По поводу покупки данного автомобиля или подбора: 
[«Написать менеджеру»]({MANAGER_LINK}) (Ответ в течении 1ч) 📧📞

{TARGET_CHANNEL_NAME}"""
    
    return cleaned + "\n" + contact_block

async def send_to_group(text: str):
    """Отправляем в целевую группу"""
    try:
        await bot.send_message(
            chat_id=TARGET_GROUP_ID,
            text=text,
            parse_mode='HTML'
        )
        return True
    except Exception as e:
        print(f"   ❌ Ошибка отправки: {e}")
        return False

# ============================================
# ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_new_message(event):
    """Ловим новые сообщения из каналов"""
    try:
        message = event.message
        text = message.text or ""
        
        # Получаем имя канала
        chat = await event.get_chat()
        channel_name = chat.username if hasattr(chat, 'username') else str(chat.id)
        
        # Проверяем не обработан ли уже
        if is_already_processed(channel_name, message.id):
            print(f"⏭️  Пост @{channel_name}/{message.id} уже обработан")
            return
        
        # Проверяем это ли объявление
        if not is_valid_announcement(text):
            print(f"❌ @{channel_name}/{message.id} - не объявление об авто")
            return
        
        # Проверяем есть ли фото
        has_media = hasattr(message, 'media') and message.media is not None
        if not has_media:
            print(f"❌ @{channel_name}/{message.id} - нет фото")
            return
        
        print(f"\n{'='*60}")
        print(f"🔍 ОБНАРУЖЕНО ОБЪЯВЛЕНИЕ")
        print(f"{'='*60}")
        print(f"📡 Источник: @{channel_name}/{message.id}")
        
        # Извлекаем цену
        price = extract_price(text)
        if not price:
            print(f"⚠️  Цена не найдена")
            return
        
        # Форматируем
        formatted_text = format_to_standard(text, price)
        
        print(f"💰 Старая цена: {price:,} ₽")
        print(f"💰 Новая цена: {price + PRICE_ADD:,} ₽")
        
        # Отправляем в группу
        if await send_to_group(formatted_text):
            print(f"✅ Отправлено в {TARGET_CHANNEL_NAME}")
            save_processed_post(channel_name, message.id)
            print(f"{'='*60}")
            print(f"✨ ГОТОВО!\n")
        else:
            print(f"❌ Не удалось отправить")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}\n")

# ============================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================

async def main():
    """Главная функция"""
    print("\n" + "="*70)
    print(" "*15 + "🚀 PROAUTO BOT - ПОЛНАЯ АВТОМАТИЗАЦИЯ")
    print("="*70 + "\n")
    
    print("📡 НАСТРОЙКА МОНИТОРИНГА:")
    print(f"   Будут отслеживаться ТОЛЬКО эти каналы:")
    for i, ch in enumerate(SOURCE_CHANNELS, 1):
        print(f"   {i}. @{ch}")
    
    print(f"\n📤 ВСЕ ОБЪЯВЛЕНИЯ ПОЙДУТ В: {TARGET_CHANNEL_NAME}")
    print(f"💰 НАЦЕНКА К ЦЕНЕ: +{PRICE_ADD:,} ₽")
    print(f"🎯 ID ГРУППЫ: {TARGET_GROUP_ID}")
    
    print("\n" + "="*70)
    print("⏳ ПОДКЛЮЧЕНИЕ К TELEGRAM...")
    print("="*70 + "\n")
    
    # Подключаемся к Telegram
    try:
        await client.start(phone=PHONE_NUMBER)
        print("✅ User API успешно подключен\n")
    except Exception as e:
        print(f"❌ ОШИБКА User API: {e}")
        print("\n💡 РЕШЕНИЯ:")
        print("   1. Включи VPN (выбери USA или UK)")
        print("   2. Проверь номер телефона в .env")
        print("   3. Проверь интернет соединение")
        print("   4. Попробуй перезагрузить бота\n")
        return
    
    # Проверяем Bot API
    try:
        bot_info = await bot.get_me()
        print(f"✅ Bot API успешно подключен: @{bot_info.username}\n")
    except Exception as e:
        print(f"❌ ОШИБКА Bot API: {e}\n")
        return
    
    # Получаем информацию о подписанных каналах
    print("📊 ПРОВЕРКА ДОСТУПА К КАНАЛАМ:")
    for channel in SOURCE_CHANNELS:
        try:
            entity = await client.get_entity(channel)
            print(f"   ✅ @{channel} - доступен")
        except Exception as e:
            print(f"   ❌ @{channel} - ошибка: {str(e)[:50]}")
    
    print("\n" + "="*70)
    print("🎯 БОТ ЗАПУЩЕН И РАБОТАЕТ 24/7")
    print("="*70)
    print("\n⏳ ОЖИДАНИЕ НОВЫХ ОБЪЯВЛЕНИЙ...")
    print("   Как только появится объявление в одном из каналов,")
    print("   оно АВТОМАТИЧЕСКИ скопируется и переформатируется.\n")
    print("   Для остановки бота нажми: Ctrl+C\n")
    print("="*70 + "\n")
    
    # Запускаем мониторинг
    await client.run_until_disconnected()

# ============================================
# ЗАПУСК
# ============================================

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ БОТ ОСТАНОВЛЕН")
    except Exception as e:
        print(f"\n\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")