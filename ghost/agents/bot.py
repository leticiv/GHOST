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

import time

from ..core import brl, cfg, dry_run, get_logger, load_json, save_json
from ..links import link
from . import cacador, curador, designer, redator, telegram, vitrine

log = get_logger("bot")
ESTADO = "bot.json"
MAX_ITENS = 8


def _donos() -> list[str]:
    return telegram.donos()


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


def _postar(n: int, estado: dict, ao_publicar=None) -> None:
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
    if ao_publicar:
        try:
            ao_publicar(o)
        except Exception as e:  # noqa: BLE001
            log.warning("pós-publicação falhou (%s)", e)
    log.info("publicado no canal: %s (#%s)", o["titulo"][:50], o.get("numero"))
    _responder(f"✅ Publicado no canal: {o['titulo'][:70]} (#{o.get('numero')})")


def _comando(texto: str, estado: dict, ao_publicar=None) -> None:
    cmd, _, resto = texto.strip().partition(" ")
    cmd = cmd.split("@")[0].lower()
    resto = resto.strip()
    if cmd in ("/buscar", "/busca"):
        _buscar(resto, estado) if resto else _responder("Use: /buscar <termo>")
    elif cmd in ("/postar", "/publicar"):
        try:
            _postar(int(resto.split()[0]), estado, ao_publicar)
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


def _get_updates(offset: int, timeout: int = 0) -> list[dict]:
    j = telegram._api("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'})
    r = j.get("result")
    return r if isinstance(r, list) else []


def _processar(updates: list[dict], estado: dict, donos: list[str], ao_publicar=None) -> None:
    for u in updates:
        estado["offset"] = u.get("update_id", estado.get("offset", 0)) + 1
        msg = u.get("message")
        if not msg:
            continue
        if str(msg.get("chat", {}).get("id")) not in donos:
            log.info("ignorando mensagem de outro chat: %s", msg.get("chat", {}).get("id"))
            continue
        _comando(msg.get("text") or "", estado, ao_publicar)


def atender() -> None:
    """Roda uma vez: processa as mensagens novas do dono (usado no GitHub Actions)."""
    if dry_run():
        log.info("DRY_RUN: bot não lê mensagens")
        return
    donos = _donos()
    if not donos:
        log.warning("TELEGRAM_OWNER_CHAT_ID não definido; o bot não vai responder")
        return
    estado = load_json(ESTADO, {"offset": 0, "itens": [], "termo": ""})
    _processar(_get_updates(estado.get("offset", 0)), estado, donos)
    save_json(ESTADO, estado)


def vigiar(poll: int = 30, ao_publicar=None) -> None:
    """Fica ligado em long polling, respondendo na hora (usado na VPS via systemd).

    `ao_publicar` (opcional) é chamado depois de cada /postar — ex.: pra sincronizar a vitrine no git.
    """
    if dry_run():
        log.info("DRY_RUN: vigia não inicia")
        return
    donos = _donos()
    if not donos:
        log.warning("TELEGRAM_OWNER_CHAT_ID não definido; o vigia não vai responder")
        return
    estado = load_json(ESTADO, {"offset": 0, "itens": [], "termo": ""})
    log.info("Vigia ligada em long polling (%ss). Mande /buscar no Telegram.", poll)
    while True:
        try:
            updates = _get_updates(estado.get("offset", 0), timeout=poll)
        except KeyboardInterrupt:
            log.info("Vigia desligada")
            break
        except Exception as e:  # noqa: BLE001
            log.warning("erro ao ler mensagens (%s); tentando de novo", e)
            time.sleep(5)
            continue
        if updates:
            _processar(updates, estado, donos, ao_publicar)
            save_json(ESTADO, estado)
