"""
PROAUTO API SERVER
==================
REST API для интеграции бота с сайтом и внешними сервисами.

Запуск:
    pip install fastapi uvicorn python-dotenv
    python api_server.py

Эндпоинты:
    GET  /api/listings          - все активные объявления
    GET  /api/listings/{id}     - конкретное объявление
    GET  /api/listings/search   - поиск по параметрам
    POST /api/leads             - заявка с сайта → уведомление в бот
    GET  /api/stats             - статистика для дашборда
    GET  /api/health            - статус сервера

Используется для:
    - Сайт ProAuto (каталог авто)
    - CRM система
    - AI-агент SEO мониторинга
    - Аналитика
"""

import json
import os
import asyncio
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════

PUBLICATIONS_DB = os.getenv('DATA_DIR', '/app/data') + '/publications.json'
LEADS_DB = os.getenv('DATA_DIR', '/app/data') + '/leads.json'
BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
MANAGER_USER_ID = int(os.getenv('MANAGER_USER_ID', '0'))

# API ключ для защиты (установить в .env)
API_KEY = os.getenv('API_KEY', 'proauto_api_2024')

# ════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════

def load_db(filepath, default=None):
    """Загружает JSON файл"""
    if default is None:
        default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default
    return default


def get_active_listings():
    """Возвращает все активные объявления"""
    db = load_db(PUBLICATIONS_DB, {'publications': {}})
    now = datetime.now()

    active = []
    for pub_id, pub in db.get('publications', {}).items():
        if pub.get('archived'):
            continue
        if pub.get('status') == 'sold':
            continue

        # Формируем чистый объект для API
        listing = {
            'id': pub_id,
            'car_brand': pub.get('car_brand'),
            'car_model': pub.get('car_model'),
            'price': pub.get('price'),
            'currency': pub.get('currency', '₽'),
            'year': pub.get('year'),
            'mileage': pub.get('mileage'),
            'city': pub.get('city'),
            'telegram_link': pub.get('telegram_link'),
            'source_link': pub.get('source_link'),
            'published_at': pub.get('published_at'),
            'status': pub.get('status', 'active'),
        }
        active.append(listing)

    # Сортируем по дате публикации (новые первые)
    active.sort(
        key=lambda x: x.get('published_at') or '',
        reverse=True
    )
    return active


async def notify_bot_about_lead(lead_data):
    """Отправляет уведомление в бот о новой заявке с сайта"""
    try:
        import httpx
        
        lead_id = lead_data.get('lead_id', 'WEB')
        
        text = (
            f"🌐 <b>ЗАЯВКА С САЙТА {lead_id}</b>\n\n"
            f"👤 Имя: {lead_data.get('name', '?')}\n"
            f"📱 Телефон: {lead_data.get('phone', 'не указан')}\n"
            f"📧 Email: {lead_data.get('email', 'не указан')}\n\n"
            f"📋 <b>Запрос:</b>\n"
        )
        
        if lead_data.get('car_brand'):
            text += f"• Марка: {lead_data['car_brand']}\n"
        if lead_data.get('car_model'):
            text += f"• Модель: {lead_data['car_model']}\n"
        if lead_data.get('year'):
            text += f"• Год: {lead_data['year']}\n"
        if lead_data.get('city'):
            text += f"• Город: {lead_data['city']}\n"
        if lead_data.get('message'):
            text += f"\n💬 Сообщение: {lead_data['message'][:200]}\n"
        
        text += f"\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        # Отправляем владельцу и менеджеру
        for chat_id in [OWNER_ID, MANAGER_USER_ID]:
            if chat_id != 0:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': 'HTML'
                }
                async with httpx.AsyncClient() as client:
                    await client.post(url, json=payload)
                    
    except Exception as e:
        print(f"Ошибка уведомления: {e}")


# ════════════════════════════════════════════════════════
# ЗАПУСК (через FastAPI или простой HTTP)
# ════════════════════════════════════════════════════════

