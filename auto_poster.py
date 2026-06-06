"""
PROAUTO BOT - AUTO INSTALL VERSION
Автоматически устанавливает зависимости при старте
"""
import sys
import os
import subprocess

print("="*50, flush=True)
print("PROAUTO BOT СТАРТ", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"PATH: {os.getcwd()}", flush=True)
print("="*50, flush=True)

# ════════════════════════════════════════════════
# ШАГ 1: АВТОУСТАНОВКА ЗАВИСИМОСТЕЙ
# ════════════════════════════════════════════════
def install(package):
    print(f"Устанавливаю {package}...", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package,
         "--break-system-packages", "--quiet"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"✅ {package} установлен", flush=True)
    else:
        print(f"⚠️ {package}: {result.stderr[:200]}", flush=True)

# Проверяем и устанавливаем нужные пакеты
try:
    import telegram
    print(f"✅ python-telegram-bot уже есть: {telegram.__version__}", flush=True)
except ImportError:
    print("⚠️ python-telegram-bot не найден, устанавливаю...", flush=True)
    install("python-telegram-bot>=20.0,<21.0")
    install("httpx>=0.24.0")

try:
    from dotenv import load_dotenv
    print("✅ python-dotenv есть", flush=True)
except ImportError:
    install("python-dotenv")

# ════════════════════════════════════════════════
# ШАГ 2: ИМПОРТЫ
# ════════════════════════════════════════════════
print("Загружаю модули...", flush=True)

try:
    import asyncio
    import re
    import json
    import threading
    from datetime import datetime, timedelta
    from http.server import HTTPServer, BaseHTTPRequestHandler

    from dotenv import load_dotenv
    from telegram import (
        Update, InputMediaPhoto,
        InlineKeyboardButton, InlineKeyboardMarkup
    )
    from telegram.ext import (
        Application, MessageHandler, CommandHandler,
        CallbackQueryHandler, filters
    )
    import logging
    print("✅ Все модули загружены", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта: {e}", flush=True)
    import time
    time.sleep(99999)

load_dotenv()

# ════════════════════════════════════════════════
# ШАГ 3: КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════
BOT_TOKEN      = os.getenv('BOT_TOKEN')
BOT_USERNAME   = os.getenv('BOT_USERNAME', 'proauto_23_bot')
TARGET_GROUP_ID = int(os.getenv('TARGET_GROUP_ID', '0'))
TARGET_CHANNEL_NAME = os.getenv('TARGET_CHANNEL_NAME', '@proauto_77')
MANAGER_LINK   = os.getenv('MANAGER_LINK', 'https://t.me/rdblm')
OWNER_ID       = int(os.getenv('OWNER_ID', '0'))
MANAGER_USER_ID = int(os.getenv('MANAGER_USER_ID', '0'))
PORT           = int(os.getenv('PORT', 3000))
DATA_DIR       = os.getenv('DATA_DIR', '/app/data')

os.makedirs(DATA_DIR, exist_ok=True)

PUBLICATIONS_DB = os.path.join(DATA_DIR, 'publications.json')
LEADS_DB        = os.path.join(DATA_DIR, 'leads.json')

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

media_groups_cache = {}
BRIEF_STATES = {}

print(f"BOT_TOKEN: {'OK' if BOT_TOKEN else 'ОТСУТСТВУЕТ!'}", flush=True)
print(f"OWNER_ID: {OWNER_ID}", flush=True)
print(f"DATA_DIR: {DATA_DIR}", flush=True)
print(f"PORT: {PORT}", flush=True)

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не задан! Проверь переменные окружения.", flush=True)
    import time; time.sleep(99999)

# ════════════════════════════════════════════════
# КОНСТАНТЫ ДЛЯ ОБРАБОТКИ ТЕКСТА
# ════════════════════════════════════════════════
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF\U00002700-\U000027BF"
    "\U000024C2-\U0001F251\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000026FF]+",
    flags=re.UNICODE
)

CAR_BRANDS = [
    'BMW', 'Mercedes', 'Audi', 'Toyota', 'Lexus', 'Honda', 'Nissan',
    'Mazda', 'Kia', 'Hyundai', 'Volkswagen', 'Porsche', 'Volvo',
    'Subaru', 'Mitsubishi', 'Infiniti', 'Geely', 'Haval', 'BYD',
    'Chery', 'Lixiang', 'NIO', 'Zeekr', 'Tesla', 'Rolls', 'Bentley',
    'Ferrari', 'Lamborghini', 'Land Rover', 'Range Rover', 'Ford',
    'Chevrolet', 'Cadillac', 'Jeep', 'Genesis', 'Skoda', 'Maserati',
]

SKIP_STATUS_LINES = [
    r'прямая\s+продажа', r'в\s+свободной\s+продаже', r'в\s+продаже',
    r'авто\s+из\s+европы', r'авто\s+прибыло', r'авто\s+из\s+',
    r'готова?\s+к\s+пригону', r'срок\s+доставки', r'авто\s+готово',
    r'^\s*[-–—]\s*$', r'^\s*$',
]

PHRASES_TO_DELETE = [
    r'пишите\s+(?:нам|в\s+личку)',
    r'звоните\s+(?:нам)?',
    r'свяжитесь\s+(?:с\s+нами)?',
    r'^.*наши\s+контакты.*$',
    r'^.*менеджер\s+[А-ЯA-Z][а-яa-z]+.*$',
    r'^.*whatsapp.*$',
    r'^.*viber.*$',
    r'^.*[Рр]ассрочк[аеу].*$',
    r'^.*[Тт]rade.?[Іи]n.*$',
    r'^.*[Тт]рейд.?[Ии]н.*$',
    r'^.*[Оо]бмен\s+вашего\s+авто.*$',
    r'^.*[Кк]редит.*$',
    r'^.*[Лл]изинг.*$',
    r'^.*[Пп]о\s+всем\s+вопросам.*$',
    r'^.*[Дд]оставка\s+по\s+регионам.*$',
    r'^.*[Аа]вто\s+готово\s+к\s+пригону.*$',
    r'^.*[Рр]аботаем.*[Дд]оговор.*$',
    r'^.*[Тт]аможенная\s+пошлина.*$',
    r'^.*[Оо]тзывы\s+наших.*$',
    r'^.*CarVertical.*$',
    r'^.*[Рр]аботаем\s+официально.*$',
    r'^.*[Нн]ужна\s+цена\s+под\s+ключ.*$',
    r'^.*[Бб]ез\s+ДТП.*[Вв]ладелец.*$',
]

