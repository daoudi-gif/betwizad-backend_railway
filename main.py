from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import re

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def scrape_betwizad():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://betwizad.com/predictions", wait_until="domcontentloaded")
        await page.wait_for_selector("table", timeout=15000)
        
        rows = await page.evaluate("""
            () => {
                const data = [];
                document.querySelectorAll('table tr').forEach(row => {
                    const cells = row.querySelectorAll('th, td');
                    if (cells.length >= 5) {
                        data.push(Array.from(cells).map(cell => cell.innerText.trim()));
                    }
                });
                return data;
            }
        """)
        await browser.close()
        return rows

def parse_matches(raw_rows):
    header_idx = -1
    for i, row in enumerate(raw_rows):
        if 'TIME' in row:
            header_idx = i
            break
    if header_idx == -1:
        return {}
    
    matchs_par_championnat = {}
    championnat_courant = "Matchs divers"
    
    for row in raw_rows[header_idx+1:]:
        if len(row) < 6:
            continue
        # Détection championnat (première cellule sans heure ni score)
        if row[0] and not re.search(r'\d+:\d+|\d+\s*:\s*\d+|\d+-\d+', row[0]) and ' - ' not in row[0]:
            championnat_courant = row[0]
            matchs_par_championnat.setdefault(championnat_courant, [])
            continue
        
        # Match
        if ':' in row[0] or '-' in row[0]:
            match = {
                'time': row[0],
                'home': '', 'away': '', 'score': '',
                'odds_1': row[2] if len(row) > 2 else '',
                'odds_x': row[3] if len(row) > 3 else '',
                'odds_2': row[4] if len(row) > 4 else '',
                'tip': row[5] if len(row) > 5 else '',
                'htft': row[6] if len(row) > 6 else '',
                'cs_tips': row[7] if len(row) > 7 else ''
            }
            match_text = row[1]
            score_match = re.search(r'(\d+\s*:\s*\d+)', match_text)
            if score_match:
                match['score'] = score_match.group(1)
                parts = match_text.split(score_match.group(1))
                match['home'] = parts[0].strip()
                match['away'] = parts[1].strip() if len(parts) > 1 else ''
            else:
                if '\n' in match_text:
                    names = match_text.split('\n')
                    match['home'] = names[0].strip()
                    match['away'] = names[1].strip() if len(names) > 1 else ''
                elif ' - ' in match_text:
                    names = match_text.split(' - ')
                    match['home'] = names[0].strip()
                    match['away'] = names[1].strip() if len(names) > 1 else ''
                else:
                    match['home'] = match_text.strip()
                    match['away'] = ''
            matchs_par_championnat.setdefault(championnat_courant, []).append(match)
    return matchs_par_championnat

@app.get("/predictions")
async def get_predictions():
    raw = await scrape_betwizad()
    parsed = parse_matches(raw)
    return parsed