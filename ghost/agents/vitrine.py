"""Agente 7 — Vitrine (o "link na bio").

Gera docs/index.html, uma página leve com as ofertas numeradas (#123) que o Instagram cita.
Publicada de graça pelo GitHub Pages.
"""
from __future__ import annotations

import html
import json

from ..core import DOCS_DIR, brl, cfg, env, get_logger, load_json, now, public_base_url, save_json
from . import logo, redator

log = get_logger("vitrine")
ARQ = "vitrine.json"


def adicionar(o: dict, url: str) -> None:
    """A vitrine usa a foto do próprio marketplace (CDN), que não some quando o site é republicado."""
    imagem_rel = o.get("imagem_url") if str(o.get("imagem_url", "")).startswith("http") else "placeholder.jpg"
    itens = [i for i in load_json(ARQ, []) if i["numero"] != o.get("numero")]
    itens.insert(0, {
        "numero": o.get("numero"),
        "titulo": redator.copy(o)["titulo_curto"],
        "preco": o.get("preco"),
        "preco_de": o.get("preco_de"),
        "plataforma": o["plataforma"],
        "imagem": imagem_rel,
        "link": url,
        "atualizado": now().strftime("%d/%m/%Y %H:%M"),
    })
    save_json(ARQ, itens[: cfg("canais")["vitrine"].get("max_ofertas", 60)])


CSS = """
:root{--p:%(primaria)s;--f:%(fundo)s;--t:%(texto)s;--d:%(destaque)s}
*{box-sizing:border-box}body{margin:0;background:var(--f);color:var(--t);font-family:Poppins,system-ui,sans-serif}
header{background:linear-gradient(135deg,var(--p),var(--d));color:#fff;padding:28px 18px 34px;text-align:center;
 border-radius:0 0 32px 32px;box-shadow:0 10px 28px rgba(34,27,51,.2)}
header .logo{width:76px;height:76px;border-radius:50%%;display:block;margin:0 auto 12px;background:rgba(255,255,255,.14);padding:6px}
header h1{margin:0;font-size:24px;letter-spacing:.3px}header p{margin:8px auto 0;font-size:13px;opacity:.92;max-width:420px}
.redes{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:14px auto 0;max-width:420px}
.redes a{color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:8px 16px;border-radius:999px;
 border:1.5px solid rgba(255,255,255,.5)}
.cta{display:inline-block;margin:14px auto 0;background:#fff;color:var(--p);text-decoration:none;
 padding:12px 22px;border-radius:999px;font-weight:700;box-shadow:0 6px 16px rgba(0,0,0,.18)}
.busca{max-width:760px;margin:20px auto 0;padding:0 18px}
.busca input{width:100%%;padding:15px 18px;border-radius:16px;border:2px solid #ddd2ef;font-size:16px;
 background:#fff;box-shadow:0 2px 10px rgba(108,74,182,.1)}
main{max-width:760px;margin:16px auto 0;padding:0 18px 40px;display:grid;gap:14px;grid-template-columns:repeat(2,1fr)}
.card{display:flex;flex-direction:column;background:#fff;border-radius:20px;overflow:hidden;text-decoration:none;
 color:inherit;box-shadow:0 4px 16px rgba(34,27,51,.08);transition:transform .15s ease,box-shadow .15s ease}
.card:hover{transform:translateY(-3px);box-shadow:0 10px 24px rgba(34,27,51,.15)}
.card img{width:100%%;aspect-ratio:4/5;object-fit:cover;background:#f2ecfb}
.card .corpo{padding:12px 14px 16px;display:flex;flex-direction:column;flex:1}
.n{font-weight:700;color:var(--p);font-size:13px;letter-spacing:.4px}
.t{font-weight:600;margin:4px 0 8px;line-height:1.28;font-size:14px}
.pr{font-weight:800;font-size:17px}.de{text-decoration:line-through;opacity:.45;font-size:12px;margin-right:6px}
.info{font-size:11px;opacity:.6;margin-top:4px}.bt{display:inline-block;margin-top:auto;align-self:flex-start;background:var(--d);
 color:#fff;padding:8px 14px;border-radius:999px;font-size:12px;font-weight:700}
footer{font-size:12px;opacity:.7;text-align:center;padding:0 18px 30px;max-width:760px;margin:0 auto}
@media(max-width:520px){main{grid-template-columns:1fr}.card img{aspect-ratio:16/10}}
"""