CITIES = [
    '🏙 Москва', '🏙 Санкт-Петербург', '🌊 Краснодар', '🌊 Сочи',
    '🏔 Екатеринбург', '🌲 Новосибирск', '🕌 Казань', '☀️ Ростов-на-Дону',
    '🏛 Нижний Новгород', '⚓ Владивосток', '🏙 Тюмень', '🏙 Уфа',
    '🏙 Красноярск', '🏙 Челябинск', '🌿 Воронеж',
]
TIMINGS = [
    '⚡ В этом месяце', '📅 1-2 месяца',
    '🗓 3-6 месяцев', '👀 Просто изучаю',
]
BRAND_GROUPS = {
    '🇩🇪 Немецкие':    ['BMW','Mercedes-Benz','Audi','Volkswagen','Porsche','Volvo'],
    '🇯🇵 Японские':    ['Toyota','Lexus','Honda','Nissan','Mazda','Subaru','Mitsubishi','Infiniti'],
    '🇰🇷 Корейские':   ['Kia','Hyundai','Genesis'],
    '🇨🇳 Китайские':   ['Geely','Haval','BYD','Chery','Lixiang','NIO','Zeekr'],
    '🇺🇸 Американские':['Tesla','Ford','Chevrolet','Cadillac','Jeep'],
    '🇬🇧 Британские':  ['Land Rover','Bentley','Rolls-Royce','Jaguar'],
    '👑 Итальянские':   ['Ferrari','Lamborghini','Maserati','Alfa Romeo'],
}
CAR_DATABASE = {
    'Alfa Romeo': {
        '33 Stradale': '2024-2026',
        '4C': '2013-2020',
        'Giulia': '1962-2026',
        'Giulietta': '1954-2020',
        'Junior': '2024-2026',
        'MiTo': '2008-2018',
        'Stelvio': '2016-2026',
        'Tonale': '2022-2026'
    },
    'Audi': {
        'A1': '2010-2026',
        'A3': '1996-2026',
        'A4': '1994-2025',
        'A4 allroad': '2009-2025',
        'A5': '2007-2026',
        'A6': '1994-2026',
        'A6 allroad': '2000-2025',
        'A6 e-tron': '2024-2026',
        'A7': '2010-2026',
        'A8': '1994-2026',
        'E5': '2025-2026',
        'E7X': '2026-2026',
        'Q2': '2016-2026',
        'Q3': '2011-2026',
        'Q3 Sportback': '2019-2026',
        'Q4 Sportback e-tron': '2021-2026',
        'Q4 e-tron': '2021-2026',
        'Q5': '2008-2026',
        'Q5 Sportback': '2020-2026',
        'Q5 e-tron': '2022-2026',
        'Q6': '2022-2026',
        'Q6 Sportback e-tron': '2024-2026',
        'Q6 e-tron': '2024-2026',
        'Q7': '2005-2026',
        'Q8': '2018-2026',
        'Q8 Sportback e-tron': '2022-2025',
        'Q8 e-tron': '2022-2026',
        'R8': '2007-2023',
        'RS 3': '2011-2026',
        'RS 4': '1999-2026',
        'RS 5': '2010-2026',
        'RS 6': '2002-2025',
        'RS 7': '2013-2025',
        'RS Q3': '2013-2026',
        'RS Q3 Sportback': '2019-2026',
        'RS Q8': '2019-2026',
        'RS e-tron GT': '2020-2026',
        'S e-tron GT': '2024-2026',
        'S1': '2014-2018',
        'S3': '1999-2026',
        'S4': '1997-2026',
        'S5': '2007-2026',
        'S6': '1994-2025',
        'S6 e-tron': '2024-2026',
        'S7': '2012-2025',
        'S8': '1996-2026',
        'SQ2': '2018-2026',
        'SQ5': '2013-2026',
        'SQ5 Sportback': '2020-2026',
        'SQ6 Sportback e-tron': '2024-2026',
        'SQ6 e-tron': '2024-2026',
        'SQ7': '2016-2026',
        'SQ8': '2019-2026',
        'SQ8 Sportback e-tron': '2022-2025',
        'SQ8 e-tron': '2022-2026',
        'TT': '1998-2023',
        'TT RS': '2009-2023',
        'TTS': '2007-2023',
        'e-tron': '2018-2023',
        'e-tron GT': '2020-2026',
        'e-tron S': '2019-2022',
        'e-tron S Sportback': '2019-2022',
        'e-tron Sportback': '2019-2022'
    },
    'BMW': {
        '1 серии': '2004-2026',
        '2 серии': '2014-2026',
        '2 серии Active Tourer': '2014-2026',
        '2 серии Gran Tourer': '2015-2022',
        '3 серии': '1975-2026',
        '4 серии': '2013-2026',
        '5 серии': '1972-2026',
        '6 серии': '1976-2024',
        '7 серии': '1977-2026',
        '8 серии': '1989-2026',
        'M2': '2015-2026',
        'M3': '1986-2026',
        'M4': '2014-2026',
        'M5': '1985-2026',
        'M6': '1984-2018',
        'M8': '2019-2026',
        'X1': '2009-2026',
        'X2': '2017-2026',
        'X3': '2003-2026',
        'X3 M': '2019-2026',
        'X4': '2014-2026',
        'X4 M': '2019-2026',
        'X5': '1999-2026',
        'X5 M': '2009-2026',
        'X6': '2007-2026',
        'X6 M': '2009-2026',
        'X7': '2019-2026',
        'XM': '2022-2026',
        'Z4': '2002-2026',
        'i3': '2013-2026',
        'i4': '2021-2026',
        'i5': '2023-2026',
        'i7': '2022-2026',
        'i8': '2014-2020',
        'iX': '2021-2026',
        'iX1': '2022-2026',
        'iX2': '2023-2026',
        'iX3': '2020-2026',
        'iX5': '2023-2026'
    },
    'BYD': {
        'Atto 2': '2025-2026',
        'Chazor': '2024-2026',
        'D1': '2020-2026',
        'Datang': '2026-2026',
        'Destroyer 05': '2022-2026',
        'Dolphin': '2021-2026',
        'E1': '2019-2021',
        'E2': '2019-2026',
        'E3': '2019-2023',
        'E5': '2015-2020',
        'E6': '2009-2021',
        'E7': '2025-2026',
        'E9': '2021-2021',
        'F3': '2005-2021',
        'F5': '2014-2018',
        'FangChengBao Leopard 5': '2023-2026',
        'FangChengBao Leopard 8': '2024-2026',
        'FangChengBao Titanium 3': '2024-2026',
        'FangChengBao Titanium 7': '2025-2026',
        'Frigate 07': '2022-2026',
        'Han': '2020-2026',
        'Han L': '2025-2026',
        'Qin': '2018-2026',
        'Qin Max': '2026-2026',
        'Racco': '2026-2026',
        'Sea Lion 05': '2024-2026',
        'Sea Lion 06': '2025-2026',
        'Sea Lion 07': '2024-2026',
        'Seagull': '2023-2026',
        'Seal': '2022-2026',
        'Seal 05': '2025-2026',
        'Seal 06': '2024-2026',
        'Seal 06 GT': '2024-2026',
        'Seal 07': '2024-2026',
        'Seal 08': '2026-2026',
        'Shark (Shark 6)': '2024-2026',
        'Song': '2015-2022',
        'Song EV': '2016-2019',
        'Song L': '2023-2026',
        'Song Max': '2017-2026',
        'Song Plus': '2020-2025',
        'Song Pro': '2019-2026',
        'Song Ultra': '2026-2026',
        'Tang': '2015-2026',
        'Tang L': '2025-2026',
        'Xia (M9)': '2024-2026',
        'Yangwang U7': '2024-2026',
        'Yangwang U8': '2023-2026',
        'Yangwang U9': '2024-2026',
        'Yuan': '2016-2023',
        'Yuan Plus': '2021-2026',
        'Yuan Up': '2024-2026'
    },
    'Bentley': {
        'Bentayga': '2015-2026',
        'Continental GT': '2003-2026',
        'Flying Spur': '2013-2026',
        'Mulliner Bacalar': '2021-2021',
        'Mulliner Batur': '2022-2026',
        'Mulsanne': '1980-2020'
    },
    'Cadillac': {
        'ATS': '2012-2019',
        'ATS-V': '2015-2019',
        'CT4': '2019-2026',
        'CT4-V': '2019-2026',
        'CT5': '2019-2026',
        'CT5-V': '2019-2026',
        'CT6': '2016-2026',
        'CTS': '2002-2019',
        'CTS-V': '2004-2019',
        'Celestiq': '2024-2026',
        'Escalade': '1998-2026',
        'Escalade iQ': '2024-2026',
        'Escalade-V': '2022-2026',
        'GT4': '2023-2026',
        'Lyriq': '2022-2026',
        'Lyriq-V': '2025-2026',
        'Optiq': '2024-2026',
        'Optiq-V': '2025-2026',
        'Vistiq': '2025-2026',
        'XT4': '2018-2026',
        'XT5': '2016-2026',
        'XT6': '2019-2026',
        'XTS': '2012-2019'
    },
    'Chery': {
        'Arrizo 3': '2014-2018',
        'Arrizo 5': '2016-2026',
        'Arrizo 5 GT': '2022-2023',
        'Arrizo 5 Plus': '2020-2026',
        'Arrizo 6': '2018-2026',
        'Arrizo 7': '2013-2018',
        'Arrizo 8': '2022-2026',
        'Arrizo 8 Pro': '2025-2026',
        'Bonus 3 (E3/A19)': '2014-2017',
        'Domi': '2025-2026',
        'Explore 06': '2023-2026',
        'Fulwin A8': '2023-2026',
        'Fulwin A9L': '2025-2026',
        'Fulwin T10': '2024-2026',
        'Fulwin T11': '2025-2026',
        'Fulwin T6': '2024-2025',
        'Fulwin T8': '2025-2026',
        'Fulwin T9': '2024-2026',
        'Fulwin T9L': '2026-2026',
        'Fulwin X3': '2025-2026',
        'Omoda 5': '2022-2026',
        'Q22': '2009-2022',
        'QQ Ice Cream': '2021-2026',
        'QQ3': '2026-2026',
        'Rely R08': '2025-2026',
        'Tiggo 2': '2016-2021',
        'Tiggo 2 Pro': '2021-2026',
        'Tiggo 3': '2014-2020',
        'Tiggo 3x': '2016-2023',
        'Tiggo 3xe': '2018-2021',
        'Tiggo 4': '2017-2026',
        'Tiggo 4 Pro': '2020-2026',
        'Tiggo 5': '2014-2020',
        'Tiggo 5x': '2017-2026',
        'Tiggo 7': '2016-2026',
        'Tiggo 7 Plus': '2021-2026',
        'Tiggo 7 Pro': '2020-2024',
        'Tiggo 7 Pro Max': '2022-2026',
        'Tiggo 7 Pro Plug-in Hybrid': '2023-2025',
        'Tiggo 7L': '2024-2026',
        'Tiggo 8': '2018-2026',
        'Tiggo 8 Plus': '2020-2026',
        'Tiggo 8 Pro': '2021-2026',
        'Tiggo 8 Pro Max': '2022-2026',
        'Tiggo 8 Pro Plug-in Hybrid': '2023-2025',
        'Tiggo 8 Pro e+': '2021-2024',
        'Tiggo 8L': '2024-2026',
        'Tiggo 9': '2023-2026',
        'Tiggo E': '2019-2022',
        'eQ1': '2017-2026',
        'eQ5': '2020-2022',
        'eQ7': '2023-2026'
    },
    'Chevrolet': {
        'Aveo': '2002-2026',
        'Blazer': '1982-2026',
        'Blazer EV': '2023-2026',
        'Bolt': '2016-2023',
        'Bolt EUV': '2021-2023',
        'Camaro': '1967-2024',
        'Caprice': '1965-2017',
        'Captiva': '2006-2026',
        'Cobalt': '2004-2026',
        'Colorado': '2004-2026',
        'Corvette': '1953-2026',
        'Cruze': '2008-2023',
        'Damas': '2019-2026',
        'Equinox': '2004-2026',
        'Equinox EV': '2024-2026',
        'Express': '1996-2026',
        'Groove': '2020-2026',
        'Impala': '1958-2020',
        'Lacetti': '2004-2024',
        'Malibu': '1978-2026',
        'Menlo': '2020-2026',
        'Monza': '1975-2026',
        'Nexia': '2017-2023',
        'Niva': '2002-2020',
        'Onix': '2012-2026',
        'Orlando': '2010-2023',
        'SS': '2013-2017',
        'Seeker': '2022-2026',
        'Silverado': '1998-2026',
        'Sonic': '2011-2020',
        'Spark': '2005-2023',
        'Spark EUV': '2025-2026',
        'Spin': '2012-2026',
        'Suburban': '1941-2026',
        'Tahoe': '1994-2026',
        'Tavera': '2002-2017',
        'Tracker': '1989-2026',
        'TrailBlazer': '2001-2026',
        'Traverse': '2008-2026',
        'Trax': '2013-2026',
        'Volt': '2010-2019'
    },
    'Ferrari': {
        '12Cilindri': '2024-2026',
        '296': '2021-2026',
        '488': '2015-2019',
        '812': '2017-2024',
        '849 Testarossa': '2025-2026',
        'Amalfi': '2025-2026',
        'California': '2008-2017',
        'Daytona SP3': '2022-2026',
        'F12': '2012-2017',
        'F8': '2019-2023',
        'F80': '2024-2026',
        'FXX K': '2015-2017',
        'GTC4Lusso': '2016-2020',
        'LaFerrari': '2013-2017',
        'Luce': '2026-2026',
        'Monza SP': '2019-2022',
        'Portofino': '2017-2023',
        'Purosangue': '2022-2026',
        'Roma': '2020-2026',
        'SC40': '2025-2026',
        'SF90': '2019-2026'
    },
    'Ford': {
        'B-MAX': '2012-2018',
        'Bronco': '1966-2026',
        'Bronco Basecamp': '2025-2026',
        'Bronco Sport': '2020-2026',
        'C-MAX': '2003-2019',
        'Capri': '1969-2026',
        'EcoSport': '2003-2023',
        'Edge': '2006-2026',
        'Equator': '2021-2026',
        'Equator Sport': '2021-2026',
        'Escape': '2000-2026',
        'Escort': '1968-2023',
        'Everest': '2003-2026',
        'Evos': '2021-2024',
        'Expedition': '1996-2026',
        'Explorer': '1990-2026',
        'Explorer EV': '2024-2026',
        'F-150': '1979-2026',
        'Fiesta': '1976-2023',
        'Fiesta ST': '2004-2023',
        'Figo': '2010-2021',
        'Flex': '2008-2019',
        'Focus': '1998-2026',
        'Focus RS': '2002-2018',
        'Focus ST': '2001-2026',
        'Fusion (North America)': '2005-2020',
        'GT': '2005-2022',
        'Galaxy': '1995-2023',
        'KA': '1996-2021',
        'Kuga': '2008-2026',
        'Maverick': '1969-2026',
        'Mondeo': '1993-2026',
        'Mustang': '1964-2026',
        'Mustang Mach-E': '2020-2026',
        'Puma': '1997-2026',
        'Puma ST': '2020-2026',
        'Ranger': '1998-2026',
        'S-MAX': '2006-2023',
        'Taurus': '1985-2026',
        'Territory': '2004-2026',
        'Tourneo Connect': '2002-2026',
        'Tourneo Courier': '2014-2026',
        'Tourneo Custom': '2012-2026',
        'Transit Connect': '2002-2024',
        'Transit Custom': '2012-2026'
    },
    'Geely': {
        'Atlas': '2016-2026',
        'Atlas Pro': '2021-2025',
        'Azkarra': '2019-2023',
        'Binrui': '2018-2022',
        'Binrui Cool': '2022-2026',
        'Binyue': '2018-2026',
        'Binyue Cool': '2022-2024',
        'Binyue L': '2024-2026',
        'Boyue': '2016-2026',
        'Boyue Cool': '2023-2025',
        'Boyue L': '2022-2026',
        'Boyue Pro': '2019-2023',
        'Boyue REV': '2026-2026',
        'Cityray': '2024-2026',
        'Coolray': '2019-2026',
        'Cowboy': '2024-2026',
        'EX2': '2025-2026',
        'EX5': '2024-2026',
        'EX5 EM-i': '2025-2026',
        'Emgrand': '2018-2026',
        'Emgrand 7': '2016-2020',
        'Emgrand GL': '2016-2021',
        'Emgrand GT': '2015-2020',
        'Emgrand L': '2021-2025',
        'Emgrand S': '2021-2024',
        'Emgrand X7': '2011-2021',
        'Farizon FX': '2020-2023',
        'Farizon Happiness': '2024-2026',
        'GC9': '2015-2024',
        'GS': '2016-2021',
        'GX3 Pro': '2021-2026',
        'Galaxy A7': '2025-2026',
        'Galaxy E5': '2024-2026',
        'Galaxy E8': '2024-2026',
        'Galaxy L6': '2023-2026',
        'Galaxy L7': '2023-2026',
        'Galaxy LEVC L380': '2025-2026',
        'Galaxy M7': '2026-2026',
        'Galaxy M9': '2025-2026',
        'Galaxy Starshine 6': '2025-2026',
        'Galaxy Starshine 7': '2026-2026',
        'Galaxy Starshine 8': '2025-2026',
        'Galaxy Starship 7': '2024-2026',
        'Galaxy V900': '2025-2026',
        'Geome Xingyuan': '2024-2026',
        'Geometry A': '2019-2026',
        'Geometry C': '2020-2024',
        'Geometry E': '2022-2026',
        'Geometry G6': '2022-2026',
        'Geometry M6': '2022-2026',
        'Haoyue': '2020-2022',
        'Haoyue L': '2022-2026',
        'Haoyue Pro': '2024-2025',
        'Icon': '2019-2026',
        'Jiaji': '2019-2025',
        'Kandi EX3': '2018-2018',
        'Monjaro': '2021-2026',
        'Okavango': '2020-2026',
        'Panda': '2022-2026',
        'Preface': '2020-2026',
        'Radar King Kong': '2024-2026',
        'TX4': '2008-2017',
        'Tugella': '2019-2024',
        'Vision S1': '2017-2021',
        'Vision X3': '2017-2021',
        'Vision X3 Pro': '2021-2023',
        'Vision X6': '2016-2021',
        'Vision X6 Pro': '2021-2024',
        'Xingyue': '2019-2023',
        'Xingyue L': '2021-2026'
    },
    'Genesis': {
        'G70': '2017-2026',
        'G80': '2016-2026',
        'G90': '2016-2026',
        'GV60': '2021-2026',
        'GV70': '2020-2026',
        'GV80': '2020-2026',
        'GV80 Coupe': '2023-2026'
    },
    'Haval': {
        'Chitu': '2021-2025',
        'DaGou (Big Dog)': '2020-2026',
        'Dargo': '2022-2026',
        'F5': '2018-2020',
        'F7': '2018-2026',
        'F7x': '2019-2026',
        'H1': '2014-2018',
        'H10': '2026-2026',
        'H2': '2014-2021',
        'H2s': '2016-2020',
        'H3': '2024-2026',
        'H4': '2018-2020',
        'H5': '2020-2026',
        'H6': '2014-2026',
        'H6 Coupe': '2015-2021',
        'H6L': '2025-2026',
        'H6S': '2021-2024',
        'H7': '2016-2026',
        'H8': '2014-2017',
        'H9': '2014-2026',
        'Jolion': '2021-2026',
        'KuGou': '2022-2024',
        'M6': '2017-2026',
        'Menglong (Raptor)': '2023-2026',
        'Shenshou': '2021-2024',
        'Xiaolong': '2023-2025',
        'Xiaolong Max': '2023-2026'
    },
    'Honda': {
        'Accord': '1976-2026',
        'Acty': '1977-2018',
        'Avancier': '1999-2026',
        'Breeze': '2019-2026',
        'Brio': '2011-2018',
        'CR-V': '1995-2026',
        'CR-Z': '2010-2017',
        'City': '1981-2026',
        'Civic': '1972-2026',
        'Civic Type R': '1997-2026',
        'Clarity': '2008-2021',
        'Crider': '2013-2026',
        'Elevate': '2023-2026',
        'Elysion': '2004-2026',
        'Envix': '2019-2026',
        'Fit': '2001-2026',
        'Freed': '2008-2026',
        'Grace': '2014-2020',
        'HR-V': '1998-2026',
        'Insight': '1999-2022',
        'Inspire': '1989-2026',
        'Integra': '1985-2026',
        'Jade': '2015-2020',
        'Jazz': '1983-2026',
        'Legend': '1985-2021',
        'Life': '1997-2026',
        'Mobilio': '2001-2024',
        'N-BOX': '2011-2026',
        'N-BOX Slash': '2014-2020',
        'N-BOX+': '2012-2018',
        'N-One': '2012-2026',
        'N-VAN': '2018-2026',
        'N-WGN': '2013-2026',
        'NSX': '1990-2022',
        'Odyssey': '1994-2026',
        'Odyssey (North America)': '1994-2026',
        'Passport': '1993-2026',
        'Pilot': '2002-2026',
        'Prelude': '1978-2026',
        'Prologue': '2024-2026',
        'Ridgeline': '2005-2026',
        'S660': '2015-2022',
        'Shuttle': '1994-2022',
        'Stepwgn': '1996-2026',
        'Super-One': '2026-2026',
        'UR-V': '2017-2026',
        'Vamos': '1999-2018',
        'Vezel': '2013-2026',
        'WR-V': '2017-2026',
        'XR-V': '2014-2026',
        'Ye P7': '2025-2026',
        'Ye S7': '2024-2026',
        'ZR-V': '2022-2026',
        'e': '2019-2024',
        'e:NP1': '2022-2026',
        'e:NP2': '2024-2026',
        'e:NS1': '2022-2026',
        'e:NS2': '2024-2026',
        'e:Ny1': '2023-2026'
    },
    'Hyundai': {
        'Accent': '1994-2026',
        'Alcazar': '2021-2026',
        'Aslan': '2014-2018',
        'Avante': '1995-2026',
        'Avante N': '2020-2026',
        'Azera': '2005-2022',
        'Bayon': '2021-2026',
        'Casper': '2021-2026',
        'Celesta': '2017-2023',
        'Creta': '2016-2026',
        'Custin': '2021-2026',
        'Custo': '2021-2026',
        'EON': '2011-2019',
        'Elantra': '1990-2026',
        'Elantra N': '2021-2026',
        'Elexio': '2025-2026',
        'Encino': '2018-2020',
        'Exter': '2023-2026',
        'Grandeur': '1986-2026',
        'H-1': '1997-2021',
        'HB20': '2012-2026',
        'IONIQ': '2016-2022',
        'IONIQ 3': '2026-2026',
        'IONIQ 5': '2021-2026',
        'IONIQ 5 N': '2023-2026',
        'IONIQ 6': '2022-2026',
        'IONIQ 9': '2025-2026',
        'Inster': '2024-2026',
        'Kona': '2017-2026',
        'Kona N': '2021-2023',
        'Lafesta': '2018-2025',
        'Maxcruz': '2012-2020',
        'Mistra': '2020-2023',
        'Mufasa': '2023-2026',
        'Nexo': '2018-2026',
        'Palisade': '2018-2026',
        'Reina': '2017-2021',
        'Santa Cruz': '2021-2026',
        'Santa Fe': '2000-2026',
        'Santro': '1998-2022',
        'Solaris': '2010-2022',
        'Sonata': '1988-2026',
        'Stargazer': '2022-2025',
        'Staria': '2021-2026',
        'Tucson': '2004-2026',
        'Veloster': '2011-2022',
        'Venue': '2019-2026',
        'Verna': '1999-2026',
        'i10': '2007-2026',
        'i20': '2008-2026',
        'i20 N': '2021-2023',
        'i30': '2007-2026',
        'i30 N': '2017-2026',
        'i40': '2011-2019',
        'ix20': '2010-2019',
        'ix25': '2014-2021',
        'ix35': '2010-2023'
    },
    'Infiniti': {
        'ESQ': '2014-2019',
        'Q30': '2015-2019',
        'Q50': '2013-2024',
        'Q60': '2013-2022',
        'Q70': '2013-2019',
        'QX30': '2016-2019',
        'QX50': '2013-2025',
        'QX55': '2021-2025',
        'QX60': '2013-2026',
        'QX65': '2026-2026',
        'QX70': '2013-2017',
        'QX80': '2013-2026'
    },
    'Jaguar': {
        'E-Pace': '2017-2024',
        'F-Pace': '2016-2025',
        'F-Type': '2013-2024',
        'I-Pace': '2018-2024',
        'XE': '2015-2024',
        'XF': '2007-2024',
        'XJ': '1968-2019',
        'XJR': '1994-2019'
    },
    'Jeep': {
        'Avenger': '2023-2026',
        'Cherokee': '1983-2026',
        'Compass': '2006-2026',
        'Gladiator': '2019-2026',
        'Grand Cherokee': '1992-2026',
        'Grand Commander': '2018-2022',
        'Recon': '2025-2026',
        'Renegade': '2014-2025',
        'Wagoneer': '1984-2026',
        'Wagoneer S': '2024-2026',
        'Wrangler': '1986-2026'
    },
    'Kia': {
        'Cachet': '2014-2020',
        'Cadenza': '2009-2021',
        'Carens': '1999-2026',
        'Carnival': '1998-2026',
        'Ceed': '2006-2026',
        'Ceed GT': '2012-2021',
        'Cerato': '2003-2026',
        'EV2': '2026-2026',
        'EV3': '2024-2026',
        'EV4': '2025-2026',
        'EV5': '2023-2026',
        'EV6': '2021-2026',
        'EV9': '2023-2026',
        'Forte': '2008-2024',
        'K3': '2012-2026',
        'K4': '2024-2026',
        'K5': '2010-2026',
        'K7': '2009-2021',
        'K8': '2021-2026',
        'K9': '2012-2026',
        'K900': '2014-2022',
        'KX1': '2018-2026',
        'KX3': '2019-2023',
        'KX5': '2016-2022',
        'KX7': '2017-2021',
        'Mohave': '2008-2025',
        'Morning': '2004-2026',
        'Niro': '2016-2026',
        'Optima': '2000-2020',
        'PV5': '2025-2026',
        'Pegas': '2017-2026',
        'Picanto': '2004-2026',
        'Pride': '1987-2017',
        'Proceed': '2018-2025',
        'Quoris': '2012-2018',
        'Ray': '2011-2026',
        'Rio': '1999-2023',
        'Sedona': '1998-2021',
        'Seltos': '2019-2026',
        'Soluto': '2025-2026',
        'Sonet': '2020-2026',
        'Sorento': '2002-2026',
        'Soul': '2008-2025',
        'Soul EV': '2014-2023',
        'Sportage': '1993-2026',
        'Sportage (China)': '2018-2026',
        'Stinger': '2017-2023',
        'Stonic': '2017-2026',
        'Syros': '2025-2026',
        'Tasman': '2025-2026',
        'Telluride': '2019-2026',
        'Venga': '2009-2018',
        'XCeed': '2019-2025'
    },
    'Lamborghini': {
        'Aventador': '2011-2022',
        'Centenario': '2016-2018',
        'Countach LPI 800-4': '2021-2023',
        'Fenomeno': '2025-2026',
        'Huracán': '2014-2024',
        'Revuelto': '2023-2026',
        'Sián': '2019-2022',
        'Temerario': '2024-2026',
        'Urus': '2017-2026'
    },
    'Land Rover': {
        'Defender': '1983-2026',
        'Discovery': '1989-2026',
        'Discovery Sport': '2014-2026',
        'Range Rover': '1970-2026',
        'Range Rover Evoque': '2011-2026',
        'Range Rover Sport': '2005-2026',
        'Range Rover Velar': '2017-2026'
    },
    'Lexus': {
        'CT': '2010-2022',
        'ES': '1989-2026',
        'GS': '1993-2020',
        'GS F': '2015-2018',
        'GX': '2002-2026',
        'HS': '2009-2018',
        'IS': '1999-2026',
        'LBX': '2023-2026',
        'LC': '2017-2026',
        'LM': '2019-2026',
        'LS': '1989-2026',
        'LX': '1995-2026',
        'NX': '2014-2026',
        'RC': '2014-2026',
        'RC F': '2014-2026',
        'RX': '1997-2026',
        'RZ': '2022-2026',
        'TX': '2023-2026',
        'TZ': '2026-2026',
        'UX': '2018-2026'
    },
    'Li Auto (Lixiang)': {
        'L6': '2024-2026',
        'L7': '2023-2026',
        'L8': '2022-2026',
        'L9': '2022-2026',
        'Mega': '2024-2026',
        'One': '2019-2023',
        'i6': '2025-2026',
        'i8': '2025-2026'
    },
    'Maserati': {
        'GT2 Stradale': '2024-2026',
        'Ghibli': '1992-2024',
        'GranCabrio': '2010-2026',
        'GranTurismo': '2007-2026',
        'Grecale': '2022-2026',
        'Levante': '2016-2024',
        'MC20': '2020-2026',
        'MCPura': '2025-2026',
        'Mostro Zagato': '2015-2022',
        'Quattroporte': '1979-2024'
    },
    'Mazda': {
        '2': '2003-2026',
        '3': '2003-2026',
        '5': '2005-2018',
        '6': '2002-2024',
        '6e': '2025-2026',
        'Atenza': '2002-2019',
        'Axela': '2003-2019',
        'BT-50': '2006-2026',
        'Biante': '2008-2018',
        'Bongo': '1966-2020',
        'CX-3': '2015-2026',
        'CX-30': '2019-2026',
        'CX-4': '2016-2024',
        'CX-5': '2011-2026',
        'CX-50': '2022-2026',
        'CX-60': '2022-2026',
        'CX-6e': '2026-2026',
        'CX-70': '2024-2026',
        'CX-8': '2017-2023',
        'CX-80': '2024-2026',
        'CX-9': '2006-2024',
        'CX-90': '2023-2026',
        'Carol': '1989-2026',
        'Demio': '1996-2019',
        'EZ-6': '2024-2026',
        'EZ-60': '2025-2026',
        'Familia': '1985-2026',
        'Flair': '2012-2026',
        'Flair Crossover': '2014-2026',
        'Flair Wagon': '2012-2026',
        'MX-30': '2020-2026',
        'MX-5': '1989-2026',
        'Premacy': '1999-2017',
        'Roadster': '1989-2026',
        'Scrum': '1991-2026'
    },
    'Mercedes-Benz': {
        'A-Class': '1997-2026',
        'A-Class AMG': '2013-2026',
        'AMG GT': '2014-2026',
        'B-Class': '2005-2026',
        'C-Class': '1993-2026',
        'C-Class AMG': '1994-2026',
        'CLA': '2013-2026',
        'CLA AMG': '2013-2026',
        'CLE': '2023-2026',
        'CLE AMG': '2023-2026',
        'CLS': '2004-2023',
        'CLS AMG': '2005-2023',
        'E-Class': '1992-2026',
        'E-Class AMG': '1994-2026',
        'EQA': '2021-2026',
        'EQB': '2021-2026',
        'EQC': '2019-2023',
        'EQE': '2022-2026',
        'EQE AMG': '2022-2026',
        'EQE SUV': '2022-2026',
        'EQE SUV AMG': '2022-2026',
        'EQS': '2021-2026',
        'EQS AMG': '2021-2026',
        'EQS SUV': '2022-2026',
        'G-Class': '1979-2026',
        'G-Class AMG': '1993-2026',
        'G-Class AMG 6x6': '2013-2024',
        'GLA': '2013-2026',
        'GLA AMG': '2014-2026',
        'GLB': '2019-2026',
        'GLB AMG': '2019-2026',
        'GLC': '2015-2026',
        'GLC AMG': '2016-2026',
        'GLC Coupe': '2016-2026',
        'GLC Coupe AMG': '2016-2026',
        'GLE': '2015-2026',
        'GLE AMG': '2015-2026',
        'GLE Coupe': '2015-2026',
        'GLE Coupe AMG': '2015-2026',
        'GLS': '2015-2026',
        'GLS AMG': '2015-2026',
        'Maybach GLS': '2019-2026',
        'Maybach S-Класс': '2014-2026',
        'R-Class': '2005-2017',
        'S-Class': '1972-2026',
        'S-Class AMG': '1999-2026',
        'SL-Class': '1954-2020',
        'SL-Class AMG': '1993-2026',
        'SLC': '1971-2020',
        'SLC AMG': '2016-2020',
        'V-Класс': '1996-2026',
        'Vito': '1996-2026'
    },
    'Mitsubishi': {
        'ASX': '2010-2026',
        'Airtrek': '2001-2023',
        'Attrage': '2014-2026',
        'Colt': '1978-2026',
        'Delica': '1979-2019',
        'Delica D:5': '2007-2026',
        'Delica Mini': '2023-2026',
        'Destinator': '2025-2026',
        'Eclipse Cross': '2017-2026',
        'Grandis': '2003-2026',
        'L200': '1986-2026',
        'Lancer': '1973-2017',
        'Mirage': '1978-2026',
        'Montero': '1982-2021',
        'Outlander': '2002-2026',
        'Outlander Sport': '2010-2026',
        'Pajero': '1982-2022',
        'Pajero Sport': '1998-2026',
        'RVR': '1991-2024',
        'Triton': '2006-2026',
        'Xforce': '2023-2026',
        'Xpander': '2017-2026'
    },
    'Nio': {
        'EC6': '2020-2026',
        'EC7': '2023-2026',
        'EL6': '2023-2026',
        'ES6': '2019-2026',
        'ES7': '2022-2026',
        'ES8': '2018-2026',
        'ES9': '2026-2026',
        'ET5': '2022-2026',
        'ET7': '2021-2026',
        'ET9': '2024-2026',
        'Firefly': '2025-2026',
        'Onvo L60': '2024-2026',
        'Onvo L80': '2026-2026',
        'Onvo L90': '2025-2026'
    },
    'Nissan': {
        '370Z': '2008-2020',
        'AD': '1982-2026',
        'Almera': '1995-2018',
        'Altima': '1992-2026',
        'Ariya': '2020-2026',
        'Armada': '2003-2026',
        'Cima': '1988-2022',
        'Cube': '1998-2020',
        'Dayz': '2013-2026',
        'Dayz Roox': '2014-2020',
        'Elgrand': '1997-2026',
        'Fairlady Z': '1969-2026',
        'Frontier': '2009-2026',
        'Frontier Pro': '2025-2026',
        'Fuga': '2004-2022',
        'GT-R': '2007-2025',
        'Gravite': '2026-2026',
        'Juke': '2010-2026',
        'Juke Nismo': '2013-2019',
        'Kait': '2025-2026',
        'Kicks': '2016-2026',
        'Lafesta': '2004-2018',
        'Lannia': '2015-2022',
        'Leaf': '2010-2026',
        'Livina': '2006-2026',
        'Magnite': '2020-2026',
        'March': '1982-2022',
        'Maxima': '1981-2023',
        'Micra': '1982-2026',
        'Murano': '2002-2026',
        'N6': '2025-2026',
        'N7': '2025-2026',
        'NP200': '2008-2024',
        'NV100 Clipper': '2003-2026',
        'NV200': '2009-2026',
        'NV300': '2016-2021',
        'NV350 Caravan': '2012-2021',
        'NX8': '2026-2026',
        'Navara (Frontier)': '1985-2026',
        'Note': '2005-2026',
        'Pathfinder': '1985-2026',
        'Patrol': '1980-2026',
        'Primastar': '2002-2026',
        'Pulsar': '1982-2018',
        'Qashqai': '2006-2026',
        'Quest': '1992-2018',
        'Rogue': '2007-2026',
        'Rogue Sport': '2017-2022',
        'Roox': '2009-2026',
        'Sakura': '2022-2026',
        'Sentra': '1982-2026',
        'Serena': '1991-2026',
        'Skyline': '1968-2026',
        'Sunny': '1982-2026',
        'Sylphy': '2012-2026',
        'Teana': '2003-2026',
        'Terra': '2018-2026',
        'Terrano': '1985-2022',
        'Tiida': '2004-2026',
        'Titan': '2003-2024',
        'Vanette': '1978-2017',
        'Versa': '2006-2026',
        'Versa Note': '2013-2019',
        'Wingroad': '1996-2018',
        'X-Terra': '2020-2026',
        'X-Trail': '2000-2026',
        'Z': '2021-2026'
    },
    'Porsche': {
        '718 Spyder': '2019-2025',
        '911': '1963-2026',
        '911 GT2': '1995-2019',
        '911 GT3': '1999-2026',
        '911 R': '2016-2019',
        '911 S/T': '2023-2026',
        'Boxster': '1996-2025',
        'Cayenne': '2002-2026',
        'Cayman': '2005-2025',
        'Cayman GT4': '2015-2026',
        'Macan': '2014-2026',
        'Panamera': '2009-2026',
        'Taycan': '2019-2026'
    },
    'Rolls-Royce': {
        'Boat Tail': '2021-2022',
        'Cullinan': '2018-2026',
        'Dawn': '2015-2023',
        'Ghost': '2010-2026',
        'Phantom': '1925-2026',
        'Spectre': '2023-2026',
        'Wraith': '2013-2023'
    },
    'Skoda': {
        'Citigo': '2011-2020',
        'Elroq': '2024-2026',
        'Elroq RS': '2025-2026',
        'Enyaq': '2020-2026',
        'Enyaq Coupe': '2022-2026',
        'Enyaq Coupe RS': '2022-2026',
        'Enyaq RS': '2022-2026',
        'Epiq': '2026-2026',
        'Fabia': '1999-2026',
        'Kamiq': '2018-2026',
        'Karoq': '2017-2026',
        'Kodiaq': '2016-2026',
        'Kodiaq GT': '2019-2026',
        'Kodiaq RS': '2018-2026',
        'Kushaq': '2021-2026',
        'Kylaq': '2024-2026',
        'Octavia': '1959-2026',
        'Octavia RS': '2001-2026',
        'Rapid': '2012-2023',
        'Scala': '2019-2026',
        'Slavia': '2021-2026',
        'Superb': '2001-2026',
        'Yeti': '2009-2018'
    },
    'Subaru': {
        'Ascent': '2017-2026',
        'BRZ': '2012-2026',
        'Crosstrek': '2012-2026',
        'Forester': '1997-2026',
        'Impreza': '1992-2026',
        'Legacy': '1989-2025',
        'Levorg': '2014-2026',
        'Outback': '1994-2026',
        'Solterra': '2022-2026',
        'WRX': '2014-2026',
        'WRX STi': '2014-2021',
        'XV': '2011-2023'
    },
    'Tesla': {
        'Cybertruck': '2023-2026',
        'Model 3': '2017-2026',
        'Model S': '2012-2026',
        'Model X': '2015-2026',
        'Model Y': '2020-2026',
        'Roadster': '2008-2017'
    },
    'Toyota': {
        '4Runner': '1984-2026',
        'Agya': '2013-2026',
        'Allion': '2001-2026',
        'Alphard': '2002-2026',
        'Aqua': '2011-2026',
        'Aurion': '2006-2017',
        'Auris': '2006-2018',
        'Avalon': '1994-2026',
        'Avanza': '2006-2026',
        'Avensis': '1997-2018',
        'Aygo': '2005-2022',
        'Aygo X': '2022-2026',
        'Belta': '2005-2026',
        'C-HR': '2016-2026',
        'C-HR+': '2025-2026',
        'COMS': '2012-2026',
        'Camry': '1980-2026',
        'Century': '1982-2026',
        'Comfort': '1995-2017',
        'Copen': '2019-2026',
        'Corolla': '1966-2026',
        'Corolla Cross': '2020-2026',
        'Crown': '1965-2026',
        'Crown Kluger': '2021-2026',
        'Crown Majesta': '1991-2018',
        'Esquire': '2014-2021',
        'Estima': '1990-2019',
        'Etios': '2010-2021',
        'FJ Cruiser': '2006-2022',
        'Fortuner': '2005-2026',
        'Frontlander': '2021-2026',
        'GR GT': '2027-2027',
        'GR86': '2021-2026',
        'GT86': '2012-2021',
        'Grand Highlander': '2023-2026',
        'Granvia': '1995-2026',
        'Harrier': '1997-2026',
        'HiAce': '1982-2026',
        'Highlander': '2001-2026',
        'Hilux': '1968-2026',
        'Hilux Champ': '2023-2026',
        'ISis': '2004-2017',
        'Innova': '2004-2026',
        'Izoa': '2018-2026',
        'JPN Taxi': '2017-2026',
        'Land Cruiser': '1960-2026',
        'Land Cruiser FJ': '2025-2026',
        'Land Cruiser Prado': '1987-2026',
        'Levin': '2014-2026',
        'Lite Ace': '1979-2020',
        'Mark X': '2004-2019',
        'Mirai': '2015-2026',
        'Noah': '2001-2026',
        'Passo': '2004-2023',
        'Pixis Epoch': '2012-2026',
        'Pixis Joy': '2016-2023',
        'Pixis Mega': '2015-2022',
        'Pixis Space': '2011-2017',
        'Pixis Van': '2011-2021',
        'Porte': '2004-2020',
        'Premio': '2001-2021',
        'Previa': '1990-2019',
        'Prius': '1997-2026',
        'Prius Alpha': '2011-2021',
        'Prius c': '2011-2021',
        'Prius v (+)': '2011-2021',
        'ProAce': '2013-2026',
        'ProAce City': '2019-2026',
        'Probox': '2002-2026',
        'RAV4': '1994-2026',
        'Raize': '2019-2026',
        'RegiusAce': '1999-2020',
        'Reiz': '2005-2017',
        'Roomy': '2016-2026',
        'Rumion': '2021-2026',
        'Rush': '2006-2026',
        'Sai': '2009-2017',
        'Sequoia': '2000-2026',
        'Sienna': '1997-2026',
        'Sienta': '2003-2026',
        'Spade': '2012-2020',
        'Starlet Cross': '2024-2026',
        'Succeed': '2002-2020',
        'Supra': '1986-2026',
        'Tacoma': '1995-2026',
        'Tank': '2016-2020',
        'Town Ace': '1976-2020',
        'Tundra': '2000-2026',
        'Urban Cruiser': '2009-2026',
        'Urban Cruiser Taisor': '2024-2026',
        'Vellfire': '2008-2026',
        'Veloz': '2021-2026',
        'Venza': '2008-2026',
        'Verso': '2009-2018',
        'Verso-S': '2010-2018',
        'Vios': '2003-2026',
        'Vitz': '1999-2020',
        'Voxy': '2001-2026',
        'Wigo': '2014-2026',
        'Wildlander': '2020-2026',
        'Wish': '2003-2017',
        'Yaris': '1999-2026',
        'Yaris Cross': '2020-2026',
        'bZ': '2026-2026',
        'bZ3': '2023-2026',
        'bZ3C': '2025-2026',
        'bZ3X': '2025-2026',
        'bZ4X': '2022-2026',
        'bZ5': '2025-2026',
        'bZ7': '2025-2026'
    },
    'Volkswagen': {
        'Amarok': '2010-2026',
        'Arteon': '2017-2024',
        'Arteon R': '2020-2024',
        'Atlas': '2017-2026',
        'Atlas Cross Sport': '2019-2026',
        'Beetle': '1997-2019',
        'Caddy': '1979-2026',
        'California': '1991-2026',
        'Caravelle': '1980-2026',
        'Golf': '1974-2026',
        'Golf GTI': '1976-2026',
        'Golf R': '2009-2026',
        'Golf Sportsvan': '2014-2020',
        'ID.3': '2019-2026',
        'ID.4': '2020-2026',
        'ID.5': '2021-2026',
        'ID.6': '2021-2026',
        'ID.7': '2023-2026',
        'ID.Buzz': '2022-2026',
        'Jetta': '1978-2026',
        'Multivan': '1984-2026',
        'Passat': '1973-2026',
        'Polo': '1975-2026',
        'Polo GTI': '1998-2026',
        'Scirocco': '1974-2017',
        'Scirocco R': '2009-2017',
        'Sharan': '1995-2022',
        'T-Cross': '2018-2026',
        'T-Roc': '2017-2026',
        'T-Roc R': '2019-2024',
        'Taos': '2020-2026',
        'Tiguan': '2007-2026',
        'Tiguan R': '2020-2024',
        'Touareg': '2002-2026',
        'Touareg R': '2020-2026',
        'Touran': '2003-2026',
        'Transporter': '1979-2026',
        'up!': '2012-2023'
    },
    'Volvo': {
        'C40': '2021-2024',
        'EC40': '2024-2026',
        'EM90': '2023-2026',
        'ES90': '2025-2026',
        'EX30': '2023-2026',
        'EX30 Cross Country': '2025-2026',
        'EX40': '2024-2026',
        'EX60': '2026-2026',
        'EX90': '2023-2026',
        'S60': '2000-2024',
        'S60 Cross Country': '2015-2018',
        'S90': '1996-2026',
        'V40': '1995-2020',
        'V40 Cross Country': '2012-2019',
        'V60': '2010-2026',
        'V60 Cross Country': '2015-2026',
        'V90': '1997-2025',
        'V90 Cross Country': '2016-2025',
        'XC40': '2017-2026',
        'XC60': '2008-2026',
        'XC70': '2000-2026',
        'XC90': '2002-2026'
    },
    'Zeekr': {
        '001': '2021-2026',
        '007': '2023-2026',
        '009': '2022-2026',
        '7X': '2024-2026',
        '8X': '2026-2026',
        '9X': '2025-2026',
        'Mix': '2024-2026',
        'X': '2023-2026'
    },
}


