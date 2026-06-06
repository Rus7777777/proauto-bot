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
    'BMW': {'1 серии':'2004-2026','2 серии':'2014-2026','3 серии':'1975-2026',
            '4 серии':'2013-2026','5 серии':'1972-2026','6 серии':'1976-2024',
            '7 серии':'1977-2026','8 серии':'1989-2026','X1':'2009-2026',
            'X2':'2017-2026','X3':'2003-2026','X4':'2014-2026','X5':'1999-2026',
            'X6':'2007-2026','X7':'2019-2026','M3':'1986-2026','M4':'2014-2026',
            'M5':'1985-2026','i4':'2021-2026','i7':'2022-2026','iX':'2021-2026'},
    'Mercedes-Benz': {'A-Class':'2013-2026','C-Class':'2000-2026','E-Class':'2002-2026',
                      'S-Class':'2006-2026','G-Class':'2000-2026','GLC':'2015-2026',
                      'GLE':'2015-2026','GLS':'2013-2026','EQS':'2021-2026'},
    'Audi': {'A3':'2003-2026','A4':'2001-2026','A5':'2007-2026','A6':'1998-2026',
             'A8':'1999-2026','Q3':'2011-2026','Q5':'2008-2026','Q7':'2006-2026',
             'Q8':'2018-2026','RS6':'2002-2026','TT':'1999-2023'},
    'Toyota': {'Camry':'1982-2026','Corolla':'1966-2026','RAV4':'1994-2026',
               'Land Cruiser':'1951-2026','Highlander':'2001-2026','Supra':'1978-2026'},
    'Lexus': {'ES':'1989-2026','GX':'2003-2026','IS':'1999-2026','LS':'1989-2026',
              'LX':'1996-2026','NX':'2014-2026','RX':'1997-2026'},
    'Honda': {'Accord':'1976-2026','Civic':'1972-2026','CR-V':'1995-2026',
              'Pilot':'2002-2026'},
    'Nissan': {'Altima':'1992-2026','GT-R':'2007-2026','Murano':'2003-2026',
               'Patrol':'1980-2026','Qashqai':'2006-2026','X-Trail':'2001-2026'},
    'Mazda': {'CX-5':'2012-2026','CX-9':'2007-2026','Mazda3':'2003-2026',
              'Mazda6':'2002-2026','MX-5':'1989-2026'},
    'Kia': {'Carnival':'1998-2026','EV6':'2021-2026','K5':'2010-2026',
            'Sorento':'2002-2026','Sportage':'1993-2026','Telluride':'2020-2026'},
    'Hyundai': {'Elantra':'1990-2026','IONIQ 5':'2021-2026','Palisade':'2019-2026',
                'Santa Fe':'2001-2026','Tucson':'2004-2026'},
    'Genesis': {'G80':'2017-2026','GV80':'2021-2026','GV70':'2021-2026'},
    'Volkswagen': {'Golf':'1974-2026','Jetta':'1979-2026','Passat':'1973-2026',
                   'T-Cross':'2019-2026','Tiguan':'2007-2026','Touareg':'2002-2026'},
    'Porsche': {'911':'1964-2026','Cayenne':'2002-2026','Macan':'2014-2026',
                'Panamera':'2009-2026','Taycan':'2020-2026'},
    'Land Rover': {'Defender':'1983-2026','Discovery':'1989-2026',
                   'Range Rover':'1970-2026','Range Rover Sport':'2005-2026'},
    'Volvo': {'S60':'2000-2026','S90':'2016-2026','XC40':'2017-2026',
              'XC60':'2008-2026','XC90':'2003-2026'},
    'Tesla': {'Model 3':'2017-2026','Model S':'2012-2026',
              'Model X':'2015-2026','Model Y':'2020-2026'},
    'BYD': {'Han':'2020-2026','Seal':'2022-2026','Tang':'2018-2026'},
    'Geely': {'Coolray':'2019-2026','Monjaro':'2022-2026','Tugella':'2020-2026'},
    'Haval': {'H6':'2011-2026','H9':'2015-2026','Jolion':'2021-2026'},
    'Chery': {'Tiggo 7 Pro':'2020-2026','Tiggo 8':'2018-2026','Omoda 5':'2022-2026'},
    'Rolls-Royce': {'Ghost':'2010-2026','Cullinan':'2019-2026','Phantom':'2003-2026'},
    'Bentley': {'Bentayga':'2016-2026','Continental GT':'2003-2026','Flying Spur':'2005-2026'},
    'Ferrari': {'Roma':'2020-2026','Purosangue':'2023-2026','SF90':'2020-2026'},
    'Lamborghini': {'Urus':'2018-2026','Huracán':'2014-2026'},
    'Lixiang': {'L7':'2023-2026','L8':'2022-2026','L9':'2022-2026'},
    'NIO': {'ES6':'2018-2026','ET5':'2022-2026','ET7':'2022-2026'},
    'Zeekr': {'001':'2021-2026','007':'2023-2026','X':'2023-2026'},
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
            brand = BRAND_GROUPS[list(BRAND_GROUPS.keys())[gi]][bi]
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
            model = get_models(brand)[idx]
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
        drop_pending_updates=False,
        poll_interval=1.0,
        timeout=30)

if __name__ == '__main__':
    main()
