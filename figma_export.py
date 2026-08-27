# figma_export.py — экспорт спецификации в SVG для импорта в Figma
from pathlib import Path

FIGMA_DIR = Path("figma_export")
FIGMA_DIR.mkdir(exist_ok=True)


def spec_to_svg(spec: dict) -> str:
    style   = spec.get("style", {})
    bg      = style.get("bg_color",    "#1a1a2e")
    text_c  = style.get("text_color",  "#eeeeee")
    btn_bg  = style.get("button_bg",   "#0f3460")
    btn_hov = style.get("button_hover","#e94560")
    font    = style.get("font_family", "Arial").split(",")[0].strip().strip("'\"")
    layout  = style.get("layout", "vertical")
    radius  = style.get("border_radius", "8px").replace("px", "") or "8"

    title   = spec.get("title", "Меню")
    items   = spec.get("items", [])
    screens = spec.get("screens", {})

    W = 900
    TITLE_Y = 80
    BTN_W, BTN_H, BTN_GAP = 320, 52, 14
    COMP_W, COMP_H, COMP_GAP = 500, 44, 12

    parts: list[str] = []
    total_height = TITLE_Y + 60  # резерв под заголовок

    # ── Главный экран ──────────────────────────────────────────────────────
    if layout == "horizontal":
        # кнопки в ряд
        total_w = len(items) * (BTN_W + BTN_GAP) - BTN_GAP
        start_x = (W - total_w) // 2
        btn_y = 140
        for i, item in enumerate(items):
            x = start_x + i * (BTN_W + BTN_GAP)
            parts.append(_rect(x, btn_y, BTN_W, BTN_H, btn_bg, radius))
            parts.append(_text(x + BTN_W // 2, btn_y + BTN_H // 2 + 6, item, text_c, font, 15, "middle", bold=True))
        total_height = btn_y + BTN_H + 40
    elif layout == "grid":
        cols = min(3, len(items))
        col_w = BTN_W + 20
        start_x = (W - cols * col_w + 20) // 2
        btn_y = 140
        for i, item in enumerate(items):
            col = i % cols
            row = i // cols
            x = start_x + col * col_w
            y = btn_y + row * (BTN_H + BTN_GAP)
            parts.append(_rect(x, y, BTN_W, BTN_H, btn_bg, radius))
            parts.append(_text(x + BTN_W // 2, y + BTN_H // 2 + 6, item, text_c, font, 15, "middle", bold=True))
        rows = (len(items) + cols - 1) // cols
        total_height = btn_y + rows * (BTN_H + BTN_GAP) + 40
    else:  # vertical
        btn_x = (W - BTN_W) // 2
        y = 140
        for item in items:
            parts.append(_rect(btn_x, y, BTN_W, BTN_H, btn_bg, radius))
            parts.append(_text(W // 2, y + BTN_H // 2 + 6, item, text_c, font, 15, "middle", bold=True))
            y += BTN_H + BTN_GAP
        total_height = y + 40

    # ── Вложенные экраны (рядом справа) ────────────────────────────────────
    SCREEN_OFFSET_X = W + 60
    for screen_id, screen_data in screens.items():
        s_title = screen_data.get("title", screen_id)
        s_items = screen_data.get("items", [])
        s_comps = screen_data.get("extra_components", [])

        screen_x = SCREEN_OFFSET_X
        y = TITLE_Y - 20
        parts.append(_text(screen_x + W // 2, y + 40, s_title, text_c, font, 28, "middle", bold=True))
        y += 80

        # Компоненты
        comp_x = screen_x + (W - COMP_W) // 2
        for comp in s_comps:
            parts.append(_render_component(comp, comp_x, y, COMP_W, COMP_H, btn_bg, btn_hov, text_c, font, radius))
            y += COMP_H + COMP_GAP

        # Кнопки
        btn_sx = screen_x + (W - BTN_W) // 2
        for item in s_items:
            color = "#555555" if item.lower() == "назад" else btn_bg
            parts.append(_rect(btn_sx, y, BTN_W, BTN_H, color, radius))
            parts.append(_text(screen_x + W // 2, y + BTN_H // 2 + 6, item, text_c, font, 15, "middle", bold=True))
            y += BTN_H + BTN_GAP

        total_height = max(total_height, y + 40)
        SCREEN_OFFSET_X += W + 60

    total_width = SCREEN_OFFSET_X
    bg_rect = f'<rect width="{total_width}" height="{total_height}" fill="{bg}"/>'

    # Заголовок главного экрана
    main_title = _text(W // 2, TITLE_Y, title.upper(), text_c, font, 36, "middle", bold=True)

    # Разделители экранов
    separators = []
    sx = W + 30
    while sx < total_width:
        separators.append(f'<line x1="{sx}" y1="0" x2="{sx}" y2="{total_height}" '
                          f'stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="6,4"/>')
        sx += W + 60

    all_parts = [bg_rect, main_title] + separators + parts
    inner = "\n  ".join(all_parts)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_width}" height="{total_height}" '
        f'viewBox="0 0 {total_width} {total_height}">\n  '
        f'{inner}\n</svg>'
    )


def export_to_svg(spec: dict) -> Path:
    svg_content = spec_to_svg(spec)
    filename = f"figma_{spec.get('title', 'export').replace(' ', '_')}.svg"
    filepath = FIGMA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)
    return filepath


# ── Хелперы ────────────────────────────────────────────────────────────────

def _rect(x, y, w, h, fill, rx="8") -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"/>'


def _text(x, y, content, fill, font, size, anchor="start", bold=False) -> str:
    weight = "bold" if bold else "normal"
    safe = (str(content)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
            f'font-family="{font}, Arial" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}">{safe}</text>')


def _render_component(comp, x, y, w, h, btn_bg, accent, text_c, font, radius) -> str:
    label = comp.get("label", "")
    ctype = comp.get("type", "text")

    parts = []
    parts.append(_rect(x, y, w, h, "rgba(255,255,255,0.05)", radius))
    parts.append(_text(x + 12, y + h // 2 + 5, label, text_c, font, 14))

    if ctype == "slider":
        val = comp.get("value", 50)
        track_x, track_y = x + 200, y + h // 2
        track_w = 240
        filled_w = int(track_w * val / 100)
        parts.append(f'<rect x="{track_x}" y="{track_y - 3}" width="{track_w}" height="6" rx="3" fill="{btn_bg}"/>')
        parts.append(f'<rect x="{track_x}" y="{track_y - 3}" width="{filled_w}" height="6" rx="3" fill="{accent}"/>')
        cx = track_x + filled_w
        parts.append(f'<circle cx="{cx}" cy="{track_y}" r="9" fill="{accent}"/>')
        parts.append(_text(track_x + track_w + 14, track_y + 5, str(val), text_c, font, 12))

    elif ctype == "checkbox":
        checked = comp.get("checked", False)
        cx, cy = x + w - 30, y + h // 2
        parts.append(f'<rect x="{cx - 10}" y="{cy - 10}" width="20" height="20" rx="4" '
                     f'fill="{""+accent if checked else btn_bg}" stroke="{accent}" stroke-width="1.5"/>')
        if checked:
            parts.append(f'<polyline points="{cx-5},{cy} {cx},{cy+5} {cx+7},{cy-6}" '
                         f'stroke="white" stroke-width="2.5" fill="none" stroke-linecap="round"/>')

    elif ctype == "select":
        options = comp.get("options", [])
        sel_text = options[0] if options else "—"
        sel_x = x + 195
        parts.append(_rect(sel_x, y + 8, 200, h - 16, btn_bg, radius))
        parts.append(_text(sel_x + 10, y + h // 2 + 5, sel_text, text_c, font, 13))
        parts.append(_text(sel_x + 178, y + h // 2 + 5, "▾", text_c, font, 12))

    elif ctype == "input":
        placeholder = comp.get("placeholder", "")
        inp_x = x + 195
        parts.append(_rect(inp_x, y + 8, 250, h - 16, btn_bg, radius))
        parts.append(_text(inp_x + 10, y + h // 2 + 5, placeholder, "rgba(200,200,200,0.4)", font, 13))

    return "\n  ".join(parts)