def get_models(brand):
    return sorted(list(CAR_DATABASE.get(brand, {}).keys()))

def get_generations(brand, model):
    v = CAR_DATABASE.get(brand, {}).get(model)
    return [v] if v else []

# ════════════════════════════════════════════════
# ПРАВА
# ════════════════════════════════════════════════
def has_rights(uid):
    return (uid == OWNER_ID and OWNER_ID != 0) or \
           (uid == MANAGER_USER_ID and MANAGER_USER_ID != 0)

# ════════════════════════════════════════════════
# БД
# ════════════════════════════════════════════════
def load_db(f, default=None):
    if default is None:
        default = {}
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except:
            return default
    return default

def save_db(f, data):
    try:
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_db error: {e}")

def next_pub_id():
    db = load_db(PUBLICATIONS_DB, {'counter':0,'publications':{}})
    db['counter'] = db.get('counter',0) + 1
    nid = f"id_{db['counter']:04d}"
    save_db(PUBLICATIONS_DB, db)
    return nid

def save_pub(pub_id, **kw):
    db = load_db(PUBLICATIONS_DB, {'counter':0,'publications':{}})
    now = datetime.now()
    db['publications'][pub_id] = {
        **kw, 'pub_id': pub_id,
        'published_at': now.isoformat(),
        'expires_at': (now + timedelta(days=30)).isoformat(),
        'status': 'active',
    }
    save_db(PUBLICATIONS_DB, db)

