#!/usr/bin/env python3
"""Janela móvel de 15 dias para alertas ChatGPT e notícias RSS arquivadas.

Os arquivos vigentes deixam de mostrar registros antigos. O histórico de commits
do GitHub permanece intacto; remoção definitiva de commits exige outra solução.
"""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CURATION = ROOT / "curadoria-chatgpt.json"
ARCHIVE_DIR = ROOT / "historico"
INDEX = ARCHIVE_DIR / "indice.json"
TIMEZONE = ZoneInfo("America/Boa_Vista")
UTC = dt.timezone.utc
RETENTION_DAYS = 15
CUTOFF = dt.datetime.now(UTC) - dt.timedelta(days=RETENTION_DAYS)


def parse_datetime(value):
    """Aceita ISO com fuso, dd/mm/aaaa e hora local. Data só vale até o fim do dia."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            # Strings no formato YYYY-MM-DD representam o dia completo, no fuso do usuário.
            if len(value) == 10:
                parsed = parsed.replace(hour=23, minute=59, second=59, tzinfo=TIMEZONE)
            else:
                parsed = parsed.replace(tzinfo=TIMEZONE)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        pass
    # Formatos legados: "16/11/2026" ou "16/11/2026 03:45 (Boa Vista ...)"
    import re
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?", value)
    if m:
        day, month, year, hour, minute = m.groups()
        try:
            local = dt.datetime(int(year), int(month), int(day),
                                int(hour) if hour else 23,
                                int(minute) if minute else 59,
                                0 if hour else 59, tzinfo=TIMEZONE)
            return local.astimezone(UTC)
        except ValueError:
            return None
    return None


def article_date(article, *, curated=False):
    if curated:
        # saved_at data da chegada ao ChatGPT/site (não da publicação).
        # Registros antigos não tinham este campo, portanto herdamos a data da matéria.
        for field in ("saved_at", "published_at", "published_on"):
            timestamp = parse_datetime(article.get(field))
            if timestamp:
                return timestamp
        return None
    return parse_datetime(article.get("date"))


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def prune_curation(now):
    if not CURATION.exists():
        return 0
    original = json.loads(CURATION.read_text(encoding="utf-8"))
    items = original.get("items", [])
    if not isinstance(items, list):
        raise ValueError("curadoria-chatgpt.json: items não é lista")
    dedupe = set()
    retained = []
    for article in items:
        if not isinstance(article, dict):
            continue
        date = article_date(article, curated=True)
        url = (article.get("url") or "").strip().lower().split("#", 1)[0]
        if not date or date < CUTOFF or date > now + dt.timedelta(hours=4):
            continue
        if not url or url in dedupe:
            continue
        dedupe.add(url)
        retained.append(article)
    # Ordem de chegada, sem limite de 40: apenas tempo e deduplicação.
    original["retention_days"] = RETENTION_DAYS
    original["retention_policy"] = "rolling_window"
    original["items"] = retained
    if retained != items or "retention_days" not in json.loads(CURATION.read_text(encoding="utf-8")):
        original["updated_at"] = now.isoformat().replace("+00:00", "Z")
        save_json(CURATION, original)
    return len(retained)


def prune_rss_history(now):
    if not ARCHIVE_DIR.exists():
        return 0
    months = []
    total = 0
    for path in sorted(ARCHIVE_DIR.glob("????-??.json"), reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        old_items = data.get("items", [])
        if not isinstance(old_items, list):
            raise ValueError(f"{path}: items não é lista")
        clean = [item for item in old_items if isinstance(item, dict)
                 and (timestamp := article_date(item))
                 and CUTOFF <= timestamp <= now + dt.timedelta(hours=4)]
        if not clean:
            path.unlink()
            continue
        clean.sort(key=lambda item: item.get("date", ""), reverse=True)
        if clean != old_items:
            data["items"] = clean
            save_json(path, data)
        month = path.stem
        months.append({"month": month, "path": f"historico/{path.name}",
                       "count": len(clean), "latest_at": clean[0].get("date", "")})
        total += len(clean)
    indexed = {"version": 1, "total": total, "months": months,
               "retention_days": RETENTION_DAYS,
               "retention_policy": "rolling_window"}
    previous = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    # Carimbo de atualização apenas quando conteúdo realmente mudar.
    compare = {key: previous.get(key) for key in indexed}
    if compare != indexed:
        indexed["updated_at"] = now.isoformat().replace("+00:00", "Z")
        save_json(INDEX, indexed)
    return total


def main():
    now = dt.datetime.now(UTC)
    curated = prune_curation(now)
    articles = prune_rss_history(now)
    print(f"Retenção móvel de {RETENTION_DAYS} dias: "
          f"{curated} alertas ChatGPT e {articles} notícias RSS no acervo.")


if __name__ == "__main__":
    main()
