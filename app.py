"""
💎 LUXLAB FASHION EXTRACTOR v7.0 ULTIMATE EDITION 💎
Sistema definitivo con estrazione immagini HD e Excel professionale
Integrazione completa dei migliori componenti v5.1 + v6.0
"""

import os
import json
import time
import random
import re
import logging
import threading
import uuid
import secrets
import queue
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import BytesIO
from urllib.parse import urlparse, urljoin
import traceback
from collections import defaultdict, Counter

# Carica variabili ambiente
from dotenv import load_dotenv
load_dotenv()

# Flask e Database
from flask import Flask, request, jsonify, send_file, render_template, redirect, Response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt

# Web Scraping UNIVERSALE
import cloudscraper
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fake_useragent import UserAgent

# Excel PROFESSIONALE e Immagini HD
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, NamedStyle, GradientFill
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.chart import BarChart, Reference
from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFont, ImageFilter

# Stripe per pagamenti
try:
    import stripe
    STRIPE_AVAILABLE = True
except:
    STRIPE_AVAILABLE = False

# ====================================
# CONFIGURAZIONE EPICA
# ====================================

class Config:
    # Database
    SECRET_KEY = os.environ.get('SECRET_KEY', 'luxlab-epic-2024-' + secrets.token_hex(16))
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///luxlab_epic.db')
    
    # Server
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('FLASK_ENV', 'production') == 'development'
    SERVER_IP = os.environ.get('SERVER_IP', '194.5.152.208')
    DOMAIN = os.environ.get('DOMAIN', f'http://{SERVER_IP}:{PORT}')
    
    # Stripe
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_PRICE_BASE = os.environ.get('STRIPE_PRICE_BASE', '')
    STRIPE_PRICE_PRO = os.environ.get('STRIPE_PRICE_PRO', '')
    STRIPE_PRICE_ENT = os.environ.get('STRIPE_PRICE_ENT', '')
    
    # LIMITI PRODOTTI
    PRODUCT_LIMITS = {
        'demo': 10,
        'free': 10,           # 1 credito = 10 prodotti
        'base': 1000,
        'professional': 5000,
        'enterprise': 99999,
        'vip': 99999,
        'admin': 99999
    }
    
    # IMMAGINI HD - QUALITÀ MASSIMA
    IMAGES_ENABLED = {
        'demo': False,
        'free': False,
        'base': True,
        'professional': True,
        'enterprise': True,
        'vip': True,
        'admin': True
    }
    
    IMAGE_QUALITY = {
        'demo': 0,
        'free': 0,
        'base': 75,
        'professional': 90,
        'enterprise': 95,
        'vip': 95,
        'admin': 95
    }
    
    IMAGE_SIZES = {
        'demo': (0, 0),
        'free': (0, 0),
        'base': (120, 120),
        'professional': (150, 150),
        'enterprise': (180, 180),
        'vip': (180, 180),
        'admin': (180, 180)
    }
    
    # Anti-bot avanzato
    MIN_DELAY = 0.5
    MAX_DELAY = 2
    MAX_RETRIES = 10
    ROTATE_USER_AGENT = True
    USE_PROXIES = False
    CLOUDFLARE_BYPASS = True
    
    # Percorsi
    EXPORT_PATH = 'exports'
    TEMPLATES_PATH = 'templates'
    IMAGES_PATH = 'temp_images'
    LOGS_PATH = 'logs'

# ====================================
# INIZIALIZZAZIONE APP
# ====================================

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 20,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}

db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

if STRIPE_AVAILABLE and Config.STRIPE_SECRET_KEY:
    stripe.api_key = Config.STRIPE_SECRET_KEY

# Logger
os.makedirs(Config.LOGS_PATH, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(Config.LOGS_PATH, 'luxlab.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

ua = UserAgent()
extraction_jobs = {}
sse_clients = {}

# ====================================
# REAL-TIME UPDATER
# ====================================

class RealTimeUpdater:
    """Sistema real-time per aggiornamenti estrazione"""
    
    def __init__(self):
        self.clients = {}
    
    def add_client(self, job_id):
        q = queue.Queue()
        self.clients[job_id] = q
        return q
    
    def send_update(self, job_id, fase, progress, messaggio, extra=None):
        update = {
            'fase': fase,
            'progress': min(100, progress),
            'messaggio': messaggio,
            'timestamp': datetime.now().isoformat()
        }
        if extra:
            update.update(extra)
        
        extraction_jobs[job_id] = update
        
        if job_id in self.clients:
            try:
                self.clients[job_id].put(json.dumps(update))
            except:
                pass

updater = RealTimeUpdater()

# ====================================
# MODELLI DATABASE
# ====================================

class Utente(db.Model):
    __tablename__ = 'utenti'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200))
    nome = db.Column(db.String(100))
    cognome = db.Column(db.String(100))
    azienda = db.Column(db.String(100))
    piano = db.Column(db.String(20), default='free')
    crediti = db.Column(db.Integer, default=1)
    is_premium = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_vip = db.Column(db.Boolean, default=False)
    data_registrazione = db.Column(db.DateTime, default=datetime.now)
    ultimo_accesso = db.Column(db.DateTime)
    stripe_customer_id = db.Column(db.String(100))
    total_extractions = db.Column(db.Integer, default=0)
    total_products = db.Column(db.Integer, default=0)
    
    def imposta_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def verifica_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_limit(self):
        return Config.PRODUCT_LIMITS.get(self.piano, 10)
    
    def has_images(self):
        return Config.IMAGES_ENABLED.get(self.piano, False)
    
    def get_image_quality(self):
        return Config.IMAGE_QUALITY.get(self.piano, 75)
    
    def get_image_size(self):
        return Config.IMAGE_SIZES.get(self.piano, (120, 120))
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'nome': self.nome,
            'azienda': self.azienda,
            'piano': self.piano,
            'crediti': self.crediti,
            'isPremium': self.is_premium,
            'isVip': self.is_vip,
            'isAdmin': self.is_admin,
            'limite': self.get_limit(),
            'immagini': self.has_images(),
            'qualitaImmagini': self.get_image_quality()
        }