def find_pub(pub_id):
    return load_db(PUBLICATIONS_DB, {'counter':0,'publications':{}})['publications'].get(pub_id)

def next_lead_id():
    db = load_db(LEADS_DB, {'counter':0,'leads':{}})
    db['counter'] = db.get('counter',0) + 1
    nid = f"lead_{db['counter']:05d}"
    save_db(LEADS_DB, db)
    return nid

def save_lead(lid, data):
    db = load_db(LEADS_DB, {'counter':0,'leads':{}})
    db['leads'][lid] = {**data, 'created_at': datetime.now().isoformat()}
    save_db(LEADS_DB, db)

def get_state(uid):
    if uid not in BRIEF_STATES:
        BRIEF_STATES[uid] = {'step': None, 'data': {}}
    return BRIEF_STATES[uid]

def clear_state(uid):
    BRIEF_STATES.pop(uid, None)

# ════════════════════════════════════════════════
# ОЧИСТКА ТЕКСТА
# ════════════════════════════════════════════════
def clean_text(text):
    if not text:
        return text
    # Удаляем эмодзи
    text = EMOJI_PATTERN.sub('', text)
    # Удаляем статусные строки
    text = re.sub(r'^[^\n]*[Вв]\s+продаже[^\n]*\n?', '', text, flags=re.IGNORECASE|re.MULTILINE)
    text = re.sub(r'^[^\n]*[Вв]\s+свободной\s+продаже[^\n]*\n?', '', text, flags=re.IGNORECASE|re.MULTILINE)
    text = re.sub(r'^[^\n]*АВТО\s+ИЗ\s+[А-ЯЁ]+[^\n]*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[^\n]*[Аа]вто\s+прибыло[^\n]*\n?', '', text, flags=re.IGNORECASE|re.MULTILINE)
    text = re.sub(r'^[^\n]*\bСБХ\b[^\n]*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[^\n]*[Аа]вто\s+готово[^\n]*\n?', '', text, flags=re.IGNORECASE|re.MULTILINE)
    text = re.sub(r'^[^\n]*срок\s+доставки[^\n]*\n?', '', text, flags=re.IGNORECASE|re.MULTILINE)
    # Хэштеги
    text = re.sub(r'#[A-Za-zА-Яа-яёЁ0-9_]+', '', text)
    # Фразы из списка
    for p in PHRASES_TO_DELETE:
        text = re.sub(p, '', text, flags=re.IGNORECASE|re.MULTILINE)
    # Имена менеджеров
    text = re.sub(r'^.*[Мм]енеджер[^\n]*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^.*[Аа]ртём[^\n]*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^.*[Рр]оман[^\n]*\n?', '', text, flags=re.MULTILINE)
    # @каналы и ссылки
    text = re.sub(r'@[A-Za-z0-9_]+', '', text)
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'\+?\d[\d\s\-()]{6,}\d', '', text)
    text = re.sub(r'Доставка\s+осуществляется[^\n]*', '', text, flags=re.IGNORECASE)
    return text

