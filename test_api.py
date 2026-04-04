import urllib.parse
import urllib.request
import json
import logging
logging.basicConfig(level=logging.DEBUG)

def test_wiki(probe):
    q   = urllib.parse.quote_plus(probe)
    url = f'https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&srlimit=1&srnamespace=0&format=json&utf8='
    
    print('Testing Wiki with query:', probe)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ProcessAuth/1.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace'))
        results = data.get('query', {}).get('search', [])
        if results:
            title   = results[0].get('title', '')
            snippet = results[0].get('snippet', '')
            probe_words = set(probe.lower().split())
            snip_words  = set(snippet.lower().split())
            overlap = len(probe_words & snip_words) / max(len(probe_words), 1)
            print(f'Wiki Title: {title}')
            print(f'Wiki Snippet: {snippet}')
            print(f'Overlap: {overlap}')
        else:
            print('No Wiki Results')
    except Exception as e:
        print('Error:', e)

probe = 'The Python programming language is a high-level, general-purpose programming lan'
test_wiki(probe)

def test_ddg(probe):
    q = urllib.parse.quote_plus(f'"{probe}"')
    url = f'https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1'
    print('Testing DDG with query:', url)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ProcessAuth/1.0'})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace'))
        print('DDG Heading:', data.get('Heading', 'None'))
        print('DDG Abstract:', data.get('Abstract', 'None'))
    except Exception as e:
        print('Error:', e)
test_ddg(probe)
