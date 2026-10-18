"""Agente 3 — Redator.

Escreve o texto de cada oferta no tom da marca (gancho, dica de chef, benefícios, roteiro de vídeo)
e formata a versão certa para cada canal. Usa IA gratuita quando há chave; senão, templates.
"""
from __future__ import annotations

import html
import random
import zlib

from .. import llm
from ..core import brl, cfg, clean_title, get_logger, load_json, public_base_url, save_json, tema_atual

log = get_logger("redator")

PROMPT = """Você é o redator da página "{marca}", de achadinhos para gatos escolhidos por quem convive com eles.
Tom de voz: {tom}
Tema comercial do momento: {tema}

Produto (dados reais do marketplace — NÃO invente características que não estejam no título):
- Título: {titulo}
- Preço: {preco}
- Desconto: {desconto}
- Avaliação: {nota} estrelas, {vendas} vendidos
{nota_chef}
Responda SOMENTE um JSON com as chaves:
"titulo_curto": nome do produto em até 38 caracteres, sem marca e sem exagero;
"gancho": frase de abertura de até 60 caracteres que fala de um problema real de quem tem gato;
"dica_chef": 1 ou 2 frases (até 200 caracteres) com uma dica prática de quem entende de gato (comportamento, saúde ou enriquecimento ambiental) relacionada a esse tipo de produto;
"beneficios": lista com 3 benefícios curtos (até 45 caracteres cada), coerentes com o título;
"video": objeto com 3 falas para narrar um Reels de 15 segundos. Escreva para serem FALADAS em voz alta, em tom de conversa de quem tem gato (pode usar "tá", "pra", "olha"), frases curtas, sem siglas: {{"gancho": até 55 caracteres, uma pergunta ou frase que prende nos 2 primeiros segundos sobre um problema real de quem tem gato, terminando com ? ou . (pode fechar com "Olha isso."); "produto": até 70 caracteres, diz o que é o produto e UMA vantagem que esteja no título; "dica": até 14 palavras, a dica mais útil, direto ao ponto, sem repetir o gancho}};
"hashtags": lista com 5 hashtags em português sem acento, relevantes.
Proibido: CAPS LOCK, "corre", urgência falsa, promessas de saúde, citar concorrentes."""

GANCHOS = [
    "Isso aqui resolve um problema chato com o gato",
    "O item que eu mais uso com o meu gato",
    "Achado que vale cada centavo",
    "Parece bobo, mas muda a rotina com o gato",
    "Mimos pro gato gastando pouco",
]
DICAS = {
    "arranhador": "Gato precisa arranhar, não tem jeito. Dê um arranhador firme e alto: ele marca o território e para de atacar o sofá.",
    "torre": "Gato adora altura pra observar. Uma torre perto da janela vira o posto favorito e ainda gasta energia.",
    "fonte": "Gato bebe pouca água por instinto. Fonte com água corrente aumenta o consumo e ajuda a prevenir problema renal.",
    "bebedouro": "Deixe a água longe da comida: gato instintivamente desconfia de água perto do que come.",
    "comedouro": "Comedouro elevado e antiderrapante evita que o gato empurre o pote e melhora a postura pra comer.",
    "areia": "Regra de ouro: uma caixa de areia por gato, mais uma. Limpe todo dia — gato limpo recusa caixa suja.",
    "tapete": "Tapete higiênico é pra gato que faz xixi em pé ou filhote. Trocar com frequência evita cheiro.",
    "escova": "Escovar todo dia reduz bola de pelo e é um carinho pro gato. Comece cedo pra ele acostumar.",
    "rasqueadeira": "Rasqueadeira no poste onde ele já se esfrega funciona melhor que uma comprada e esquecida no canto.",
    "brinquedo": "Cinco minutos de brincadeira com varinha, todo dia, resolve tédio e destrói menos a casa.",
    "laser": "O laser empolga, mas termine jogando um brinquedo de verdade: gato precisa pegar algo de vez em quando.",
    "catnip": "Catnip dá uma moleza gostosa em uns e não faz efeito em outros. Teste e veja se o seu gato é do time.",
    "cama": "Gato dorme onde é quente e alto. Cama perto do seu canto favorito tem muito mais chance de ser usada.",
    "casinha": "Toca é refúgio: deixe num canto tranquilo, nunca num lugar de passagem. Gato quer sossego.",
    "mochila": "Acostume devagar: deixe a mochila aberta em casa com um petisco dentro antes de qualquer viagem.",
    "transporte": "Deixe a bolsa de transporte sempre à vista em casa — gato que conhece a caixa viaja sem estresse.",
    "tela": "Gato na janela sem tela é risco de queda. A tela de proteção é o item mais barato pra evitar uma tragédia.",
    "coleira": "Coleira com elástico de segurança solta se enroscar. Ponha bem folgada, cabendo dois dedos.",
    "petisco": "Petisco é a melhor ferramenta de treino: recompense na hora e o gato aprende rápido.",
    "torre arranhador": "Uma torre junta o melhor dos dois: altura pra observar e corda pra arranhar. Ganha o gato e ganha o sofá.",
}


