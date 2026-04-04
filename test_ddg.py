import urllib.parse
import urllib.request

def test_ddg_lite(probe):
    q = urllib.parse.quote_plus(f'"{probe}"')
    url = f'https://html.duckduckgo.com/html/'
    data = urllib.parse.urlencode({'q': q}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode('utf-8')
            if 'result__snippet' in html:
                print('Hit found on DDG lite!')
            else:
                print('No results string found')
    except Exception as e:
        print('Error:', e)

test_ddg_lite('the external web hits isnt functional anymore')
