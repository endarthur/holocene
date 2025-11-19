#!/usr/bin/env python3
"""Test Mercado Livre product page structure."""

import requests
from bs4 import BeautifulSoup
import json

url = 'https://produto.mercadolivre.com.br/MLB-4020400791-projetor-display-holograma-3d-ventilador-holografico-34cm-_JM'

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)

soup = BeautifulSoup(r.text, 'html.parser')

# Check for JSON-LD
json_ld = soup.find_all('script', type='application/ld+json')
print(f'Found {len(json_ld)} JSON-LD scripts')

if json_ld:
    for idx, script in enumerate(json_ld[:3]):
        print(f'\n=== JSON-LD #{idx+1} ===')
        try:
            data = json.loads(script.string)
            print(json.dumps(data, indent=2, ensure_ascii=False)[:800])
        except:
            print('Failed to parse')

# Check for window.__NEXT_DATA__ or similar
scripts = soup.find_all('script')
for script in scripts:
    if script.string and '__NEXT_DATA__' in script.string:
        print('\n=== Found __NEXT_DATA__ ===')
        print(script.string[:500])
        break