def _dica(titulo: str) -> str:
    t = titulo.lower()
    for k, v in DICAS.items():
        if k in t:
            return v
    return "Um gato entretido e bem cuidado dá trabalho zero. Vale a pena escolher a ferramenta certa pro seu companheiro."


GANCHOS_VIDEO = [
    "Isso resolve um problema chato com o gato.",
    "Parece bobo, mas muda a rotina com o gato.",
    "Olha esse achado pro seu gato.",
    "Mimos pro gato gastando pouco? Olha isso.",
    "Achado que vale cada centavo.",
]


def _dica_curta(texto: str, max_palavras: int = 18) -> str:
    """Trecho da dica enxuto para ser falado em ~6 segundos (junta frases curtas, cortando na pontuação)."""
    frases = [f.strip() for f in texto.strip().split(". ") if f.strip()]
    frase = frases[0] if frases else ""
    if len(frase.split()) < 8 and len(frases) > 1:
        segunda = frases[1]
        if len(frase.split()) + len(segunda.split()) <= 18:
            frase = f"{frase.rstrip('.')}. {segunda}"
        elif len(segunda.split()) <= max_palavras:
            frase = segunda
    palavras = frase.split()
    if len(palavras) > 22:
        corte = " ".join(palavras[:max_palavras])
        pos = max(corte.rfind(","), corte.rfind(":"), corte.rfind(";"))
        frase = (corte[:pos] if pos > len(corte) * 0.5 else corte).rstrip(",;:")
    return frase if frase.endswith((".", "!", "?")) else frase + "."


def _template(o: dict) -> dict:
    rnd = random.Random(zlib.crc32(o["id"].encode()))
    curto = clean_title(o["titulo"], 38)
    return {
        "titulo_curto": curto,
        "gancho": rnd.choice(GANCHOS),
        "dica_chef": o.get("nota_chef") or _dica(o["titulo"]),
        "beneficios": [
            f"Nota {o['nota']:.1f} de quem comprou".replace(".", ",") if o.get("nota") else "Bem avaliado por quem comprou",
            f"{o['vendas']:,} vendidos".replace(",", ".") if o.get("vendas") else "Muito procurado",
            f"{o['desconto_pct']}% abaixo do preço cheio" if o.get("desconto_pct") else "Preço justo pelo que entrega",
        ],
        "video": {
            "gancho": rnd.choice(GANCHOS_VIDEO),
            "produto": f"{curto}.",
            "dica": _dica_curta(o.get("nota_chef") or _dica(o["titulo"])),
        },
        "hashtags": ["gatos", "gatinhos", "dicasdegato", "mundofelino", "achadinhos"],
    }


def copy(o: dict) -> dict:
    """Retorna (e guarda no pool) o texto-base da oferta."""
    if o.get("copy"):
        return o["copy"]
    marca = cfg("marca")
    c = None
    if llm.disponivel():
        c = llm.gerar_json(PROMPT.format(
            marca=marca["nome"], tom=marca["tom_de_voz"].strip(), tema=tema_atual().get("gancho", ""),
            titulo=o["titulo"], preco=brl(o.get("preco")) or "não informado",
            desconto=f"{o.get('desconto_pct', 0)}%", nota=o.get("nota", "?"), vendas=o.get("vendas", "?"),
            nota_chef=f"- Observação do tutor (use!): {o['nota_chef']}\n" if o.get("nota_chef") else "",
        ))
    base = _template(o)
    if c:
        for k in base:  # completa o que faltar
            if not c.get(k):
                c[k] = base[k]
        c["titulo_curto"] = c["titulo_curto"][:40]
        if not isinstance(c.get("video"), dict):
            c["video"] = dict(base["video"])
        for k, v in base["video"].items():  # completa falas que a IA esqueceu
            if not str(c["video"].get(k) or "").strip():
                c["video"][k] = v
            c["video"][k] = str(c["video"][k])
        c["origem"] = "ia"
    else:
        c = base
        c["origem"] = "template"
    o["copy"] = c
    pool = load_json("ofertas.json", [])
    for p in pool:
        if p["id"] == o["id"]:
            p["copy"] = c
    save_json("ofertas.json", pool)
    return c


# ------------------------------------------------------------------ formatos por canal
def _linha_preco(o: dict) -> str:
    if not o.get("preco"):
        return "Confira o preço atualizado no link."
    s = f"Por {brl(o['preco'])}"
    if o.get("preco_de") and o["preco_de"] > o["preco"]:
        s = f"De {brl(o['preco_de'])} por {brl(o['preco'])}"
    return s


