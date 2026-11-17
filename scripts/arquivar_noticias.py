#!/usr/bin/env python3
"""Acrescenta notícias públicas do RSS ao histórico mensal, sem apagar as anteriores."""
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "noticias.json"
ARCHIVE = ROOT / "historico"
INDEX = ARCHIVE / "indice.json"
FIELDS = ("title", "title_pt", "summary", "summary_pt", "category", "region",
          "country", "source", "url", "date", "lang", "image", "forcedSev",
          "lat", "lon", "depth_km")
IGNORED_QUERY = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                 "utm_content", "fbclid", "gclid", "at_medium", "at_campaign"}


def key_for(url):
    try:
        bits = urlsplit(url)
        if bits.scheme not in ("http", "https") or not bits.hostname:
            return ""
        query = urlencode([(k, v) for k, v in parse_qsl(bits.query, keep_blank_values=True)
                           if k.lower() not in IGNORED_QUERY])
        return urlunsplit((bits.scheme.lower(), bits.netloc.lower(),
                           bits.path.rstrip("/") or "/", query, ""))
    except (TypeError, ValueError):
        return ""


def month_for(value):
    try:
        when = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if when.tzinfo is None:
            return ""
        return when.astimezone(dt.timezone.utc).strftime("%Y-%m")
    except (TypeError, ValueError, OverflowError):
        return ""


def load(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")


def normalize(article):
    return {field: article[field] for field in FIELDS if article.get(field) not in (None, "")}


def merge(existing, incoming):
    # Preserva o registro publicado, mas complementa traduções/imagens posteriores.
    output = dict(existing)
    for field, value in incoming.items():
        if field not in output or not output[field]:
            output[field] = value
    return output


def main():
    current = load(NEWS, [])
    if not isinstance(current, list) or not current:
        raise SystemExit("Feed vazio: histórico anterior preservado.")
    buckets = {}
    for article in current:
        if not isinstance(article, dict):
            continue
        month = month_for(article.get("date"))
        identity = key_for(article.get("url"))
        if month and identity:
            buckets.setdefault(month, []).append(article)
    if not buckets:
        raise SystemExit("Sem links e datas válidas: histórico anterior preservado.")

    previous = load(INDEX, {"version": 1, "months": []})
    previous_months = {row["month"]: row for row in previous.get("months", [])
                       if isinstance(row, dict) and row.get("month")}
    changed = False
    new_articles = 0
    for month, articles in sorted(buckets.items()):
        path = ARCHIVE / (month + ".json")
        old = load(path, {"month": month, "items": []})
        existing = {key_for(article.get("url")): article
                    for article in old.get("items", [])
                    if isinstance(article, dict) and key_for(article.get("url"))}
        month_changed = False
        for article in articles:
            identity = key_for(article["url"])
            candidate = normalize(article)
            if identity not in existing:
                existing[identity] = candidate
                new_articles += 1
                month_changed = True
            else:
                refreshed = merge(existing[identity], candidate)
                if refreshed != existing[identity]:
                    existing[identity] = refreshed
                    month_changed = True

        sorted_items = sorted(existing.values(), key=lambda row: row.get("date", ""),
                              reverse=True)
        if month_changed or not path.exists():
            save(path, {"month": month, "items": sorted_items})
            changed = True
        previous_months[month] = {
            "month": month,
            "path": "historico/" + month + ".json",
            "count": len(sorted_items),
            "latest_at": sorted_items[0].get("date", "") if sorted_items else ""
        }

    months = sorted(previous_months.values(), key=lambda row: row["month"], reverse=True)
    index = {"version": 1, "total": sum(int(row.get("count", 0)) for row in months),
             "months": months}
    # Não reescrever o índice se nada mudou: evita commits repetidos a cada 5 minutos.
    if {key: previous.get(key) for key in index} != index or not INDEX.exists():
        index["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        save(INDEX, index)
        changed = True
    print(f"Histórico: {index['total']} matérias, {len(months)} meses, "
          f"{new_articles} novas, alterações={changed}.")


if __name__ == "__main__":
    main()