def markup_price(text):
    def replace(m):
        raw = re.sub(r'[\s,.\u00a0]','', m.group(1))
        cur = m.group(2)
        if cur in ('руб','RUB'): cur = '₽'
        try:
            p = int(raw)
            if cur == '₽':
                if p>=30_000_000: add=1_000_000
                elif p>=25_000_000: add=500_000
                elif p>=20_000_000: add=350_000
                elif p>=15_000_000: add=250_000
                elif p>=10_000_000: add=180_000
                elif p>=7_000_000: add=100_000
                elif p>=5_000_000: add=80_000
                else: add=40_000
            else: add=1_000
            np = p+add
            return f"{np:,}".replace(',','.')+cur
        except: return m.group(0)
    for pat in [r'(\d[\d\s.,\u00a0]*\d)\s*(₽|руб|RUB)',
                r'(\d[\d\s.,\u00a0]*\d)\s*(€)',
                r'(\d[\d\s.,\u00a0]*\d)\s*(\$)']:
        text = re.sub(pat, replace, text)
    return text

def format_text(text):
    lines = text.split('\n')
    result = []
    for line in lines:
        s = line.strip()
        if not s: result.append(''); continue
        if re.match(r'^[•\-–—\s:]+$', s): continue
        s = re.sub(r'^[-–—]\s*', '', s)
        if not s or re.match(r'^[•\s:]+$', s): continue
        if s.startswith('•') or s.startswith('▪'):
            c = re.sub(r'^[•▪]\s*', '', s)
            c = re.sub(r'^[-–—]\s*', '', c)
            if c and not re.match(r'^[\s:]+$', c): result.append(f'• {c}')
            continue
        if ':' in s and len(s.split(':')[0]) < 40 and not re.search(r'[₽€$]', s):
            val = s.split(':',1)[1].strip()
            if val: result.append(f'• {s}'); continue
        result.append(s)
    text = '\n'.join(result)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^\s*[•\-–—]?\s*:\s*$', '', text, flags=re.MULTILINE)
    return text.strip()

