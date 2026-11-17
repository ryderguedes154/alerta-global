#!/usr/bin/env python3
"""Coleta manchetes públicas de RSS e eventos sísmicos USGS para o Alerta Global."""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
import email.utils
import html
import json
import re
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "noticias.json"
STATUS_OUT = ROOT / "status_fontes.json"
MAX_ARTICLES = 500
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
    # Novas fontes internacionais: RSS oficial, salvo AP (feed da conta verificada no Flipboard).
    ("Associated Press", "https://flipboard.com/@associatedpress/international-news-miluvhmaz.rss", "Geral", "US", "en"),
    ("France 24", "https://www.france24.com/en/rss", "Geral", "FR", "en"),
    ("France 24", "https://www.france24.com/en/europe/rss", "Geral", "FR", "en"),
    ("Euronews", "https://www.euronews.com/rss?format=mrss&level=theme&name=news", "Geral", "EU", "en"),
    ("Euronews", "https://www.euronews.com/rss?format=mrss&level=vertical&name=earth", "Clima e desastres", "EU", "en"),
    ("DW Brasil", "https://rss.dw.com/rdf/rss-br-br", "Geral", "BR", "pt"),
    ("CNN Brasil", "https://www.cnnbrasil.com.br/feed/", "Geral", "BR", "pt"),
    ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/internacional/feed.xml", "Geral", "BR", "pt"),
    ("NPR", "https://feeds.npr.org/1004/rss.xml", "Geral", "US", "en"),
    ("Sky News", "https://feeds.skynews.com/feeds/rss/world.xml", "Geral", "GB", "en"),
    ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "Geral", "US", "en"),
    ("CBS News", "https://www.cbsnews.com/latest/rss/world", "Geral", "US", "en"),
    # Reuters via Google Notícias: o feed lista artigos atribuídos à Reuters;
    # somente itens com a origem Reuters serão aceitos.
    ("Reuters", "https://news.google.com/rss/search?q=site%3Areuters.com%20when%3A2d&hl=en-US&gl=US&ceid=US%3Aen", "Geral", "GLOBAL", "en"),
]
NOW = dt.datetime.now(dt.timezone.utc)
UA = "Mozilla/5.0 (compatible; AlertaGlobalRSS/2.0; public-news-aggregator)"
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


class ArticleImageParser(HTMLParser):
    """Lê apenas imagens editoriais declaradas nos metadados da matéria."""
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.images = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        name = (values.get("property") or values.get("name") or "").lower().strip()
        candidate = ""
        priority = 0
        if tag == "meta" and name in ("og:image", "og:image:url", "og:image:secure_url",
                                      "twitter:image", "twitter:image:src"):
            candidate = values.get("content", "")
            priority = 2 if name.startswith("og:") else 1
        elif tag == "link" and (values.get("rel") or "").lower() == "image_src":
            candidate = values.get("href", "")
            priority = 1
        if candidate:
            link = image_url(urllib.parse.urljoin(self.page_url, candidate))
            if link and not re.search(r"(?:logo|favicon|sprite|tracking-pixel)", urllib.parse.urlsplit(link).path, re.I):
                self.images.append((priority, link))

