"""Publica automaticamente as notícias de um site (via RSS) no Instagram.

Uso:
  python publicar.py testar     # busca notícias, gera imagem + legenda e só MOSTRA (não publica nada)
  python publicar.py preparar   # gera imagem + legenda das notícias novas e coloca em fila.json
  python publicar.py publicar   # publica no Instagram o que está em fila.json

No GitHub Actions o fluxo é: preparar -> (commit/push das imagens) -> publicar.
O Instagram exige que a imagem esteja num endereço público, por isso as imagens
são enviadas ao repositório antes de publicar.
"""

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------- configuração
PASTA = Path(__file__).resolve().parent
PASTA_IMAGENS = PASTA / "imagens"
ARQ_PUBLICADOS = PASTA / "publicados.json"
ARQ_FILA = PASTA / "fila.json"


def _env(nome, padrao=""):
    return (os.environ.get(nome) or padrao).strip()


# Fonte das notícias: todas as notícias do Alerta Global (padrão) ou um feed RSS
NOTICIAS_JSON_URL = _env(
    "NOTICIAS_JSON_URL",
    "https://raw.githubusercontent.com/ryderguedes154/alerta-global/main/noticias.json",
)
RSS_URL = _env("RSS_URL")  # se preenchido, usa o RSS no lugar do JSON
NOME_DO_SITE = _env("NOME_DO_SITE", "Alerta Global")
# O Instagram aceita no máximo 100 posts por dia pela API.
# 2 posts a cada 30 minutos = 96 por dia.
MAX_POSTS = int(_env("MAX_POSTS_POR_EXECUCAO", "2"))
IDADE_MAXIMA_HORAS = float(_env("IDADE_MAXIMA_HORAS", "6"))  # não posta notícia velha
SIM = ("sim", "s", "true", "1", "yes")
# Atenção: as fotos são dos veículos originais (CNN, BBC, Getty...) e têm direitos autorais.
USAR_IMAGEM_DA_MATERIA = _env("USAR_IMAGEM_DA_MATERIA", "sim").lower() in SIM
# "sim": o Claude reescreve a descrição. "nao": usa o título e o resumo do site como estão.
USAR_CLAUDE = _env("USAR_CLAUDE", "sim").lower() in SIM
COR_DE_FUNDO = _env("COR_DE_FUNDO", "#1a1a2e")  # usada quando não há imagem da matéria
HASHTAGS_FIXAS = _env("HASHTAGS_FIXAS")  # ex: "#noticias #minhacidade"

# Caminho 1: Make.com (o Make publica no Instagram). Basta o endereço do webhook do cenário.
MAKE_WEBHOOK_URL = _env("MAKE_WEBHOOK_URL")
# Caminho 2: API oficial do Instagram (precisa de app no Meta for Developers)
IG_USER_ID = _env("IG_USER_ID")
IG_ACCESS_TOKEN = _env("IG_ACCESS_TOKEN")
# graph.instagram.com = "API do Instagram com login do Instagram" (recomendado)
# graph.facebook.com  = "API do Instagram com login do Facebook" (conta ligada a uma Página)
GRAPH_HOST = _env("GRAPH_HOST", "graph.instagram.com")
GRAPH_VERSION = _env("GRAPH_VERSION", "v23.0")

MODELO = "claude-opus-5-5"
USER_AGENT = "Mozilla/5.0 (compatible; noticias-instagram/1.0)"
LARGURA, ALTURA = 1080, 1350  # formato retrato 4:5, o que mais ocupa a tela no feed


def url_base_imagens():
    """Endereço público onde as imagens ficam (o Instagram baixa a imagem daqui)."""
    base = _env("IMAGEM_BASE_URL")
    if base:
        return base.rstrip("/")
    repo = _env("GITHUB_REPOSITORY")
    branch = _env("GITHUB_REF_NAME", "main")
    if repo:
        return f"https://raw.githubusercontent.com/{repo}/{branch}/imagens"
    sys.exit("Defina IMAGEM_BASE_URL (ou rode no GitHub Actions) para publicar.")


# ---------------------------------------------------------------- utilidades
def carregar_json(caminho, padrao):
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return padrao