def make_bold_model(text):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith('•') and not s.startswith('<b>'):
            lines[i] = f'<b>{s}</b>'
            break
    return '\n'.join(lines)

def make_bold_prices(text):
    def bold(m):
        l = m.group(1).strip()
        return f'<b>{l}</b>' if not l.startswith('<b>') else l
    return re.sub(r'^([^\n<]*\d[\d\s.,\u00a0]*\d\s*[₽€$][^\n<]*)$', bold, text, flags=re.MULTILINE)

def make_headers_bold(text):
    for h in ['Комплектация:', 'Состояние:', 'Комплектация и оснащение:']:
        text = re.sub(re.escape(h), f'<b>{h}</b>', text, flags=re.IGNORECASE)
    return text

def insert_id(text, pub_id, link):
    tag = f'<a href="{link}">{pub_id}</a>' if link else pub_id
    lines = text.split('\n')
    last_price = -1
    for i, l in enumerate(lines):
        if re.search(r'<b>[^<]*\d[^<]*[₽€$][^<]*</b>', l):
            last_price = i
    if last_price >= 0:
        lines.insert(last_price+1, tag)
    else:
        lines.append(tag)
    return '\n'.join(lines)

def build_footer(text, pub_id):
    has_moscow = 'в москве' in text.lower() or 'во владивостоке' in text.lower()
    sp = pub_id or 'start'
    mgr = f'<a href="https://t.me/{BOT_USERNAME}?start={sp}">«Написать менеджеру»</a> 📞 ✅'
    ch  = f'<a href="https://t.me/{TARGET_CHANNEL_NAME.replace("@","")}">{TARGET_CHANNEL_NAME}</a>'
    order = f'🏎️ Заказать другое авто — <a href="https://t.me/{BOT_USERNAME}">жми сюда</a>'
    if has_moscow or '₽' in text:
        return (f"\n\nДоставка осуществляется во все города РФ\n\n"
                f"По поводу покупки или подбора:\n{mgr}\n"
                f"(Ответ в течении часа)\n{order}\n\n{ch}")
    return (f"\n\nРассчитаем стоимость до Вашего дома 🏠 ✅\n{mgr}\n"
            f"(Ответ в течении часа)\n{order}\n\n{ch}")

def hashtags(text):
    tags = set()
    tl = text.lower()
    for kw, tag in [('bmw','#BMW'),('mercedes','#Mercedes'),('audi','#Audi'),
                    ('toyota','#Toyota'),('lexus','#Lexus'),('kia','#Kia'),
                    ('hyundai','#Hyundai'),('volkswagen','#Volkswagen'),
                    ('porsche','#Porsche'),('tesla','#Tesla'),
                    ('geely','#Geely'),('haval','#Haval')]:
        if kw in tl: tags.add(tag)
        if len(tags) >= 2: break
    return ' '.join(list(tags)[:2] + ['#авточастно','#автоподзаказ','#ProAuto77'])

def smart_car_name(original):
    if not original: return None
    for line in original.split('\n'):
        c = EMOJI_PATTERN.sub('', line).strip()
        c = re.sub(r'^[-–—•*]\s*', '', c).strip()
        if not c or len(c) < 3: continue
        for brand in CAR_BRANDS:
            if brand.lower() in c.lower():
                name = re.sub(r'\bв\s+продаже\b|\bв\s+наличии\b', '', c, flags=re.IGNORECASE)
                name = re.sub(r'[‼!]+', '', name).strip()
                if len(name) > 3: return name[:80]
    return None

def format_announcement(original, pub_id, pub_link):
    if not original: return None
    t = clean_text(original)
    t = markup_price(t)
    if re.search(r'в москве', t, re.IGNORECASE):
        t = re.sub(r'^.*Цена.*в (?:Уссурийске|Владивостоке).*\n?', '', t,
                   flags=re.IGNORECASE|re.MULTILINE)
    t = format_text(t)
    t = make_headers_bold(t)
    t = make_bold_model(t)
    t = make_bold_prices(t)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    t = insert_id(t, pub_id, pub_link)
    header = "Прямая продажа ✅\n\n"
    footer = build_footer(t, pub_id)
    ht = hashtags(original)
    return header + t + footer + (f"\n\n{ht}" if ht else "")

