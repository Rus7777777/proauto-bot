"""
PROAUTO BOT — ПОЛНАЯ ВЕРСИЯ
Публикация объявлений + Бриф + Уведомления + API
"""
import sys, os, subprocess

print("="*60, flush=True)
print("PROAUTO BOT ЗАПУСК", flush=True)
print(f"Python: {sys.version}", flush=True)
print("="*60, flush=True)

# ── Автоустановка зависимостей ───────────────────────────────
try:
    import telegram
    print(f"✅ python-telegram-bot: {telegram.__version__}", flush=True)
except ImportError:
    print("⚠️ Устанавливаю python-telegram-bot...", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "python-telegram-bot>=20.0,<21.0",
                    "--break-system-packages", "-q"],
                   capture_output=True)

try:
    from dotenv import load_dotenv
    print("✅ python-dotenv", flush=True)
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "python-dotenv", "--break-system-packages", "-q"],
                   capture_output=True)

# ── Импорты ──────────────────────────────────────────────────
import asyncio, re, json, logging, threading, sqlite3
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv
from telegram import (
    Update, InputMediaPhoto, InputMediaVideo,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)

print("✅ Все модули загружены", flush=True)
load_dotenv()

# ════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════════

BOT_TOKEN         = os.getenv('BOT_TOKEN')
BOT_USERNAME      = os.getenv('BOT_USERNAME', 'proauto_23_bot')
TARGET_GROUP_ID   = int(os.getenv('TARGET_GROUP_ID', '0'))
TARGET_CHANNEL    = os.getenv('TARGET_CHANNEL_NAME', '@proauto_77')
MANAGER_LINK      = os.getenv('MANAGER_LINK', 'https://t.me/rdblm')
OWNER_ID          = int(os.getenv('OWNER_ID', '0'))
MANAGER_USER_ID   = int(os.getenv('MANAGER_USER_ID', '0'))
PORT              = int(os.getenv('PORT', 3000))
DATA_DIR          = os.getenv('DATA_DIR', '/app/data')

os.makedirs(DATA_DIR, exist_ok=True)
PUBS_DB  = os.path.join(DATA_DIR, 'publications.json')   # legacy JSON (бэкап после миграции)
LEADS_DB = os.path.join(DATA_DIR, 'leads.json')          # legacy JSON (бэкап после миграции)
SQLITE_DB = os.path.join(DATA_DIR, 'proauto.db')         # основное хранилище

logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

media_cache   = {}
BRIEF_STATES  = {}
RELAY_SESSIONS = {}   # {manager_id: client_id} — активные диалоги менеджер↔клиент

print(f"BOT_TOKEN: {'OK' if BOT_TOKEN else '❌ НЕТ!'}", flush=True)
print(f"OWNER_ID: {OWNER_ID}", flush=True)
print(f"DATA_DIR: {DATA_DIR}", flush=True)
print(f"PORT: {PORT}", flush=True)

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не задан!", flush=True)
    import time; time.sleep(99999)

# ════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════

EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF\U00002700-\U000027BF"
    "\U000024C2-\U0001F251\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000026FF]+",
    flags=re.UNICODE
)

CAR_BRANDS_LIST = [
    'BMW','Mercedes','Audi','Toyota','Lexus','Honda','Nissan',
    'Mazda','Kia','Hyundai','Volkswagen','Porsche','Volvo','Subaru',
    'Mitsubishi','Infiniti','Geely','Haval','BYD','Chery','Lixiang',
    'NIO','Zeekr','Tesla','Rolls','Bentley','Ferrari','Lamborghini',
    'Land Rover','Range Rover','Ford','Chevrolet','Cadillac','Jeep',
    'Genesis','Skoda','Maserati','Alfa Romeo','Jaguar','Peugeot',
    'Renault','Suzuki','Acura','Dodge','Lincoln','Buick',
]

SKIP_STATUS = [
    r'прямая\s+продажа', r'в\s+свободной\s+продаже', r'в\s+продаже',
    r'авто\s+из\s+европы', r'авто\s+прибыло', r'авто\s+из\s+',
    r'готова?\s+к\s+пригону', r'срок\s+доставки', r'авто\s+готово',
    r'^\s*[-–—]\s*$', r'^\s*$',
]

DELETE_PHRASES = [
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
    r'^.*[Рр]аботаем.*[Дд]оговор.*$',
    r'^.*[Тт]аможенная\s+пошлина.*$',
    r'^.*[Оо]тзывы\s+наших.*$',
    r'^.*CarVertical.*$',
    r'^.*[Рр]аботаем\s+официально.*$',
    r'^.*[Нн]ужна\s+цена\s+под\s+ключ.*$',
    r'^.*[Бб]ез\s+ДТП.*[Вв]ладелец.*$',
    r'^.*[Нн]е\s+аукцион.*$',
    r'^.*[Аа]укцион.*$',
    # Универсальное удаление любых упоминаний сторонних площадок/сайтов/
    # соцдоказательств — работает для любой группы-источника, не привязано
    # к конкретному названию сайта или формулировке.
    r'^.*\b[Сс]айт[а-яё]*\b.*$',
    r'^.*\b[Мм]арке[тй]плейс[а-яё]*\b.*$',
    r'^.*\b[Пп]лощадк[а-яё]*\b.*$',
    r'^.*\b[Оо]тзыв[а-яё]*\b.*$',
    r'^.*\b[Сс]сылк[а-яё]*\b.*$',
    r'^.*\bYoutube\b.*$',
    r'^.*\bИнстаграм[а-яё]*\b.*$',
    r'^.*\bInstagram\b.*$',
    r'^.*\bВКонтакте\b.*$',
    r'^.*\bTikTok\b.*$',
    r'^.*\bТикток[а-яё]*\b.*$',
]

CITIES = [
    '🏙 Москва', '🏙 Санкт-Петербург', '🌊 Краснодар', '🌊 Сочи',
    '🏔 Екатеринбург', '🌲 Новосибирск', '🕌 Казань', '☀️ Ростов-на-Дону',
    '🏛 Нижний Новгород', '⚓ Владивосток', '🏙 Тюмень', '🏙 Уфа',
    '🏙 Красноярск', '🏙 Челябинск', '🌿 Воронеж',
]

TIMINGS = [
    '⚡ В этом месяце',
    '📅 1-2 месяца',
    '🗓 3-6 месяцев',
    '👀 Просто изучаю',
]

BRAND_GROUPS = {
    '🇩🇪 Немецкие':     ['BMW','Mercedes-Benz','Audi','Volkswagen','Porsche','Volvo'],
    '🇯🇵 Японские':     ['Toyota','Lexus','Honda','Nissan','Mazda','Subaru','Mitsubishi','Infiniti'],
    '🇰🇷 Корейские':    ['Kia','Hyundai','Genesis'],
    '🇨🇳 Китайские':    ['Geely','Haval','BYD','Chery','Lixiang','NIO','Zeekr'],
    '🇺🇸 Американские': ['Tesla','Ford','Chevrolet','Cadillac','Jeep'],
    '🇬🇧 Британские':   ['Land Rover','Bentley','Rolls-Royce','Jaguar'],
    '👑 Итальянские':   ['Ferrari','Lamborghini','Maserati','Alfa Romeo'],
}

# ════════════════════════════════════════════════════════════
# БАЗА АВТО — загружаем из car_database.py или встроенная
# ════════════════════════════════════════════════════════════

try:
    from car_database import CAR_DATABASE, get_brands, get_models, get_generations
    logger.info(f"📚 car_database.py загружен: {len(CAR_DATABASE)} марок")