def telegram(o: dict) -> str:
    """HTML do Telegram (legenda de foto, máx. 1024 caracteres)."""
    c, m = copy(o), cfg("marca")
    e = html.escape
    partes = [
        f"<b>{e(c['gancho'])}</b>",
        "",
        f"🐾 <b>{e(c['titulo_curto'])}</b>",
        f"💰 {e(_linha_preco(o))}" + (f" <i>(-{o['desconto_pct']}%)</i>" if o.get("desconto_pct") else ""),
        "",
        f"🐱 {e(c['dica_chef'])}",
        "",
        *[f"✔️ {e(b)}" for b in c["beneficios"][:3]],
        "",
        f"<i>{e(m['aviso_afiliado'])} {e(m['aviso_preco'])}</i>",
    ]
    return "\n".join(partes)[:1024]


def threads(o: dict, url: str) -> str:
    c, m = copy(o), cfg("marca")
    txt = (
        f"{c['gancho']}\n\n{c['titulo_curto']}: {_linha_preco(o)}\n\n"
        f"Dica: {c['dica_chef']}\n\n{url}\n\n{m['aviso_afiliado']}"
    )
    if len(txt.encode()) > 490:  # limite de 500 (em bytes UTF-8)
        txt = f"{c['gancho']}\n\n{c['titulo_curto']}: {_linha_preco(o)}\n\n{url}\n\n{m['aviso_afiliado']}"
    return txt


def instagram(o: dict) -> str:
    c, m = copy(o), cfg("marca")
    vitrine = public_base_url()
    tags = " ".join(["#publi"] + ["#" + h.lstrip("#") for h in c["hashtags"][:4]])
    return (
        f"{c['gancho']}\n\n"
        f"{c['titulo_curto']} | {_linha_preco(o)}\n\n"
        f"🐱 Dica: {c['dica_chef']}\n\n"
        + "\n".join(f"✔️ {b}" for b in c["beneficios"][:3])
        + f"\n\n🔗 Link na bio → procure a oferta #{o.get('numero')}"
        + (" na vitrine" if vitrine else "")
        + "\n📲 Ofertas todo dia no nosso canal do Telegram (link na bio)\n"
        f"💾 Salva pra achar depois.\n\n{m['aviso_afiliado']} {m['aviso_preco']}\n\n{tags}"
    )[:2200]


def _telegram_handle() -> str:
    url = cfg("canais").get("telegram", {}).get("url", "")
    if url:
        return url.rstrip("/").split("/")[-1].lstrip("@")
    return cfg("marca").get("arroba", "").lstrip("@")


def tiktok(o: dict) -> str:
    """Legenda para TikTok e YouTube Shorts: sem link clicável, então aponta para o Telegram."""
    c, m = copy(o), cfg("marca")
    handle = _telegram_handle()
    tags = " ".join(dict.fromkeys(["#" + h.lstrip("#") for h in c["hashtags"][:4]] + ["#achadinhos", "#fyp"]))
    return (
        f"{c['gancho']} 🐱 {c['titulo_curto']} | {_linha_preco(o)}\n\n"
        f"🔎 Link: procure \"{handle}\" no Telegram (oferta #{o.get('numero')})\n"
        f"{m['aviso_afiliado']}\n\n{tags}"
    )[:2000]


def comentario_fixado(o: dict) -> str:
    """Comentário para fixar no vídeo do TikTok/Shorts."""
    return f"🔗 O link dessa oferta (#{o.get('numero')}) tá no Telegram: procure {_telegram_handle()} 🐱"


def instagram_carrossel(ofertas: list[dict]) -> str:
    m = cfg("marca")
    linhas = [f"#{o.get('numero')} {copy(o)['titulo_curto']} | {_linha_preco(o)}" for o in ofertas]
    return (
        f"Top {len(ofertas)} achados da semana, escolhidos a dedo 🐾\n\n" + "\n".join(linhas)
        + "\n\n🔗 Todos os links na vitrine (link na bio), é só procurar o número.\n"
        f"Qual você levaria? Comenta o número 👇\n\n{m['aviso_afiliado']} {m['aviso_preco']}\n\n"
        "#gatos #gatinhos #dicasdegato #mundofelino #achadinhos"
    )


def whatsapp(ofertas_links: list[tuple[dict, str]]) -> str:
    m = cfg("marca")
    blocos = [f"🐾 *Achados do dia: {m['nome']}*\n"]
    for o, url in ofertas_links:
        c = copy(o)
        blocos.append(f"*{c['titulo_curto']}*\n{_linha_preco(o)}\n{url}\n")
    blocos.append(f"_{m['aviso_afiliado']}_")
    return "\n".join(blocos)
