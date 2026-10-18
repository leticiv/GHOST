"""Símbolo da marca (patinha de gato) desenhado em código.

Gera o logo, a imagem de compartilhamento (og.png) e o ícone da aba (favicon.png) da vitrine,
sem precisar subir arquivos binários no repositório.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..core import FONTS_DIR, cfg

SS = 4  # desenha 4x maior e reduz: bordas suaves


def _cores():
    c = cfg("marca")["cores"]
    return c["primaria"], c["fundo"]


def _font(nome: str, size: int):
    try:
        return ImageFont.truetype(str(FONTS_DIR / nome), size)
    except OSError:
        return ImageFont.load_default()


def pata(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float, cor: str) -> None:
    rx, ry = s * 0.36, s * 0.32
    py = cy + s * 0.16
    d.ellipse([cx - rx, py - ry, cx + rx, py + ry], fill=cor)
    tr = s * 0.16
    for dx, dy in ((-0.42, -0.22), (-0.16, -0.42), (0.16, -0.42), (0.42, -0.22)):
        tx, ty = cx + dx * s, cy + dy * s
        d.ellipse([tx - tr, ty - tr * 1.15, tx + tr, ty + tr * 1.15], fill=cor)


def avatar(tamanho: int = 1080) -> Image.Image:
    primaria, fundo = _cores()
    W = tamanho * SS
    img = Image.new("RGB", (W, W), primaria)
    pata(ImageDraw.Draw(img), W * 0.5, W * 0.5, W * 0.5, fundo)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


def og(nome: str, slogan: str) -> Image.Image:
    """Imagem de compartilhamento 1200x630 (WhatsApp, Telegram, redes)."""
    primaria, fundo = _cores()
    W, H = 1200 * SS, 630 * SS
    img = Image.new("RGB", (W, H), primaria)
    d = ImageDraw.Draw(img)
    d.ellipse([90 * SS, 150 * SS, 420 * SS, 480 * SS], fill=fundo)
    pata(d, 255 * SS, 320 * SS, 195 * SS, primaria)
    fb, fm = _font("Poppins-Bold.ttf", 70 * SS), _font("Poppins-Medium.ttf", 34 * SS)
    while d.textlength(nome, font=fb) > 660 * SS and fb.size > 40 * SS:
        fb = _font("Poppins-Bold.ttf", fb.size - 3)
    d.text((480 * SS, 250 * SS), nome, font=fb, fill=fundo, anchor="lm")
    # quebra o slogan em até 2 linhas
    linhas, atual = [], ""
    for p in slogan.split():
        t = f"{atual} {p}".strip()
        if d.textlength(t, font=fm) <= 660 * SS:
            atual = t
        else:
            linhas.append(atual)
            atual = p
    linhas.append(atual)
    for i, ln in enumerate(linhas[:2]):
        d.text((480 * SS, (335 + i * 45) * SS), ln, font=fm, fill=fundo, anchor="lm")
    return img.resize((1200, 630), Image.LANCZOS)


def gerar_arquivos(pasta: Path) -> None:
    """Cria og.png, favicon.png e logo.png na pasta da vitrine (sempre refeitos: seguem o slogan atual)."""
    m = cfg("marca")
    og(m["nome"], m["slogan"]).save(pasta / "og.png", optimize=True)
    avatar(256).resize((64, 64), Image.LANCZOS).save(pasta / "favicon.png")
    avatar(160).save(pasta / "logo.png", optimize=True)