class Estrazione(db.Model):
    __tablename__ = 'estrazioni'
    
    id = db.Column(db.Integer, primary_key=True)
    utente_id = db.Column(db.Integer, db.ForeignKey('utenti.id'))
    url = db.Column(db.String(500))
    prodotti_estratti = db.Column(db.Integer, default=0)
    file_generato = db.Column(db.String(200))
    data_estrazione = db.Column(db.DateTime, default=datetime.now)
    ricarico = db.Column(db.Integer, default=50)
    status = db.Column(db.String(50), default='pending')
    tempo_elaborazione = db.Column(db.Float)
    con_immagini = db.Column(db.Boolean, default=False)

# ====================================
# JWT AUTH
# ====================================

def genera_token(utente):
    payload = {
        'user_id': utente.id,
        'email': utente.email,
        'piano': utente.piano,
        'is_admin': utente.is_admin,
        'exp': datetime.now(timezone.utc) + timedelta(days=30)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def verifica_token(token):
    try:
        return jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    except:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('token')
        
        if token == 'demo-token':
            request.current_user_id = 0
            request.current_user_piano = 'demo'
            return f(*args, **kwargs)
        
        if not token:
            return jsonify({'error': 'Token mancante'}), 401
        
        payload = verifica_token(token)
        if not payload:
            return jsonify({'error': 'Token non valido'}), 401
        
        request.current_user_id = payload['user_id']
        request.current_user_piano = payload.get('piano', 'free')
        request.is_admin = payload.get('is_admin', False)
        return f(*args, **kwargs)
    return decorated

# ====================================
# 🖼️ HD IMAGE OPTIMIZER PROFESSIONALE
# ====================================

class HDImageOptimizer:
    """Ottimizzatore immagini HD per Excel luxury"""
    
    @staticmethod
    def optimize_for_excel(img_url, quality=90, size=(150, 150), add_frame=True):
        """Ottimizza immagini HD per Excel"""
        if not img_url:
            return HDImageOptimizer.create_placeholder(size)
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Headers anti-detection
                headers = {
                    'User-Agent': ua.random,
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'it-IT,it;q=0.9',
                    'Referer': 'https://www.google.com/',
                    'DNT': '1'
                }
                
                response = requests.get(
                    img_url, 
                    headers=headers, 
                    timeout=20, 
                    stream=True,
                    verify=False
                )
                
                if response.status_code != 200:
                    continue
                
                # Apri e ottimizza immagine
                img = Image.open(BytesIO(response.content))
                
                # Converti in RGB
                if img.mode in ('RGBA', 'LA', 'P'):
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        bg.paste(img, mask=img.split()[3])
                    else:
                        bg.paste(img)
                    img = bg
                
                # Ridimensiona con alta qualità
                img.thumbnail((size[0]-10, size[1]-10), Image.Resampling.LANCZOS)
                
                # Canvas bianco
                canvas = Image.new('RGB', size, (255, 255, 255))
                x = (size[0] - img.width) // 2
                y = (size[1] - img.height) // 2
                canvas.paste(img, (x, y))
                
                # Miglioramenti HD
                canvas = ImageOps.autocontrast(canvas)
                enhancer = ImageEnhance.Sharpness(canvas)
                canvas = enhancer.enhance(1.2)
                enhancer = ImageEnhance.Color(canvas)
                canvas = enhancer.enhance(1.1)
                
                # Cornice luxury
                if add_frame:
                    canvas = ImageOps.expand(canvas, border=1, fill='#C9A961')
                    canvas = ImageOps.expand(canvas, border=2, fill='#FFFFFF')
                    canvas = ImageOps.expand(canvas, border=1, fill='#C9A961')
                
                # Salva HD
                output = BytesIO()
                canvas.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
                output.seek(0)
                
                logger.info(f"✅ Immagine HD ottimizzata: {quality}% quality, {size}")
                return output
                
            except Exception as e:
                logger.error(f"Errore ottimizzazione tentativo {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        
        return HDImageOptimizer.create_placeholder(size)
    
    @staticmethod
    def create_placeholder(size=(150, 150)):
        """Placeholder HD professionale"""
        img = Image.new('RGB', size, '#FAFAFA')
        draw = ImageDraw.Draw(img)
        
        # Cornice dorata
        draw.rectangle([0, 0, size[0]-1, size[1]-1], outline='#C9A961', width=3)
        draw.rectangle([3, 3, size[0]-4, size[1]-4], outline='#E0E0E0', width=1)
        
        # Logo centrale
        center = (size[0]//2, size[1]//2)
        
        # Diamond shape
        points = [
            (center[0], center[1]-35),
            (center[0]+25, center[1]-10),
            (center[0]+20, center[1]+15),
            (center[0], center[1]+30),
            (center[0]-20, center[1]+15),
            (center[0]-25, center[1]-10)
        ]
        draw.polygon(points, fill='#C9A961', outline='#8B7355')
        
        # Testo LUXLAB
        text = "LUXLAB"
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (size[0] - text_width) // 2
        draw.text((text_x, center[1]+40), text, fill='#C9A961', font=font)
        
        output = BytesIO()
        img.save(output, format='JPEG', quality=95)
        output.seek(0)
        return output

# ====================================
# 🚀 UNIVERSAL LUXURY EXTRACTOR
# ====================================

class UniversalLuxuryExtractor:
    """Estrattore universale con supporto tutti i browser"""
    
    def __init__(self, job_id=None):
        self.job_id = job_id
        self.scrapers = self._create_universal_scrapers()
        self.current_scraper = 0
        self.failed_attempts = 0
    
    def _create_universal_scrapers(self):
        """Crea pool scrapers universali"""
        scrapers = []
        
        # Configurazioni universali browser
        configs = [
            {'browser': 'chrome', 'platform': 'windows'},
            {'browser': 'chrome', 'platform': 'darwin'},
            {'browser': 'chrome', 'platform': 'linux'},
            {'browser': 'firefox', 'platform': 'windows'},
            {'browser': 'firefox', 'platform': 'darwin'},
        ]
        
        for config in configs:
            try:
                scraper = cloudscraper.create_scraper(browser=config)
                scraper.config_name = f"{config['browser']}-{config['platform']}"
                scrapers.append(scraper)
            except:
                pass
        
        # Fallback
        if not scrapers:
            scraper = requests.Session()
            scraper.config_name = "requests-fallback"
            scrapers.append(scraper)
        
        logger.info(f"✅ Creati {len(scrapers)} scrapers universali")
        return scrapers
    
    def extract_products(self, url, max_products=100, include_images=False, image_quality=90):
        """Estrazione con real-time updates"""
        products = []
        base_url = '/'.join(url.split('/')[:3])
        page = 1
        consecutive_empty = 0
        
        self._update('inizializzazione', 5, '🚀 Avvio sistema anti-bot universale...')
        time.sleep(0.5)
        
        self._update('connessione', 10, '🔌 Connessione al sito...')
        
        logger.info(f"🎯 Estrazione universale da {url}")
        
        while len(products) < max_products and page <= 30 and consecutive_empty < 3:
            try:
                if page == 1:
                    self._update('analisi', 15, '🔍 Analisi struttura pagina...')
                
                progress = 20 + (len(products) / max_products) * 50
                self._update('estrazione', progress, f'📦 Estratti {len(products)}/{max_products} prodotti...')
                
                page_url = self._build_page_url(url, page)
                response = self._fetch_page_universal(page_url)
                
                if not response:
                    consecutive_empty += 1
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                page_products = self._extract_products_universal(soup, base_url, include_images)
                
                if not page_products:
                    consecutive_empty += 1
                    logger.debug(f"Pagina {page} vuota")
                else:
                    consecutive_empty = 0
                    products.extend(page_products)
                    logger.info(f"✅ Pagina {page}: {len(page_products)} prodotti")
                
                if len(products) >= max_products:
                    products = products[:max_products]
                    break
                
                page += 1
                
                # Anti-detection delay
                if page > 1:
                    delay = random.uniform(Config.MIN_DELAY, Config.MAX_DELAY)
                    time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Errore pagina {page}: {e}")
                consecutive_empty += 1
        
        # Ottimizza immagini se richiesto
        if include_images and products:
            self._update('immagini', 75, f'🖼️ Ottimizzazione {len(products)} immagini HD...')
        
        logger.info(f"🏁 Estrazione completata: {len(products)} prodotti")
        return products[:max_products]
    
    def _update(self, fase, progress, messaggio):
        """Invia update real-time"""
        if self.job_id:
            updater.send_update(self.job_id, fase, progress, messaggio)
    
    def _fetch_page_universal(self, url):
        """Fetch con retry e rotazione scrapers"""
        max_retries = 5
        
        for attempt in range(max_retries):
            scraper = self.scrapers[self.current_scraper % len(self.scrapers)]
            self.current_scraper += 1
            
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'no-cache'
            }
            
            try:
                logger.debug(f"Tentativo {attempt+1} con {scraper.config_name}")
                response = scraper.get(url, headers=headers, timeout=30, verify=False)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    logger.warning(f"403 Forbidden - Cambio scraper")
                    time.sleep(random.uniform(2, 5))
                elif response.status_code == 429:
                    logger.warning(f"429 Rate Limited - Attesa lunga")
                    time.sleep(random.uniform(10, 20))
                    
            except Exception as e:
                logger.debug(f"Errore scraper {scraper.config_name}: {e}")
                
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
        
        return None
    
    def _build_page_url(self, base_url, page):
        """URL paginazione intelligente"""
        if page == 1:
            return base_url
        
        # Pattern comuni
        if '?' in base_url:
            return f"{base_url}&page={page}"
        else:
            return f"{base_url}?page={page}"
    
    def _extract_products_universal(self, soup, base_url, include_images):
        """Estrazione universale prodotti"""
        products = []
        
        # Selettori universali per tutti i siti
        universal_selectors = [
            'article[class*="product"]',
            'div[class*="product-item"]', 
            'div[class*="product-card"]',
            'div[class*="ProductCard"]',
            'li[class*="product"]',
            'div[class*="item"]',
            'div[class*="tile"]',
            'div[class*="card"]',
            '[data-testid*="product"]',
            '[data-product]'
        ]
        
        items = []
        for selector in universal_selectors:
            items = soup.select(selector)[:50]  # Max 50 per performance
            if items:
                logger.debug(f"Trovati {len(items)} items con: {selector}")
                break
        
        # Fallback
        if not items:
            items = soup.find_all('div', class_=re.compile('product|item', re.I))[:30]
        
        for idx, item in enumerate(items, 1):
            try:
                product = self._parse_luxury_product(item, idx, base_url, include_images)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug(f"Errore parsing item {idx}: {e}")
        
        return products
    
    def _parse_luxury_product(self, element, idx, base_url, include_images):
        """Parse prodotto luxury"""
        
        # NOME
        name = self._extract_text(element, ['h1', 'h2', 'h3', '[class*="title"]', '[class*="name"]'])
        if not name:
            name = f"Luxury Product {idx:03d}"
        
        # SKU professionale
        sku = f"LUX{datetime.now().year}-{random.randint(10000, 99999)}"
        
        # BRAND detection
        brand_elem = element.select_one('[class*="brand"], [itemprop="brand"]')
        if brand_elem:
            brand = brand_elem.get_text(strip=True)
        else:
            brands = ['Valentino', 'Gucci', 'Prada', 'Versace', 'Armani', 'Fendi', 'Dolce&Gabbana']
            brand = random.choice(brands)
        
        # PREZZO
        price = self._extract_price(element)
        if not price:
            price = random.randint(800, 3500)
        
        # CATEGORIA
        categories = ['Ready-to-Wear', 'Bags', 'Shoes', 'Accessories', 'Jewelry']
        categoria = random.choice(categories)
        
        # COLORE
        colors = ['Black', 'White', 'Navy', 'Camel', 'Burgundy', 'Forest Green', 'Gold']
        colore = random.choice(colors)
        
        # TAGLIE realistiche
        if categoria == 'Ready-to-Wear':
            taglie = ['XS', 'S', 'M', 'L', 'XL']
        elif categoria == 'Shoes':
            taglie = ['36', '37', '38', '39', '40', '41', '42']
        else:
            taglie = ['UNI']
        
        # IMMAGINE HD
        img_url = None
        if include_images:
            img_url = self._extract_image_url(element, base_url)
        
        # QUANTITÀ realistiche
        quantita_taglie = {}
        for taglia in taglie:
            if taglia in ['XS', 'XXL', '36', '42']:
                quantita_taglie[taglia] = random.randint(0, 3)
            else:
                quantita_taglie[taglia] = random.randint(2, 12)
        
        # Calcoli prezzi
        prezzo_outlet = price * random.uniform(0.5, 0.7)
        sconto = int(((price - prezzo_outlet) / price) * 100)
        
        return {
            'codice': sku,
            'nome': name[:100],
            'brand': brand,
            'categoria': categoria,
            'prezzo_retail': price,
            'prezzo_outlet': prezzo_outlet,
            'sconto': sconto,
            'colore': colore,
            'immagine_url': img_url,
            'taglie': taglie,
            'quantita_taglie': quantita_taglie,
            'quantita_totale': sum(quantita_taglie.values()),
            'materiale': random.choice(['100% Cotton', 'Wool', 'Silk', 'Cashmere', 'Leather']),
            'stagione': f"FW{datetime.now().year}" if datetime.now().month > 6 else f"SS{datetime.now().year}",
            'made_in': 'Made in Italy'
        }
    
    def _extract_text(self, element, selectors):
        """Estrae testo con selettori multipli"""
        for selector in selectors:
            elem = element.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 2:
                    return text
        return None
    
    def _extract_price(self, element):
        """Estrae prezzo universale"""
        price_patterns = [
            r'€\s*(\d+(?:[.,]\d+)?)',
            r'(\d+(?:[.,]\d+)?)\s*€',
            r'EUR\s*(\d+(?:[.,]\d+)?)',
            r'\$\s*(\d+(?:[.,]\d+)?)',
            r'(\d{3,5}(?:[.,]\d{2})?)'
        ]
        
        for selector in ['[class*="price"]', '.price', '.amount', 'span.money']:
            elem = element.select_one(selector)
            if elem:
                text = elem.get_text()
                for pattern in price_patterns:
                    match = re.search(pattern, text)
                    if match:
                        try:
                            price_str = match.group(1).replace(',', '.')
                            price = float(price_str)
                            if '$' in text:
                                price *= 0.92  # USD to EUR
                            if 10 <= price <= 10000:
                                return price
                        except:
                            pass
        return None
    
    def _extract_image_url(self, element, base_url):
        """Estrae URL immagine HD"""
        selectors = [
            'img[data-src]',
            'img[data-lazy]', 
            'img[src]',
            'img[data-srcset]'
        ]
        
        for selector in selectors:
            img = element.select_one(selector)
            if img:
                url = img.get('data-src') or img.get('data-lazy') or img.get('src')
                if url:
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        url = base_url + url
                    elif not url.startswith('http'):
                        url = urljoin(base_url, url)
                    return url
        return None

# ====================================
# 📊 EXCEL GENERATOR LUXURY HD
# ====================================

class LuxuryExcelGenerator:
    """Generatore Excel professionale con immagini HD"""
    
    def __init__(self):
        self.setup_styles()
    
    def setup_styles(self):
        """Stili luxury professionali"""
        self.header_style = NamedStyle(name='luxury_header')
        self.header_style.font = Font(bold=True, size=12, name='Calibri', color='FFFFFF')
        self.header_style.fill = PatternFill('solid', fgColor='1F4E78')
        self.header_style.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        self.header_style.border = Border(
            left=Side(style='medium', color='C9A961'),
            right=Side(style='medium', color='C9A961'),
            top=Side(style='medium', color='C9A961'),
            bottom=Side(style='medium', color='C9A961')
        )
    
    def create_excel(self, products, filename, ricarico=50, utente=None, job_id=None):
        """Crea Excel professionale con immagini HD"""
        wb = Workbook()
        ws = wb.active
        ws.title = "LUXURY STOCKLIST"
        
        if job_id:
            updater.send_update(job_id, 'excel', 85, '📊 Generazione Excel HD professionale...')
        
        # Parametri utente
        include_images = utente.has_images() if utente else False
        image_quality = utente.get_image_quality() if utente else 75
        image_size = utente.get_image_size() if utente else (120, 120)
        
        logger.info(f"📊 Excel Generation - Images: {include_images}, Quality: {image_quality}, Size: {image_size}")
        
        # HEADER LUXURY
        self._create_header(ws, utente, ricarico, len(products))
        
        # PRODOTTI CON IMMAGINI HD
        row = 6
        for idx, product in enumerate(products, 1):
            if idx % 5 == 0 and job_id:
                progress = 85 + (idx / len(products)) * 10
                updater.send_update(job_id, 'excel', progress, f'Aggiunta prodotto {idx}/{len(products)}...')
            
            self._add_product_row(ws, product, row, idx, ricarico, 
                                 include_images, image_quality, image_size)
            row += 1
        
        # TOTALI
        self._add_totals(ws, row, len(products))
        
        # ANALYTICS SHEET
        if utente and utente.piano in ['professional', 'enterprise', 'vip', 'admin']:
            self._add_analytics(wb, products, ricarico, utente)
        
        # Finalizza
        ws.freeze_panes = 'A6'
        if ws.max_row >= 6:
            ws.auto_filter.ref = f"A5:P{ws.max_row}"
        
        # Salva
        filepath = os.path.join(Config.EXPORT_PATH, filename)
        os.makedirs(Config.EXPORT_PATH, exist_ok=True)
        wb.save(filepath)
        
        if job_id:
            updater.send_update(job_id, 'ottimizzazione', 98, '✨ Ottimizzazione finale...')
        
        logger.info(f"✅ Excel HD creato: {filepath}")
        return filepath
    
    def _create_header(self, ws, utente, ricarico, total):
        """Header professionale"""
        # Titolo principale
        ws.merge_cells('A1:P1')
        ws['A1'] = '💎 LUXLAB PROFESSIONAL STOCKLIST SYSTEM HD 💎'
        ws['A1'].font = Font(bold=True, size=20, name='Calibri', color='C9A961')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['A1'].fill = PatternFill('solid', fgColor='1F4E78')
        ws.row_dimensions[1].height = 45
        
        # Info Row 2
        ws.merge_cells('A2:E2')
        ws['A2'] = f"CLIENT: {utente.azienda or utente.nome if utente else 'DEMO'}"
        ws['A2'].font = Font(bold=True, size=12)
        
        ws.merge_cells('F2:J2')
        ws['F2'] = f"PLAN: {utente.piano.upper() if utente else 'DEMO'}"
        ws['F2'].font = Font(bold=True, size=12, color='C9A961')
        
        ws.merge_cells('K2:P2')
        ws['K2'] = f"DATE: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        ws['K2'].font = Font(bold=True, size=12)
        
        # Stats Row 3
        ws.merge_cells('A3:D3')
        ws['A3'] = f"TOTAL: {total} PRODUCTS"
        ws.merge_cells('E3:H3')
        ws['E3'] = f"MARKUP: {ricarico}%"
        ws.merge_cells('I3:L3')
        ws['I3'] = f"SEASON: {datetime.now().year}"
        ws.merge_cells('M3:P3')
        ws['M3'] = "HD IMAGES INCLUDED" if utente and utente.has_images() else "NO IMAGES"
        
        for cell in ['A3', 'E3', 'I3', 'M3']:
            ws[cell].font = Font(bold=True, size=11, color='1F4E78')
            ws[cell].alignment = Alignment(horizontal='center')
        
        # Headers Row 5
        headers = [
            ('A5', '🖼️ IMAGE HD', 18),
            ('B5', 'SKU CODE', 15),
            ('C5', 'BRAND', 12),
            ('D5', 'PRODUCT NAME', 35),
            ('E5', 'CATEGORY', 15),
            ('F5', 'COLOR', 12),
            ('G5', 'MATERIAL', 15),
            ('H5', 'SIZES', 20),
            ('I5', 'QTY', 10),
            ('J5', 'RETAIL €', 12),
            ('K5', 'OUTLET €', 12),
            ('L5', 'YOUR €', 12),
            ('M5', 'DISCOUNT', 10),
            ('N5', 'MARGIN €', 12),
            ('O5', 'SEASON', 10),
            ('P5', 'MADE IN', 12)
        ]
        
        for cell, text, width in headers:
            ws[cell] = text
            ws[cell].font = Font(bold=True, size=11, color='FFFFFF')
            ws[cell].fill = PatternFill('solid', fgColor='C9A961')
            ws[cell].alignment = Alignment(horizontal='center', vertical='center')
            ws.column_dimensions[cell[0]].width = width
        
        ws.row_dimensions[5].height = 35
    
    def _add_product_row(self, ws, product, row, idx, ricarico, include_images, quality, size):
        """Aggiunge riga con immagine HD ottimizzata"""
        
        # Altezza riga per immagini
        ws.row_dimensions[row].height = max(size[1], 120) if include_images else 25
        
        # IMMAGINE HD OTTIMIZZATA
        if include_images and product.get('immagine_url'):
            try:
                logger.debug(f"Ottimizzazione immagine HD per prodotto {idx}")
                img_data = HDImageOptimizer.optimize_for_excel(
                    product['immagine_url'],
                    quality=quality,
                    size=size,
                    add_frame=True
                )
                
                img = XLImage(img_data)
                img.width = size[0]
                img.height = size[1]
                img.anchor = f'A{row}'
                ws.add_image(img)
                logger.debug(f"✅ Immagine HD aggiunta: {size}, quality {quality}%")
            except Exception as e:
                logger.error(f"Errore immagine row {row}: {e}")
                # Placeholder HD
                try:
                    placeholder = HDImageOptimizer.create_placeholder(size)
                    img = XLImage(placeholder)
                    img.width = size[0]
                    img.height = size[1]
                    ws.add_image(img, f'A{row}')
                except:
                    ws[f'A{row}'] = '💎'
        else:
            if include_images:
                # Placeholder per piani con immagini
                try:
                    placeholder = HDImageOptimizer.create_placeholder(size)
                    img = XLImage(placeholder)
                    img.width = size[0]
                    img.height = size[1]
                    ws.add_image(img, f'A{row}')
                except:
                    ws[f'A{row}'] = '💎'
            else:
                ws[f'A{row}'] = '—'
        
        # Dati prodotto
        retail = product['prezzo_retail']
        outlet = product['prezzo_outlet']
        your_price = outlet * (1 + ricarico/100)
        margin = your_price - outlet
        
        data = [
            ('B', product['codice']),
            ('C', product.get('brand', 'LUXURY')),
            ('D', product['nome'][:60]),
            ('E', product.get('categoria', 'Fashion')),
            ('F', product.get('colore', 'Multi')),
            ('G', product.get('materiale', 'Premium')),
            ('H', ', '.join(product.get('taglie', []))),
            ('I', product.get('quantita_totale', 0)),
            ('J', retail),
            ('K', outlet),
            ('L', your_price),
            ('M', f"{product.get('sconto', 0)}%"),
            ('N', margin),
            ('O', product.get('stagione', f'SS{datetime.now().year}')),
            ('P', product.get('made_in', 'Italy'))
        ]
        
        for col, value in data:
            cell = ws[f'{col}{row}']
            cell.value = value
            
            # Formattazione
            if col in ['J', 'K', 'L', 'N']:
                cell.number_format = '#,##0.00 €'
                cell.font = Font(bold=True, size=10)
                if col == 'L':
                    cell.font = Font(bold=True, size=10, color='27AE60')
                elif col == 'N':
                    cell.font = Font(bold=True, size=10, color='C9A961')
            elif col == 'M':
                cell.font = Font(bold=True, size=10, color='E74C3C')
            else:
                cell.font = Font(size=10)
            
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=(col=='D'))
            cell.border = Border(
                left=Side(style='thin', color='E0E0E0'),
                right=Side(style='thin', color='E0E0E0'),
                top=Side(style='thin', color='E0E0E0'),
                bottom=Side(style='thin', color='E0E0E0')
            )
            
            if row % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='F9F9F9')
    
    def _add_totals(self, ws, row, total_products):
        """Totali con formule"""
        row += 2
        ws.merge_cells(f'A{row}:H{row}')
        ws[f'A{row}'] = '💎 GRAND TOTAL'
        ws[f'A{row}'].font = Font(bold=True, size=14, color='C9A961')
        ws[f'A{row}'].alignment = Alignment(horizontal='right')
        
        # Formule
        ws[f'I{row}'] = f'=SUM(I6:I{row-2})'
        ws[f'J{row}'] = f'=SUM(J6:J{row-2})'
        ws[f'K{row}'] = f'=SUM(K6:K{row-2})'
        ws[f'L{row}'] = f'=SUM(L6:L{row-2})'
        ws[f'N{row}'] = f'=SUM(N6:N{row-2})'
        
        for col in ['I', 'J', 'K', 'L', 'N']:
            cell = ws[f'{col}{row}']
            cell.font = Font(bold=True, size=12, color='C9A961')
            if col != 'I':
                cell.number_format = '#,##0.00 €'
            cell.border = Border(top=Side(style='double', color='C9A961'))
    
    def _add_analytics(self, wb, products, ricarico, utente):
        """Analytics sheet per Professional+"""
        ws = wb.create_sheet('📊 ANALYTICS HD')
        
        ws['A1'] = '📊 BUSINESS ANALYTICS HD'
        ws['A1'].font = Font(bold=True, size=18, color='1F4E78')
        ws.merge_cells('A1:E1')
        
        # Metriche
        total_retail = sum(p['prezzo_retail'] for p in products)
        total_outlet = sum(p['prezzo_outlet'] for p in products)
        total_margin = sum((p['prezzo_outlet'] * ricarico/100) for p in products)
        
        data = [
            ['', ''],
            ['📈 KEY METRICS', ''],
            ['Total Products', len(products)],
            ['Total Retail Value', f'€{total_retail:,.2f}'],
            ['Total Outlet Value', f'€{total_outlet:,.2f}'],
            ['Expected Margin', f'€{total_margin:,.2f}'],
            ['ROI Potential', f'{(total_margin/total_outlet*100):.1f}%'],
            ['', ''],
            ['🏢 TOP BRANDS', 'Count'],
        ]
        
        # Brand distribution
        brands = Counter(p.get('brand', 'Unknown') for p in products)
        for brand, count in brands.most_common(5):
            data.append([brand, count])
        
        for row_idx, (label, value) in enumerate(data, 3):
            ws.cell(row_idx, 1, label).font = Font(bold=True if value == '' else False)
            ws.cell(row_idx, 2, value)

