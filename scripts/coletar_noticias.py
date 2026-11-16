#!/usr/bin/env python3
"""Coleta manchetes públicas de RSS e eventos sísmicos USGS para o Alerta Global."""
import datetime as dt
import email.utils
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "noticias.json"
FEEDS = [
    # (fonte, endereço RSS, categoria padrão, país ISO, idioma ISO)
    ("BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "Geral", "GB", "en"),
    ("BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml", "Economia", "GB", "en"),
    ("BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml", "Tecnologia", "GB", "en"),
    ("BBC News", "https://feeds.bbci.co.uk/news/health/rss.xml", "Saúde", "GB", "en"),
    ("BBC News", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "Clima e desastres", "GB", "en"),
    ("Deutsche Welle", "https://rss.dw.com/rdf/rss-en-all", "Geral", "DE", "en"),
    ("The Guardian", "https://www.theguardian.com/world/rss", "Geral", "GB", "en"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Geral", "QA", "en"),
    ("G1 Mundo", "https://g1.globo.com/rss/g1/mundo/", "Geral", "BR", "pt"),
    ("Le Monde", "https://www.lemonde.fr/international/rss_full.xml", "Geral", "FR", "fr"),
    ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "Geral", "ES", "es"),
    ("NHK World", "https://www3.nhk.or.jp/rss/news/cat6.xml", "Geral", "JP", "en"),
    # Reuters via Google Notícias: o feed lista artigos atribuídos à Reuters;
    # somente itens com a origem Reuters serão aceitos.
    ("Reuters", "https://news.google.com/rss/search?q=site%3Areuters.com%20when%3A2d&hl=en-US&gl=US&ceid=US%3Aen", "Geral", "GLOBAL", "en"),
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

def image_url(value):
    """Aceita somente links de imagem HTTP(S) vindos do feed da matéria."""
    value = html.unescape(str(value or "")).strip()
    if value.startswith("//"):
        value = "https:" + value
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return ""
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        return ""
    if parsed.hostname in ("news.google.com", "www.google.com", "google.com"):
        return ""
    if parsed.path.lower().endswith((".svg", ".gif", ".ico")):
        return ""
    return value[:1800]

def image_from_entry(entry):
    """Obtém a imagem real declarada no item RSS (media/enclosure/HTML)."""
    candidates = []
    for node in entry.iter():
        name = node.tag.split("}")[-1].lower()
        attrs = node.attrib
        url = ""
        if name in ("thumbnail", "enclosure", "image"):
            url = attrs.get("url") or attrs.get("href") or ""
        elif name == "content":
            media_type = (attrs.get("type") or "").lower()
            medium = (attrs.get("medium") or "").lower()
            if medium == "image" or media_type.startswith("image/"):
                url = attrs.get("url", "")
        if name == "image" and not url:
            url = child(node, "url")
        link = image_url(url)
        if link:
            try:
                width = int(attrs.get("width", "0"))
                height = int(attrs.get("height", "0"))
            except ValueError:
                width = height = 0
            if (width and width < 90) or (height and height < 65):
                continue
            candidates.append((width * height, link))
    if candidates:
        return max(candidates, key=lambda x: x[0])[1]
    # Muitas fontes publicam a foto apenas no HTML do resumo RSS.
    for node in entry:
        name = node.tag.split("}")[-1].lower()
        if name not in ("description", "encoded", "summary", "content"):
            continue
        markup = html.unescape(node.text or "")
        for match in re.finditer(r'<img\b[^>]*\b(?:src|data-src)\s*=\s*["\']([^"\']+)', markup, re.I):
            link = image_url(match.group(1))
            if link:
                return link
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
def parse_feed(source, url, default, country, lang):
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
        if source == "Reuters":
            # Google Notícias pode agregar resultados de várias editoras.
            # Não atribuímos notícias de outros veículos à Reuters.
            publisher = child(e, "source").strip().lower()
            if "reuters" not in publisher and not re.search(r"\s[-–]\sReuters$", title, re.I):
                continue
            title = re.sub(r"\s[-–]\sReuters$", "", title, flags=re.I)
        if not title or not link.startswith("https://") and not link.startswith("http://"):
            continue
        date = parsedate(child(e, "pubDate") or child(e, "published") or child(e, "updated") or child(e, "date"))
        if date:
            age = NOW - dt.datetime.fromisoformat(date.replace("Z", "+00:00"))
            if age > dt.timedelta(days=4) or age < -dt.timedelta(hours=4):
                continue
        output.append({"title": title, "summary": clean(child(e, "description") or child(e, "summary"))[:360],
                       "category": category(title, default), "region": "Global", "country": country,
                       "source": source, "url": link, "date": date, "lang": lang,
                       "image": image_from_entry(e)})
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
def translate(text, lang):
    """Tradução gratuita (MyMemory, sem chave). Retorna '' se a cota acabar ou não houver resposta."""
    q = urllib.parse.quote(text[:450])
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair={lang}|pt-BR"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=7) as response:
        j = json.load(response)
    t = (j.get("responseData") or {}).get("translatedText") or ""
    if not t or "MYMEMORY WARNING" in t.upper():
        return ""
    return clean(t)
def main():
    data = []
    success = 0
    for source, url, cat, country, lang in FEEDS:
        try:
            articles = parse_feed(source, url, cat, country, lang)
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
    # Tradução progressiva e com cache. Respeita limites do serviço gratuito.
    cache = {}
    if OUT.exists():
        try:
            for old in json.loads(OUT.read_text(encoding="utf-8")):
                cache[old.get("title", "")] = old
        except (ValueError, TypeError):
            pass
    remaining_titles = 18
    remaining_summaries = 55
    title_count = 0
    summary_count = 0
    # Tradução de notícias recentes primeiro. O restante será traduzido
    # em execuções seguintes, sem apagar traduções realizadas.
    for item in sorted_items:
        previous = cache.get(item["title"], {})
        if not item.get("image") and previous.get("image"):
            item["image"] = previous["image"]
        lang = item.get("lang", "")
        if lang == "pt":
            item["title_pt"] = item["title"]
            item["summary_pt"] = item["summary"]
            continue
        if not lang:
            continue
        # Resumo primeiro: o objetivo é apresentar a notícia em português.
        if previous.get("summary_pt"):
            item["summary_pt"] = previous["summary_pt"]
        elif remaining_summaries > 0 and item.get("summary"):
            remaining_summaries -= 1
            try:
                value = translate(item["summary"][:350], lang)
                if value:
                    item["summary_pt"] = value
                    summary_count += 1
            except Exception as err:
                print(f"Serviço de tradução de resumos indisponível: {err}")
                remaining_summaries = 0
        if previous.get("title_pt"):
            item["title_pt"] = previous["title_pt"]
        elif remaining_titles > 0:
            remaining_titles -= 1
            try:
                value = translate(item["title"], lang)
                if value:
                    item["title_pt"] = value
                    title_count += 1
            except Exception as err:
                print(f"Serviço de tradução de títulos indisponível: {err}")
                remaining_titles = 0
    print(f"Traduções novas: {title_count} títulos e {summary_count} resumos")
    OUT.write_text(json.dumps(sorted_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravadas {len(sorted_items)} ocorrências em {OUT.name}")
if __name__ == "__main__":
    main()
