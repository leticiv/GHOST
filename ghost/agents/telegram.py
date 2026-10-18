"""Agente 6a — Publicador do Telegram (+ canal de avisos privados para o dono).

TELEGRAM_BOT_TOKEN      token do @BotFather
TELEGRAM_CHANNEL_ID     @seucanal (o bot precisa ser administrador do canal)
TELEGRAM_OWNER_CHAT_ID  seu chat pessoal com o bot (recebe relatórios, vídeos e alertas)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..core import OUT_DIR, dry_run, env, get_logger, http, retry

log = get_logger("telegram")


def donos() -> list[str]:
    """Chats autorizados do dono (aceita vários, separados por vírgula/espaço)."""
    return [x for x in re.split(r"[,\s]+", env("TELEGRAM_OWNER_CHAT_ID") or "") if x]


_canal_id: str | None = None


def _id_do_canal() -> str:
    """Id numérico do canal (cacheado) — usado pra nunca mandar recado privado pro canal."""
    global _canal_id
    if _canal_id is None:
        cid = env("TELEGRAM_CHANNEL_ID")
        if not cid or dry_run():
            _canal_id = ""
        else:
            try:
                _canal_id = str(_api("getChat", {"chat_id": cid})["result"]["id"])
            except Exception:  # noqa: BLE001
                _canal_id = ""
    return _canal_id


def donos_privados() -> list[str]:
    """Como donos(), mas sem o canal — recados (buscas, relatórios) nunca vão pro canal."""
    canal = _id_do_canal()
    return [c for c in donos() if c != canal]


def _api(metodo: str, data: dict, files: dict | None = None) -> dict:
    token = env("TELEGRAM_BOT_TOKEN")
    if dry_run() or not token:
        OUT_DIR.mkdir(exist_ok=True)
        with open(OUT_DIR / "telegram_simulado.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"metodo": metodo, **data, "arquivos": list((files or {}).keys())},
                               ensure_ascii=False) + "\n---\n")
        log.info("[simulado] telegram.%s", metodo)
        return {"ok": True, "result": {"message_id": 0}}

    def go():
        r = http().post(f"https://api.telegram.org/bot{token}/{metodo}", data=data, files=files, timeout=120)
        j = r.json()
        if not j.get("ok"):
            raise RuntimeError(j.get("description"))
        return j

    return retry(go, what=f"telegram.{metodo}")


def _teclado(texto: str, url: str) -> str:
    return json.dumps({"inline_keyboard": [[{"text": texto, "url": url}]]})


def oferta(foto: Path, legenda_html: str, url: str, botao: str = "🛒 Ver oferta") -> dict:
    canal = env("TELEGRAM_CHANNEL_ID") or "@canal_simulado"
    with open(foto, "rb") as f:
        return _api("sendPhoto", {"chat_id": canal, "caption": legenda_html, "parse_mode": "HTML",
                                  "reply_markup": _teclado(botao, url)}, {"photo": f})


def para_dono(texto: str, html: bool = False) -> None:
    chats = donos_privados()
    if not chats and not dry_run():
        log.info("TELEGRAM_OWNER_CHAT_ID ausente; mensagem ao dono:\n%s", texto)
        return
    for chat in chats or ["dono"]:
        for i in range(0, len(texto), 4000):  # limite de 4096 por mensagem
            d = {"chat_id": chat, "text": texto[i:i + 4000], "disable_web_page_preview": "true"}
            if html:
                d["parse_mode"] = "HTML"
            _api("sendMessage", d)


def video_para_dono(video: Path, legenda: str) -> None:
    for chat in donos_privados() or ["dono"]:
        with open(video, "rb") as f:
            _api("sendVideo", {"chat_id": chat, "caption": legenda[:1024], "supports_streaming": "true"}, {"video": f})