def salvar_json(caminho, dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def texto_limpo(trecho_html):
    texto = BeautifulSoup(trecho_html or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


# ---------------------------------------------------------------- notícias
def buscar_noticias():
    if RSS_URL:
        return buscar_noticias_rss()
    r = requests.get(NOTICIAS_JSON_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    dados = r.json()
    itens = dados.get("items", []) if isinstance(dados, dict) else dados
    agora = datetime.now(timezone.utc)
    noticias = []
    for i in itens:
        link = i.get("url")
        titulo = i.get("title_pt") or i.get("title")
        if not link or not titulo:
            continue
        data = _ler_data(i.get("date"))
        if data and (agora - data).total_seconds() > IDADE_MAXIMA_HORAS * 3600:
            continue
        noticias.append(
            {
                "link": link,
                "titulo": texto_limpo(titulo),
                "resumo": texto_limpo(i.get("summary_pt") or i.get("summary", ""))[:3000],
                "fonte": i.get("source", ""),
                "categoria": i.get("category", ""),
                "url_imagem": melhorar_resolucao(i["image"]) if i.get("image") else None,
                "data": data,
                "entrada": {},
            }
        )
    if not noticias:
        print(f"Nenhuma notícia das últimas {IDADE_MAXIMA_HORAS:g} horas em {NOTICIAS_JSON_URL}.")
    # mais nova primeiro
    noticias.sort(key=lambda n: n["data"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return noticias


def _ler_data(texto):
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None


def melhorar_resolucao(url):
    """Os sites guardam miniaturas pequenas; pede a versão grande da mesma foto."""
    url = re.sub(r"([?&])w=\d+&?", r"\1", url).rstrip("?&")  # CNN Brasil: ?w=200
    url = re.sub(r"/ace/standard/\d+/", "/ace/standard/1024/", url)  # BBC
    return url


def buscar_noticias_rss():
    feed = feedparser.parse(RSS_URL, agent=USER_AGENT)
    if not feed.entries:
        sys.exit(f"Nenhuma notícia encontrada em {RSS_URL}. Confira se é um feed RSS válido.")
    noticias = []
    for e in feed.entries:
        link = e.get("link")
        if not link:
            continue
        resumo = e.get("summary", "")
        if e.get("content"):
            resumo = e.content[0].get("value", resumo)
        noticias.append(
            {
                "link": link,
                "titulo": texto_limpo(e.get("title", "")),
                "resumo": texto_limpo(resumo)[:3000],
                "entrada": e,
            }
        )
    return noticias  # normalmente da mais nova para a mais antiga


def endereco_imagem_da_materia(noticia):
    if noticia.get("url_imagem"):
        return noticia["url_imagem"]
    e = noticia["entrada"]
    for campo in ("media_content", "media_thumbnail"):
        for m in e.get(campo, []) or []:
            if m.get("url"):
                return m["url"]
    for enc in e.get("enclosures", []) or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    # Senão, procura a imagem de destaque (og:image) na página da matéria
    try:
        r = requests.get(noticia["link"], headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        sopa = BeautifulSoup(r.text, "html.parser")
        for atributo in ({"property": "og:image"}, {"name": "twitter:image"}):
            tag = sopa.find("meta", attrs=atributo)
            if tag and tag.get("content"):
                return tag["content"]
    except requests.RequestException as erro:
        print(f"  aviso: não consegui abrir a matéria para achar a imagem ({erro})")
    return None


def baixar_imagem(url):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as erro:  # imagem quebrada/formato estranho: segue sem imagem
        print(f"  aviso: não consegui baixar a imagem ({erro})")
        return None


# ---------------------------------------------------------------- imagem do post
def carregar_fonte(tamanho):
    candidatas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux / GitHub Actions
        "C:/Windows/Fonts/arialbd.ttf",  # Windows
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    ]
    for caminho in candidatas:
        if os.path.exists(caminho):
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default(size=tamanho)


def quebrar_linhas(desenho, texto, fonte, largura_max):
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if desenho.textlength(teste, font=fonte) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def cortar_para_preencher(img, largura, altura):
    proporcao = max(largura / img.width, altura / img.height)
    img = img.resize((round(img.width * proporcao), round(img.height * proporcao)), Image.LANCZOS)
    esq = (img.width - largura) // 2
    topo = (img.height - altura) // 2
    return img.crop((esq, topo, esq + largura, topo + altura))


def gerar_imagem(noticia, foto, destino):
    titulo = noticia["titulo"]
    if foto is not None:
        base = cortar_para_preencher(foto, LARGURA, ALTURA)
    else:
        base = Image.new("RGB", (LARGURA, ALTURA), COR_DE_FUNDO)

    # Degradê escuro na parte de baixo para o título ficar legível
    sombra = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    d = ImageDraw.Draw(sombra)
    inicio = int(ALTURA * 0.35)
    for y in range(inicio, ALTURA):
        alfa = int(235 * (y - inicio) / (ALTURA - inicio))
        d.line([(0, y), (LARGURA, y)], fill=(0, 0, 0, alfa))
    img = Image.alpha_composite(base.convert("RGBA"), sombra)

    desenho = ImageDraw.Draw(img)
    margem = 70
    tamanho = 76
    while True:
        fonte = carregar_fonte(tamanho)
        linhas = quebrar_linhas(desenho, titulo, fonte, LARGURA - 2 * margem)
        if len(linhas) <= 6 or tamanho <= 40:
            break
        tamanho -= 4

    altura_linha = int(tamanho * 1.22)
    y = ALTURA - margem - 60 - altura_linha * len(linhas)
    for linha in linhas:
        desenho.text((margem, y), linha, font=fonte, fill="white")
        y += altura_linha

    fonte_pequena = carregar_fonte(32)
    if NOME_DO_SITE:
        desenho.text((margem, ALTURA - margem - 30), NOME_DO_SITE.upper(), font=fonte_pequena, fill=(255, 210, 0))
    if noticia.get("fonte"):
        credito = f"Fonte: {noticia['fonte']}"
        largura_credito = desenho.textlength(credito, font=fonte_pequena)
        desenho.text((LARGURA - margem - largura_credito, ALTURA - margem - 30), credito,
                     font=fonte_pequena, fill=(220, 220, 220))

    # Etiqueta da categoria no topo (ex: CONFLITOS)
    categoria = (noticia.get("categoria") or "").upper()
    if categoria and categoria != "GERAL":
        caixa = desenho.textbbox((0, 0), categoria, font=fonte_pequena)
        w, h = caixa[2] - caixa[0], caixa[3] - caixa[1]
        desenho.rectangle([margem, margem, margem + w + 36, margem + h + 30], fill=(220, 30, 50))
        desenho.text((margem + 18, margem + 15 - caixa[1]), categoria, font=fonte_pequena, fill="white")

    destino.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(destino, "JPEG", quality=90)  # o Instagram só aceita JPEG


# ---------------------------------------------------------------- legenda (Claude)
INSTRUCOES = """Você é o social media de um site de notícias e escreve legendas para o Instagram em português do Brasil.

Regras:
- Escreva com as suas próprias palavras. Não copie frases do texto original.
- Comece com uma frase curta e chamativa sobre o fato principal (sem exagero nem sensacionalismo).
- Depois, 2 a 4 frases curtas explicando o essencial: o quê, quem, onde, quando.
- Seja fiel aos fatos do texto fornecido. Não invente números, nomes, datas ou declarações.
- No máximo 2 emojis, e só se combinarem com o tom da notícia (nenhum em notícias tristes ou graves).
- Termine com uma linha "📲 Leia a matéria completa: link na bio".
- Na última linha, de 3 a 5 hashtags relevantes.
- Responda APENAS com o texto da legenda, sem comentários antes ou depois."""


def rodape_legenda(noticia):
    partes = []
    if noticia.get("fonte"):
        partes.append(f"Fonte: {noticia['fonte']}")
    if NOME_DO_SITE:
        partes.append(f"via {NOME_DO_SITE}")
    rodape = " · ".join(partes)
    if HASHTAGS_FIXAS:
        rodape += f"\n{HASHTAGS_FIXAS}"
    return rodape.strip()


def legenda_simples(noticia):
    """Sem Claude: título + resumo do próprio site."""
    texto = f"{noticia['titulo']}\n\n{noticia['resumo']}".strip()
    texto += "\n\n📲 Leia a matéria completa: link na bio"
    return (texto + "\n\n" + rodape_legenda(noticia)).strip()[:2200]


def gerar_legenda(cliente, noticia):
    if cliente is None:
        return legenda_simples(noticia)
    pedido = f"Título: {noticia['titulo']}\n\nTexto da notícia:\n{noticia['resumo'] or '(sem resumo, use só o título)'}"

    resposta = cliente.beta.messages.create(
        model=MODELO,
        max_tokens=8000,
        system=INSTRUCOES,
        messages=[{"role": "user", "content": pedido}],
        output_config={"effort": "medium"},
        # Se o modelo recusar o pedido, a API tenta de novo com outro modelo automaticamente
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resposta.stop_reason == "refusal":
        raise RuntimeError("O Claude recusou gerar a legenda desta notícia.")

    legenda = "".join(b.text for b in resposta.content if b.type == "text").strip()
    rodape = rodape_legenda(noticia)
    if rodape:
        legenda += "\n\n" + rodape
    return legenda[:2200]  # limite do Instagram


# ---------------------------------------------------------------- etapas
def preparar(so_testar=False):
    publicados = carregar_json(ARQ_PUBLICADOS, [])
    fila = carregar_json(ARQ_FILA, [])
    noticias = buscar_noticias()

    if not ARQ_PUBLICADOS.exists() and not so_testar:
        # Primeira execução: não publica o histórico inteiro do site, só a notícia mais recente.
        publicados = [n["link"] for n in noticias[1:]]
        print(f"Primeira execução: {len(publicados)} notícias antigas marcadas como já vistas.")

    ja_tratados = set(publicados) | {item["link"] for item in fila}
    novas = [n for n in noticias if n["link"] not in ja_tratados][:MAX_POSTS]
    novas.reverse()  # publica da mais antiga para a mais nova

    if not novas:
        print("Nenhuma notícia nova.")
    # Sem a chave do Claude, usa título + resumo do site (não trava o robô)
    cliente = anthropic.Anthropic() if (USAR_CLAUDE and novas and _env("ANTHROPIC_API_KEY")) else None

    for noticia in novas:
        print(f"\n▶ {noticia['titulo']}\n  {noticia['link']}")
        foto = None
        if USAR_IMAGEM_DA_MATERIA:
            url_foto = endereco_imagem_da_materia(noticia)
            foto = baixar_imagem(url_foto) if url_foto else None
        nome_arquivo = hashlib.sha1(noticia["link"].encode()).hexdigest()[:12] + ".jpg"
        gerar_imagem(noticia, foto, PASTA_IMAGENS / nome_arquivo)
        legenda = gerar_legenda(cliente, noticia)

        print(f"  imagem: imagens/{nome_arquivo}\n  legenda:\n" + "\n".join("    " + l for l in legenda.splitlines()))
        fila.append({"link": noticia["link"], "titulo": noticia["titulo"], "imagem": nome_arquivo, "legenda": legenda})

    if not so_testar:
        salvar_json(ARQ_FILA, fila)
        salvar_json(ARQ_PUBLICADOS, publicados)


def _graph(metodo, caminho, **params):
    params["access_token"] = IG_ACCESS_TOKEN
    url = f"https://{GRAPH_HOST}/{GRAPH_VERSION}/{caminho}"
    r = requests.request(metodo, url, params=params if metodo == "GET" else None,
                         data=params if metodo == "POST" else None, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Erro da API do Instagram ({r.status_code}): {r.text}")
    return r.json()


def esperar_url_publica(url, limite_s=120):
    fim = time.time() + limite_s
    while time.time() < fim:
        try:
            if requests.head(url, timeout=15).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise RuntimeError(f"A imagem não ficou acessível em {url}. O repositório é público?")


def publicar_no_instagram(item, base):
    url_imagem = f"{base}/{item['imagem']}"
    esperar_url_publica(url_imagem)

    if MAKE_WEBHOOK_URL:
        # O cenário do Make recebe estes campos e cria o post no Instagram
        r = requests.post(
            MAKE_WEBHOOK_URL,
            json={"image_url": url_imagem, "caption": item["legenda"],
                  "titulo": item["titulo"], "link": item["link"]},
            timeout=120,
        )
        if not r.ok:
            raise RuntimeError(f"O Make recusou o envio ({r.status_code}): {r.text[:300]}")
        return f"enviado ao Make ({r.text.strip()[:40]})"

    container = _graph("POST", f"{IG_USER_ID}/media", image_url=url_imagem, caption=item["legenda"])
    id_container = container["id"]

    for _ in range(30):  # o Instagram processa a imagem antes de liberar a publicação
        status = _graph("GET", id_container, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"O Instagram não aceitou a imagem (status {status}).")
        time.sleep(5)

    post = _graph("POST", f"{IG_USER_ID}/media_publish", creation_id=id_container)
    return post["id"]


def publicar():
    if not MAKE_WEBHOOK_URL and not (IG_USER_ID and IG_ACCESS_TOKEN):
        sys.exit("Defina MAKE_WEBHOOK_URL (Make.com) ou IG_USER_ID + IG_ACCESS_TOKEN (API oficial).")
    fila = carregar_json(ARQ_FILA, [])
    publicados = carregar_json(ARQ_PUBLICADOS, [])
    if not fila:
        print("Fila vazia, nada para publicar.")
        return
    base = url_base_imagens()

    falhas = 0
    for item in list(fila):
        print(f"\nPublicando: {item['titulo']}")
        try:
            id_post = publicar_no_instagram(item, base)
        except Exception as erro:
            falhas += 1
            print(f"  ✗ falhou: {erro}  (fica na fila para a próxima execução)")
            continue
        print(f"  ✓ publicado (id {id_post})")
        fila.remove(item)
        publicados.append(item["link"])
        salvar_json(ARQ_FILA, fila)
        salvar_json(ARQ_PUBLICADOS, publicados)

    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "testar":
        preparar(so_testar=True)
    elif comando == "preparar":
        preparar()
    elif comando == "publicar":
        publicar()
    else:
        print(__doc__)
        sys.exit(2)
