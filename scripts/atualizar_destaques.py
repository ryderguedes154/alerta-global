#!/usr/bin/env python3
"""Atualiza os destaques do Radar Mundial usando notícias reais do RSS coletado."""
import datetime as dt
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "noticias.json"
OUT = ROOT / "destaques-radar.json"
TIMEZONE = ZoneInfo("America/Boa_Vista")
UTC = dt.timezone.utc
MAX_AGE_HOURS = 36
MAX_HIGHLIGHTS = 8

# A escolha é automática e baseada na manchete de fontes jornalísticas,
# nunca em geração de fatos, previsões ou relatos sem link original.
TRUSTED_SOURCES = {
    "Associated Press", "Reuters", "BBC News", "The Guardian", "France 24",
    "Deutsche Welle", "DW Brasil", "Le Monde", "El País", "G1 Mundo",
    "CNN Brasil", "Agência Brasil", "Al Jazeera", "NHK World", "NPR",
    "Sky News", "The New York Times", "CBS News", "Euronews", "USGS"
}
BLOCKED = re.compile(
    r"\b(?:futebol|football|soccer|basquete|basketball|hipopotamo|"
    r"cinema|ator|atriz|celebridade|celebrity|receita|recipe|"
    r"campeonato|championship|moda|fashion|esportes|sports|"
    r"novela|telenovela|oscar|super bowl|tennis|tenis)\b"
)
IMPORTANT_PATTERNS = (
    (12, r"\b(?:guerra nuclear|nuclear war|acidente nuclear|nuclear accident|"
         r"tsunami|pandemia|pandemic|cyberattack|ciberataque|ransomware|"
         r"terremoto|earthquake)\b"),
    (9, r"\b(?:guerra|war|conflict|conflito|ataques?|attacks?|"
        r"misseis|missiles?|bombardeio|bombing|airstrikes?|"
        r"san[cç][oõ]es|sanctions?|cessar.fogo|ceasefire|invas[aã]o|invasion|"
        r"militar(?:es)?|military|armas? autonom|autonomous weapons|"
        r"energia|energy crisis|power grid|apag[aã]o|blackout)\b"),
    (8, r"\b(?:cop31|clima|climate|global|mundial|"
        r"chanceler|president|presidente|"
        r"uni[aã]o europeia|european union|europa|nato|otan|"
        r"onu|united nations|nacoes unidas|g7|g20|"
        r"russia|r[uú]ssia|ucr[aâ]nia|ukraine|china|"
        r"trump|putin|xi jinping|israel|ir[aã]|iran|"
        r"orbital|space mission|sat[eé]lite|satellite)\b"),
    (7, r"\b(?:petr[oó]leo|oil prices?|natural gas|g[aá]s natural|"
        r"economia|economy|infla[cç][aã]o|inflation|recess[aã]o|recession|"
        r"juros|interest rates?|tarifas?|tariffs?|trade|com[eé]rcio|"
        r"embargo|mercado global|world market|"
        r"semicondutores|semiconductors?|intelig[eê]ncia artificial|"
        r"artificial intelligence|ai chips?|export controls?|"
        r"sa[uú]de p[uú]blica|public health|epidemia|outbreak|"
        r"enchentes?|floods?|furac[aã]o|hurricane|"
        r"imigrantes?|migrants?|refugiados?|refugees?)\b"),
)
STOP = set("para pelos pelas uma umas uns por que como ainda com sobre contra entre desde"
           " dos das nas nos estao esta este esse isso seus suas seus mundo global"
           " after with from into their which says said amid have will what when".split())


def normalized(value):
    raw = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(c for c in raw if unicodedata.category(c) != "Mn")


def parsed_date(value):
    try:
        result = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            return None
        return result.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def category_of(item, text):
    if item.get("source") == "USGS":
        return "Clima e desastres"
    categories = (
        ("Segurança cibernética", r"\b(?:ciberataque|cyberattack|ransomware|hackers?|data breach)\b"),
        ("Clima e desastres", r"\b(?:cop31|clima|climate|terremoto|earthquake|"
         r"tsunami|furac[aã]o|floods?|inunda[cç][oõ]es|queimadas|wildfires?)\b"),
        ("Saúde", r"\b(?:pandemia|pandemic|epidemia|outbreak|oms|who|sa[uú]de|health)\b"),
        ("Economia", r"\b(?:petr[oó]leo|oil|gas|g[aá]s natural|economia|economy|"
         r"inflation|infla[cç][aã]o|tariffs?|tarifas?|com[eé]rcio|trade|"
         r"bancos?|banks?|mercados?|markets?)\b"),
        ("Tecnologia", r"\b(?:intelig[eê]ncia artificial|artificial intelligence|"
         r"chips?|semicondutores|semiconductors?|technology|tecnologia|sat[eé]lite)\b"),
        ("Conflitos", r"\b(?:guerra|war|attacks?|ataques?|bombardeio|missiles?|"
         r"misseis|militar|military|armas|sanctions?|san[cç][oõ]es|"
         r"ucrania|ukraine|russia|israel|iran)\b")
    )
    for name, pattern in categories:
        if re.search(pattern, text, re.I):
            return name
    existing = item.get("category", "Geral")
    return existing if existing in ("Conflitos", "Saúde", "Clima e desastres",
                                   "Segurança cibernética", "Economia", "Tecnologia") else "Geral"


def topic_tokens(text):
    return set(w for w in re.findall(r"[a-z]{4,}", normalized(text))
               if w not in STOP and not w.isdigit())


