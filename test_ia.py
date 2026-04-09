import urllib.request
import urllib.parse
import json

probe = "It was the best of times, it was the worst of times"
q = urllib.parse.quote_plus(f'"{probe}"')
url = f'https://archive.org/services/search/v1/scrape?fields=title,identifier,description&q={q}'

req = urllib.request.Request(url, headers={'User-Agent': 'ProcessAuth/1.0'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print(json.dumps(data.get('items', [])[:2], indent=2))
        print("TOTAL:", data.get('total'))
except Exception as e:
    print('Failed:', e)