# ════════════════════════════════════════════════
# ПУБЛИКАЦИЯ ОБЪЯВЛЕНИЙ
# ════════════════════════════════════════════════
def fwd_source(message):
    if not message.forward_from_chat:
        return {'is_forwarded': False}
    return {
        'is_forwarded': True,
        'source_chat_id': message.forward_from_chat.id,
        'source_message_id': message.forward_from_message_id,
        'source_chat_username': message.forward_from_chat.username,
    }

def orig_link(src):
    if not src.get('is_forwarded'): return None
    mid = src['source_message_id']
    un  = src['source_chat_username']
    cid = src['source_chat_id']
    if un: return f"https://t.me/{un}/{mid}"
    cid_s = str(cid)[4:] if str(cid).startswith('-100') else str(abs(cid))
    return f"https://t.me/c/{cid_s}/{mid}"

def pub_link(msg_id):
    return f"https://t.me/{TARGET_CHANNEL_NAME.replace('@','')}/{msg_id}"

def is_valid(text, has_media):
    if not has_media: return False, "нет медиа"
    if not text or len(text) < 5: return True, "OK"
    has_p = bool(re.search(r'\d[\d\s.,]*\d\s*[₽€$]', text))
    has_k = bool(re.search(
        r'BMW|Mercedes|Audi|Toyota|Kia|Hyundai|Volkswagen|Porsche|'
        r'Honda|Nissan|Mazda|Geely|Haval|BYD|Tesla|Lexus|Volvo|'
        r'авто|машин|двигател', text, re.IGNORECASE))
    return (True, "OK") if (has_p or has_k) else (False, "не авто")

async def publish(update, context, src):
    msg = update.message
    mgid = msg.media_group_id
    text = msg.text or msg.caption or ""
    has_photo = bool(msg.photo)
    has_video = bool(msg.video)

    if mgid:
        if mgid not in media_groups_cache:
            media_groups_cache[mgid] = {'photos':[], 'caption':'', 'src':src}
            asyncio.create_task(_process_album(mgid, context))
        if msg.photo:
            media_groups_cache[mgid]['photos'].append(msg.photo[-1].file_id)
        if msg.video:
            media_groups_cache[mgid]['photos'].append(msg.video.file_id)
        if msg.caption and not media_groups_cache[mgid]['caption']:
            media_groups_cache[mgid]['caption'] = msg.caption
        return

    valid, reason = is_valid(text, has_photo or has_video)
    if not valid:
        logger.info(f"⏭ {reason}")
        return

    pid = next_pub_id()
    sl  = orig_link(src) if src else None
    fmt = format_announcement(text, pid, None)
    if not fmt: return

    try:
        if has_photo:
            sent = await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID,
                photo=msg.photo[-1].file_id,
                caption=fmt, parse_mode='HTML')
        elif has_video:
            sent = await context.bot.send_video(
                chat_id=TARGET_GROUP_ID,
                video=msg.video.file_id,
                caption=fmt, parse_mode='HTML')
        else:
            sent = await context.bot.send_message(
                chat_id=TARGET_GROUP_ID, text=fmt, parse_mode='HTML')

        pmid = sent.message_id
        pl   = pub_link(pmid)
        new  = format_announcement(text, pid, pl)
        try:
            if has_photo or has_video:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID, message_id=pmid,
                    caption=new, parse_mode='HTML')
            else:
                await context.bot.edit_message_text(
                    chat_id=TARGET_GROUP_ID, message_id=pmid,
                    text=new, parse_mode='HTML')
        except: pass

        save_pub(pid, source_link=sl,
                 source_username=src.get('source_chat_username') if src else None,
                 published_message_id=pmid,
                 original_caption=text,
                 telegram_link=pl)
        logger.info(f"✅ {pid}")
    except Exception as e:
        logger.error(f"❌ publish: {e}")

async def _process_album(mgid, context):
    await asyncio.sleep(3)
    if mgid not in media_groups_cache: return
    gd = media_groups_cache[mgid]
    photos, caption, src = gd['photos'], gd['caption'], gd['src']
    if not photos:
        del media_groups_cache[mgid]; return
    valid, reason = is_valid(caption, True)
    if not valid:
        del media_groups_cache[mgid]; return
    pid = next_pub_id()
    sl  = orig_link(src) if src else None
    fmt = format_announcement(caption, pid, None)
    if not fmt:
        del media_groups_cache[mgid]; return
    try:
        media = [InputMediaPhoto(media=photos[0], caption=fmt, parse_mode='HTML')] + \
                [InputMediaPhoto(media=p) for p in photos[1:]]
        sent = await context.bot.send_media_group(chat_id=TARGET_GROUP_ID, media=media)
        pmid = sent[0].message_id if sent else None
        if pmid:
            pl  = pub_link(pmid)
            new = format_announcement(caption, pid, pl)
            try:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID, message_id=pmid,
                    caption=new, parse_mode='HTML')
            except: pass
            save_pub(pid, source_link=sl,
                     source_username=src.get('source_chat_username') if src else None,
                     published_message_id=pmid,
                     original_caption=caption,
                     telegram_link=pl)
        logger.info(f"✅ Альбом {pid}")
    except Exception as e:
        logger.error(f"❌ album: {e}")
    finally:
        if mgid in media_groups_cache: del media_groups_cache[mgid]

# ════════════════════════════════════════════════
# УВЕДОМЛЕНИЕ МЕНЕДЖЕРУ
# ════════════════════════════════════════════════
async def notify(context, lid, data):
    uid  = data['user_id']
    un   = data.get('username')
    fn   = data.get('first_name','Клиент')
    text = f"🆕 <b>ЗАЯВКА {lid}</b>\n\n"
    if un: text += f"👤 @{un} ({fn})\n"
    text += f"🆔 <code>{uid}</code>\n\n"
    if data.get('pub_id'):
        text += f"🚗 {data.get('car_name','')}\n({data['pub_id']})\n\n"
    text += "<b>Параметры:</b>\n"
    for k,l in [('brand','Марка'),('model','Модель'),('generation','Поколение'),
                ('city','Город'),('timing','Срок')]:
        if data.get(k): text += f"• {l}: {data[k]}\n"
    if un:
        text += f"\n💬 <a href='https://t.me/{un}'>Написать @{un}</a>"
    else:
        text += f"\n💬 <a href='tg://user?id={uid}'>{fn} (нажми)</a>"
        text += f"\n   ID: <code>{uid}</code>"
    for rid in [OWNER_ID, MANAGER_USER_ID]:
        if rid:
            try: await context.bot.send_message(chat_id=rid, text=text, parse_mode='HTML')
            except Exception as e: logger.error(f"notify {rid}: {e}")

# ════════════════════════════════════════════════
# БРИФ — ФИНАЛИЗАЦИЯ
# ════════════════════════════════════════════════
async def finalize(update, context, uid, data_extra=None):
    st   = get_state(uid)
    data = st['data']
    if data_extra: data.update(data_extra)
    user = update.effective_user
    lid  = next_lead_id()
    ld   = {'user_id':uid, 'username':user.username,
            'first_name':user.first_name, 'last_name':user.last_name, **data}
    save_lead(lid, ld)

    if data.get('interest_type') == 'consultation':
        msg = (f"✅ <b>Спасибо! Заявка #{lid} принята</b>\n\n"
               f"✍️ Запрос консультации\n\nМенеджер свяжется с Вами в течение 1 часа\n"
               f"Благодарим за доверие к ProAuto ✅\n\n{TARGET_CHANNEL_NAME}")
    elif data.get('pub_id'):
        msg = (f"✅ <b>Заявка #{lid} принята</b>\n\n"
               f"🚗 {data.get('car_name','авто')}\n"
               f"📍 {data.get('city','?')}\n⏰ {data.get('timing','?')}\n\n"
               f"Менеджер свяжется с Вами в течение 1 часа\n"
               f"Благодарим за доверие к ProAuto ✅\n\n{TARGET_CHANNEL_NAME}")
    else:
        car = f"{data.get('brand','')} {data.get('model','')}".strip()
        if data.get('generation'): car += f" ({data['generation']})"
        msg = (f"✅ <b>Заявка #{lid} принята</b>\n\n"
               f"🚗 {car or 'Авто на заказ'}\n"
               f"📍 {data.get('city','?')}\n⏰ {data.get('timing','?')}\n\n"
               f"Менеджер свяжется с Вами в течение 1 часа\n"
               f"Благодарим за доверие к ProAuto ✅\n\n{TARGET_CHANNEL_NAME}")

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=msg, parse_mode='HTML')
    await notify(context, lid, ld)
    clear_state(uid)

# ════════════════════════════════════════════════
# CALLBACK КНОПОК
# ════════════════════════════════════════════════
def city_kb(prefix):
    kb, row = [], []
    for i, c in enumerate(CITIES):
        row.append(InlineKeyboardButton(c, callback_data=f"{prefix}city_{i}"))
        if len(row)==2: kb.append(row); row=[]
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("✍️ Другой город", callback_data=f"{prefix}city_other")])
    return kb

def timing_kb(prefix):
    return [[InlineKeyboardButton(t, callback_data=f"{prefix}timing_{i}")]
            for i,t in enumerate(TIMINGS)]

