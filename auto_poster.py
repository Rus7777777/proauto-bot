import asyncio
import re
import json
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

load_dotenv()

API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
BOT_TOKEN = os.getenv('BOT_TOKEN')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID'))
MANAGER_LINK = os.getenv('MANAGER_LINK')
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME')
PRICE_ADD = int(os.getenv('PRICE_ADD', 40000))
SOURCE_CHANNELS = [ch.strip() for ch in os.getenv('SOURCE_CHANNELS').split(',')]

PROCESSED_FILE = 'processed_posts.json'

client = TelegramClient('session_name', API_ID, API_HASH)
bot = Bot(token=BOT_TOKEN)

def load_processed_posts():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_processed_post(channel, msg_id):
    processed = load_processed_posts()
    key = f"{channel}_{msg_id}"
    processed[key] = datetime.now().isoformat()
    try:
        with open(PROCESSED_FILE, 'w', encoding='utf-8') as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
    except:
        pass

def is_already_processed(channel, msg_id):
    processed = load_processed_posts()
    key = f"{channel}_{msg_id}"
    return key in processed

def is_valid_announcement(text, has_photo):
    if not text or not has_photo:
        return False, "no text or photo"
    
    price_triggers = [
        r'Цена под ключ',
        r'Цена\s*:',
        r'Цена\s*\(',
        r'Под ключ',
        r'Итоговая цена',
    ]
    
    has_price = any(re.search(t, text, re.IGNORECASE) for t in price_triggers)
    if not has_price:
        return False, "no price"
    
    auto_keywords = [
        r'BMW|Audi|Mercedes|Toyota|Volkswagen|Ford|Kia|Mazda|Honda|Hyundai|Volvo|Skoda|LADA',
        r'авто|машин|автомобиль|кроссовер|седан',
    ]
    
    has_auto = any(re.search(k, text, re.IGNORECASE) for k in auto_keywords)
    if not has_auto:
        return False, "not auto"
    
    return True, "OK"

def extract_price(text):
    pattern = r'([\d\s,]+)\s*₽'
    matches = re.findall(pattern, text)
    if matches:
        try:
            return int(matches[-1].replace(' ', '').replace(',', ''))
        except:
            return None
    return None

def clean_text(text):
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'\[«[^»]+»\]\([^\)]+\)', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'\n\n+', '\n', text)
    return text.strip()

def format_text(original_text, price):
    cleaned = clean_text(original_text)
    new_price = price + PRICE_ADD
    
    pattern = r'([\d\s,]+)\s*₽'
    def replace_price(m):
        try:
            old = int(m.group(1).replace(' ', '').replace(',', ''))
            if abs(old - price) < 150000:
                return f"{new_price:,} ₽".replace(',', ' ')
        except:
            pass
        return m.group(0)
    
    cleaned = re.sub(pattern, replace_price, cleaned)
    
    footer = f"\nПо поводу покупки данного автомобиля или подбора:\n[«Написать менеджеру»]({MANAGER_LINK}) (Ответ в течении 1ч) 📞📧\n\n{TARGET_CHANNEL_NAME}"
    
    return cleaned + footer

async def download_photo(message):
    try:
        if hasattr(message, 'media') and isinstance(message.media, MessageMediaPhoto):
            return await client.download_media(message.media)
    except:
        pass
    return None

async def send_post(photo_path, text):
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                await bot.send_photo(chat_id=TARGET_GROUP_ID, photo=f, caption=text, parse_mode='HTML')
            try:
                os.remove(photo_path)
            except:
                pass
        else:
            await bot.send_message(chat_id=TARGET_GROUP_ID, text=text, parse_mode='HTML')
        return True
    except Exception as e:
        print(f"Send error: {e}")
        return False

async def process_msg(event, channel_name, msg_id):
    message = event.message
    text = message.text or ""
    has_photo = hasattr(message, 'media') and isinstance(message.media, MessageMediaPhoto)
    
    valid, reason = is_valid_announcement(text, has_photo)
    if not valid:
        return False
    
    price = extract_price(text)
    if not price:
        return False
    
    formatted = format_text(text, price)
    photo = await download_photo(message)
    
    if await send_post(photo, formatted):
        save_processed_post(channel_name, msg_id)
        return True
    return False

@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handle_message(event):
    message = event.message
    chat = await event.get_chat()
    channel_name = chat.username if hasattr(chat, 'username') else str(chat.id)
    
    if is_already_processed(channel_name, message.id):
        return
    
    print(f"\nProcessing: @{channel_name}/{message.id}")
    await process_msg(event, channel_name, message.id)

async def process_old():
    print("\nProcessing old posts from last day...")
    yesterday = datetime.now() - timedelta(days=1)
    count = 0
    
    for ch_name in SOURCE_CHANNELS:
        try:
            async for msg in client.iter_messages(ch_name, reverse=True, offset_date=yesterday):
                if is_already_processed(ch_name, msg.id):
                    continue
                
                print(f"\nOld post: @{ch_name}/{msg.id}")
                
                class FakeEvent:
                    def __init__(self, m):
                        self.message = m
                
                if await process_msg(FakeEvent(msg), ch_name, msg.id):
                    count += 1
                
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Error in {ch_name}: {e}")
    
    print(f"\nProcessed old posts: {count}")

async def main():
    print("\n" + "="*70)
    print("PROAUTO BOT STARTED")
    print("="*70)
    print(f"Sources: {SOURCE_CHANNELS}")
    print(f"Group: {TARGET_CHANNEL_NAME}")
    print(f"Markup: +{PRICE_ADD:,} RUB")
    print("="*70 + "\n")
    
    try:
        await client.start(phone=PHONE_NUMBER)
        print("OK: User API connected\n")
    except Exception as e:
        print(f"ERROR User API: {e}")
        return
    
    try:
        bot_info = await bot.get_me()
        print(f"OK: Bot API connected: @{bot_info.username}\n")
    except Exception as e:
        print(f"ERROR Bot API: {e}")
        return
    
    print("Checking channels:")
    for ch in SOURCE_CHANNELS:
        try:
            await client.get_entity(ch)
            print(f"   OK: @{ch}")
        except:
            print(f"   ERROR: @{ch}")
    
    await process_old()
    
    print("\n" + "="*70)
    print("BOT READY - LISTENING FOR MESSAGES")
    print("="*70 + "\n")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBOT STOPPED")
    except Exception as e:
        print(f"\nERROR: {e}")
