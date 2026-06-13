import os
import re
import time
import logging
import urllib.parse
import threading
import requests
from html.parser import HTMLParser
from sqlalchemy.orm import Session
from .models import Match
from .fifa import _normalize

logger = logging.getLogger("bolao_broadcasters")

class BroadcasterHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.matches = []
        self.current_match = None
        self.in_article = False
        self.depth = 0
        self.current_broadcaster = None
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'article':
            aria_label = attrs_dict.get('aria-label')
            if aria_label and ' x ' in aria_label:
                self.in_article = True
                self.depth = 1
                self.current_match = {
                    'teams': [t.strip() for t in aria_label.split(' x ')],
                    'broadcasters': []
                }
        elif self.in_article:
            self.depth += 1
            if tag == 'a' and 'title' in attrs_dict:
                title = attrs_dict['title']
                self.current_broadcaster = {
                    'name': title,
                    'logo': None
                }
                self.current_match['broadcasters'].append(self.current_broadcaster)
            elif tag == 'img' and self.current_broadcaster:
                src = attrs_dict.get('src', '')
                logo_path = None
                if 'url=' in src:
                    parsed = urllib.parse.urlparse(src)
                    qs = urllib.parse.parse_qs(parsed.query)
                    logo_paths = qs.get('url', [])
                    if logo_paths:
                        logo_path = logo_paths[0]
                elif src.startswith('/logos/'):
                    logo_path = src
                
                if logo_path:
                    if not logo_path.startswith('http'):
                        logo_path = 'https://ondevaipassar.app' + logo_path
                    self.current_broadcaster['logo'] = logo_path

    def handle_endtag(self, tag):
        if self.in_article:
            self.depth -= 1
            if self.depth == 0:
                self.in_article = False
                if self.current_match:
                    self.matches.append(self.current_match)
                    self.current_match = None
            if tag == 'a':
                self.current_broadcaster = None

def custom_normalize(name: str) -> str:
    if not name:
        return ''
    import unicodedata
    val = unicodedata.normalize('NFKD', name)
    val = ''.join(ch for ch in val if not unicodedata.combining(ch))
    val = val.casefold().strip()
    
    # Custom maps for team names
    if val in ['rep dem do congo', 'rep. dem. do congo', 'rep. dem do congo', 'republica democratica do congo']:
        return 'rd congo'
        
    # Pattern for 1º Grupo X -> 1X
    m = re.match(r'([12])\s*º\s*grupo\s*([a-l])', val)
    if m:
        return f'{m.group(1)}{m.group(2).upper()}'
        
    # Pattern for Vencedor JX -> WX
    m_win = re.match(r'vencedor\s*j\s*(\d+)', val)
    if m_win:
        return f'W{m_win.group(1)}'
        
    # Pattern for Perdedor JX -> LX
    m_lose = re.match(r'perdedor\s*j\s*(\d+)', val)
    if m_lose:
        return f'L{m_lose.group(1)}'
        
    # Fallback to standard
    return _normalize(name)

# In-memory cache variables
_cache = {}
_last_fetch = 0
_cache_lock = threading.Lock()
CACHE_DURATION = 3600  # 1 hour in seconds

def fetch_and_map_broadcasters(db: Session) -> dict:
    url = "https://ondevaipassar.app/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        logger.info("Scraping ondevaipassar.app for broadcast info...")
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        html_content = resp.text
    except Exception as e:
        logger.error(f"Failed to fetch broadcast page: {e}")
        return {}
        
    try:
        parser = BroadcasterHTMLParser()
        parser.feed(html_content)
        scraped_matches = parser.matches
    except Exception as e:
        logger.error(f"Failed to parse broadcast HTML: {e}")
        return {}
        
    # Deduplicate scraped listings by sorted normalized teams
    deduped = {}
    for sm in scraped_matches:
        if len(sm['teams']) < 2:
            continue
        t1 = custom_normalize(sm['teams'][0])
        t2 = custom_normalize(sm['teams'][1])
        key = tuple(sorted([t1, t2]))
        if key not in deduped:
            deduped[key] = sm['broadcasters']
            
    # Map to database matches
    try:
        db_matches = db.query(Match).all()
        mapping = {}
        for dm in db_matches:
            db_t1 = custom_normalize(dm.team1_name)
            db_t2 = custom_normalize(dm.team2_name)
            key = tuple(sorted([db_t1, db_t2]))
            
            if key in deduped:
                # Filter out any broadcaster without a valid name or logo
                valid_broadcasters = [
                    b for b in deduped[key] if b.get('name')
                ]
                # Default empty logo to a placeholder or keep as None
                mapping[dm.id] = valid_broadcasters
            else:
                mapping[dm.id] = []
                
        return mapping
    except Exception as e:
        logger.error(f"Error mapping database matches: {e}")
        return {}

def get_match_broadcasters(db: Session) -> dict:
    global _cache, _last_fetch
    
    now = time.time()
    # Check if cache is empty or expired
    if not _cache or (now - _last_fetch > CACHE_DURATION):
        with _cache_lock:
            # Double check inside lock
            if not _cache or (now - _last_fetch > CACHE_DURATION):
                new_data = fetch_and_map_broadcasters(db)
                if new_data:
                    _cache = new_data
                    _last_fetch = now
                    logger.info("Broadcaster cache successfully refreshed.")
                elif _cache:
                    logger.warning("Using stale broadcaster cache due to fetch failure.")
                else:
                    logger.warning("Broadcaster cache is empty and fetch failed.")
                    
    return _cache