except ImportError:
    logger.warning("⚠️ car_database.py не найден — используем встроенную базу")

    CAR_DATABASE = {
        'BMW': {
            '1 серии':   ['F20/F21 (2011-2019)', 'F40 (2019-2026)'],
            '2 серии':   ['F22/F23 (2014-2021)', 'G42 (2021-2026)'],
            '3 серии':   ['F30 (2012-2018)', 'G20 (2019-2022)', 'G20 LCI (2022-2026)'],
            '4 серии':   ['F32/F36 (2013-2020)', 'G22/G26 (2020-2026)'],
            '5 серии':   ['F10 (2010-2017)', 'G30 (2017-2020)', 'G30 LCI (2020-2024)', 'G60 (2024-2026)'],
            '7 серии':   ['F01 (2009-2015)', 'G11 (2016-2022)', 'G70 (2022-2026)'],
            '8 серии':   ['G14/G15 (2018-2022)', 'G14/G15 LCI (2022-2026)'],
            'X1':  ['F48 (2015-2022)', 'U11 (2022-2026)'],
            'X2':  ['F39 (2018-2023)', 'U10 (2024-2026)'],
            'X3':  ['F25 (2011-2017)', 'G01 (2017-2021)', 'G01 LCI (2021-2026)'],
            'X4':  ['F26 (2014-2018)', 'G02 (2018-2021)', 'G02 LCI (2021-2026)'],
            'X5':  ['F15 (2014-2018)', 'G05 (2018-2023)', 'G05 LCI (2023-2026)'],
            'X5 M':['F85 (2015-2018)', 'F95 (2020-2026)'],
            'X6':  ['F16 (2015-2019)', 'G06 (2019-2023)', 'G06 LCI (2023-2026)'],
            'X7':  ['G07 (2019-2022)', 'G07 LCI (2022-2026)'],
            'XM':  ['G09 (2022-2026)'],
            'M2':  ['F87 (2016-2021)', 'G87 (2022-2026)'],
            'M3':  ['F80 (2014-2018)', 'G80 (2020-2026)'],
            'M4':  ['F82/F83 (2014-2020)', 'G82/G83 (2020-2026)'],
            'M5':  ['F90 (2018-2024)', 'G90 (2024-2026)'],
            'M8':  ['G14/G15 (2019-2026)'],
            'Z4':  ['E89 (2009-2016)', 'G29 (2018-2026)'],
            'i3':  ['I01 (2013-2017)', 'I01 LCI (2017-2022)'],
            'i4':  ['G26 (2021-2026)'],
            'i5':  ['G60 (2023-2026)'],
            'i7':  ['G70 (2022-2026)'],
            'i8':  ['I12 (2014-2018)', 'I12 LCI (2018-2020)'],
            'iX':  ['I20 (2021-2026)'],
            'iX1': ['U11 (2022-2026)'],
            'iX3': ['G08 (2020-2026)'],
        },
        'Mercedes-Benz': {
            'A-Class':       ['W176 (2012-2018)', 'W177 (2018-2023)', 'W177 FL (2023-2026)'],
            'B-Class':       ['W246 (2012-2018)', 'W247 (2019-2026)'],
            'C-Class':       ['W205 (2014-2018)', 'W205 FL (2018-2021)', 'W206 (2021-2026)'],
            'CLA':           ['C117 (2013-2019)', 'C118 (2019-2026)'],
            'CLE':           ['C236 (2023-2026)'],
            'E-Class':       ['W212 (2009-2016)', 'W213 (2016-2020)', 'W213 FL (2020-2024)', 'W214 (2024-2026)'],
            'G-Class':       ['W463 (2012-2018)', 'W464 (2018-2026)'],
            'G-Class AMG':   ['W464 AMG (2018-2026)'],
            'GLA':           ['X156 (2013-2020)', 'H247 (2020-2026)'],
            'GLB':           ['X247 (2019-2026)'],
            'GLC':           ['X253/C253 (2016-2022)', 'X254 (2022-2026)'],
            'GLC Coupe':     ['C253 (2016-2022)', 'C254 (2023-2026)'],
            'GLE':           ['W166 (2015-2019)', 'V167 (2019-2026)'],
            'GLS':           ['X166 (2016-2019)', 'X167 (2019-2026)'],
            'S-Class':       ['W222 (2013-2020)', 'W223 (2020-2026)'],
            'S-Class AMG':   ['W222 AMG (2015-2020)', 'W223 AMG (2021-2026)'],
            'Maybach S-Class':['W222 Maybach (2015-2020)', 'W223 Maybach (2021-2026)'],
            'SL-Class':      ['R231 (2012-2021)', 'R232 (2021-2026)'],
            'AMG GT':        ['C190 (2015-2023)', 'C192 (2023-2026)'],
            'EQA':  ['H243 (2021-2026)'],
            'EQB':  ['X243 (2021-2026)'],
            'EQE':  ['V295 (2022-2026)'],
            'EQS':  ['V297 (2021-2026)'],
            'EQS SUV': ['X296 (2022-2026)'],
        },
        'Audi': {
            'A3':  ['8V (2012-2020)', '8Y (2020-2026)'],
            'A4':  ['B8 FL (2012-2015)', 'B9 (2016-2019)', 'B9 FL (2019-2026)'],
            'A5':  ['8T (2007-2016)', 'F5 (2016-2023)', 'F5 FL (2023-2026)'],
            'A6':  ['C7 (2011-2018)', 'C8 (2018-2023)', 'C8 FL (2023-2026)'],
            'A7':  ['4G (2010-2018)', '4K (2018-2026)'],
            'A8':  ['D4 (2010-2017)', 'D5 (2017-2026)'],
            'Q3':  ['8U (2011-2018)', 'F3 (2018-2024)', 'F3 FL (2024-2026)'],
            'Q4 e-tron': ['FZ (2021-2026)'],
            'Q5':  ['8R (2008-2017)', 'FY (2017-2020)', 'FY FL (2020-2026)'],
            'Q7':  ['4L (2006-2015)', '4M (2015-2020)', '4M FL (2020-2026)'],
            'Q8':  ['F1 (2018-2023)', 'F1 FL (2023-2026)'],
            'e-tron': ['GE (2018-2023)', 'GE FL (2023-2026)'],
            'e-tron GT': ['FW (2021-2026)'],
            'RS3': ['8V (2015-2020)', '8Y (2021-2026)'],
            'RS4': ['B9 (2017-2020)', 'B9 FL (2020-2026)'],
            'RS5': ['F5 (2017-2023)', 'F5 FL (2023-2026)'],
            'RS6': ['C7 (2013-2018)', 'C8 (2019-2026)'],
            'RS7': ['4G (2013-2018)', '4K (2019-2026)'],
            'TT':  ['8J (2006-2014)', '8S (2014-2023)'],
        },
        'Toyota': {
            'Camry':       ['XV50 (2012-2017)', 'XV70 (2018-2021)', 'XV70 FL (2021-2026)'],
            'Corolla':     ['E170 (2013-2019)', 'E210 (2019-2022)', 'E210 FL (2022-2026)'],
            'Highlander':  ['XU50 (2014-2020)', 'XU70 (2020-2024)', 'XU80 (2024-2026)'],
            'Land Cruiser':['J200 FL (2016-2021)', 'J300 (2021-2026)'],
            'Land Cruiser Prado': ['J150 FL3 (2017-2021)', 'J150 FL4 (2021-2024)', 'J250 (2024-2026)'],
            'RAV4':        ['XA40 FL (2015-2018)', 'XA50 (2018-2022)', 'XA50 FL (2022-2026)'],
            'Supra':       ['A80 (1993-2002)', 'A90 (2019-2026)'],
            'C-HR':        ['X10 (2016-2020)', 'X10 FL (2020-2023)', 'AX10 (2023-2026)'],
            'Fortuner':    ['II (2016-2020)', 'II FL (2020-2026)'],
            'bZ4X':        ['ZYM10 (2022-2026)'],
        },
        'Lexus': {
            'ES':   ['XV60 (2012-2018)', 'XV70 (2018-2022)', 'XV70 FL (2022-2026)'],
            'GX':   ['J150 (2010-2019)', 'J150 FL (2019-2023)', 'J250 (2024-2026)'],
            'IS':   ['XE30 (2013-2021)', 'XE30 FL (2021-2026)'],
            'LC':   ['Z100 (2017-2026)'],
            'LS':   ['F50 (2017-2022)', 'F50 FL (2022-2026)'],
            'LX':   ['J200 (2012-2021)', 'J310 (2022-2026)'],
            'NX':   ['AZ10 (2014-2021)', 'AZ20 (2021-2026)'],
            'RC':   ['C10 (2014-2026)'],
            'RX':   ['AL20 (2016-2022)', 'AL30 (2022-2026)'],
            'TX':   ['AL30 (2024-2026)'],
            'UX':   ['ZA10 (2018-2026)'],
        },
        'Honda': {
            'Accord':  ['IX (2013-2017)', 'X (2017-2022)', 'XI (2022-2026)'],
            'Civic':   ['X (2015-2021)', 'XI (2021-2026)'],
            'Civic Type R': ['FK8 (2017-2021)', 'FL5 (2022-2026)'],
            'CR-V':    ['IV (2012-2016)', 'V (2017-2021)', 'VI (2022-2026)'],
            'HR-V':    ['II (2015-2021)', 'III (2022-2026)'],
            'Passport':['I (2019-2022)', 'II (2022-2026)'],
            'Pilot':   ['III (2016-2022)', 'IV (2022-2026)'],
        },
        'Nissan': {
            'Altima':    ['L33 (2013-2018)', 'L34 (2019-2026)'],
            'GT-R':      ['R35 FL (2016-2026)'],
            'Juke':      ['F15 (2010-2019)', 'F16 (2019-2026)'],
            'Murano':    ['Z52 (2016-2020)', 'Z52 FL (2020-2026)'],
            'Patrol':    ['Y62 (2010-2019)', 'Y62 FL2 (2019-2026)'],
            'Qashqai':   ['J11 (2014-2021)', 'J12 (2021-2026)'],
            'X-Trail':   ['T32 (2014-2022)', 'T33 (2022-2026)'],
            'Ariya':     ['FE0 (2022-2026)'],
        },
        'Mazda': {
            'CX-3':   ['DK (2015-2023)'],
            'CX-30':  ['DM (2019-2026)'],
            'CX-5':   ['KE FL (2015-2017)', 'KF (2017-2021)', 'KF FL (2021-2026)'],
            'CX-60':  ['KH (2022-2026)'],
            'CX-9':   ['TC (2016-2020)', 'TC FL (2020-2026)'],
            'Mazda3': ['BM (2013-2018)', 'BP (2019-2026)'],
            'Mazda6': ['GJ FL (2015-2018)', 'GL (2018-2023)'],
            'MX-5':   ['ND (2015-2019)', 'ND FL (2019-2026)'],
        },
        'Subaru': {
            'Ascent':    ['I (2018-2022)', 'II (2023-2026)'],
            'BRZ':       ['ZC6 (2012-2021)', 'ZD8 (2021-2026)'],
            'Crosstrek': ['GP (2012-2017)', 'GT (2017-2023)', 'GU (2023-2026)'],
            'Forester':  ['SJ FL (2016-2019)', 'SK (2018-2023)', 'SJ6 (2023-2026)'],
            'Impreza':   ['GP (2012-2016)', 'GT (2016-2022)', 'GU (2022-2026)'],
            'Legacy':    ['BN (2015-2019)', 'BN FL (2019-2022)', 'BS (2022-2026)'],
            'Outback':   ['BS (2015-2019)', 'BS FL (2019-2021)', 'BT (2021-2026)'],
            'Solterra':  ['I (2022-2026)'],
            'WRX':       ['VA (2014-2021)', 'VB (2021-2026)'],
        },
        'Mitsubishi': {
            'ASX':            ['GA1W (2010-2016)', 'GA3W FL (2016-2019)', 'GA8W (2023-2026)'],
            'Eclipse Cross':  ['GK (2017-2021)', 'GK FL (2021-2026)'],
            'Outlander':      ['GF (2012-2021)', 'GN (2021-2026)'],
            'Outlander PHEV': ['GG (2013-2021)', 'GN PHEV (2021-2026)'],
            'Pajero Sport':   ['KH (2016-2019)', 'KH FL (2019-2026)'],
            'L200':           ['KL (2015-2019)', 'KL FL (2019-2026)'],
        },
        'Infiniti': {
            'Q50':  ['II (2014-2018)', 'II FL (2018-2026)'],
            'Q60':  ['II (2016-2026)'],
            'QX50': ['I (2014-2017)', 'II (2017-2026)'],
            'QX55': ['I (2021-2026)'],
            'QX60': ['L50 (2013-2021)', 'L51 (2021-2026)'],
            'QX80': ['Z62 (2013-2019)', 'Z62 FL (2019-2026)'],
        },
        'Kia': {
            'Carnival':  ['YP (2015-2020)', 'KA4 (2021-2026)'],
            'EV6':       ['CV (2021-2026)'],
            'EV9':       ['MV (2023-2026)'],
            'K5':        ['JF (2016-2020)', 'DL3 (2020-2026)'],
            'K8':        ['GL3 (2021-2026)'],
            'Seltos':    ['SP2 (2019-2022)', 'SP2 FL (2022-2026)'],
            'Sorento':   ['UM (2015-2020)', 'MQ4 (2020-2026)'],
            'Sportage':  ['QL (2016-2022)', 'NQ5 (2022-2026)'],
            'Stinger':   ['CK (2018-2023)'],
            'Telluride': ['ON (2020-2022)', 'ON FL (2022-2026)'],
            'XCeed':     ['CD (2019-2026)'],
        },
        'Hyundai': {
            'Elantra':  ['AD (2016-2019)', 'AD FL (2019-2021)', 'CN7 (2020-2026)'],
            'IONIQ 5':  ['NE (2021-2026)'],
            'IONIQ 6':  ['CE (2022-2026)'],
            'Kona':     ['OS (2017-2023)', 'SX2 (2023-2026)'],
            'Palisade': ['LX2 (2019-2023)', 'LX2 FL (2023-2026)'],
            'Santa Fe': ['TM (2018-2021)', 'TM FL (2021-2024)', 'MX5 (2024-2026)'],
            'Staria':   ['US4 (2021-2026)'],
            'Tucson':   ['TL (2015-2020)', 'NX4 (2021-2026)'],
        },
        'Genesis': {
            'G70':  ['IK (2017-2021)', 'IK FL (2021-2026)'],
            'G80':  ['DH (2017-2020)', 'RG3 (2020-2026)'],
            'G90':  ['HI (2017-2022)', 'RS4 (2022-2026)'],
            'GV60': ['JW (2021-2026)'],
            'GV70': ['JK1 (2021-2026)'],
            'GV80': ['JX1 (2021-2026)'],
        },
        'Volkswagen': {
            'Arteon':  ['3H (2017-2020)', '3H FL (2020-2024)'],
            'Atlas':   ['CA1 (2017-2020)', 'CA1 FL (2021-2026)'],
            'Golf':    ['VII (2013-2019)', 'VIII (2019-2026)'],
            'Golf GTI':['VII GTI (2013-2020)', 'VIII GTI (2020-2026)'],
            'ID.3':    ['E11 (2019-2026)'],
            'ID.4':    ['E21 (2020-2026)'],
            'ID.5':    ['E21 (2021-2026)'],
            'ID.Buzz': ['E89 (2022-2026)'],
            'Jetta':   ['VI (2011-2018)', 'VII (2018-2026)'],
            'Multivan':['T6 (2015-2021)', 'T7 (2021-2026)'],
            'Passat':  ['B8 (2015-2019)', 'B8 FL (2019-2023)', 'B9 (2023-2026)'],
            'Polo':    ['AW (2017-2021)', 'AW FL (2021-2026)'],
            'T-Cross': ['C11 (2019-2023)', 'C11 FL (2023-2026)'],
            'T-Roc':   ['A1 (2017-2021)', 'A1 FL (2021-2026)'],
            'Tiguan':  ['II (2016-2020)', 'II FL (2020-2024)', 'III (2024-2026)'],
            'Touareg': ['II FL (2014-2018)', 'CR (2018-2026)'],
        },
        'Porsche': {
            '911':          ['991 (2011-2019)', '992 (2019-2026)'],
            '911 Turbo':    ['991 Turbo (2013-2019)', '992 Turbo (2020-2026)'],
            '718 Cayman':   ['982 (2016-2026)'],
            '718 Boxster':  ['982 (2016-2026)'],
            'Cayenne':      ['II FL (2014-2018)', 'III (2018-2022)', 'III FL (2022-2026)'],
            'Cayenne Coupe':['III (2019-2026)'],
            'Macan':        ['95B (2014-2018)', '95B FL (2018-2023)', 'J1 EV (2024-2026)'],
            'Panamera':     ['I FL (2014-2016)', 'II (2016-2020)', 'II FL (2020-2026)'],
            'Taycan':       ['Y1A (2019-2023)', 'Y1A FL (2024-2026)'],
        },
        'Land Rover': {
            'Defender 90':      ['L316 (1990-2016)', 'L663 (2020-2026)'],
            'Defender 110':     ['L316 (1990-2016)', 'L663 (2020-2026)'],
            'Discovery':        ['L462 (2017-2021)', 'L462 FL (2021-2026)'],
            'Discovery Sport':  ['L550 (2015-2019)', 'L550 FL (2019-2024)', 'L560 (2024-2026)'],
            'Range Rover':      ['L405 (2012-2022)', 'L460 (2022-2026)'],
            'Range Rover Evoque':['L538 (2011-2018)', 'L551 (2019-2026)'],
            'Range Rover Sport':['L494 (2013-2022)', 'L461 (2022-2026)'],
            'Range Rover Velar':['L560 (2017-2022)', 'L560 FL (2022-2026)'],
        },
        'Volvo': {
            'C40':  ['EX40 (2021-2026)'],
            'EX30': ['EB (2023-2026)'],
            'S60':  ['III (2018-2026)'],
            'S90':  ['II (2016-2021)', 'II FL (2021-2026)'],
            'V60':  ['II (2018-2026)'],
            'V90':  ['II (2016-2021)', 'II FL (2021-2026)'],
            'XC40': ['536 (2017-2022)', '536 FL (2022-2026)'],
            'XC60': ['II (2017-2021)', 'II FL (2021-2026)'],
            'XC90': ['II (2015-2022)', 'II FL (2022-2026)'],
        },
        'Tesla': {
            'Cybertruck': ['I (2023-2026)'],
            'Model 3':    ['I (2017-2020)', 'I FL (2020-2023)', 'Highland (2023-2026)'],
            'Model S':    ['I (2012-2016)', 'II (2016-2021)', 'Plaid (2021-2026)'],
            'Model X':    ['I (2015-2016)', 'II (2016-2021)', 'Plaid (2021-2026)'],
            'Model Y':    ['I (2020-2024)', 'Juniper (2024-2026)'],
        },
        'BYD': {
            'Atto 3': ['I (2022-2026)'],
            'Han':    ['DM-i (2020-2023)', 'DM-i FL (2023-2026)'],
            'Han EV': ['I (2020-2023)', 'I FL (2023-2026)'],
            'Seal':   ['I (2022-2026)'],
            'Tang':   ['II DM (2018-2023)', 'II DM FL (2023-2026)'],
        },
        'Geely': {
            'Coolray':  ['SX11 (2019-2023)', 'SX11 FL (2023-2026)'],
            'Monjaro':  ['KX11 (2022-2026)'],
            'Tugella':  ['FY11 (2019-2023)', 'FY11 FL (2023-2026)'],
        },
        'Haval': {
            'Dargo': ['D (2021-2026)'],
            'H6':    ['III (2021-2026)'],
            'H9':    ['II (2021-2026)'],
            'Jolion':['B06 (2021-2026)'],
        },
        'Chery': {
            'Omoda 5':     ['I (2022-2026)'],
            'Tiggo 7 Pro': ['I (2020-2023)', 'II (2023-2026)'],
            'Tiggo 8 Pro': ['I (2020-2023)', 'II (2023-2026)'],
        },
        'Rolls-Royce': {
            'Cullinan':  ['RR31 (2018-2021)', 'Series II (2022-2026)'],
            'Ghost':     ['RR12 (2020-2026)'],
            'Phantom':   ['VIII (2017-2026)'],
            'Spectre':   ['RR14 (2023-2026)'],
        },
        'Bentley': {
            'Bentayga':        ['I (2016-2020)', 'I FL (2020-2026)'],
            'Continental GT':  ['III (2018-2022)', 'III FL (2022-2026)'],
            'Flying Spur':     ['III (2019-2022)', 'III FL (2022-2026)'],
        },
        'Ferrari': {
            '296 GTB':    ['I (2022-2026)'],
            'F8 Tributo': ['I (2019-2023)'],
            'Purosangue': ['I (2023-2026)'],
            'Roma':       ['I (2020-2026)'],
            'SF90':       ['I (2020-2026)'],
        },
        'Lamborghini': {
            'Huracán EVO': ['LB724 (2019-2023)'],
            'Revuelto':    ['LB834 (2023-2026)'],
            'Urus':        ['LA1 (2018-2022)', 'Urus S (2022-2026)'],
        },
        'Lixiang': {
            'L7': ['I (2022-2026)'],
            'L8': ['I (2022-2026)'],
            'L9': ['I (2022-2026)'],
        },
        'NIO': {
            'ES6': ['I (2018-2023)', 'II (2023-2026)'],
            'ES8': ['I (2018-2023)', 'II (2023-2026)'],
            'ET5': ['I (2022-2026)'],
            'ET7': ['I (2022-2026)'],
        },
        'Zeekr': {
            '001': ['I (2021-2026)'],
            '007': ['I (2023-2026)'],
            'X':   ['I (2023-2026)'],
        },
        'Ford': {
            'Bronco':    ['VI (2021-2026)'],
            'Explorer':  ['VI (2019-2026)'],
            'F-150':     ['XIII (2015-2020)', 'XIV (2020-2026)'],
            'Mustang':   ['VI (2015-2022)', 'VII (2023-2026)'],
            'Ranger':    ['III (2019-2022)', 'IV (2022-2026)'],
        },
        'Chevrolet': {
            'Camaro':    ['VI (2016-2024)'],
            'Silverado': ['IV (2019-2026)'],
            'Tahoe':     ['IV (2015-2020)', 'V (2020-2026)'],
            'Traverse':  ['II (2018-2022)', 'III (2023-2026)'],
        },
        'Jeep': {
            'Grand Cherokee': ['WL (2021-2026)'],
            'Wrangler':       ['JK (2007-2018)', 'JL (2018-2026)'],
            'Compass':        ['MP (2017-2021)', 'MP FL (2021-2026)'],
        },
        'Jaguar': {
            'E-Pace': ['X540 (2017-2020)', 'X540 FL (2020-2026)'],
            'F-Pace': ['X761 (2016-2021)', 'X761 FL (2021-2026)'],
            'F-Type': ['X152 (2013-2020)', 'X152 FL (2020-2026)'],
            'I-Pace': ['X590 (2018-2026)'],
        },
        'Maserati': {
            'Ghibli':      ['M157 (2013-2021)', 'M157 FL (2021-2024)'],
            'Grecale':     ['M300 (2022-2026)'],
            'Levante':     ['M161 (2016-2022)', 'M161 FL (2022-2026)'],
            'MC20':        ['I (2020-2026)'],
            'Quattroporte':['M156 (2013-2022)', 'M156 FL (2022-2026)'],
        },
        'Alfa Romeo': {
            'Giulia':   ['952 (2016-2026)'],
            'Stelvio':  ['949 (2017-2026)'],
            'Tonale':   ['965 (2022-2026)'],
        },
        'Skoda': {
            'Enyaq':  ['IV (2020-2026)'],
            'Fabia':  ['III (2015-2021)', 'IV (2021-2026)'],
            'Karoq':  ['NU7 (2017-2021)', 'NU7 FL (2021-2026)'],
            'Kodiaq': ['NS7 (2017-2021)', 'NS7 FL (2021-2026)'],
            'Octavia':['III (2012-2017)', 'III FL (2017-2020)', 'IV (2020-2026)'],
            'Superb': ['III (2015-2019)', 'III FL (2019-2025)'],
        },
    }

    def get_brands():
        return sorted(CAR_DATABASE.keys())

    def get_models(brand):
        if brand in CAR_DATABASE:
            return sorted(CAR_DATABASE[brand].keys())
        for k in CAR_DATABASE:
            if k.lower() == brand.lower():
                return sorted(CAR_DATABASE[k].keys())
        return []

    def get_generations(brand, model):
        for k, v in CAR_DATABASE.items():
            if k == brand or k.lower() == brand.lower():
                for m, gens in v.items():
                    if m == model or m.lower() == model.lower():
                        return gens if isinstance(gens, list) else [gens]
        return []

