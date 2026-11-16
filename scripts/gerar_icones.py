#!/usr/bin/env python3
"""Gera ícones PNG do app a partir da identidade vetorial Alerta Global."""
from pathlib import Path
import cairosvg

ROOT = Path(__file__).resolve().parent.parent
source = ROOT / "icons" / "alerta-global.svg"
for size in (192, 512):
    target = ROOT / "icons" / f"icon-{size}.png"
    cairosvg.svg2png(url=str(source), write_to=str(target),
                    output_width=size, output_height=size)
    print(f"Gerado {target.relative_to(ROOT)} ({size} x {size})")