try:
    from fastapi import FastAPI, HTTPException, Header, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn

    app = FastAPI(
        title="ProAuto API",
        description="API для каталога автомобилей ProAuto",
        version="1.0.0"
    )

    # CORS для фронтенда
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # В продакшене указать домен сайта
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Модели данных ─────────────────────────────────────────
    class LeadCreate(BaseModel):
        name: str
        phone: Optional[str] = None
        email: Optional[str] = None
        car_brand: Optional[str] = None
        car_model: Optional[str] = None
        year: Optional[int] = None
        city: Optional[str] = None
        message: Optional[str] = None
        listing_id: Optional[str] = None  # ID объявления если пришёл из карточки

    # ── Эндпоинты ──────────────────────────────────────────────

    @app.get("/api/health")
    def health():
        """Статус сервера"""
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    @app.get("/api/listings")
    def get_listings(
        brand: Optional[str] = Query(None, description="Фильтр по марке"),
        min_price: Optional[int] = Query(None),
        max_price: Optional[int] = Query(None),
        year: Optional[int] = Query(None),
        city: Optional[str] = Query(None),
        limit: int = Query(50, le=200),
        offset: int = Query(0),
    ):
        """
        Получить список активных объявлений.
        Поддерживает фильтрацию и пагинацию.
        """
        listings = get_active_listings()

        # Фильтрация
        if brand:
            listings = [l for l in listings
                       if l.get('car_brand') and
                       brand.lower() in l['car_brand'].lower()]
        if min_price:
            listings = [l for l in listings
                       if l.get('price') and l['price'] >= min_price]
        if max_price:
            listings = [l for l in listings
                       if l.get('price') and l['price'] <= max_price]
        if year:
            listings = [l for l in listings
                       if l.get('year') == year]
        if city:
            listings = [l for l in listings
                       if l.get('city') and
                       city.lower() in l['city'].lower()]

        total = len(listings)
        paginated = listings[offset:offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "listings": paginated
        }

    @app.get("/api/listings/{pub_id}")
    def get_listing(pub_id: str):
        """Получить конкретное объявление по ID"""
        db = load_db(PUBLICATIONS_DB, {'publications': {}})
        pub = db.get('publications', {}).get(pub_id)

        if not pub:
            raise HTTPException(status_code=404, detail=f"Объявление {pub_id} не найдено")

        return {
            'id': pub_id,
            'car_brand': pub.get('car_brand'),
            'car_model': pub.get('car_model'),
            'price': pub.get('price'),
            'currency': pub.get('currency', '₽'),
            'year': pub.get('year'),
            'mileage': pub.get('mileage'),
            'city': pub.get('city'),
            'telegram_link': pub.get('telegram_link'),
            'published_at': pub.get('published_at'),
            'status': pub.get('status', 'active'),
        }

    @app.post("/api/leads")
    async def create_lead(lead: LeadCreate):
        """
        Создать заявку с сайта.
        Автоматически уведомляет менеджера в Telegram.
        """
        # Сохраняем в leads.json
        leads_db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})
        leads_db['counter'] = leads_db.get('counter', 0) + 1
        lead_id = f"web_{leads_db['counter']:05d}"

        lead_data = {
            **lead.dict(),
            'lead_id': lead_id,
            'source': 'website',
            'created_at': datetime.now().isoformat(),
        }

        leads_db['leads'][lead_id] = lead_data

        with open(LEADS_DB, 'w', encoding='utf-8') as f:
            json.dump(leads_db, f, ensure_ascii=False, indent=2)

        # Уведомляем в Telegram
        await notify_bot_about_lead(lead_data)

        return {
            "success": True,
            "lead_id": lead_id,
            "message": "Заявка принята. Менеджер свяжется с Вами в течение часа."
        }

    @app.get("/api/stats")
    def get_stats():
        """Статистика для дашборда"""
        pubs_db = load_db(PUBLICATIONS_DB, {'counter': 0, 'publications': {}})
        leads_db = load_db(LEADS_DB, {'counter': 0, 'leads': {}})

        listings = get_active_listings()

        # Подсчёт по брендам
        brands = {}
        for l in listings:
            b = l.get('car_brand', 'Другое')
            brands[b] = brands.get(b, 0) + 1

        # Подсчёт заявок по источникам
        sources = {}
        for lead in leads_db.get('leads', {}).values():
            src = lead.get('source', 'bot')
            sources[src] = sources.get(src, 0) + 1

        return {
            "total_listings": pubs_db.get('counter', 0),
            "active_listings": len(listings),
            "total_leads": leads_db.get('counter', 0),
            "brands_breakdown": dict(sorted(brands.items(), key=lambda x: -x[1])[:10]),
            "leads_by_source": sources,
            "last_updated": datetime.now().isoformat(),
        }

    # ── Запуск сервера ─────────────────────────────────────────
    if __name__ == "__main__":
        port = int(os.getenv('API_PORT', 8000))
        print(f"🚀 ProAuto API запущен: http://0.0.0.0:{port}")
        print(f"📚 Документация: http://0.0.0.0:{port}/docs")
        uvicorn.run(app, host="0.0.0.0", port=port)

except ImportError:
    # Fallback: простой HTTP сервер если нет FastAPI
    print("⚠️ FastAPI не установлен. Запусти: pip install fastapi uvicorn")
    print("Запускаем простой сервер...")

    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json as jsonlib

    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/api/listings':
                data = get_active_listings()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(jsonlib.dumps(data, ensure_ascii=False).encode())
            elif self.path == '/api/health':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Тихий режим

    if __name__ == "__main__":
        port = int(os.getenv('API_PORT', 8000))
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        print(f"🚀 Простой API запущен: http://0.0.0.0:{port}/api/listings")
        server.serve_forever()
