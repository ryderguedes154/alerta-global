#!/usr/bin/env python3
"""Coleta manchetes públicas de RSS e eventos sísmicos USGS para o Alerta Global."""
import datetime as dt
import email.utils
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "noticias.json"
FEEDS = [
    ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "Geral"),
    ("BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml", "Economia"),
    ("BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml", "Tecnologia"),
    ("BBC News", "https://feeds.bbci.co.uk/news/health/rss.xml", "Saúde"),
    ("BBC News", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "Clima e desastres"),
    ("Deutsche Welle", "https://rss.dw.com/rdf/rss-en-all", "Geral"),
    ("The Guardian", "https://www.theguardian.com/world/rss", "Geral"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Geral"),
]
NOW = dt.datetime.now(dt.timezone.utc)
UA = "AlertaGlobalRSS/1.0 (public news aggregator)"
def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, application/json, */*"})
    with urllib.request.urlopen(req, timeout=18) as response:
        return response.read(3_000_000)
def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()[:550]
def child(node, name):
    for el in node:
        if el.tag.split("}")[-1].lower() == name.lower():
            return "".join(el.itertext()).strip()
    return ""
def parsedate(value):
    if not value:
        return ""
    try:
        result = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt.timezone.utc)
    return result.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def category(title, default):
    title = title.lower()
    lookup = [
        ("Saúde", ["outbreak", "pandemic", "vaccine", "disease", "health", "virus"]),
        ("Clima e desastres", ["earthquake", "tsunami", "hurricane", "flood", "storm", "wildfire", "climate"]),
        ("Segurança cibernética", ["cyberattack", "ransomware", "data breach", "hacker"]),
        ("Conflitos", ["war", "missile", "airstrike", "military", "ceasefire", "invasion"]),
        ("Economia", ["economy", "inflation", "stock market", "tariff", "interest rate", "bank"]),
        ("Tecnologia", ["artificial intelligence", "technology", "tech", "ai regulation"]),
    ]
    return next((label for label, words in lookup if any(w in title for w in words)), default)
def parse_feed(source, url, default):
    root = ET.fromstring(download(url))
    entries = [n for n in root.iter() if n.tag.split("}")[-1] in ("item", "entry")]
    output = []
    for e in entries[:65]:
        title = clean(child(e, "title"))
        link = child(e, "link")
        if not link:
            for el in e:
                if el.tag.split("}")[-1] == "link" and el.attrib.get("href"):
                    link = el.attrib["href"]
                    break
        if not title or not link.startswith("https://") and not link.startswith("http://"):
            continue
        date = parsedate(child(e, "pubDate") or child(e, "published") or child(e, "updated") or child(e, "date"))
        if date:
            age = NOW - dt.datetime.fromisoformat(date.replace("Z", "+00:00"))
            if age > dt.timedelta(days=4) or age < -dt.timedelta(hours=4):
                continue
        output.append({"title": title, "summary": clean(child(e, "description") or child(e, "summary"))[:360],
                       "category": category(title, default), "region": "Global", "country": "GLOBAL",
                       "source": source, "url": link, "date": date})
    return output
def earthquakes():
    j = json.loads(download("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"))
    result = []
    for f in j.get("features", []):
        p = f.get("properties") or {}
        mag = float(p.get("mag") or 0)
        place = str(p.get("place") or "local não informado")
        date = dt.datetime.fromtimestamp(p["time"] / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z") if p.get("time") else ""
        result.append({"title": f"Terremoto de magnitude {mag:.1f} — {place}",
                       "summary": "Evento sísmico registrado pelo USGS. Consulte a fonte oficial para localização, profundidade e atualizações.",
                       "category": "Clima e desastres", "region": place, "country": "GLOBAL",
                       "source": "USGS", "url": p.get("url", ""), "date": date,
                       "forcedSev": "crit" if mag >= 7 else "high" if mag >= 6 else "med" if mag >= 5 else "low"})
    return result
def main():
    data = []
    success = 0
    for source, url, cat in FEEDS:
        try:
            articles = parse_feed(source, url, cat)
            print(f"{source}: {len(articles)} notícias ({url})")
            data.extend(articles)
            success += 1
        except Exception as err:
            print(f"FALHA em {source} ({url}): {err}")
    try:
        quakes = earthquakes()
        data.extend(quakes)
        success += 1
        print(f"USGS: {len(quakes)} terremotos")
    except Exception as err:
        print(f"FALHA no USGS: {err}")
    if not success:
        raise SystemExit("Todas as fontes falharam; preservando o JSON anterior.")
    unique = {}
    for item in data:
        key = re.sub(r"\W+", "", item["title"].lower())[:100]
        if key and key not in unique:
            unique[key] = item
    sorted_items = sorted(unique.values(), key=lambda x: x.get("date", ""), reverse=True)[:200]
    if not sorted_items:
        raise SystemExit("Nenhuma notícia coletada; preservando o JSON anterior.")
    OUT.write_text(json.dumps(sorted_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravadas {len(sorted_items)} ocorrências em {OUT.name}")
if __name__ == "__main__":
    main()