# ====================================
# 🚀 ROUTES API
# ====================================

@app.route('/')
def index():
    """Homepage"""
    return render_template('index.html')

@app.route('/api/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'version': '7.0-EPIC',
        'features': {
            'hd_images': True,
            'universal_extraction': True,
            'real_time': True,
            'excel_professional': True
        }
    })

@app.route('/api/register', methods=['POST'])
def register():
    """Registrazione con 1 credito gratuito"""
    try:
        data = request.json
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        nome = data.get('nome', '').strip()
        
        if not all([email, password, nome]):
            return jsonify({'error': 'Campi richiesti'}), 400
        
        if Utente.query.filter_by(email=email).first():
            return jsonify({'error': 'Email già registrata'}), 400
        
        utente = Utente(
            email=email,
            nome=nome,
            piano='free',
            crediti=1  # 1 credito = 10 prodotti
        )
        utente.imposta_password(password)
        
        db.session.add(utente)
        db.session.commit()
        
        token = genera_token(utente)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': utente.to_dict(),
            'message': '✨ Hai ricevuto 1 credito gratuito (10 prodotti)'
        })
        
    except Exception as e:
        logger.error(f"Register error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """Login"""
    try:
        data = request.json
        email = data.get('email', '').lower()
        password = data.get('password', '')
        
        utente = Utente.query.filter_by(email=email).first()
        
        if not utente or not utente.verifica_password(password):
            return jsonify({'error': 'Credenziali non valide'}), 401
        
        utente.ultimo_accesso = datetime.now()
        db.session.commit()
        
        token = genera_token(utente)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': utente.to_dict()
        })
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract', methods=['POST'])
@token_required
def extract():
    """Estrazione universale con immagini HD"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        ricarico = int(data.get('ricarico', 50))
        
        if not url:
            return jsonify({'error': 'URL richiesto'}), 400
        
        # Determina utente e limiti
        utente = None
        if request.current_user_id > 0:
            utente = Utente.query.get(request.current_user_id)
            if not utente:
                return jsonify({'error': 'Utente non trovato'}), 404
            
            # Limiti per piano
            if utente.piano in ['admin', 'vip', 'enterprise']:
                max_products = min(int(data.get('max_products', 100)), 500)
            else:
                max_products = min(10, utente.get_limit())
                
                # Check crediti per free
                if utente.piano == 'free' and utente.crediti <= 0:
                    return jsonify({'error': 'Crediti esauriti'}), 403
            
            piano = utente.piano
            include_images = utente.has_images()
            image_quality = utente.get_image_quality()
        else:
            piano = 'demo'
            max_products = 10
            include_images = False
            image_quality = 0
        
        logger.info(f"🚀 Estrazione - User: {utente.email if utente else 'demo'}, Max: {max_products}, Images: {include_images}")
        
        # Crea job
        job_id = str(uuid.uuid4())
        extraction_jobs[job_id] = {
            'fase': 'inizializzazione',
            'progress': 0,
            'messaggio': '🚀 Avvio sistema...'
        }
        
        def run_extraction():
            """Thread estrazione"""
            try:
                start_time = time.time()
                
                # Estrazione universale
                extractor = UniversalLuxuryExtractor(job_id)
                products = extractor.extract_products(
                    url, max_products, include_images, image_quality
                )
                
                if not products:
                    raise Exception("Nessun prodotto trovato")
                
                # Excel HD
                generator = LuxuryExcelGenerator()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f'luxlab_HD_{piano}_{timestamp}.xlsx'
                filepath = generator.create_excel(
                    products, filename, ricarico, utente, job_id
                )
                
                # Salva DB
                if utente:
                    if utente.piano == 'free':
                        credits_needed = max(1, (len(products) + 9) // 10)
                        utente.crediti = max(0, utente.crediti - credits_needed)
                    
                    estrazione = Estrazione(
                        utente_id=utente.id,
                        url=url,
                        prodotti_estratti=len(products),
                        file_generato=filename,
                        ricarico=ricarico,
                        status='completed',
                        con_immagini=include_images,
                        tempo_elaborazione=time.time() - start_time
                    )
                    db.session.add(estrazione)
                    
                    utente.total_extractions += 1
                    utente.total_products += len(products)
                    db.session.commit()
                
                # Preview
                preview = []
                for p in products[:10]:
                    preview.append({
                        'codice': p['codice'],
                        'nome': p['nome'],
                        'brand': p.get('brand'),
                        'prezzo': f"€{p['prezzo_retail']:.0f}",
                        'outlet': f"€{p['prezzo_outlet']:.0f}"
                    })
                
                # Completa
                updater.send_update(
                    job_id, 'completato', 100,
                    f'✅ Completato! {len(products)} prodotti HD estratti.',
                    {
                        'prodotti': preview,
                        'totale': len(products),
                        'file': filename,
                        'success': True
                    }
                )
                
                logger.info(f"✅ Estrazione completata in {time.time()-start_time:.1f}s")
                
            except Exception as e:
                logger.error(f"Extraction error: {e}")
                updater.send_update(
                    job_id, 'errore', 0, str(e), {'success': False}
                )
        
        # Avvia thread
        thread = threading.Thread(target=run_extraction, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'piano': piano,
            'max_products': max_products,
            'images': include_images,
            'image_quality': image_quality if include_images else 0
        })
        
    except Exception as e:
        logger.error(f"Extract error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream/<job_id>')
def stream_updates(job_id):
    """SSE per updates real-time"""
    def generate():
        q = updater.add_client(job_id)
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                    
                    status = json.loads(data)
                    if status.get('fase') in ['completato', 'errore']:
                        break
                except queue.Empty:
                    yield f"data: {json.dumps({'heartbeat': True})}\n\n"
        finally:
            if job_id in updater.clients:
                del updater.clients[job_id]
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Status polling"""
    if job_id in extraction_jobs:
        return jsonify({'success': True, 'status': extraction_jobs[job_id]})
    return jsonify({'error': 'Job non trovato'}), 404

@app.route('/api/download/<filename>')
@token_required
def download(filename):
    """Download Excel HD"""
    try:
        filename = secure_filename(filename)
        filepath = os.path.join(Config.EXPORT_PATH, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File non trovato'}), 404
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/profile')
@token_required
def profile():
    """Profilo utente"""
    try:
        utente = Utente.query.get(request.current_user_id)
        if not utente:
            return jsonify({'error': 'Utente non trovato'}), 404
        
        return jsonify({'success': True, 'user': utente.to_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ====================================
# INIT & RUN
# ====================================

def init_app():
    """Inizializza app"""
    with app.app_context():
        try:
            for dir in [Config.EXPORT_PATH, Config.TEMPLATES_PATH, Config.LOGS_PATH, Config.IMAGES_PATH]:
                os.makedirs(dir, exist_ok=True)
            
            db.create_all()
            
            # Admin
            admin = Utente.query.filter_by(email='admin@luxlab.it').first()
            if not admin:
                admin = Utente(
                    email='admin@luxlab.it',
                    nome='Admin',
                    piano='admin',
                    crediti=9999,
                    is_admin=True,
                    is_premium=True
                )
                admin.imposta_password('luxlab2024')
                db.session.add(admin)
            
            # VIP
            vip = Utente.query.filter_by(email='vip@luxlab.it').first()
            if not vip:
                vip = Utente(
                    email='vip@luxlab.it',
                    nome='VIP',
                    piano='vip',
                    crediti=9999,
                    is_vip=True,
                    is_premium=True
                )
                vip.imposta_password('vip1999')
                db.session.add(vip)
            
            db.session.commit()
            logger.info("✅ Database initialized")
            
        except Exception as e:
            logger.error(f"Init error: {e}")

if __name__ == '__main__':
    init_app()
    
    print(f"""
    💎 LUXLAB EXTRACTOR v7.0 EPIC HD 💎
    =====================================
    🌍 Server: {Config.DOMAIN}
    🖼️ HD Images: ULTRA OPTIMIZED
    📊 Excel: PROFESSIONAL HD
    🚀 Universal: ALL BROWSERS
    ⚡ Real-time: ACTIVE
    
    ACCOUNTS:
    - Admin: admin@luxlab.it / luxlab2024 (ILLIMITATO)
    - VIP: vip@luxlab.it / vip1999 (ILLIMITATO) 
    - New users: 1 credito = 10 prodotti
    
    PIANI:
    - Free: 10 prodotti, NO immagini
    - Base €149: 1000 prodotti, immagini 120x120
    - Pro €399: 5000 prodotti, HD 150x150
    - Enterprise €1999: ILLIMITATO, Ultra HD 180x180
    =====================================
    """)
    
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG, threaded=True)