def redundant(title, selected):
    tokens = topic_tokens(title)
    for candidate in selected:
        existing = topic_tokens(candidate["title"])
        overlap = len(tokens & existing)
        if overlap >= 5 and overlap / max(1, min(len(tokens), len(existing))) >= 0.65:
            return True
    return False


def article_candidate(item, now):
    source = item.get("source", "")
    if source not in TRUSTED_SOURCES:
        return None
    url = item.get("url", "")
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            return None
        if parsed.hostname in ("news.google.com", "google.com", "www.google.com"):
            # Links intermediários não substituem a URL da matéria original.
            return None
    except (TypeError, ValueError):
        return None
    date = parsed_date(item.get("date"))
    if not date:
        return None
    age = (now - date).total_seconds() / 3600
    if not -1 <= age <= MAX_AGE_HOURS:
        return None
    title = (item.get("title_pt") if item.get("lang") != "pt"
             else item.get("title")) or ""
    summary = (item.get("summary_pt") if item.get("lang") != "pt"
               else item.get("summary")) or ""
    if source == "USGS":
        title = item.get("title", "")
        summary = item.get("summary", "")
        match = re.search(r"magnitude\s+(\d+(?:[.,]\d+)?)", title, re.I)
        if not match or float(match.group(1).replace(",", ".")) < 6.0:
            return None
    if not title or not summary:
        return None  # Sem tradução disponível: esperar a próxima coleta.
    heading = normalized(title)
    if BLOCKED.search(heading) or re.match(r"^(?:ao vivo|live:|live\s)", heading):
        return None
    text = normalized(title + " " + summary)
    title_score = sum(weight for weight, pattern in IMPORTANT_PATTERNS
                      if re.search(pattern, heading, re.I))
    if source == "USGS":
        title_score += 5
    if title_score < 8:
        return None
    category = category_of(item, text)
    if category == "Geral" and title_score < 12:
        return None
    # Bônus de atualidade sem transformar notícias antigas em notícias de hoje.
    score = title_score + max(0, 4 - int(age // 6))
    if source in ("Associated Press", "Reuters", "BBC News", "USGS"):
        score += 2
    posted = date.astimezone(TIMEZONE).strftime("%d/%m/%Y %H:%M")
    return {
        "score": score, "date": date, "article": {
            "title": title.strip()[:180],
            "summary": summary.strip()[:360],
            "impact_br": "Impactos específicos no Brasil não foram avaliados automaticamente. Consulte a matéria original.",
            "category": category,
            "region": item.get("region") or "Global",
            "country": item.get("country") or "GLOBAL",
            "source": source,
            "url": url,
            "published_on": posted + " (Boa Vista)",
            "image": item.get("image") or "",
            "selection": "automatic",
        }
    }


def main():
    if not NEWS.exists():
        raise SystemExit("Arquivo noticias.json ausente; mantendo destaques existentes.")
    news = json.loads(NEWS.read_text(encoding="utf-8"))
    if not isinstance(news, list) or len(news) < 12:
        raise SystemExit("Coleta insuficiente; mantendo destaques anteriores.")
    now = dt.datetime.now(UTC)
    candidates = [article_candidate(item, now) for item in news]
    candidates = [candidate for candidate in candidates if candidate]
    candidates.sort(key=lambda item: (item["score"], item["date"]), reverse=True)
    selected, used_urls = [], set()
    by_category = {}
    by_source = {}
    for candidate in candidates:
        item = candidate["article"]
        if item["url"] in used_urls or redundant(item["title"], selected):
            continue
        cat, source = item["category"], item["source"]
        if by_category.get(cat, 0) >= (3 if cat == "Conflitos" else 2):
            continue
        if by_source.get(source, 0) >= 3:
            continue
        selected.append(item)
        used_urls.add(item["url"])
        by_category[cat] = by_category.get(cat, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1
        if len(selected) >= MAX_HIGHLIGHTS:
            break
    if len(selected) < 3:
        print("Menos de três destaques confiáveis e traduzidos; preservando lista anterior.")
        if OUT.exists():
            try:
                previous = json.loads(OUT.read_text(encoding="utf-8"))
                if isinstance(previous.get("items"), list) and previous["items"]:
                    previous["checked_at"] = now.isoformat().replace("+00:00", "Z")
                    previous["status"] = "sem_novas_materias_relevantes"
                    OUT.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except (ValueError, TypeError):
                pass
        return
    edition = now.astimezone(TIMEZONE).strftime("%d/%m/%Y")
    output = {
        "edition": edition,
        "description": ("Seleção automática de manchetes publicadas por fontes jornalísticas "
                        "e oficiais, com links originais. As informações devem ser "
                        "confirmadas na fonte e podem ser atualizadas."),
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "status": "checado",
        "items": selected
    }
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            old_keys = [x.get("url") for x in old.get("items", [])]
            new_keys = [x["url"] for x in selected]
            if old.get("edition") == edition and old_keys == new_keys:
                # Checagem executada sem novidade: preservar os resumos já publicados.
                # Atualizar somente o registro da última verificação, não a data da matéria.
                old["checked_at"] = output["checked_at"]
                old["status"] = "sem_novas_materias_relevantes"
                OUT.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("Checagem concluída; nenhuma manchete nova entre os destaques.")
                return
        except (ValueError, TypeError):
            pass
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Atualizados {len(selected)} destaques automáticos do Radar Mundial para {edition}.")


if __name__ == "__main__":
    main()