def image_from_article(url):
    """Busca og:image/twitter:image da matéria original quando o RSS omite a foto."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return ""
        if parsed.hostname.endswith(("google.com", "news.google.com")):
            return ""
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AlertaGlobalNews/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.8,en;q=0.7",
        })
        with urllib.request.urlopen(req, timeout=9) as response:
            if "html" not in response.headers.get("Content-Type", "").lower():
                return ""
            page = response.read(750_000).decode("utf-8", errors="replace")
            base_url = response.geturl()
        parser = ArticleImageParser(base_url)
        parser.feed(page)
        return sorted(parser.images, key=lambda item: item[0], reverse=True)[0][1] if parser.images else ""
    except Exception:
        return ""

def enrich_article_images(articles, cache):
    """Busca imagens em paralelo sem bloquear indefinidamente o fluxo de notícias."""
    pending = []
    for item in articles:
        old = cache.get(item["title"], {})
        if item.get("image"):
            continue
        if image_url(old.get("image")):
            item["image"] = old["image"]
            continue
        if item.get("source") == "USGS" or "google.com" in urllib.parse.urlsplit(item.get("url", "")).netloc:
            continue
        if len(pending) < 140:
            pending.append(item)
    if not pending:
        return
    found = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(image_from_article, item["url"]): item for item in pending}
        for future in as_completed(futures):
            photo = future.result()
            if photo:
                futures[future]["image"] = photo
                found += 1
    print(f"Fotos reais identificadas nos artigos: {found}/{len(pending)} consultados")

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
CATEGORY_RULES = [
    ("Saúde", r"\b(?:outbreak|pandemic|vaccine|disease|epidemia|pandemia|vacina|surto|saude|salud|sante|virus)\b"),
    ("Clima e desastres", r"\b(?:earthquake|terremoto|tsunami|hurricane|furacao|huracan|flood|flooding|inundacao|inundaciones|storm|tempestade|wildfire|climate|clima|cyclone|ciclone)\b"),
    ("Segurança cibernética", r"\b(?:cyberattack|cyberattacks|ciberataque|ransomware|data breach|vazamento de dados|hacker|hackers|ciberseguranca)\b"),
    ("Conflitos", r"\b(?:war|guerra|guerre|missile|missiles|misil|misiles|misseis|airstrike|bombardeio|bombardement|military|militar|militares|ceasefire|cessar.fogo|invasion|invasao|invasion|armed forces)\b"),
    ("Economia", r"\b(?:economy|economia|inflation|inflacao|inflacion|stock market|bolsa de valores|tariff|tarifa|interest rates|taxa de juros|central bank|banco central|recession|recessao|recesion)\b"),
    ("Tecnologia", r"\b(?:artificial intelligence|inteligencia artificial|intelligence artificielle|semiconductor|semicondutor|ai regulation|regulamentacao de ia|technology|tecnologia)\b"),
]

def category(title, default):
    """Correspondência por palavras inteiras, sem confundir 'war' com 'software'."""
    normalized = "".join(
        ch for ch in unicodedata.normalize("NFD", title.lower())
        if unicodedata.category(ch) != "Mn"
    )
    return next((label for label, pattern in CATEGORY_RULES
                 if re.search(pattern, normalized, re.I)), default)

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
        coordinates = (f.get("geometry") or {}).get("coordinates") or []
        longitude = float(coordinates[0]) if len(coordinates) >= 2 else None
        latitude = float(coordinates[1]) if len(coordinates) >= 2 else None
        depth_km = float(coordinates[2]) if len(coordinates) >= 3 else None
        date = dt.datetime.fromtimestamp(p["time"] / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z") if p.get("time") else ""
        result.append({"title": f"Terremoto de magnitude {mag:.1f} — {place}",
                       "summary": "Evento sísmico registrado pelo USGS. Consulte a fonte oficial para localização, profundidade e atualizações.",
                       "category": "Clima e desastres", "region": place, "country": "GLOBAL",
                       "source": "USGS", "url": p.get("url", ""), "date": date,
                       "lat": latitude, "lon": longitude, "depth_km": depth_km,
                       "forcedSev": "crit" if mag >= 7 else "high" if mag >= 6 else "med" if mag >= 5 else "low"})
    return result
# Dois provedores para ampliar a cobertura. O segundo usa um endpoint público
# não documentado; se falhar/bloquear, preservamos a notícia e tentamos novamente
# em uma atualização futura, sem inventar tradução.
TRANSLATION_DISABLED = set()
TRANSLATION_METRICS = {"mymemory": 0, "google_web": 0, "failed": 0}

def translate_mymemory(text, lang):
    if "mymemory" in TRANSLATION_DISABLED:
        return ""
    params = urllib.parse.urlencode({"q": text[:440], "langpair": f"{lang}|pt-BR"})
    req = urllib.request.Request(
        "https://api.mymemory.translated.net/get?" + params,
        headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=7) as response:
            data = json.load(response)
        status = int(data.get("responseStatus") or 200)
        message = str(data.get("responseDetails") or "")
        if status != 200 or re.search(r"quota|limit|blocked|daily|exceeded", message, re.I):
            TRANSLATION_DISABLED.add("mymemory")
            return ""
        translated = (data.get("responseData") or {}).get("translatedText") or ""
        translated = clean(translated)
        if not translated or re.search(r"MYMEMORY WARNING|QUOTA EXCEEDED|TOO MANY REQUESTS", translated, re.I):
            TRANSLATION_DISABLED.add("mymemory")
            return ""
        return translated if translated.lower() != text.lower() else ""
    except Exception:
        # Um erro isolado não torna a fonte permanentemente indisponível.
        return ""

def translate_google_web(text, lang):
    if "google_web" in TRANSLATION_DISABLED:
        return ""
    params = urllib.parse.urlencode({
        "client": "gtx", "sl": lang, "tl": "pt", "dt": "t", "q": text[:650]})
    req = urllib.request.Request(
        "https://translate.googleapis.com/translate_a/single?" + params,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AlertaGlobal/2.1)",
            "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            parts = json.load(response)
        translated = clean("".join(str(segment[0] or "") for segment in parts[0]
                                   if isinstance(segment, list) and segment))
        return translated if translated and translated.lower() != text.lower() else ""
    except urllib.error.HTTPError as err:
        if err.code in (401, 403, 429):
            TRANSLATION_DISABLED.add("google_web")
        return ""
    except Exception:
        return ""

def translate(text, lang):
    """Traduz para pt-BR, sem substituir o texto original se houver falha."""
    text = clean(text)
    if not text or lang in ("pt", "pt-BR"):
        return text
    for name, fn in (("mymemory", translate_mymemory),
                     ("google_web", translate_google_web)):
        result = fn(text, lang)
        if result:
            TRANSLATION_METRICS[name] += 1
            return result
    TRANSLATION_METRICS["failed"] += 1
    return ""

def main():
    data = []
    success = 0
    feed_report = {}
    # Várias fontes: consultas paralelas para não aumentar demais o tempo do workflow.
    # Cada fonte é independente: falhas em um RSS não interrompem os demais.
    with ThreadPoolExecutor(max_workers=8) as executor:
        jobs = {
            executor.submit(parse_feed, source, url, cat, country, lang): (source, url)
            for source, url, cat, country, lang in FEEDS
        }
        for job in as_completed(jobs):
            source, url = jobs[job]
            try:
                articles = job.result()
                print(f"{source}: {len(articles)} notícias ({url})")
                data.extend(articles)
                success += 1
                record = feed_report.setdefault(source, {"success": 0, "failed": 0, "collected": 0})
                record["success"] += 1
                record["collected"] += len(articles)
            except Exception as err:
                record = feed_report.setdefault(source, {"success": 0, "failed": 0, "collected": 0})
                record["failed"] += 1
                print(f"FALHA em {source} ({url}): {err}")
    try:
        quakes = earthquakes()
        data.extend(quakes)
        success += 1
        print(f"USGS: {len(quakes)} terremotos")
        feed_report["USGS"] = {"success": 1, "failed": 0, "collected": len(quakes)}
    except Exception as err:
        feed_report["USGS"] = {"success": 0, "failed": 1, "collected": 0}
        print(f"FALHA no USGS: {err}")
    if not success:
        raise SystemExit("Todas as fontes falharam; preservando o JSON anterior.")
    unique = {}
    for item in data:
        key = re.sub(r"\W+", "", item["title"].lower())[:100]
        if key and key not in unique:
            unique[key] = item
    # Diversidade editorial: preservar mais veículos e até 500 registros.
    # Não sobrescrever o feed anterior se todos os veículos jornalísticos falharem.
    editorial_count = sum(1 for item in unique.values() if item.get("source") != "USGS")
    if editorial_count < 12 and OUT.exists():
        raise SystemExit("Coleta editorial insuficiente; preservando o feed anterior.")
    sorted_items = []
    by_source = {}
    for item in sorted(unique.values(), key=lambda x: x.get("date", ""), reverse=True):
        source = item.get("source", "")
        limit = 35 if source == "USGS" else 55
        if by_source.get(source, 0) >= limit:
            continue
        sorted_items.append(item)
        by_source[source] = by_source.get(source, 0) + 1
        if len(sorted_items) >= MAX_ARTICLES:
            break
    if not sorted_items:
        raise SystemExit("Nenhuma notícia coletada; preservando o JSON anterior.")
    print(f"Fontes diferentes no painel: {len(by_source)}. Distribuição: {by_source}")
    # Tradução progressiva e com cache. Respeita limites do serviço gratuito.
    cache = {}
    if OUT.exists():
        try:
            for old in json.loads(OUT.read_text(encoding="utf-8")):
                cache[old.get("title", "")] = old
        except (ValueError, TypeError):
            pass
    enrich_article_images(sorted_items, cache)
    # Títulos primeiro para evitar o Radar Mundial com manchetes em outros idiomas.
    # Reaproveita traduções anteriores; limita novas chamadas por execução.
    # Traduções são incrementais: cache preservado e orçamento por execução.
    # Títulos recebem prioridade para evitar cards multilíngues; resumos são
    # completados gradualmente, sem disparar centenas de requisições por rodada.
    title_budget = 130
    summary_budget = 130
    title_count = 0
    summary_count = 0

    for item in sorted_items:
        previous = cache.get(item["title"], {})
        if not item.get("image") and previous.get("image"):
            item["image"] = previous["image"]
        lang = item.get("lang", "")
        if lang == "pt":
            item["title_pt"] = item["title"]
            item["summary_pt"] = item["summary"]
            continue
        if not lang or item.get("source") == "USGS":
            continue
        if previous.get("title_pt"):
            item["title_pt"] = previous["title_pt"]
        elif title_budget > 0 and item.get("title"):
            title_budget -= 1
            value = translate(item["title"], lang)
            if value:
                item["title_pt"] = value
                title_count += 1
        if previous.get("summary_pt"):
            item["summary_pt"] = previous["summary_pt"]

    # Priorizamos resumos de acontecimentos mais importantes; matérias
    # secundárias ainda mantêm o resumo original se não houver tradução.
    for item in sorted_items:
        if summary_budget <= 0:
            break
        if item.get("summary_pt") or not item.get("summary") or item.get("lang") in ("pt", "", None):
            continue
        summary_budget -= 1
        value = translate(item["summary"][:340], item["lang"])
        if value:
            item["summary_pt"] = value
            summary_count += 1

    print(f"Traduções novas: {title_count} títulos e {summary_count} resumos")
    print(f"Serviços de tradução: {TRANSLATION_METRICS}. Indisponíveis: {sorted(TRANSLATION_DISABLED)}")
    print(f"Total em português: {sum(bool(i.get('title_pt') or i.get('lang') == 'pt' or i.get('source') == 'USGS') for i in sorted_items)} títulos, "
          f"{sum(bool(i.get('summary_pt') or i.get('lang') == 'pt' or i.get('source') == 'USGS') for i in sorted_items)} resumos")

    OUT.write_text(json.dumps(sorted_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_data = []
    for source in sorted(feed_report):
        report = feed_report[source]
        source_items = [item for item in sorted_items if item.get("source") == source]
        dated = [item["date"] for item in source_items if item.get("date")]
        source_data.append({
            "name": source,
            "count": len(source_items),
            "collected": report["collected"],
            "working_feeds": report["success"],
            "failed_feeds": report["failed"],
            "status": ("online" if report["success"] and not report["failed"] else
                       "parcial" if report["success"] else "indisponivel"),
            "latest_article_at": max(dated) if dated else None,
            "checked_at": NOW.isoformat().replace("+00:00", "Z"),
        })
    # status_fontes.json descreve a execução do coletor, não confirma que
    # todos os veículos publicaram notícias novas naquele momento.
    status = {
        "updated_at": NOW.isoformat().replace("+00:00", "Z"),
        "total": len(sorted_items),
        "total_sources": sum(bool(item["count"]) for item in source_data),
        "translated_titles": sum(bool(item.get("title_pt") or item.get("source") == "USGS") for item in sorted_items),
        "translated_summaries": sum(bool(item.get("summary_pt") or item.get("source") == "USGS") for item in sorted_items),
        "with_images": sum(bool(item.get("image")) for item in sorted_items),
        "sources": source_data,
    }
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravadas {len(sorted_items)} ocorrências em {OUT.name} com status em {STATUS_OUT.name}")
if __name__ == "__main__":
    main()
