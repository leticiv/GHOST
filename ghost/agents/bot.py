"""Agente 9 — Bot de curadoria (escolher à mão).

Lê as mensagens que você manda para o bot no Telegram e responde:
    /buscar <termo>  → procura na Shopee, filtra como o Curador e lista as melhores opções
    /postar <n>      → publica no canal a opção n da última busca (com arte, link e vitrine)
    /lista           → repete a última lista
    /ajuda           → comandos

Só responde ao TELEGRAM_OWNER_CHAT_ID (ninguém mais consegue publicar no canal).
Roda num workflow agendado (ver .github/workflows/bot.yml), sem precisar de servidor.
"""
from __future__ import annotations

from ..core import brl, cfg, dry_run, env, get_logger, load_json, save_json
from ..links import link
from . import cacador, curador, designer, redator, telegram, vitrine

log = get_logger("bot")
ESTADO = "bot.json"
MAX_ITENS = 8


def _owner() -> str:
    return env("TELEGRAM_OWNER_CHAT_ID") or ""


def _responder(texto: str) -> None:
    telegram.para_dono(texto)


def _ajuda() -> str:
    return ("🐾 Bot da Achados Escondidos\n\n"
            "/buscar <termo> — procuro na Shopee e mostro as melhores opções\n"
            "/postar <n> — publica no canal a opção n da última busca\n"
            "/lista — mostra de novo a última lista\n"
            "/ajuda — esta mensagem")


def _lista_texto(termo: str, itens: list[dict]) -> str:
    if not itens:
        return f"Nada passou nos filtros para “{termo}”. Tente outra palavra."
    linhas = [f"🔎 “{termo}” — {len(itens)} opção(ões):", ""]
    for i, o in enumerate(itens, 1):
        preco = brl(o["preco"]) if o.get("preco") else "sem preço"
        nota = f"{o['nota']:.1f}".replace(".", ",") if o.get("nota") else "?"
        vendas = f"{o['vendas']:,}".replace(",", ".") if o.get("vendas") else "?"
        linhas += [f"{i}. {o['titulo'][:70]}", f"   {preco} · ⭐ {nota} · {vendas} vendidos", f"   {o.get('link', '')}", ""]
    linhas.append("Para publicar no canal: /postar N")
    return "\n".join(linhas)


def _buscar(termo: str, estado: dict) -> None:
    bons = [o for o in cacador.buscar(termo) if curador._passa_filtros(o)]
    bons.sort(key=curador.nota, reverse=True)
    top = bons[:MAX_ITENS]
    estado["itens"] = top
    estado["termo"] = termo
    log.info("busca '%s': %d aprovadas, mostrando %d", termo, len(bons), len(top))
    _responder(_lista_texto(termo, top))


def _postar(n: int, estado: dict) -> None:
    itens = estado.get("itens") or []
    if not itens:
        _responder("Faça uma busca primeiro: /buscar <termo>")
        return
    if not 1 <= n <= len(itens):
        _responder(f"Número fora da lista (1 a {len(itens)}).")
        return
    o = itens[n - 1]
    curador.numerar(o)
    arte = designer.post(o)
    url = link(o, "telegram")
    telegram.oferta(arte, redator.telegram(o), url, cfg("canais")["telegram"].get("botao", "🛒 Ver oferta"))
    curador.registrar(o, "telegram")
    vitrine.adicionar(o, link(o, "vitrine"))
    vitrine.gerar()
    log.info("publicado no canal: %s (#%s)", o["titulo"][:50], o.get("numero"))
    _responder(f"✅ Publicado no canal: {o['titulo'][:70]} (#{o.get('numero')})")


def _comando(texto: str, estado: dict) -> None:
    cmd, _, resto = texto.strip().partition(" ")
    cmd = cmd.split("@")[0].lower()
    resto = resto.strip()
    if cmd in ("/buscar", "/busca"):
        _buscar(resto, estado) if resto else _responder("Use: /buscar <termo>")
    elif cmd in ("/postar", "/publicar"):
        try:
            _postar(int(resto.split()[0]), estado)
        except (ValueError, IndexError):
            _responder("Use: /postar N (ex.: /postar 2)")
    elif cmd in ("/lista", "/opcoes", "/opções"):
        _responder(_lista_texto(estado.get("termo", "última busca"), estado.get("itens") or []))
    elif cmd in ("/limpar",):
        estado["itens"] = []
        _responder("Lista limpa.")
    elif cmd in ("/ajuda", "/start", "/help", "/comandos"):
        _responder(_ajuda())
    else:
        _responder("Não entendi. " + _ajuda())


def _get_updates(offset: int) -> list[dict]:
    j = telegram._api("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": '["message"]'})
    r = j.get("result")
    return r if isinstance(r, list) else []


def atender() -> None:
    """Processa as mensagens novas do dono no Telegram e responde aos comandos."""
    if dry_run():
        log.info("DRY_RUN: bot não lê mensagens")
        return
    owner = _owner()
    if not owner:
        log.warning("TELEGRAM_OWNER_CHAT_ID não definido; o bot não vai responder")
        return
    estado = load_json(ESTADO, {"offset": 0, "itens": [], "termo": ""})
    for u in _get_updates(estado.get("offset", 0)):
        estado["offset"] = u.get("update_id", estado.get("offset", 0)) + 1
        msg = u.get("message")
        if not msg:
            continue
        if str(msg.get("chat", {}).get("id")) != str(owner):
            log.info("ignorando mensagem de outro chat: %s", msg.get("chat", {}).get("id"))
            continue
        _comando(msg.get("text") or "", estado)
    save_json(ESTADO, estado)