def gerar() -> None:
    m = cfg("marca")
    itens = load_json(ARQ, [])
    tg = env("TELEGRAM_CHANNEL_URL") or cfg("canais").get("telegram", {}).get("url", "")
    e = html.escape
    redes = [r for r in cfg("canais").get("redes", []) if r.get("url")]
    redes_html = "".join(
        f'<a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["nome"])}</a>' for r in redes)
    base = public_base_url()
    og_img = f"{base}/og.png" if base else "og.png"
    cards = []
    for i in itens:
        preco = ""
        if i.get("preco"):
            de = f'<span class="de">{brl(i["preco_de"])}</span>' if i.get("preco_de") else ""
            preco = f'<div>{de}<span class="pr">{brl(i["preco"])}</span></div>' \
                    f'<div class="info">Preço em {e(i["atualizado"])}, pode mudar.</div>'
        else:
            preco = '<div class="info">Confira o preço atualizado no site.</div>'
        cards.append(
            f'<a class="card" data-n="{i["numero"]}" href="{e(i["link"])}" target="_blank" rel="sponsored noopener">'
            f'<img src="{e(i["imagem"])}" alt="{e(i["titulo"])}" loading="lazy"><div class="corpo">'
            f'<div class="n">#{i["numero"]} · {e(i["plataforma"].capitalize())}</div>'
            f'<div class="t">{e(i["titulo"])}</div>{preco}'
            f'<span class="bt">Ver oferta</span></div></a>'
        )
    pagina = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(m['nome'])} | Achados</title>
<meta name="description" content="{e(m['slogan'])}">
<meta property="og:title" content="{e(m['nome'])} | Achados"><meta property="og:description" content="{e(m['slogan'])}">
<meta property="og:image" content="{e(og_img)}"><meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image"><link rel="icon" type="image/png" href="favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS % m['cores']}</style></head><body>
<header><img class="logo" src="logo.png" alt=""><h1>{e(m['nome'])}</h1><p>{e(m['slogan'])}</p>
{f'<a class="cta" href="{e(tg)}">📲 Ofertas todo dia no Telegram</a>' if tg else ''}
{f'<nav class="redes" aria-label="Redes sociais">{redes_html}</nav>' if redes_html else ''}</header>
<div class="busca"><input id="q" inputmode="numeric" placeholder="Digite o número da oferta (ex.: 12)"></div>
<main id="lista">{''.join(cards) or '<p>As primeiras ofertas chegam em breve.</p>'}</main>
<footer>{e(m['aviso_afiliado'])} {e(m['aviso_preco'])}<br>Atualizado em {now().strftime('%d/%m/%Y %H:%M')}.</footer>
<script>
const q=document.getElementById('q');q.addEventListener('input',()=>{{const v=q.value.replace(/\\D/g,'');
document.querySelectorAll('.card').forEach(c=>{{c.style.display=!v||c.dataset.n===v?'flex':'none'}})}});
const h=location.hash.replace('#','');if(h){{q.value=h;q.dispatchEvent(new Event('input'))}}
</script></body></html>"""
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(pagina, encoding="utf-8")
    (DOCS_DIR / ".nojekyll").write_text("")
    logo.gerar_arquivos(DOCS_DIR)
    if not (DOCS_DIR / "placeholder.jpg").exists():
        from .designer import imagem_produto
        imagem_produto({"id": "placeholder"}).resize((400, 400)).save(DOCS_DIR / "placeholder.jpg", quality=85)
    (DOCS_DIR / "ofertas.json").write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    log.info("vitrine gerada com %d ofertas", len(itens))