# ════════════════════════════════════════════════════════════
# ПРАВА
# ════════════════════════════════════════════════════════════

def has_rights(uid):
    return ((uid == OWNER_ID and OWNER_ID != 0) or
            (uid == MANAGER_USER_ID and MANAGER_USER_ID != 0))

# ════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ — SQLite (надёжное хранилище)
# ════════════════════════════════════════════════════════════
#
# Почему SQLite, а не JSON-файлы, как было раньше:
#   • JSON перезаписывался целиком при каждом сохранении — при двух
#     публикациях в одну секунду одна могла затереть другую (гонка),
#     то есть терялись заявки/объявления.
#   • SQLite с журналом WAL безопасно обрабатывает параллельную запись.
#
# ВАЖНО про совместимость: функции _load/_save/save_pub/find_pub/
# next_pub_id/save_lead/next_lead_id снаружи ведут себя ТОЧНО так же,
# как раньше (те же аргументы, те же форматы данных), поэтому весь
# остальной код (cmd_stats, cmd_leads, button_cb и т.д.) не меняется.

_db_lock = threading.Lock()

def _db_conn():
    # timeout=30 — ждём, если база временно занята другой записью,
    # вместо мгновенной ошибки. WAL включаем при каждом соединении.
    conn = sqlite3.connect(SQLITE_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception as e:
        logger.error(f"db pragma: {e}")
    return conn

def _db_init():
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value INTEGER
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS publications (
                    pub_id TEXT PRIMARY KEY,
                    data   TEXT NOT NULL
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id TEXT PRIMARY KEY,
                    data    TEXT NOT NULL
                )""")
            # Счётчики хранятся в meta, чтобы next_pub_id/next_lead_id
            # выдавали строго возрастающие номера без коллизий.
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('pub_counter',0)")
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('lead_counter',0)")
            conn.commit()
        finally:
            conn.close()

def _migrate_json_to_sqlite():
    """
    Один раз переносит данные из старых JSON-файлов в SQLite.
    JSON-файлы НЕ удаляются — остаются как резервная копия.
    Повторный запуск безопасен: если запись с таким id уже есть в
    SQLite, она не перезатирается (INSERT OR IGNORE).
    """
    migrated_pubs = 0
    migrated_leads = 0

    # --- публикации ---
    if os.path.exists(PUBS_DB):
        try:
            with open(PUBS_DB, 'r', encoding='utf-8') as fp:
                old = json.load(fp)
            with _db_lock:
                conn = _db_conn()
                try:
                    for pid, pdata in (old.get('publications') or {}).items():
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO publications(pub_id,data) VALUES(?,?)",
                            (pid, json.dumps(pdata, ensure_ascii=False)))
                        if cur.rowcount:
                            migrated_pubs += 1
                    # Счётчик берём максимальным из старого JSON и текущего SQLite
                    old_counter = int(old.get('counter', 0) or 0)
                    row = conn.execute("SELECT value FROM meta WHERE key='pub_counter'").fetchone()
                    cur_counter = int(row['value']) if row else 0
                    conn.execute("UPDATE meta SET value=? WHERE key='pub_counter'",
                                 (max(old_counter, cur_counter),))
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"migrate publications: {e}")

    # --- заявки ---
    if os.path.exists(LEADS_DB):
        try:
            with open(LEADS_DB, 'r', encoding='utf-8') as fp:
                old = json.load(fp)
            with _db_lock:
                conn = _db_conn()
                try:
                    for lid, ldata in (old.get('leads') or {}).items():
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO leads(lead_id,data) VALUES(?,?)",
                            (lid, json.dumps(ldata, ensure_ascii=False)))
                        if cur.rowcount:
                            migrated_leads += 1
                    old_counter = int(old.get('counter', 0) or 0)
                    row = conn.execute("SELECT value FROM meta WHERE key='lead_counter'").fetchone()
                    cur_counter = int(row['value']) if row else 0
                    conn.execute("UPDATE meta SET value=? WHERE key='lead_counter'",
                                 (max(old_counter, cur_counter),))
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"migrate leads: {e}")

    if migrated_pubs or migrated_leads:
        logger.info(f"🔄 Миграция JSON→SQLite: {migrated_pubs} публикаций, "
                    f"{migrated_leads} заявок перенесено (JSON сохранён как бэкап)")
    else:
        logger.info("🗄 SQLite готов (миграция не потребовалась)")

# --- Совместимость: _load/_save в старом формате, но поверх SQLite ---
# Возвращают/принимают ровно те же структуры, что и прежние JSON-версии:
#   publications → {'counter':N, 'publications':{pub_id:{...}}}
#   leads        → {'counter':N, 'leads':{lead_id:{...}}}
# Благодаря этому cmd_stats/cmd_leads и прочий код работают без изменений.

def _load(f, default=None):
    if default is None: default = {}
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                if f == PUBS_DB:
                    rows = conn.execute("SELECT pub_id,data FROM publications").fetchall()
                    pubs = {r['pub_id']: json.loads(r['data']) for r in rows}
                    row = conn.execute("SELECT value FROM meta WHERE key='pub_counter'").fetchone()
                    counter = int(row['value']) if row else 0
                    return {'counter': counter, 'publications': pubs}
                elif f == LEADS_DB:
                    rows = conn.execute("SELECT lead_id,data FROM leads").fetchall()
                    lds = {r['lead_id']: json.loads(r['data']) for r in rows}
                    row = conn.execute("SELECT value FROM meta WHERE key='lead_counter'").fetchone()
                    counter = int(row['value']) if row else 0
                    return {'counter': counter, 'leads': lds}
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"_load {f}: {e}")
        return default
    return default

def _save(f, data):
    # Полная перезапись коллекции. Используется редко (в основном код
    # ходит через save_pub/save_lead с точечной записью), но оставлено
    # для полной совместимости со старым интерфейсом.
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                if f == PUBS_DB:
                    for pid, pdata in (data.get('publications') or {}).items():
                        conn.execute(
                            "INSERT OR REPLACE INTO publications(pub_id,data) VALUES(?,?)",
                            (pid, json.dumps(pdata, ensure_ascii=False)))
                    if 'counter' in data:
                        conn.execute("UPDATE meta SET value=? WHERE key='pub_counter'",
                                     (int(data['counter']),))
                elif f == LEADS_DB:
                    for lid, ldata in (data.get('leads') or {}).items():
                        conn.execute(
                            "INSERT OR REPLACE INTO leads(lead_id,data) VALUES(?,?)",
                            (lid, json.dumps(ldata, ensure_ascii=False)))
                    if 'counter' in data:
                        conn.execute("UPDATE meta SET value=? WHERE key='lead_counter'",
                                     (int(data['counter']),))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"_save {f}: {e}")

def next_pub_id():
    # Атомарный инкремент счётчика прямо в SQL — исключает коллизию
    # номеров при одновременных публикациях.
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute("UPDATE meta SET value=value+1 WHERE key='pub_counter'")
            row = conn.execute("SELECT value FROM meta WHERE key='pub_counter'").fetchone()
            conn.commit()
            n = int(row['value'])
        finally:
            conn.close()
    return f"id_{n:04d}"

def save_pub(pub_id, **kw):
    now = datetime.now()
    # Извлекаем бренд/модель из оригинала (логика без изменений)
    orig = kw.get('original_caption','')
    brand = None
    model_name = None
    for line in orig.split('\n'):
        c = EMOJI_RE.sub('',line).strip()
        c = re.sub(r'^[-–—•*]\s*','',c).strip()
        if not c or len(c)<3: continue
        for b in CAR_BRANDS_LIST:
            if b.lower() in c.lower():
                model_name = re.sub(r'\bв\s+продаже\b|\bв\s+наличии\b','',c,flags=re.I).strip()
                model_name = re.sub(r'[‼!]+','',model_name).strip()[:80]
                brand = b
                break
        if brand: break

    telegram_link = None
    pmid = kw.get('published_message_id')
    if pmid:
        telegram_link = f"https://t.me/{TARGET_CHANNEL.replace('@','')}/{pmid}"

    record = {
        **kw,
        'pub_id': pub_id,
        'car_brand': brand,
        'car_model': model_name,
        'telegram_link': telegram_link,
        'status': 'active',
        'published_at': now.isoformat(),
        'expires_at': (now + timedelta(days=30)).isoformat(),
    }
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO publications(pub_id,data) VALUES(?,?)",
                    (pub_id, json.dumps(record, ensure_ascii=False)))
                conn.commit()
            finally:
                conn.close()
        logger.info(f"💾 {pub_id} | {brand or '?'} | {model_name or '?'}")
    except Exception as e:
        logger.error(f"save_pub {pub_id}: {e}")

def find_pub(pub_id):
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                row = conn.execute(
                    "SELECT data FROM publications WHERE pub_id=?", (pub_id,)).fetchone()
                return json.loads(row['data']) if row else None
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"find_pub {pub_id}: {e}")
        return None

def update_pub_status(pub_id, status):
    """Меняет статус публикации (active/expired/sold), не трогая остальные поля."""
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                row = conn.execute(
                    "SELECT data FROM publications WHERE pub_id=?", (pub_id,)).fetchone()
                if not row:
                    return None
                rec = json.loads(row['data'])
                rec['status'] = status
                rec['status_changed_at'] = datetime.now().isoformat()
                conn.execute("UPDATE publications SET data=? WHERE pub_id=?",
                             (json.dumps(rec, ensure_ascii=False), pub_id))
                conn.commit()
                return rec
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"update_pub_status {pub_id}: {e}")
        return None

def next_lead_id():
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute("UPDATE meta SET value=value+1 WHERE key='lead_counter'")
            row = conn.execute("SELECT value FROM meta WHERE key='lead_counter'").fetchone()
            conn.commit()
            n = int(row['value'])
        finally:
            conn.close()
    return f"lead_{n:05d}"

def save_lead(lid, data):
    record = {**data, 'created_at': datetime.now().isoformat()}
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO leads(lead_id,data) VALUES(?,?)",
                    (lid, json.dumps(record, ensure_ascii=False)))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"save_lead {lid}: {e}")

def find_lead(lid):
    """Возвращает данные заявки по id или None."""
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                row = conn.execute(
                    "SELECT data FROM leads WHERE lead_id=?", (lid,)).fetchone()
                return json.loads(row['data']) if row else None
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"find_lead {lid}: {e}")
        return None

def update_lead(lid, **changes):
    """
    Точечно обновляет поля заявки (например статус), не затирая остальные.
    Возвращает обновлённую запись или None, если заявки нет.
    """
    try:
        with _db_lock:
            conn = _db_conn()
            try:
                row = conn.execute(
                    "SELECT data FROM leads WHERE lead_id=?", (lid,)).fetchone()
                if not row:
                    return None
                rec = json.loads(row['data'])
                rec.update(changes)
                conn.execute(
                    "UPDATE leads SET data=? WHERE lead_id=?",
                    (json.dumps(rec, ensure_ascii=False), lid))
                conn.commit()
                return rec
            finally:
                conn.close()
    except Exception as e:
        logger.error(f"update_lead {lid}: {e}")
        return None

def get_state(uid):
    if uid not in BRIEF_STATES:
        BRIEF_STATES[uid] = {'step':None,'data':{}}
    return BRIEF_STATES[uid]

def clear_state(uid):
    BRIEF_STATES.pop(uid, None)

# ════════════════════════════════════════════════════════════
# ОЧИСТКА ТЕКСТА
# ════════════════════════════════════════════════════════════

def clean(text):
    if not text: return text
    text = EMOJI_RE.sub('', text)

    # Защита цены от чистки "похожих на телефон" номеров ниже.
    # Прячем "число + валюта" под плейсхолдер ДО всех остальных
    # регулярок, а в конце функции возвращаем на место — так цена
    # никогда не пострадает независимо от формата (пробелы, точки,
    # руб/₽/€/$), а обрезка телефонов продолжает работать как раньше.
    _price_tokens = []
    def _mask_price(m):
        _price_tokens.append(m.group(0))
        return f"\x00PRICE{len(_price_tokens)-1}\x00"
    text = re.sub(
        r'\d[\d\s.,\u00a0]*\d\s*(?:₽|€|\$|руб\.?|RUB)',
        _mask_price, text, flags=re.I)

    # Статусные строки
    text = re.sub(r'^[^\n]*[Вв]\s+продаже[^\n]*\n?','',text,flags=re.I|re.M)
    text = re.sub(r'^[^\n]*[Вв]\s+свободной\s+продаже[^\n]*\n?','',text,flags=re.I|re.M)
    text = re.sub(r'^[^\n]*АВТО\s+ИЗ\s+[А-ЯЁ]+[^\n]*\n?','',text,flags=re.M)
    text = re.sub(r'^[^\n]*[Аа]вто\s+прибыло[^\n]*\n?','',text,flags=re.I|re.M)
    text = re.sub(r'^[^\n]*\bСБХ\b[^\n]*\n?','',text,flags=re.M)
    text = re.sub(r'^[^\n]*[Аа]вто\s+готово[^\n]*\n?','',text,flags=re.I|re.M)
    text = re.sub(r'^[^\n]*срок\s+доставки[^\n]*\n?','',text,flags=re.I|re.M)
    # Хэштеги
    text = re.sub(r'#[A-Za-zА-Яа-яёЁ0-9_]+','',text)
    # Список фраз
    for p in DELETE_PHRASES:
        text = re.sub(p,'',text,flags=re.I|re.M)
    # Имена менеджеров
    text = re.sub(r'^.*[Мм]енеджер[^\n]*\n?','',text,flags=re.M)
    text = re.sub(r'^.*[Аа]ртём[^\n]*\n?','',text,flags=re.M)
    text = re.sub(r'^.*[Рр]оман[^\n]*\n?','',text,flags=re.M)
    # Контакты
    text = re.sub(r'@[A-Za-z0-9_]+','',text)
    text = re.sub(r'https?://[^\s]+','',text)
    # Номера телефонов (цены уже спрятаны выше, так что этот шаг
    # больше не может случайно съесть цифры цены)
    text = re.sub(r'\+?\d[\d\s\-()]{6,}\d','',text)
    text = re.sub(r'Доставка\s+осуществляется[^\n]*','',text,flags=re.I)

    # Возвращаем спрятанные цены на место
    for _i, _tok in enumerate(_price_tokens):
        text = text.replace(f"\x00PRICE{_i}\x00", _tok)

    return text

def markup_prices(text):
    def rep(m):
        raw = re.sub(r'[\s,.\u00a0]','',m.group(1))
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
            return f"{(p+add):,}".replace(',','.')+cur
        except: return m.group(0)
    for pat in [r'(\d[\d\s.,\u00a0]*\d)\s*(₽|руб|RUB)',
                r'(\d[\d\s.,\u00a0]*\d)\s*(€)',
                r'(\d[\d\s.,\u00a0]*\d)\s*(\$)']:
        text = re.sub(pat, rep, text)
    return text

def fmt_chars(text):
    lines = text.split('\n')
    result = []
    for line in lines:
        s = line.strip()
        if not s: result.append(''); continue
        if re.match(r'^[•\-–—\s:]+$', s): continue
        s = re.sub(r'^[-–—]\s*','',s)
        if not s or re.match(r'^[•\s:]+$', s): continue
        if s.startswith('•') or s.startswith('▪'):
            c = re.sub(r'^[•▪]\s*','',s)
            c = re.sub(r'^[-–—]\s*','',c)
            if c and not re.match(r'^[\s:]+$',c): result.append(f'• {c}')
            continue
        if ':' in s:
            fld = s.split(':')[0].strip()
            val = s.split(':',1)[1].strip()
            if len(fld)<40 and val and not re.search(r'[₽€$]',s):
                result.append(f'• {s}'); continue
        result.append(s)
    text = '\n'.join(result)
    text = re.sub(r'^\s*[•\-–—]?\s*:\s*$','',text,flags=re.M)
    text = re.sub(r'\n{3,}','\n\n',text)
    return text.strip()

def bold_model(text):
    lines = text.split('\n')
    for i,l in enumerate(lines):
        s = l.strip()
        if s and not s.startswith('•') and not s.startswith('<b>'):
            lines[i] = f'<b>{s}</b>'
            break
    return '\n'.join(lines)

def bold_prices(text):
    def b(m):
        l = m.group(1).strip()
        return f'<b>{l}</b>' if not l.startswith('<b>') else l
    return re.sub(r'^([^\n<]*\d[\d\s.,\u00a0]*\d\s*[₽€$][^\n<]*)$',b,text,flags=re.M)

def bold_headers(text):
    for h in ['Комплектация:','Состояние:','Состояние автомобиля:',
              'Комплектация и оснащение:','Дополнительно:']:
        text = re.sub(re.escape(h),f'<b>{h}</b>',text,flags=re.I)
    return text

def insert_id(text, pub_id, link):
    tag = f'<a href="{link}">{pub_id}</a>' if link else pub_id
    lines = text.split('\n')
    last_p = -1
    for i,l in enumerate(lines):
        if re.search(r'<b>[^<]*\d[^<]*[₽€$][^<]*</b>',l):
            last_p = i
    if last_p >= 0:
        lines.insert(last_p+1, tag)
    else:
        lines.append(tag)
    return '\n'.join(lines)

def build_footer(text, pub_id):
    sp = pub_id or 'start'
    is_rub = '₽' in text and 'в москве' not in text.lower()
    mgr = f'<a href="https://t.me/{BOT_USERNAME}?start={sp}">«Написать менеджеру»</a> 📞 ✅'
    ch  = f'<a href="https://t.me/{TARGET_CHANNEL.replace("@","")}">{TARGET_CHANNEL}</a>'
    order = f'🏎️ Заказать другое авто — <a href="https://t.me/{BOT_USERNAME}">жми сюда</a>'
    if 'в москве' in text.lower() or '₽' in text:
        return (f"\n\nДоставка осуществляется во все города РФ\n\n"
                f"По поводу покупки или подбора:\n{mgr}\n"
                f"(Ответ в течении часа)\n{order}\n\n{ch}")
    return (f"\n\nРассчитаем стоимость до Вашего дома 🏠 ✅\n{mgr}\n"
            f"(Ответ в течении часа)\n{order}\n\n{ch}")

def _hashtag_safe(s):
    # Хештег в Telegram не может содержать пробелы/дефисы/точки —
    # убираем всё, кроме букв и цифр, получаем слитный тег.
    return re.sub(r'[^0-9A-Za-zА-Яа-яЁё]+', '', s)

def hashtags(text):
    tl = text.lower()
    matched_brand_variant = None
    matched_brand_key = None

    # Ищем марку по ВСЕЙ базе автомобилей (все марки из CAR_DATABASE),
    # а не по жёсткому списку из 15 популярных — работает для любой
    # марки/модели, какая бы ни встретилась в объявлении. Сортируем
    # варианты по убыванию длины, чтобы более специфичное совпадение
    # (например "Range Rover Sport") матчилось раньше короткого
    # ("Range Rover"), если оба присутствуют в тексте.
    brand_candidates = []
    for brand in CAR_DATABASE:
        # Некоторые марки в базе записаны через "/" (алиасы),
        # например "Lixiang / Li Auto" — проверяем каждый вариант.
        for variant in re.split(r'\s*/\s*', brand):
            if variant:
                brand_candidates.append((variant, brand))
    brand_candidates.sort(key=lambda x: -len(x[0]))

    for variant, brand in brand_candidates:
        if variant.lower() in tl:
            matched_brand_variant = variant
            matched_brand_key = brand
            break

    matched_model_variant = None
    if matched_brand_variant:
        # Модель ищем только внутри уже найденной марки — так тег модели
        # не перепутает, например, BMW X3 и Audi Q3. Тоже сортируем по
        # убыванию длины (например "911 Turbo" раньше просто "911").
        model_candidates = []
        for model in CAR_DATABASE[matched_brand_key]:
            for variant in re.split(r'\s*/\s*', model):
                if variant:
                    model_candidates.append(variant)
        model_candidates.sort(key=lambda x: -len(x))
        for variant in model_candidates:
            if variant.lower() in tl:
                matched_model_variant = variant
                break

    tags = []
    if matched_brand_variant:
        brand_tag = '#' + _hashtag_safe(matched_brand_variant)
        tags.append(brand_tag)
        if matched_model_variant:
            # Тег модели включает марку в начале (#BMWX5, а не просто
            # #X5), чтобы не пересекаться с одноимёнными моделями
            # у других марок и чтобы поиск по тегу сразу был однозначным.
            model_tag = '#' + _hashtag_safe(matched_brand_variant) + _hashtag_safe(matched_model_variant)
            tags.append(model_tag)

    return ' '.join(tags[:2] + ['#авточастно', '#автоподзаказ', '#АвтоНаЗаказ', '#ProAuto77'])

def format_post(original, pub_id, pub_link):
    if not original: return None
    logger.info(f"🔧 {pub_id}")
    t = clean(original)
    t = markup_prices(t)
    if re.search(r'в москве',t,re.I):
        t = re.sub(r'^.*Цена.*в (?:Уссурийске|Владивостоке).*\n?','',t,flags=re.I|re.M)
    t = fmt_chars(t)
    t = bold_headers(t)
    t = bold_model(t)
    t = bold_prices(t)
    t = re.sub(r'\n{3,}','\n\n',t).strip()
    t = insert_id(t, pub_id, pub_link)
    ht = hashtags(original)
    footer = build_footer(t, pub_id)
    return "Прямая продажа ✅\n\n" + t + footer + (f"\n\n{ht}" if ht else "")

# ════════════════════════════════════════════════════════════
# ПУБЛИКАЦИЯ
# ════════════════════════════════════════════════════════════

def fwd_info(msg):
    if not msg.forward_from_chat:
        return {'is_forwarded':False}
    return {
        'is_forwarded':True,
        'source_chat_id': msg.forward_from_chat.id,
        'source_message_id': msg.forward_from_message_id,
        'source_chat_username': msg.forward_from_chat.username,
    }

def orig_link(info):
    if not info.get('is_forwarded'): return None
    mid = info['source_message_id']
    un  = info['source_chat_username']
    cid = info['source_chat_id']
    if un: return f"https://t.me/{un}/{mid}"
    cid_s = str(cid)[4:] if str(cid).startswith('-100') else str(abs(cid))
    return f"https://t.me/c/{cid_s}/{mid}"

def pub_link(msg_id):
    return f"https://t.me/{TARGET_CHANNEL.replace('@','')}/{msg_id}"

def is_valid(text, has_media):
    if not has_media: return False, "нет медиа"
    if not text or len(text)<5: return True, "OK"
    hp = bool(re.search(r'\d[\d\s.,]*\d\s*[₽€$]',text))
    hk = bool(re.search(
        r'BMW|Mercedes|Audi|Toyota|Kia|Hyundai|Volkswagen|Porsche|'
        r'Honda|Nissan|Mazda|Geely|Haval|BYD|Tesla|Lexus|Volvo|'
        r'авто|машин|двигател',text,re.I))
    return (True,"OK") if (hp or hk) else (False,"не авто")

async def publish(update, context, info):
    msg = update.message
    mgid = msg.media_group_id
    text = msg.text or msg.caption or ""
    hp = bool(msg.photo)
    hv = bool(msg.video)

    if mgid:
        if mgid not in media_cache:
            media_cache[mgid] = {'photos':[],'caption':'','info':info}
            asyncio.create_task(_album(mgid, context))
        if msg.photo:
            media_cache[mgid]['photos'].append(('photo', msg.photo[-1].file_id))
        if msg.video:
            media_cache[mgid]['photos'].append(('video', msg.video.file_id))
        if msg.caption and not media_cache[mgid]['caption']:
            media_cache[mgid]['caption'] = msg.caption
        return

    ok, reason = is_valid(text, hp or hv)
    if not ok: logger.info(f"⏭ {reason}"); return

    pid = next_pub_id()
    sl  = orig_link(info) if info else None
    fmt = format_post(text, pid, None)
    if not fmt: return

    try:
        if hp:
            sent = await context.bot.send_photo(
                chat_id=TARGET_GROUP_ID, photo=msg.photo[-1].file_id,
                caption=fmt, parse_mode='HTML')
        elif hv:
            sent = await context.bot.send_video(
                chat_id=TARGET_GROUP_ID, video=msg.video.file_id,
                caption=fmt, parse_mode='HTML')
        else:
            sent = await context.bot.send_message(
                chat_id=TARGET_GROUP_ID, text=fmt, parse_mode='HTML')

        pmid = sent.message_id
        pl   = pub_link(pmid)
        new  = format_post(text, pid, pl)
        try:
            if hp or hv:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID, message_id=pmid,
                    caption=new, parse_mode='HTML')
            else:
                await context.bot.edit_message_text(
                    chat_id=TARGET_GROUP_ID, message_id=pmid,
                    text=new, parse_mode='HTML')
        except: pass

        save_pub(pid, source_link=sl,
                 source_username=info.get('source_chat_username') if info else None,
                 published_message_id=pmid,
                 original_caption=text,
                 telegram_link=pl)
        logger.info(f"✅ {pid}")
    except Exception as e:
        logger.error(f"❌ publish: {e}")

async def _album(mgid, context):
    await asyncio.sleep(3)
    if mgid not in media_cache: return
    gd = media_cache[mgid]
    photos, caption, info = gd['photos'], gd['caption'], gd['info']
    if not photos: del media_cache[mgid]; return
    ok, reason = is_valid(caption, True)
    if not ok: del media_cache[mgid]; return
    pid = next_pub_id()
    sl  = orig_link(info) if info else None
    fmt = format_post(caption, pid, None)
    if not fmt: del media_cache[mgid]; return
    try:
        # Каждый элемент альбома — (тип, file_id). Раньше все элементы
        # (в т.ч. видео) заворачивались в InputMediaPhoto, из-за чего
        # Telegram отклонял альбом с видео ошибкой "Can't use file of
        # type video as photo". Теперь тип элемента учитывается.
        def _media_item(kind, file_id, caption=None, parse_mode=None):
            cls = InputMediaVideo if kind == 'video' else InputMediaPhoto
            if caption is not None:
                return cls(media=file_id, caption=caption, parse_mode=parse_mode)
            return cls(media=file_id)

        first_kind, first_id = photos[0]
        media = [_media_item(first_kind, first_id, caption=fmt, parse_mode='HTML')]
        media += [_media_item(k, fid) for k, fid in photos[1:]]
        sent = await context.bot.send_media_group(chat_id=TARGET_GROUP_ID, media=media)
        pmid = sent[0].message_id if sent else None
        if pmid:
            pl  = pub_link(pmid)
            new = format_post(caption, pid, pl)
            try:
                await context.bot.edit_message_caption(
                    chat_id=TARGET_GROUP_ID, message_id=pmid,
                    caption=new, parse_mode='HTML')
            except: pass
            save_pub(pid, source_link=sl,
                     source_username=info.get('source_chat_username') if info else None,
                     published_message_id=pmid,
                     original_caption=caption,
                     telegram_link=pl)
        logger.info(f"✅ Альбом {pid}")
    except Exception as e:
        logger.error(f"❌ _album: {e}")
    finally:
        if mgid in media_cache: del media_cache[mgid]

# ════════════════════════════════════════════════════════════
# УВЕДОМЛЕНИЕ МЕНЕДЖЕРУ
# ════════════════════════════════════════════════════════════

async def notify_manager(context, lid, data):
    """
    Уведомление менеджеру о новой заявке.
    Ссылка на клиента:
      - Есть username → https://t.me/username  (работает везде)
      - Нет username  → tg://user?id=ID        (работает в TG-приложении,
                                                 бот должен знать этого пользователя)
    Плюс, если заявка привязана к конкретному объявлению (pub_id),
    добавляем кликабельную ссылку на ОРИГИНАЛ этого объявления в
    группе-источнике — чтобы менеджер мог сразу перейти туда и
    связаться с тем, кто изначально выложил авто.
    """
    uid = data['user_id']
    un  = data.get('username')
    fn  = data.get('first_name') or 'Клиент'
    ln  = data.get('last_name') or ''
    full_name = f"{fn} {ln}".strip()

    # Подтягиваем данные исходной публикации (для ссылки на оригинал)
    pub = find_pub(data.get('pub_id')) if data.get('pub_id') else None

    text = f"🆕 <b>ЗАЯВКА {lid}</b>\n\n"

    # ── Данные клиента ──────────────────────────────────────
    if un:
        # username есть — простая ссылка
        text += f"👤 <a href='https://t.me/{un}'>@{un}</a> ({full_name})\n"
    else:
        # username нет — text mention через tg://
        # Telegram откроет профиль при клике в приложении
        text += f"👤 <a href='tg://user?id={uid}'>{full_name}</a>\n"

    text += f"🆔 ID: <code>{uid}</code>\n\n"

    # ── Тип заявки ─────────────────────────────────────────
    itype = data.get('interest_type','')
    if itype == 'consultation':
        text += "✍️ <b>Запрос консультации</b>\n\n"
    elif data.get('pub_id'):
        text += f"🚗 <b>Интересует:</b> {data.get('car_model','?')}\n"
        text += f"({data['pub_id']})\n\n"
    else:
        text += "<b>Параметры заказа:</b>\n"

    for k, label in [('brand','Марка'), ('model','Модель'),
                     ('generation','Поколение'), ('city','Город'),
                     ('timing','Срок')]:
        if data.get(k):
            text += f"• {label}: {data[k]}\n"

    # ── Ссылка на оригинал объявления (группа-источник) ─────
    if pub and pub.get('source_link'):
        text += f"\n🔗 <a href='{pub['source_link']}'>Оригинал объявления в группе-источнике</a>\n"

    # ── Кнопки для менеджера ───────────────────────────────
    # Если есть username — кнопка открывает чат напрямую.
    # Если нет — используем ТОЛЬКО callback-кнопку через relay бота.
    # ВАЖНО: url=tg://user?id=... как inline-кнопка не годится — Telegram
    # проверяет настройки приватности получателя и, если они ограничены
    # (стандартная ситуация для большинства клиентов), отклоняет ВЕСЬ
    # запрос sendMessage целиком с ошибкой "Button_user_privacy_restricted",
    # из-за чего пропадает вся заявка, а не только кнопка. Текстовая
    # ссылка tg://user?id= в теле сообщения (выше) этой проблеме не
    # подвержена — это другой механизм, её оставляем.
    rows = []
    if un:
        rows.append([InlineKeyboardButton(
            "💬 Написать клиенту", url=f"https://t.me/{un}"
        )])
    else:
        rows.append([InlineKeyboardButton(
            "✉️ Написать через бота", callback_data=f"write_{uid}_{lid}"
        )])
    if pub and pub.get('source_link'):
        rows.append([InlineKeyboardButton(
            "🔗 Оригинал объявления", url=pub['source_link']
        )])
    # ── Кнопки статуса заявки (мини-CRM) ───────────────────
    # Меняют статус в один тап: новая → в работе → сделка/отказ.
    # /stats потом считает по этим статусам реальную конверсию.
    rows.append([
        InlineKeyboardButton("🔄 В работу", callback_data=f"st_{lid}_work"),
        InlineKeyboardButton("✅ Сделка",   callback_data=f"st_{lid}_deal"),
        InlineKeyboardButton("❌ Отказ",    callback_data=f"st_{lid}_lost"),
    ])
    kb = InlineKeyboardMarkup(rows)

    # ── Отправляем владельцу и менеджеру ───────────────────
    for rid in [OWNER_ID, MANAGER_USER_ID]:
        if rid:
            try:
                await context.bot.send_message(
                    chat_id=rid, text=text,
                    parse_mode='HTML',
                    reply_markup=kb)
            except Exception as e:
                logger.error(f"notify {rid}: {e}")
                # Подстраховка: если сообщение не ушло именно из-за
                # клавиатуры (например, снова какая-то кнопка не понравится
                # Telegram по новой причине) — пробуем отправить хотя бы
                # текст заявки без кнопок, чтобы менеджер её точно увидел.
                try:
                    await context.bot.send_message(
                        chat_id=rid, text=text, parse_mode='HTML')
                except Exception as e2:
                    logger.error(f"notify {rid} (fallback без кнопок): {e2}")

# ════════════════════════════════════════════════════════════
# БРИФ — ФИНАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════

async def finalize(update, context, uid):
    st   = get_state(uid)
    data = st['data']
    user = update.effective_user
    lid  = next_lead_id()
    ld   = {
        'user_id': uid,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'status': 'new',        # начальный статус для мини-CRM
        'notified': False,      # для напоминания о зависшей заявке
        **data
    }
    save_lead(lid, ld)

    itype = data.get('interest_type','')
    if itype == 'consultation':
        msg = (f"✅ <b>Спасибо! Заявка #{lid} принята</b>\n\n"
               f"✍️ Запрос консультации\n\n"
               f"Менеджер свяжется с Вами в течение 1 часа\n"
               f"Благодарим за доверие к ProAuto ✅\n\n"
               f"Наш канал с актуальными предложениями:\n"
               f'<a href="https://t.me/{TARGET_CHANNEL.replace("@","")}">{TARGET_CHANNEL}</a>')
    elif data.get('pub_id'):
        msg = (f"✅ <b>Заявка #{lid} принята</b>\n\n"
               f"🚗 {data.get('car_model','авто')}\n"
               f"📍 {data.get('city','?')}\n"
               f"⏰ {data.get('timing','?')}\n\n"
               f"Менеджер свяжется с Вами в течение 1 часа\n"
               f"Благодарим за доверие к ProAuto ✅\n\n"
               f'<a href="https://t.me/{TARGET_CHANNEL.replace("@","")}">{TARGET_CHANNEL}</a>')
    else:
        car = f"{data.get('brand','')} {data.get('model','')}".strip()
        if data.get('generation') and data['generation'] != 'Любое':
            car += f" ({data['generation']})"
        msg = (f"✅ <b>Заявка #{lid} принята</b>\n\n"
               f"🚗 {car or 'Авто на заказ'}\n"
               f"📍 {data.get('city','?')}\n"
               f"⏰ {data.get('timing','?')}\n\n"
               f"Менеджер свяжется с Вами в течение 1 часа\n"
               f"Благодарим за доверие к ProAuto ✅\n\n"
               f'<a href="https://t.me/{TARGET_CHANNEL.replace("@","")}">{TARGET_CHANNEL}</a>')

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg, parse_mode='HTML',
        disable_web_page_preview=True)
    await notify_manager(context, lid, ld)
    clear_state(uid)

# ════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ════════════════════════════════════════════════════════════

def city_kb(prefix):
    kb, row = [], []
    for i,c in enumerate(CITIES):
        row.append(InlineKeyboardButton(c, callback_data=f"{prefix}city_{i}"))
        if len(row)==2: kb.append(row); row=[]
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("✍️ Другой город", callback_data=f"{prefix}city_other")])
    return kb

def timing_kb(prefix):
    return [[InlineKeyboardButton(t, callback_data=f"{prefix}timing_{i}")]
            for i,t in enumerate(TIMINGS)]

# ════════════════════════════════════════════════════════════
# CALLBACK КНОПОК
# ════════════════════════════════════════════════════════════

async def button_cb(update, context):
    q   = update.callback_query
    await q.answer()
    d   = q.data
    uid = q.from_user.id
    st  = get_state(uid)
    logger.info(f"🔘 {uid}: {d[:50]}")

    # ── КОНКРЕТНОЕ АВТО ──────────────────────────────────────
    if d.startswith("yes_"):
        pid = d[4:]
        pub = find_pub(pid)
        orig = pub.get('original_caption','') if pub else ''
        cm = None
        if orig:
            for line in orig.split('\n'):
                c = EMOJI_RE.sub('',line).strip()
                c = re.sub(r'^[-–—•*]\s*','',c).strip()
                if not c or len(c)<3: continue
                for b in CAR_BRANDS_LIST:
                    if b.lower() in c.lower():
                        cm = re.sub(r'\bв\s+продаже\b|\bв\s+наличии\b','',c,flags=re.I).strip()
                        cm = re.sub(r'[‼!]+','',cm).strip()[:70]
                        break
                if cm: break
        cm = cm or 'автомобиль'
        st['data'] = {'pub_id':pid,'car_model':cm,'interest_type':'specific_car'}
        await q.edit_message_text(f"🚗 {cm}", parse_mode='HTML')
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🏙 <b>В какой город нужна доставка?</b>",
            reply_markup=InlineKeyboardMarkup(city_kb("s_")),
            parse_mode='HTML')
        return

    if d.startswith("s_city_"):
        idx = d[7:]
        st['data']['city'] = (CITIES[int(idx)] if idx!='other'
                              else 'Другой (уточнить с менеджером)')
        await q.edit_message_text(f"🏙 {st['data']['city']}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏰ <b>Когда планируете покупку?</b>",
            reply_markup=InlineKeyboardMarkup(timing_kb("s_")),
            parse_mode='HTML')
        return

    if d.startswith("s_timing_"):
        try:
            st['data']['timing'] = TIMINGS[int(d[9:])]
        except:
            st['data']['timing'] = 'Не указано'
        await q.edit_message_text(f"⏰ {st['data']['timing']} ✅")
        await finalize(update, context, uid)
        return

    # ── КОНСУЛЬТАЦИЯ ─────────────────────────────────────────
    if d == "consult":
        st['data']['interest_type'] = 'consultation'
        await q.edit_message_text("✍️ Оформляем запрос консультации...")
        await finalize(update, context, uid)
        return

    # ── ИНДИВИДУАЛЬНЫЙ ЗАКАЗ ─────────────────────────────────
    if d == "custom":
        st['data'] = {'interest_type':'custom'}
        kb = [[InlineKeyboardButton(g, callback_data=f"bg_{i}")]
              for i,g in enumerate(BRAND_GROUPS.keys())]
        kb.append([InlineKeyboardButton("🤔 Любая марка", callback_data="bg_any")])
        await q.edit_message_text(
            "🚗 <b>Какие марки Вас интересуют?</b>",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        return

    if d == "bg_any":
        st['data'].update({'brand':'Любая','model':'Любая','generation':'Любое'})
        await q.edit_message_text("🚗 Марка: <b>Любая</b>", parse_mode='HTML')
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
        except Exception as e:
            logger.error(f"bg_: {e}")
        return

    if d.startswith("br_"):
        try:
            parts = d.split("_")
            gi, bi = int(parts[1]), int(parts[2])
            brands = BRAND_GROUPS[list(BRAND_GROUPS.keys())[gi]]
            if bi >= len(brands):
                await q.edit_message_text("⚠️ Попробуйте заново /start")
                clear_state(uid); return
            brand = brands[bi]
            st['data']['brand'] = brand
            await q.edit_message_text(f"✅ Марка: <b>{brand}</b>", parse_mode='HTML')
            models = get_models(brand)
            if not models:
                st['data']['model'] = 'Любая'
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⏰ <b>Когда планируете покупку?</b>",
                    reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
                return
            kb, row = [], []
            for i,m in enumerate(models):
                row.append(InlineKeyboardButton(m, callback_data=f"mo_{i}"))
                if len(row)==2: kb.append(row); row=[]
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"bg_{gi}")])
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"<b>{brand}</b> — выберите модель:",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except Exception as e:
            logger.error(f"br_: {e}")
        return

    if d.startswith("mo_"):
        try:
            idx   = int(d[3:])
            brand = st['data'].get('brand','')
            mlist = get_models(brand)
            if not mlist or idx >= len(mlist):
                await q.edit_message_text("⚠️ Список изменился. Начните заново /start")
                clear_state(uid); return
            model = mlist[idx]
            st['data']['model'] = model
            await q.edit_message_text(f"✅ Модель: <b>{model}</b>", parse_mode='HTML')
            gens = get_generations(brand, model)
            if not gens:
                st['data']['generation'] = 'Не указано'
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⏰ <b>Когда планируете покупку?</b>",
                    reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
                return
            kb = [[InlineKeyboardButton(g, callback_data=f"ge_{i}")]
                  for i,g in enumerate(gens)]
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"br_{st['data'].get('gidx',0)}_{list(get_models(brand)).index(model) if brand in CAR_DATABASE else 0}")])
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"<b>{brand} {model}</b> — выберите поколение:",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except Exception as e:
            logger.error(f"mo_: {e}")
        return

    if d.startswith("ge_"):
        try:
            brand = st['data'].get('brand','')
            model = st['data'].get('model','')
            gens  = get_generations(brand, model)
            idx   = int(d[3:])
            if not gens or idx >= len(gens):
                await q.edit_message_text("⚠️ Попробуйте заново /start")
                clear_state(uid); return
            st['data']['generation'] = gens[idx]
            await q.edit_message_text(
                f"✅ Поколение: <b>{gens[idx]}</b>", parse_mode='HTML')
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⏰ <b>Когда планируете покупку?</b>",
                reply_markup=InlineKeyboardMarkup(timing_kb("c_")), parse_mode='HTML')
        except Exception as e:
            logger.error(f"ge_: {e}")
        return

    if d.startswith("c_timing_"):
        try:
            st['data']['timing'] = TIMINGS[int(d[9:])]
        except:
            st['data']['timing'] = 'Не указано'
        await q.edit_message_text(f"⏰ {st['data']['timing']}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🏙 <b>В какой город нужна доставка?</b>",
            reply_markup=InlineKeyboardMarkup(city_kb("c_")), parse_mode='HTML')
        return

    if d.startswith("c_city_"):
        idx = d[7:]
        st['data']['city'] = (CITIES[int(idx)] if idx!='other'
                              else 'Другой (уточнить с менеджером)')
        await q.edit_message_text(f"🏙 {st['data']['city']} ✅")
        await finalize(update, context, uid)
        return

    # ── СТАТУС ЗАЯВКИ (мини-CRM) ────────────────────────────
    # callback: st_{lead_id}_{status}. lead_id сам содержит "_"
    # (lead_00017), поэтому статус берём как последний сегмент,
    # а lead_id — всё, что между "st_" и последним "_".
    if d.startswith("st_"):
        try:
            body = d[3:]                    # "lead_00017_deal"
            status = body.rsplit("_", 1)[1] # "deal"
            lid    = body.rsplit("_", 1)[0] # "lead_00017"
            labels = {'work':'🔄 В работе', 'deal':'✅ Сделка', 'lost':'❌ Отказ'}
            rec = update_lead(lid, status=status,
                              status_at=datetime.now().isoformat(),
                              status_by=uid)
            if not rec:
                await q.answer("Заявка не найдена")
                return
            await q.answer(f"Статус: {labels.get(status, status)}")

            # Реферальный бонус: если сделка закрыта и клиента кто-то
            # привёл (referred_by) — уведомляем пригласившего.
            if status == 'deal' and rec.get('referred_by') and not rec.get('ref_rewarded'):
                referrer = rec['referred_by']
                try:
                    car = rec.get('car_model') or 'авто'
                    await context.bot.send_message(
                        chat_id=referrer,
                        text=(f"🎉 <b>Ваш реферальный бонус!</b>\n\n"
                              f"Приглашённый вами человек оформил покупку ({car}).\n"
                              f"Свяжитесь с менеджером ProAuto для получения бонуса. 🎁"),
                        parse_mode='HTML')
                    update_lead(lid, ref_rewarded=True)
                    # и владельцу — напоминание выдать бонус
                    if OWNER_ID:
                        await context.bot.send_message(
                            chat_id=OWNER_ID,
                            text=(f"🎁 Реферальный бонус к выдаче!\n"
                                  f"Пригласивший: <code>{referrer}</code>\n"
                                  f"Заявка: {lid}"),
                            parse_mode='HTML')
                except Exception as e:
                    logger.error(f"ref reward {lid}: {e}")

            try:
                base = q.message.text_html if q.message.text else (q.message.caption_html or "")
            except Exception:
                base = q.message.text or ""
            new_text = f"{base}\n\n<b>Статус:</b> {labels.get(status, status)}"
            try:
                if q.message.text:
                    await q.edit_message_text(new_text, parse_mode='HTML',
                                              disable_web_page_preview=True)
                else:
                    await q.edit_message_caption(new_text, parse_mode='HTML')
            except Exception:
                try: await q.edit_message_reply_markup(reply_markup=None)
                except Exception: pass
        except Exception as e:
            logger.error(f"st_: {e}")
            await q.answer("Ошибка смены статуса")
        return

    # ── НАПИСАТЬ КЛИЕНТУ (кнопка из уведомления) ────────────
    if d.startswith("write_"):
        try:
            # формат write_{client_id}_{lead_id}, где lead_id = "lead_00017"
            body = d[len("write_"):]        # "7631042064_lead_00017"
            first = body.split("_", 1)      # ["7631042064", "lead_00017"]
            client_id = int(first[0])
            lid_str   = first[1] if len(first) > 1 else "?"
            manager_id = uid

            RELAY_SESSIONS[manager_id] = client_id
            RELAY_SESSIONS[client_id]  = manager_id

            await q.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(
                chat_id=manager_id,
                text=(
                    f"✏️ <b>Диалог с клиентом открыт</b>\n"
                    f"Заявка: <b>{lid_str}</b> | "
                    f"ID клиента: <code>{client_id}</code>\n\n"
                    f"Напишите следующее сообщение — "
                    f"бот перешлёт его клиенту.\n\n"
                    f"Завершить диалог: /endchat"
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"write_: {e}")
            await q.answer("Ошибка — попробуйте /msg")
        return

# ════════════════════════════════════════════════════════════
# КОМАНДЫ
# ════════════════════════════════════════════════════════════

async def cmd_msg(update, context):
    """
    /msg USER_ID текст сообщения
    Отправить сообщение клиенту без username через бота.
    Пример: /msg 7631042064 Здравствуйте, ваша заявка принята!
    """
    if not has_rights(update.effective_user.id):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📤 <b>Отправка сообщения клиенту</b>\n\n"
            "Использование:\n"
            "<code>/msg USER_ID текст сообщения</code>\n\n"
            "Пример:\n"
            "<code>/msg 7631042064 Здравствуйте! Ваша заявка на BMW Z4 принята. "
            "Когда вам удобно созвониться?</code>\n\n"
            "После отправки клиент ответит боту, "
            "и его ответ придёт вам сюда.",
            parse_mode='HTML'
        )
        return

    try:
        client_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ USER_ID должен быть числом")
        return

    message_text = ' '.join(args[1:])
    manager_id   = update.effective_user.id

    # Оборачиваем в красивый блок от ProAuto
    outgoing = (
        f"📩 <b>Сообщение от менеджера ProAuto:</b>\n\n"
        f"{message_text}\n\n"
        f"─────────────────\n"
        f"💬 Чтобы ответить — просто напишите в этот чат."
    )

    try:
        await context.bot.send_message(
            chat_id=client_id,
            text=outgoing,
            parse_mode='HTML'
        )
        # Запоминаем активный диалог
        RELAY_SESSIONS[client_id] = manager_id
        RELAY_SESSIONS[manager_id] = client_id

        await update.message.reply_text(
            f"✅ <b>Сообщение доставлено клиенту</b> (ID: <code>{client_id}</code>)\n\n"
            f"Когда клиент ответит — его ответ придёт вам сюда автоматически.\n\n"
            f"Чтобы завершить диалог: /endchat",
            parse_mode='HTML'
        )
        logger.info(f"📤 Менеджер {manager_id} написал клиенту {client_id}")
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Не удалось отправить сообщение</b>\n\n"
            f"Причина: {str(e)}\n\n"
            f"Возможные причины:\n"
            f"• Клиент заблокировал бота\n"
            f"• Клиент ещё не писал боту\n"
            f"• Неверный ID\n\n"
            f"💡 Попросите клиента написать /start в боте.",
            parse_mode='HTML'
        )


async def cmd_endchat(update, context):
    """Завершить активный диалог с клиентом"""
    if not has_rights(update.effective_user.id):
        return
    manager_id = update.effective_user.id
    client_id  = RELAY_SESSIONS.pop(manager_id, None)
    if client_id:
        RELAY_SESSIONS.pop(client_id, None)
        await update.message.reply_text(
            f"✅ Диалог с клиентом <code>{client_id}</code> завершён.",
            parse_mode='HTML')
    else:
        await update.message.reply_text("ℹ️ Нет активных диалогов.")


async def cmd_chats(update, context):
    """Показать активные диалоги"""
    if not has_rights(update.effective_user.id):
        return
    manager_id = update.effective_user.id
    active = {k:v for k,v in RELAY_SESSIONS.items()
              if k == manager_id or v == manager_id}
    if not active:
        await update.message.reply_text("ℹ️ Нет активных диалогов с клиентами.")
        return
    txt = "💬 <b>Активные диалоги:</b>\n"
    seen = set()
    for k,v in active.items():
        pair = tuple(sorted([k,v]))
        if pair in seen: continue
        seen.add(pair)
        client_id = v if k == manager_id else k
        txt += f"• Клиент ID: <code>{client_id}</code>\n"
    txt += "\n/endchat — завершить диалог"
    await update.message.reply_text(txt, parse_mode='HTML')


async def cmd_start(update, context):
    uid  = update.effective_user.id
    args = context.args

    # ── Метка источника трафика ──────────────────────────────
    # Ссылки вида t.me/proauto_23_bot?start=src_vk запоминают, откуда
    # пришёл клиент. Метка сохраняется в состоянии и позже попадает в
    # заявку (lead_source) — так в /stats видно, какой канал даёт заявки.
    # Поддерживаются и комбинированные метки: src_vk_id_0013 (источник
    # + конкретное объявление одновременно).
    if args and args[0].startswith('src_'):
        raw = args[0][4:]  # убираем "src_"
        # если внутри есть привязка к объявлению вида ..._id_0013
        m = re.search(r'(id_\d{4})', raw)
        pub_from_src = m.group(1) if m else None
        source = re.sub(r'_?id_\d{4}$', '', raw) or 'unknown'
        st = get_state(uid)
        st['data']['lead_source'] = source
        if pub_from_src:
            # превращаем в обычный сценарий "конкретное авто",
            # переставив args, чтобы сработала ветка ниже
            args = [pub_from_src]
        else:
            args = []

    # ── Реферальная ссылка ───────────────────────────────────
    # t.me/bot?start=ref_123456789 — 123456789 это user_id пригласившего.
    # Запоминаем, кто привёл клиента (referred_by), чтобы при сделке
    # начислить бонус пригласившему. Метку источника ставим 'referral'.
    if args and args[0].startswith('ref_'):
        try:
            referrer_id = int(args[0][4:])
            if referrer_id != uid:   # нельзя пригласить самого себя
                st = get_state(uid)
                st['data']['referred_by'] = referrer_id
                st['data'].setdefault('lead_source', 'referral')
        except ValueError:
            pass
        args = []

    if args and args[0].startswith('id_'):
        pid = args[0]
        pub = find_pub(pid)
        orig = pub.get('original_caption','') if pub else ''
        cm = None
        if orig:
            for line in orig.split('\n'):
                c = EMOJI_RE.sub('',line).strip()
                c = re.sub(r'^[-–—•*]\s*','',c).strip()
                if not c or len(c)<3: continue
                for b in CAR_BRANDS_LIST:
                    if b.lower() in c.lower():
                        cm = re.sub(r'\bв\s+продаже\b|\bв\s+наличии\b','',c,flags=re.I).strip()
                        cm = re.sub(r'[‼!]+','',cm).strip()[:60]
                        break
                if cm: break
        cm = cm or 'автомобиль'
        _prev_src = get_state(uid)['data'].get('lead_source')
        get_state(uid)['data'] = {
            'pub_id':pid,'car_model':cm,'interest_type':'specific_car'}
        if _prev_src:
            get_state(uid)['data']['lead_source'] = _prev_src

        kb = [
            [InlineKeyboardButton(f"✅ {cm[:45]}",  callback_data=f"yes_{pid}")],
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
            f"🚀 <b>PROAUTO BOT — Панель управления</b>\n\n"
            f"📤 Пересылай объявления → публикую в {TARGET_CHANNEL}\n"
            f"📹 Фото и видео — оба работают\n"
            f"📦 Альбомы — работают\n\n"
            f"<b>Команды:</b>\n"
            f"📊 /stats — статистика\n"
            f"📋 /leads — последние заявки\n"
            f"📤 /export id_XXXX — тексты для площадок",
            parse_mode='HTML')
        return

    # Клиент
    kb = [
        [InlineKeyboardButton("🏎️ Подобрать автомобиль", callback_data="custom")],
        [InlineKeyboardButton("✍️ Консультация",          callback_data="consult")],
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=("Здравствуйте! 👋\n\n"
              "Я представляю компанию <b>ProAuto</b> — профессиональный подбор "
              "и доставка автомобилей по всей России и СНГ.\n\n"
              "<b>Наши преимущества:</b>\n"
              "• ✅ Прозрачные цены без скрытых платежей\n"
              "• 🚗 Подбор авто под любой бюджет\n"
              "• 📦 Доставка во все города РФ\n"
              "• 📋 Полное юридическое сопровождение\n"
              "• 🛡 Гарантия качества\n\n"
              "<b>Что Вас интересует?</b>"),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode='HTML', disable_web_page_preview=True)

async def cmd_stats(update, context):
    if not has_rights(update.effective_user.id): return
    pd = _load(PUBS_DB, {'counter':0,'publications':{}})
    ld = _load(LEADS_DB, {'counter':0,'leads':{}})
    week_ago = datetime.now() - timedelta(days=7)

    rp = sum(1 for p in pd['publications'].values()
             if _recent(p.get('published_at'), week_ago))
    rl = sum(1 for l in ld['leads'].values()
             if _recent(l.get('created_at'), week_ago))

    # Топ марок
    brands = {}
    for p in pd['publications'].values():
        b = p.get('car_brand') or 'Другое'
        brands[b] = brands.get(b,0) + 1
    top = sorted(brands.items(), key=lambda x:-x[1])[:5]
    top_str = '\n'.join(f"  • {b}: {n}" for b,n in top) if top else "  нет данных"

    # Разбивка заявок по источнику трафика (метки src_*)
    sources = {}
    for l in ld['leads'].values():
        s = l.get('lead_source') or 'напрямую'
        sources[s] = sources.get(s,0) + 1
    src_top = sorted(sources.items(), key=lambda x:-x[1])[:8]
    src_str = '\n'.join(f"  • {s}: {n}" for s,n in src_top) if src_top else "  нет данных"

    # Воронка по статусам (мини-CRM): конверсия заявка→сделка
    statuses = {'new':0, 'work':0, 'deal':0, 'lost':0}
    for l in ld['leads'].values():
        s = l.get('status') or 'new'
        statuses[s] = statuses.get(s, 0) + 1
    total_leads = sum(statuses.values())
    deals = statuses.get('deal', 0)
    conv_deal = round(deals / max(total_leads, 1) * 100, 1)
    funnel_str = (f"  🆕 Новые: {statuses.get('new',0)}\n"
                  f"  🔄 В работе: {statuses.get('work',0)}\n"
                  f"  ✅ Сделки: {statuses.get('deal',0)}\n"
                  f"  ❌ Отказы: {statuses.get('lost',0)}")

    await update.message.reply_text(
        f"📊 <b>СТАТИСТИКА ProAuto</b>\n\n"
        f"📢 <b>Публикации:</b>\n"
        f"  Всего: {pd.get('counter',0)}\n"
        f"  За 7 дней: {rp}\n\n"
        f"📋 <b>Заявки:</b>\n"
        f"  Всего: {ld.get('counter',0)}\n"
        f"  За 7 дней: {rl}\n\n"
        f"🎯 <b>Воронка заявок:</b>\n{funnel_str}\n"
        f"  📈 Конверсия в сделку: {conv_deal}%\n\n"
        f"🏎️ <b>Топ марок:</b>\n{top_str}\n\n"
        f"📡 <b>Источники заявок:</b>\n{src_str}",
        parse_mode='HTML')

def _recent(dt_str, threshold):
    try: return datetime.fromisoformat(dt_str) > threshold
    except: return False

async def cmd_leads(update, context):
    if not has_rights(update.effective_user.id): return
    db = _load(LEADS_DB, {'counter':0,'leads':{}})
    if not db['leads']:
        await update.message.reply_text("📋 Заявок пока нет")
        return
    items = sorted(db['leads'].items(),
                   key=lambda x: x[1].get('created_at',''), reverse=True)[:10]
    _stemoji = {'new':'🆕','work':'🔄','deal':'✅','lost':'❌'}
    text = f"📋 <b>ПОСЛЕДНИЕ {len(items)} ЗАЯВОК</b>\n\n"
    for lid,l in items:
        try:
            d = datetime.fromisoformat(l.get('created_at','')).strftime('%d.%m %H:%M')
        except: d = "?"
        itype = l.get('interest_type','')
        stt = l.get('status','new')
        text += f"{_stemoji.get(stt,'🆕')} <b>{lid}</b> | {d}\n"
        text += f"👤 @{l.get('username','?')} ({l.get('first_name','')})\n"
        if itype == 'consultation':
            text += "✍️ Консультация\n"
        elif l.get('pub_id'):
            text += f"🚗 {(l.get('car_model') or '')[:40]}\n"
        elif l.get('brand'):
            text += f"🔍 {l.get('brand','')} {l.get('model','')}\n"
        if l.get('city'):  text += f"🏙 {l['city']}\n"
        if l.get('timing'):text += f"⏰ {l['timing']}\n"
        if l.get('lead_source'): text += f"📡 {l['lead_source']}\n"
        text += "━━━━━━━━━\n"
    if len(text)>4000: text=text[:3950]+"..."
    await update.message.reply_text(text, parse_mode='HTML')

async def cmd_export(update, context):
    if not has_rights(update.effective_user.id): return
    args = context.args
    if not args:
        await update.message.reply_text(
            "📤 Использование: <code>/export id_0001</code>",
            parse_mode='HTML'); return
    pub = find_pub(args[0])
    if not pub:
        await update.message.reply_text(f"❌ {args[0]} не найдено"); return
    orig = pub.get('original_caption','')
    if not orig:
        await update.message.reply_text("❌ Нет текста"); return

    c = clean(orig)
    c = markup_prices(c)

    avito = (f"🚗 Подбор и доставка автомобиля\n\n{c}\n\n"
             f"✅ Растаможка под ключ\n✅ Доставка в ваш город\n"
             f"✅ Юр. сопровождение\n\n"
             f"Telegram: t.me/{BOT_USERNAME}?start={args[0]}\n\n"
             f"КЛЮЧИ: авто под заказ, пригон авто, авто из кореи, "
             f"авто из германии, подбор автомобиля")

    vk = (f"🚗 Подбор и доставка авто\n\n{c}\n\n"
          f"✅ Прозрачные цены\n✅ Доставка РФ\n✅ Гарантия\n\n"
          f"t.me/{BOT_USERNAME}?start={args[0]}\n\n"
          f"#авто #автоподзаказ #пригонавто #авточастно")

    await update.message.reply_text(
        f"📤 <b>ЭКСПОРТ {args[0]}</b>", parse_mode='HTML')
    for title, body in [("🟢 АВИТО", avito), ("🟦 ВКОНТАКТЕ", vk)]:
        if len(body) > 3000: body = body[:3000]+"..."
        await update.message.reply_text(
            f"{title}:\n\n<code>{body}</code>", parse_mode='HTML')

# ════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════

async def handle_msg(update, context):
    try:
        msg = update.message
        if not msg: return
        uid  = msg.from_user.id
        text = msg.text or msg.caption or ""

        if has_rights(uid):
            info = fwd_info(msg)
            # Проверяем — есть ли pub_id в тексте (поиск оригинала)
            eid = re.search(r'id_(\d{4})', text)
            if eid:
                pid = f"id_{eid.group(1)}"
                pub = find_pub(pid)
                if pub:
                    await msg.reply_text(
                        f"🔗 <b>{pid}</b>\n\n"
                        f"Источник: @{pub.get('source_username','?')}\n"
                        f"{pub.get('source_link','нет')}",
                        parse_mode='HTML')
                else:
                    await msg.reply_text(f"❌ {pid} не найдено")
                return

            if info.get('is_forwarded') or msg.photo or msg.video:
                await publish(update, context,
                              info if info.get('is_forwarded') else None)
            else:
                # ── RELAY: менеджер отвечает клиенту ──
                if uid in RELAY_SESSIONS and text and not text.startswith('/'):
                    client_id = RELAY_SESSIONS[uid]
                    outgoing = (
                        f"📩 <b>Сообщение от менеджера ProAuto:</b>\n\n"
                        f"{text}\n\n"
                        f"─────────────────\n"
                        f"💬 Чтобы ответить — просто напишите в этот чат."
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=client_id,
                            text=outgoing,
                            parse_mode='HTML'
                        )
                        await msg.reply_text(
                            f"✅ Доставлено клиенту <code>{client_id}</code>",
                            parse_mode='HTML')
                        logger.info(f"🔄 Relay: менеджер {uid} → клиент {client_id}")
                    except Exception as e:
                        await msg.reply_text(f"❌ Не доставлено: {e}")
                else:
                    await msg.reply_text(
                        "ℹ️ Пересылай объявления → публикую\n"
                        "/stats | /leads | /export id_XXXX | /msg USER_ID текст")
        else:
            # ── RELAY: клиент отвечает в активном диалоге ──
            if uid in RELAY_SESSIONS:
                manager_id = RELAY_SESSIONS[uid]
                try:
                    # forward_message: заголовок "Переслано от [Имя]" — кликабелен!
                    await context.bot.forward_message(
                        chat_id=manager_id,
                        from_chat_id=msg.chat_id,
                        message_id=msg.message_id
                    )
                    logger.info(f"🔄 Relay forward: клиент {uid} → менеджер {manager_id}")
                except Exception as e:
                    logger.error(f"relay error: {e}")
                return

            st = get_state(uid)
            if st.get('step'):
                await msg.reply_text("ℹ️ Используйте кнопки выше")
                return

            # Уведомляем менеджера о новом обращении —
            # forward даёт кликабельный заголовок "Переслано от [Имя]"
            for rid in [OWNER_ID, MANAGER_USER_ID]:
                if rid and rid != uid:
                    try:
                        await context.bot.send_message(
                            chat_id=rid,
                            text=(
                                f"👋 <b>Новое обращение в бот</b>\n"
                                f"Нажмите на имя в пересланном сообщении ниже "
                                f"чтобы открыть профиль:"
                            ),
                            parse_mode='HTML'
                        )
                        await context.bot.forward_message(
                            chat_id=rid,
                            from_chat_id=msg.chat_id,
                            message_id=msg.message_id
                        )
                    except Exception as e:
                        logger.error(f"notify new user: {e}")

            await cmd_start(update, context)

    except Exception as e:
        logger.error(f"handle_msg: {e}")
        import traceback; logger.error(traceback.format_exc())

# ════════════════════════════════════════════════════════════
# HEALTH SERVER ДЛЯ BOTHOST.RU
# ════════════════════════════════════════════════════════════

def health_server():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","bot":"ProAuto"}')
        def do_HEAD(self):
            self.send_response(200); self.end_headers()
        def log_message(self,*a): pass
    try:
        s = HTTPServer(('0.0.0.0',PORT),H)
        print(f"🌐 Health server PORT={PORT}", flush=True)
        s.serve_forever()
    except Exception as e:
        print(f"health error: {e}", flush=True)

# ════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ПЕРЕХВАТ ОШИБОК + АВТОБЭКАП
# ════════════════════════════════════════════════════════════

async def error_handler(update, context):
    """
    Ловит ЛЮБУЮ необработанную ошибку в боте, чтобы он не падал молча.
    Пишет полный traceback в лог и шлёт краткое уведомление владельцу.
    """
    import traceback
    err = context.error
    tb = ''.join(traceback.format_exception(type(err), err, err.__traceback__))
    logger.error(f"‼️ Необработанная ошибка: {err}\n{tb}")
    if OWNER_ID:
        try:
            short = tb[-1500:] if len(tb) > 1500 else tb
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=(f"‼️ <b>Ошибка в боте</b>\n\n"
                      f"<code>{err}</code>\n\n"
                      f"Бот продолжает работать. Подробности в логах.\n"
                      f"<pre>{short[-800:]}</pre>"),
                parse_mode='HTML')
        except Exception as e:
            logger.error(f"error_handler notify: {e}")

async def _daily_backup(context):
    """
    Раз в сутки отправляет файл базы SQLite владельцу в личку —
    страховка от сброса диска на хостинге (данные не пропадут).
    """
    if not OWNER_ID:
        return
    try:
        if os.path.exists(SQLITE_DB):
            with open(SQLITE_DB, 'rb') as f:
                await context.bot.send_document(
                    chat_id=OWNER_ID,
                    document=f,
                    filename=f"proauto_backup_{datetime.now():%Y%m%d}.db",
                    caption=f"🗄 Автобэкап базы ProAuto\n{datetime.now():%d.%m.%Y %H:%M}")
            logger.info("🗄 Автобэкап отправлен владельцу")
    except Exception as e:
        logger.error(f"backup: {e}")

async def _check_stale_leads(context):
    """
    Каждые 15 минут ищет заявки со статусом 'new' старше 1 часа, по которым
    ещё не отправляли напоминание, и напоминает менеджеру/владельцу.
    Скорость ответа = главный рычаг конверсии, поэтому не даём заявке зависнуть.
    """
    try:
        db = _load(LEADS_DB, {'counter':0,'leads':{}})
        now = datetime.now()
        for lid, l in db['leads'].items():
            if l.get('status', 'new') != 'new':
                continue
            if l.get('notified'):
                continue
            try:
                created = datetime.fromisoformat(l.get('created_at',''))
            except Exception:
                continue
            if now - created < timedelta(hours=1):
                continue
            # заявка висит больше часа и без ответа — напоминаем
            car = l.get('car_model') or f"{l.get('brand','')} {l.get('model','')}".strip() or 'заявка'
            uname = f"@{l['username']}" if l.get('username') else f"id {l.get('user_id')}"
            mins = int((now - created).total_seconds() // 60)
            txt = (f"⏰ <b>Зависшая заявка {lid}</b>\n\n"
                   f"🚗 {car}\n"
                   f"👤 {uname}\n"
                   f"🕐 Без ответа уже {mins} мин\n\n"
                   f"Клиенту обещан ответ в течение часа — стоит связаться.")
            for rid in [OWNER_ID, MANAGER_USER_ID]:
                if rid:
                    try:
                        await context.bot.send_message(chat_id=rid, text=txt, parse_mode='HTML')
                    except Exception as e:
                        logger.error(f"stale notify {rid}: {e}")
            update_lead(lid, notified=True)
            logger.info(f"⏰ Напоминание о зависшей заявке {lid}")
    except Exception as e:
        logger.error(f"_check_stale_leads: {e}")

async def _check_expired_pubs(context):
    """
    Раз в сутки ищет публикации старше expires_at (30 дней) со статусом
    'active' и присылает владельцу сводку "актуальны ли ещё эти авто?".
    Сам НЕ удаляет из канала (не может знать, продано ли) — помечает
    'expired' и уведомляет, чтобы владелец решил вручную.
    """
    try:
        db = _load(PUBS_DB, {'counter':0,'publications':{}})
        now = datetime.now()
        expired = []
        for pid, p in db['publications'].items():
            if p.get('status') != 'active':
                continue
            try:
                exp = datetime.fromisoformat(p.get('expires_at',''))
            except Exception:
                continue
            if now < exp:
                continue
            expired.append((pid, p))
        if not expired:
            return
        # помечаем и собираем сводку
        lines = []
        for pid, p in expired[:30]:
            update_pub_status(pid, 'expired')
            car = p.get('car_model') or p.get('car_brand') or '?'
            link = p.get('telegram_link') or ''
            lines.append(f"• {pid} — {car} {link}".strip())
        if OWNER_ID:
            txt = ("🗓 <b>Объявления старше 30 дней</b>\n"
                   "Проверь актуальность — возможно, уже проданы:\n\n"
                   + "\n".join(lines))
            if len(txt) > 4000: txt = txt[:3950] + "..."
            try:
                await context.bot.send_message(chat_id=OWNER_ID, text=txt,
                                               parse_mode='HTML',
                                               disable_web_page_preview=True)
            except Exception as e:
                logger.error(f"expired notify: {e}")
        logger.info(f"🗓 Помечено {len(expired)} устаревших объявлений")
    except Exception as e:
        logger.error(f"_check_expired_pubs: {e}")

async def cmd_backup(update, context):
    """Ручной бэкап по команде /backup — присылает базу прямо сейчас."""
    if not has_rights(update.effective_user.id):
        return
    await _daily_backup(context)
    await update.message.reply_text("🗄 Бэкап отправлен.")

async def cmd_ref(update, context):
    """
    /ref — выдаёт пользователю его персональную реферальную ссылку.
    Доступна всем (и клиентам, и менеджеру), чтобы каждый мог приглашать.
    """
    uid = update.effective_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    await update.message.reply_text(
        f"🎁 <b>Ваша реферальная ссылка</b>\n\n"
        f"Поделитесь ей с друзьями:\n"
        f"<code>{link}</code>\n\n"
        f"Когда приглашённый вами человек оформит покупку через ProAuto — "
        f"вы получите бонус. Чем больше друзей — тем больше бонусов! 🚗",
        parse_mode='HTML', disable_web_page_preview=True)

async def on_start(app):
    print("✅ Bot polling started!", flush=True)
    brands_count = len(CAR_DATABASE)
    models_count = sum(len(v) for v in CAR_DATABASE.values())
    logger.info(f"🚀 PROAUTO BOT — @{BOT_USERNAME}")
    logger.info(f"OWNER={OWNER_ID} | GROUP={TARGET_CHANNEL}")
    logger.info(f"DATA_DIR={DATA_DIR}")
    logger.info(f"📚 БД: {brands_count} марок, {models_count} моделей")
    logger.info(
        "💰 Наценки: <5млн +40k | 5-7 +80k | 7-10 +100k | "
        "10-15 +180k | 15-20 +250k | 20-25 +350k | 25-30 +500k | 30+ +1млн | EUR/USD +1000")
    # Планируем ежедневный автобэкап (если JobQueue доступна).
    # JobQueue требует установки extras: pip install "python-telegram-bot[job-queue]".
    # Если недоступна — не критично, есть ручная команда /backup.
    try:
        if app.job_queue:
            app.job_queue.run_repeating(_daily_backup, interval=timedelta(days=1),
                                        first=timedelta(minutes=5))
            logger.info("🗄 Автобэкап запланирован (раз в сутки)")
            # Напоминание о зависших заявках — каждые 15 минут
            app.job_queue.run_repeating(_check_stale_leads, interval=timedelta(minutes=15),
                                        first=timedelta(minutes=2))
            logger.info("⏰ Контроль зависших заявок запланирован (каждые 15 мин)")
            # Контроль устаревших объявлений — раз в сутки
            app.job_queue.run_repeating(_check_expired_pubs, interval=timedelta(days=1),
                                        first=timedelta(minutes=10))
            logger.info("🗓 Контроль устаревших объявлений запланирован (раз в сутки)")
        else:
            logger.warning("⚠️ JobQueue недоступна — автобэкап, напоминания и контроль "
                           "срока работают только вручную. Установи "
                           "python-telegram-bot[job-queue].")
    except Exception as e:
        logger.error(f"schedule jobs: {e}")

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════

def main():
    print("--- main() ---", flush=True)

    # Инициализируем SQLite и переносим данные из старых JSON (если есть).
    # Делается ДО запуска бота, чтобы данные были готовы к первому запросу.
    try:
        _db_init()
        _migrate_json_to_sqlite()
        print("--- SQLite готов ---", flush=True)
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}", flush=True)
        import traceback; traceback.print_exc()

    threading.Thread(target=health_server, daemon=True).start()
    print("--- health thread OK ---", flush=True)

    print(f"--- token: {BOT_TOKEN[:10]}... ---", flush=True)

    try:
        app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    except Exception as e:
        print(f"❌ Application error: {e}", flush=True)
        import traceback; traceback.print_exc()
        import time; time.sleep(99999)

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CommandHandler("leads",   cmd_leads))
    app.add_handler(CommandHandler("export",  cmd_export))
    app.add_handler(CommandHandler("msg",     cmd_msg))
    app.add_handler(CommandHandler("endchat", cmd_endchat))
    app.add_handler(CommandHandler("chats",   cmd_chats))
    app.add_handler(CommandHandler("backup",  cmd_backup))
    app.add_handler(CommandHandler("ref",     cmd_ref))
    app.add_handler(CallbackQueryHandler(button_cb))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO,
        handle_msg))

    # Глобальный перехватчик ошибок — бот не падает молча
    app.add_error_handler(error_handler)

    print("--- run_polling() ---", flush=True)
    try:
        app.run_polling(
            allowed_updates=['message','callback_query'],
            drop_pending_updates=True,
            poll_interval=1.0,
            timeout=30)
    except Exception as e:
        print(f"❌ Polling error: {e}", flush=True)
        import traceback; traceback.print_exc()
        import time; time.sleep(99999)

if __name__ == '__main__':
    main()