async def button_callback(update, context):
    q = update.callback_query
    await q.answer()
    d  = q.data
    uid = q.from_user.id
    st  = get_state(uid)

    # ── КОНКРЕТНОЕ АВТО ──────────────────────────
    if d.startswith("yes_"):
        pid = d[4:]
        pub = find_pub(pid)
        cn  = smart_car_name(pub.get('original_caption','') if pub else '') or 'автомобиль'
        st['data'] = {'pub_id':pid,'car_name':cn,'interest_type':'specific_car'}
        await q.edit_message_text(f"✅ {cn[:50]}\n\nВ какой город?", parse_mode='HTML')
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🏙 <b>В какой город нужна доставка?</b>",
            reply_markup=InlineKeyboardMarkup(city_kb("s_")), parse_mode='HTML')
        return

    if d.startswith("s_city_"):
        idx = d[7:]
        st['data']['city'] = CITIES[int(idx)] if idx!='other' else 'Другой'
        await q.edit_message_text(f"🏙 {st['data']['city']}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏰ <b>Когда планируете покупку?</b>",
            reply_markup=InlineKeyboardMarkup(timing_kb("s_")), parse_mode='HTML')
        return

    if d.startswith("s_timing_"):
        st['data']['timing'] = TIMINGS[int(d[9:])]
        await q.edit_message_text(f"⏰ {st['data']['timing']} ✅")
        await finalize(update, context, uid)
        return

    # ── КОНСУЛЬТАЦИЯ ─────────────────────────────
    if d == "consult":
        st['data']['interest_type'] = 'consultation'
        await q.edit_message_text("✍️ Оформляем запрос консультации...")
        await finalize(update, context, uid)
        return

    # ── ИНДИВИДУАЛЬНЫЙ ЗАКАЗ ─────────────────────
    if d == "custom":
        st['data'] = {'interest_type':'custom'}
        kb = [[InlineKeyboardButton(g, callback_data=f"bg_{i}")]
              for i,g in enumerate(BRAND_GROUPS.keys())]
        kb.append([InlineKeyboardButton("🤔 Любая марка", callback_data="bg_any")])
        await q.edit_message_text("🚗 <b>Какие марки интересуют?</b>",
                                  reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        return

    if d == "bg_any":
        st['data'].update({'brand':'Любая','model':'Любая','generation':'Любое'})
        await q.edit_message_text("🚗 Марка: Любая")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏰ <b>Когда планируете покупку?</b>",
            reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
        return

    if d.startswith("bg_"):
        try:
            gi = int(d[3:])
            gn = list(BRAND_GROUPS.keys())[gi]
            brands = BRAND_GROUPS[gn]
            st['data']['gidx'] = gi
            kb, row = [], []
            for i,b in enumerate(brands):
                row.append(InlineKeyboardButton(b, callback_data=f"br_{gi}_{i}"))
                if len(row)==2: kb.append(row); row=[]
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="custom")])
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"<b>{gn}</b>\n\nВыберите марку:",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except: pass
        return

    if d.startswith("br_"):
        try:
            parts = d.split("_")
            gi,bi = int(parts[1]), int(parts[2])
            brands_in_group = BRAND_GROUPS[list(BRAND_GROUPS.keys())[gi]]
            if bi >= len(brands_in_group):
                await q.edit_message_text("⚠️ Попробуйте заново /start"); clear_state(uid); return
            brand = brands_in_group[bi]
            st['data']['brand'] = brand
            await q.edit_message_text(f"✅ Марка: <b>{brand}</b>", parse_mode='HTML')
            models = get_models(brand)
            if not models:
                st['data']['model'] = 'Любая'
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⏰ <b>Когда планируете?</b>",
                    reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
                return
            kb, row = [], []
            for i,m in enumerate(models):
                row.append(InlineKeyboardButton(m, callback_data=f"mo_{i}"))
                if len(row)==2: kb.append(row); row=[]
            if row: kb.append(row)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"<b>{brand}</b> — выберите модель:",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except Exception as e:
            logger.error(f"br_ error: {e}")
        return

    if d.startswith("mo_"):
        try:
            idx   = int(d[3:])
            brand = st['data'].get('brand','')
            models_list = get_models(brand)
            if not models_list or idx >= len(models_list):
                await q.edit_message_text(
                    "⚠️ Список моделей изменился. Выберите заново:",
                    parse_mode='HTML'
                )
                clear_state(uid)
                return
            model = models_list[idx]
            st['data']['model'] = model
            await q.edit_message_text(f"✅ Модель: <b>{model}</b>", parse_mode='HTML')
            gens = get_generations(brand, model)
            if not gens:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⏰ <b>Когда планируете?</b>",
                    reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
                return
            kb = [[InlineKeyboardButton(g, callback_data=f"ge_{i}")]
                  for i,g in enumerate(gens)]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"<b>{brand} {model}</b> — поколение:",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except Exception as e:
            logger.error(f"mo_ error: {e}")
        return

    if d.startswith("ge_"):
        try:
            brand = st['data'].get('brand','')
            model = st['data'].get('model','')
            gen   = get_generations(brand, model)[int(d[3:])]
            st['data']['generation'] = gen
            await q.edit_message_text(f"✅ Поколение: <b>{gen}</b>", parse_mode='HTML')
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⏰ <b>Когда планируете?</b>",
                reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
        except Exception as e:
            logger.error(f"ge_ error: {e}")
        return

    if d.startswith("c_timing_"):
        st['data']['timing'] = TIMINGS[int(d[9:])]
        await q.edit_message_text(f"⏰ {st['data']['timing']}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🏙 <b>В какой город?</b>",
            reply_markup=InlineKeyboardMarkup(city_kb("c_")), parse_mode='HTML')
        return

    if d.startswith("c_city_"):
        idx = d[7:]
        st['data']['city'] = CITIES[int(idx)] if idx!='other' else 'Другой'
        await q.edit_message_text(f"🏙 {st['data']['city']} ✅")
        await finalize(update, context, uid)
        return

# ════════════════════════════════════════════════
# КОМАНДЫ
# ════════════════════════════════════════════════
async def cmd_start(update, context):
    uid  = update.effective_user.id
    args = context.args

    if args and args[0].startswith('id_'):
        pid = args[0]
        pub = find_pub(pid)
        cn  = smart_car_name(pub.get('original_caption','') if pub else '') or 'автомобиль'
        get_state(uid)['data'] = {'pub_id':pid,'car_name':cn,'interest_type':'specific_car'}
        btn_name = cn[:45]
        kb = [
            [InlineKeyboardButton(f"✅ {btn_name}", callback_data=f"yes_{pid}")],
            [InlineKeyboardButton("🏎️ Другой автомобиль", callback_data="custom")],
            [InlineKeyboardButton("✍️ Консультация",     callback_data="consult")],
        ]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Здравствуйте! 👋\n\nБольшое спасибо за Ваше обращение!\nЧто Вас интересует?",
            reply_markup=InlineKeyboardMarkup(kb))
        return

    if has_rights(uid):
        await update.message.reply_text(
            f"🚀 <b>PROAUTO BOT — Панель</b>\n\n"
            f"• Пересылай объявления → публикую в {TARGET_CHANNEL_NAME}\n"
            f"• /stats — статистика\n• /leads — заявки",
            parse_mode='HTML')
    else:
        kb = [[InlineKeyboardButton("🏎️ Подобрать автомобиль", callback_data="custom")],
              [InlineKeyboardButton("✍️ Консультация",          callback_data="consult")]]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=("Здравствуйте! 👋\n\nЯ представляю <b>ProAuto</b> — профессиональный подбор "
                  "и доставка автомобилей по всей России и СНГ.\n\n"
                  "<b>Наши преимущества:</b>\n"
                  "• ✅ Прозрачные цены без скрытых платежей\n"
                  "• 🚗 Подбор авто под любой бюджет\n"
                  "• 📦 Доставка во все города РФ\n"
                  "• 📋 Полное юридическое сопровождение\n"
                  "• 🛡 Гарантия качества\n\n"
                  "<b>Что Вас интересует?</b>"),
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

async def cmd_stats(update, context):
    if not has_rights(update.effective_user.id):
        return
    p = load_db(PUBLICATIONS_DB, {'counter':0,'publications':{}})
    l = load_db(LEADS_DB, {'counter':0,'leads':{}})
    await update.message.reply_text(
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"📢 Публикаций: {p.get('counter',0)}\n"
        f"📋 Заявок: {l.get('counter',0)}",
        parse_mode='HTML')

async def cmd_leads(update, context):
    if not has_rights(update.effective_user.id):
        return
    db = load_db(LEADS_DB, {'counter':0,'leads':{}})
    if not db['leads']:
        await update.message.reply_text("📋 Заявок пока нет"); return
    items = sorted(db['leads'].items(), key=lambda x: x[1].get('created_at',''), reverse=True)[:10]
    text = f"📋 <b>ПОСЛЕДНИЕ {len(items)} ЗАЯВОК</b>\n\n"
    for lid, l in items:
        text += f"<b>{lid}</b> — @{l.get('username','?')} ({l.get('first_name','')})\n"
        if l.get('brand'): text += f"  🚗 {l['brand']} {l.get('model','')}\n"
        if l.get('pub_id'): text += f"  📌 {l.get('car_name','')[:40]}\n"
        if l.get('city'):  text += f"  🏙 {l['city']}\n"
        text += "━━━━━━━━\n"
    if len(text)>4000: text = text[:3950]+"..."
    await update.message.reply_text(text, parse_mode='HTML')

async def handle_msg(update, context):
    try:
        msg = update.message
        if not msg: return
        uid = msg.from_user.id
        text = msg.text or msg.caption or ""

        if has_rights(uid):
            src = fwd_source(msg)
            eid = re.search(r'id_(\d{4})', text)
            if eid:
                pid = f"id_{eid.group(1)}"
                pub = find_pub(pid)
                if pub:
                    await msg.reply_text(
                        f"🔗 <b>{pid}</b>\n\n"
                        f"Источник: {pub.get('source_username','?')}\n"
                        f"{pub.get('source_link','нет')}",
                        parse_mode='HTML')
                else:
                    await msg.reply_text(f"❌ {pid} не найдено")
                return
            if src.get('is_forwarded') or msg.photo or msg.video:
                await publish(update, context, src if src.get('is_forwarded') else None)
            else:
                await msg.reply_text(
                    "ℹ️ Пересылай объявления\n/stats — статистика\n/leads — заявки")
        else:
            st = get_state(uid)
            if st.get('step'):
                await msg.reply_text("ℹ️ Используйте кнопки выше")
                return
            await cmd_start(update, context)
    except Exception as e:
        logger.error(f"handle_msg: {e}")

# ════════════════════════════════════════════════
# HEALTH SERVER + ЗАПУСК
# ════════════════════════════════════════════════
def health_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        def do_HEAD(self):
            self.send_response(200); self.end_headers()
        def log_message(self,*a): pass
    try:
        s = HTTPServer(('0.0.0.0', PORT), H)
        print(f"🌐 Health server PORT={PORT}", flush=True)
        s.serve_forever()
    except Exception as e:
        print(f"health error: {e}", flush=True)

async def on_start(app):
    print("✅ Bot polling started!", flush=True)
    logger.info(f"🚀 PROAUTO BOT — @{BOT_USERNAME}")
    logger.info(f"OWNER={OWNER_ID} | GROUP={TARGET_CHANNEL_NAME}")
    logger.info(f"DATA_DIR={DATA_DIR}")

def main():
    print("--- main() ---", flush=True)

    # Health server
    threading.Thread(target=health_server, daemon=True).start()
    print("--- health thread OK ---", flush=True)

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN ПУСТ", flush=True)
        import time; time.sleep(99999)

    print(f"--- token: {BOT_TOKEN[:10]}... ---", flush=True)

    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO,
        handle_msg))

    print("--- run_polling() ---", flush=True)
    app.run_polling(
        allowed_updates=['message','callback_query'],
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30)

if __name__ == '__main__':
    main()
