import requests
from urllib.parse import urlparse
import re
import time

FILTER_URL = "filter url here"

_filter_cache = {
    'domains': set(),
    'patterns': [],
    'last_update': 0,
    'update_interval': 3600
}

def download_filter_list():

    try:
        response = requests.get(FILTER_URL, timeout=10)
        
        if response.status_code == 200:
            domains = set()
            patterns = []
            
            for line in response.text.split('\n'):
                line = line.strip()
                
                if not line or line.startswith('!') or line.startswith('['):
                    continue
                
                if line.startswith('||') and '^' in line:
                    domain = line[2:].split('^')[0]
                    if domain:
                        domains.add(domain)
                        pattern = re.escape(domain).replace(r'\*', '.*')
                        patterns.append(re.compile(pattern, re.IGNORECASE))
                
                elif not line.startswith(('|', '/', '@', '#')) and '.' in line:
                    domain = line.rstrip('^')
                    domains.add(domain)
                    pattern = re.escape(domain).replace(r'\*', '.*')
                    patterns.append(re.compile(pattern, re.IGNORECASE))
            
            _filter_cache['domains'] = domains
            _filter_cache['patterns'] = patterns
            _filter_cache['last_update'] = time.time()
            
            print(f"フィルターを更新: {len(domains)} ドメイン")
            return True
        
    except Exception as e:
        print(f"フィルター更新エラー: {e}")
    
    return False

def ensure_filter_updated():

    current_time = time.time()
    
    if (not _filter_cache['patterns'] or 
        current_time - _filter_cache['last_update'] > _filter_cache['update_interval']):
        download_filter_list()
    
    return bool(_filter_cache['patterns'])

def extract_domain_from_url(url):

    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        parsed = urlparse(url)
        domain = parsed.netloc
        
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain
    except:
        return None

def check_url_with_filter(url):

    try:
        if not ensure_filter_updated():
            return False
        
        domain = extract_domain_from_url(url)
        if not domain:
            return False
        
        if domain in _filter_cache['domains']:
            return True

        full_url = url
        if not full_url.startswith(('http://', 'https://')):
            full_url = 'http://' + full_url
        
        for pattern in _filter_cache['patterns']:
            if pattern.search(full_url) or pattern.search(domain):
                return True
        
        return False
        
    except Exception as e:
        print(f"URLチェックエラー: {e}")
        return False
