class HTMLGenerator:
    """
    Генератор HTML/CSS/JS интерфейса на основе спецификации.
    Layouts: vertical, horizontal, grid, sidebar (дашборд с боковым меню).
    Компоненты: slider, checkbox, select, input, text.
    """

    def __init__(self, spec: dict):
        self.spec = spec
        self.title = spec.get("title", "Меню")
        self.items = spec.get("items", [])
        self.style = spec.get("style", {})
        self.screens = spec.get("screens", {})
        self.layout = self.style.get("layout", "vertical")

    def generate(self) -> str:
        css = self._build_css()
        html = self._build_html()
        js = self._build_js()
        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.title}</title>
    <style>{css}</style>
</head>
<body>
{html}
<script>{js}</script>
</body>
</html>"""

    # ─── CSS ──────────────────────────────────────────────────────────────────

    def _build_css(self) -> str:
        s = self.style
        bg        = s.get("bg_color",      "#1a1a2e")
        text_c    = s.get("text_color",    "#eeeeee")
        btn_bg    = s.get("button_bg",     "#0f3460")
        btn_hover = s.get("button_hover",  "#e94560")
        font      = s.get("font_family",   "'Segoe UI', 'Arial', sans-serif")
        layout    = self.layout
        radius    = s.get("border_radius", "8px")
        transform = s.get("text_transform","uppercase")
        shadow    = s.get("box_shadow",    "none")
        animation = s.get("animation",     "scale(1.05)")

        # Боковое меню — отдельный layout
        if layout == "sidebar":
            return self._css_sidebar(bg, text_c, btn_bg, btn_hover, font, radius, transform, shadow)

        # Классические layout'ы
        if layout == "grid":
            container_css = """
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;"""
        elif layout == "horizontal":
            container_css = """
            display: flex;
            flex-direction: row;
            flex-wrap: wrap;
            justify-content: center;
            gap: 20px;"""
        else:
            container_css = """
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 15px;"""

        return f"""
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            background: {bg};
            font-family: {font};
            color: {text_c};
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}

        .screen {{ display: none; width: 100%; max-width: 900px; }}
        .screen.active {{ display: block; }}

        .menu-container {{
            width: 100%;
            text-align: center;
            padding: 40px 20px;
            border-radius: 20px;
            background: rgba(0,0,0,0.2);
            backdrop-filter: blur(5px);
        }}

        h1 {{
            font-size: 3rem;
            margin-bottom: 2rem;
            text-transform: uppercase;
            letter-spacing: 4px;
            text-shadow: 0 0 15px currentColor;
        }}

        .button-wrapper {{{container_css}
            margin-bottom: 30px;
        }}

        .menu-btn {{
            background: {btn_bg};
            border: 1px solid rgba(255,255,255,0.1);
            color: {text_c};
            padding: 15px 40px;
            font-size: 1.3rem;
            font-family: inherit;
            font-weight: bold;
            text-transform: {transform};
            border-radius: {radius};
            box-shadow: {shadow};
            cursor: pointer;
            transition: all 0.3s ease;
            min-width: 180px;
            letter-spacing: 1px;
        }}

        .menu-btn:hover {{ background: {btn_hover}; transform: {animation}; }}
        .menu-btn.back-btn {{ background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.2); }}
        .menu-btn.back-btn:hover {{ background: rgba(255,255,255,0.15); }}

        {self._css_components(btn_bg, btn_hover, text_c, radius)}

        @media (max-width: 600px) {{
            h1 {{ font-size: 2rem; }}
            .menu-btn {{ padding: 12px 25px; font-size: 1.1rem; min-width: 140px; }}
            input[type="range"] {{ width: 130px; }}
        }}
        """

    def _css_sidebar(self, bg, text_c, btn_bg, btn_hover, font, radius, transform, shadow) -> str:
        """CSS для дашборда с боковым меню (sidebar layout)."""
        # Вычисляем чуть более тёмный цвет для сайдбара
        sidebar_bg = self._darken(bg, 0.15)
        return f"""
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            background: {bg};
            font-family: {font};
            color: {text_c};
            display: flex;
            min-height: 100vh;
            overflow: hidden;
        }}

        /* ── Sidebar ── */
        .sidebar {{
            width: 240px;
            min-height: 100vh;
            background: {sidebar_bg};
            display: flex;
            flex-direction: column;
            padding: 0;
            box-shadow: 2px 0 12px rgba(0,0,0,0.3);
            flex-shrink: 0;
            z-index: 10;
        }}

        .sidebar-header {{
            padding: 28px 24px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}

        .sidebar-title {{
            font-size: 1.1rem;
            font-weight: bold;
            text-transform: {transform};
            letter-spacing: 2px;
            opacity: 0.95;
        }}

        .sidebar-subtitle {{
            font-size: 0.75rem;
            opacity: 0.45;
            margin-top: 4px;
            text-transform: none;
            letter-spacing: 0;
        }}

        .sidebar-nav {{
            flex: 1;
            padding: 16px 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .nav-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 11px 16px;
            border-radius: {radius};
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 500;
            transition: all 0.2s ease;
            border: none;
            background: transparent;
            color: {text_c};
            font-family: inherit;
            text-align: left;
            width: 100%;
            text-transform: {transform};
            letter-spacing: 0.5px;
            opacity: 0.7;
        }}

        .nav-item:hover {{
            background: {btn_bg};
            opacity: 1;
        }}

        .nav-item.active {{
            background: {btn_hover};
            opacity: 1;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}

        .nav-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
            opacity: 0.5;
            flex-shrink: 0;
        }}

        .nav-item.active .nav-dot {{ opacity: 1; }}

        /* ── Content area ── */
        .content {{
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }}

        .content-header {{
            padding: 24px 32px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            background: rgba(0,0,0,0.1);
        }}

        .content-header h1 {{
            font-size: 1.6rem;
            font-weight: 700;
            text-transform: {transform};
            letter-spacing: 1px;
            text-shadow: none;
            margin-bottom: 0;
        }}

        .content-body {{
            padding: 28px 32px;
            flex: 1;
        }}

        /* ── Screens ── */
        .screen {{ display: none; }}
        .screen.active {{ display: flex; width: 100%; min-height: 100vh; }}

        /* ── Cards (кнопки-карточки в content area) ── */
        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 16px;
            margin-top: 8px;
        }}

        .card-btn {{
            background: {btn_bg};
            border: 1px solid rgba(255,255,255,0.08);
            color: {text_c};
            padding: 20px 16px;
            border-radius: {radius};
            cursor: pointer;
            font-size: 1rem;
            font-family: inherit;
            font-weight: 600;
            text-transform: {transform};
            transition: all 0.25s ease;
            text-align: center;
            letter-spacing: 0.5px;
            box-shadow: {shadow};
        }}

        .card-btn:hover {{
            background: {btn_hover};
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
        }}

        {self._css_components(btn_bg, btn_hover, text_c, radius)}

        /* ── Секции ── */
        .section-title {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 2px;
            opacity: 0.4;
            margin-bottom: 16px;
            margin-top: 8px;
        }}

        @media (max-width: 700px) {{
            .sidebar {{ width: 60px; }}
            .sidebar-title, .sidebar-subtitle, .nav-item span {{ display: none; }}
            .content-header h1 {{ font-size: 1.3rem; }}
            .content-body {{ padding: 16px; }}
        }}
        """

    def _css_components(self, btn_bg, btn_hover, text_c, radius) -> str:
        return f"""
        .components-wrapper {{
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-width: 560px;
            margin-top: 8px;
        }}

        .component-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 15px;
            padding: 12px 16px;
            background: rgba(255,255,255,0.04);
            border-radius: {radius};
            border: 1px solid rgba(255,255,255,0.06);
        }}

        .component-label {{
            font-size: 0.97rem;
            min-width: 130px;
            opacity: 0.9;
        }}

        input[type="range"] {{
            -webkit-appearance: none;
            width: 180px;
            height: 5px;
            background: {btn_bg};
            border-radius: 3px;
            outline: none;
        }}
        input[type="range"]::-webkit-slider-thumb {{
            -webkit-appearance: none;
            width: 17px; height: 17px;
            background: {btn_hover};
            border-radius: 50%;
            cursor: pointer;
        }}

        .slider-value {{
            min-width: 32px;
            text-align: right;
            font-size: 0.9rem;
            opacity: 0.6;
        }}

        input[type="checkbox"] {{
            width: 20px; height: 20px;
            accent-color: {btn_hover};
            cursor: pointer;
        }}

        select {{
            background: {btn_bg};
            color: {text_c};
            border: 1px solid rgba(255,255,255,0.2);
            padding: 7px 12px;
            border-radius: {radius};
            font-size: 0.95rem;
            font-family: inherit;
            cursor: pointer;
            outline: none;
        }}

        input[type="text"] {{
            background: {btn_bg};
            color: {text_c};
            border: 1px solid rgba(255,255,255,0.2);
            padding: 9px 14px;
            border-radius: {radius};
            font-size: 0.95rem;
            font-family: inherit;
            width: 195px;
            outline: none;
        }}
        input[type="text"]::placeholder {{ opacity: 0.4; }}

        .static-text {{
            opacity: 0.5;
            font-size: 0.9rem;
            padding: 6px 0;
        }}
        """

    # ─── HTML ─────────────────────────────────────────────────────────────────

    def _build_html(self) -> str:
        if self.layout == "sidebar":
            return self._html_sidebar()
        return self._html_classic()

    def _html_classic(self) -> str:
        html = '<div id="screen-main" class="screen active">\n'
        html += self._render_screen_classic(self.title, self.items, extra_components=[])
        html += "</div>\n"

        for screen_id, screen_data in self.screens.items():
            screen_title = screen_data.get("title", screen_id.capitalize())
            screen_items = list(screen_data.get("items", [])) + ["Назад"]
            extra = screen_data.get("extra_components", [])
            html += f'<div id="screen-{screen_id}" class="screen">\n'
            html += self._render_screen_classic(screen_title, screen_items, extra_components=extra)
            html += "</div>\n"

        return html

    def _html_sidebar(self) -> str:
        """HTML для дашборд-стиля с боковым меню."""
        # Главный экран (main) — sidebar + контент первого пункта
        first_screen_id = next(iter(self.screens), None)

        # Sidebar строим один раз — он общий для всех экранов
        sidebar_nav = ""
        for item in self.items:
            sid = self._find_screen_id_by_title(item)
            target = sid if sid else ""
            active_class = " active" if (target == first_screen_id) else ""
            onclick = f"showScreen('{target}')" if target else ""
            onclick_attr = f' onclick="{onclick}"' if onclick else ""
            sidebar_nav += (
                f'            <button class="nav-item{active_class}"{onclick_attr}>\n'
                f'                <span class="nav-dot"></span>\n'
                f'                <span>{item}</span>\n'
                f'            </button>\n'
            )

        sidebar_html = f"""    <div class="sidebar">
        <div class="sidebar-header">
            <div class="sidebar-title">{self.title}</div>
            <div class="sidebar-subtitle">Navigation</div>
        </div>
        <nav class="sidebar-nav">
{sidebar_nav}        </nav>
    </div>
"""

        # Контент-экраны
        screens_html = ""
        for idx, (screen_id, screen_data) in enumerate(self.screens.items()):
            screen_title = screen_data.get("title", screen_id.capitalize())
            screen_items = screen_data.get("items", [])
            extra        = screen_data.get("extra_components", [])
            active       = " active" if idx == 0 else ""

            content_body = ""
            if extra:
                content_body += '            <div class="components-wrapper">\n'
                for comp in extra:
                    content_body += self._render_component(comp)
                content_body += "            </div>\n"

            if screen_items:
                content_body += '            <p class="section-title">Разделы</p>\n'
                content_body += '            <div class="cards-grid">\n'
                for sit in screen_items:
                    sub_sid = self._find_screen_id_by_title(sit)
                    onclick = f' onclick="showScreen(\'{sub_sid}\')"' if sub_sid else ""
                    content_body += f'                <button class="card-btn"{onclick}>{sit}</button>\n'
                content_body += "            </div>\n"

            screens_html += f"""    <div id="screen-{screen_id}" class="screen{active}">
{sidebar_html}        <div class="content">
            <div class="content-header"><h1>{screen_title}</h1></div>
            <div class="content-body">
{content_body}            </div>
        </div>
    </div>
"""

        # Если вообще нет экранов — fallback на главный
        if not self.screens:
            content_body = '            <div class="cards-grid">\n'
            for item in self.items:
                content_body += f'                <button class="card-btn">{item}</button>\n'
            content_body += "            </div>\n"
            screens_html = f"""    <div id="screen-main" class="screen active">
{sidebar_html}        <div class="content">
            <div class="content-header"><h1>{self.title}</h1></div>
            <div class="content-body">
{content_body}            </div>
        </div>
    </div>
"""

        return screens_html

    def _render_screen_classic(self, title: str, items: list, extra_components: list = None) -> str:
        html = '    <div class="menu-container">\n'
        html += f"        <h1>{title}</h1>\n"

        if extra_components:
            html += '        <div class="components-wrapper">\n'
            for comp in extra_components:
                html += self._render_component(comp)
            html += "        </div>\n"

        if items:
            html += '        <div class="button-wrapper">\n'
            for item in items:
                html += self._render_button(item)
            html += "        </div>\n"

        html += "    </div>\n"
        return html

    def _find_screen_id_by_title(self, title: str) -> str:
        title_lower = title.lower()
        for screen_id, screen_data in self.screens.items():
            if screen_data.get("title", "").lower() == title_lower:
                return screen_id
        return ""

    def _render_button(self, item) -> str:
        if isinstance(item, dict):
            label = item.get("label", "")
            target_screen = item.get("screen", "")
        else:
            label = str(item)
            target_screen = self._find_screen_id_by_title(label)

        if target_screen:
            onclick = f"showScreen('{target_screen}')"
            btn_class = "menu-btn"
        elif label.lower() in ("назад", "back"):
            onclick = "goBack()"
            btn_class = "menu-btn back-btn"
        else:
            onclick = ""
            btn_class = "menu-btn"

        onclick_attr = f' onclick="{onclick}"' if onclick else ""
        return f'            <button class="{btn_class}"{onclick_attr}>{label}</button>\n'

    def _render_component(self, comp: dict) -> str:
        comp_type = comp.get("type", "text")
        label = comp.get("label", "")
        uid = "c_" + label.lower().replace(" ", "_").replace("/", "_")[:30]

        if comp_type == "slider":
            min_v = comp.get("min", 0)
            max_v = comp.get("max", 100)
            val   = comp.get("value", 50)
            return (
                f'            <div class="component-row">\n'
                f'                <span class="component-label">{label}</span>\n'
                f'                <input type="range" id="{uid}" min="{min_v}" max="{max_v}" value="{val}" '
                f'oninput="document.getElementById(\'{uid}_val\').textContent=this.value">\n'
                f'                <span class="slider-value" id="{uid}_val">{val}</span>\n'
                f"            </div>\n"
            )
        elif comp_type == "checkbox":
            checked = "checked" if comp.get("checked", False) else ""
            return (
                f'            <div class="component-row">\n'
                f'                <span class="component-label">{label}</span>\n'
                f'                <input type="checkbox" id="{uid}" {checked}>\n'
                f"            </div>\n"
            )
        elif comp_type == "select":
            options  = comp.get("options", [])
            opts_html = "".join(f"<option>{o}</option>" for o in options)
            return (
                f'            <div class="component-row">\n'
                f'                <span class="component-label">{label}</span>\n'
                f'                <select id="{uid}">{opts_html}</select>\n'
                f"            </div>\n"
            )
        elif comp_type == "input":
            placeholder = comp.get("placeholder", "")
            return (
                f'            <div class="component-row">\n'
                f'                <span class="component-label">{label}</span>\n'
                f'                <input type="text" id="{uid}" placeholder="{placeholder}">\n'
                f"            </div>\n"
            )
        else:
            content = comp.get("content", label)
            return f'            <p class="static-text">{content}</p>\n'

    # ─── JS ───────────────────────────────────────────────────────────────────

    def _build_js(self) -> str:
        if self.layout == "sidebar":
            return self._js_sidebar()
        return self._js_classic()

    def _js_classic(self) -> str:
        return """
        const _history = ['main'];

        function showScreen(screenId) {
            document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
            const target = document.getElementById('screen-' + screenId);
            if (target) {
                target.classList.add('active');
                if (_history[_history.length - 1] !== screenId) _history.push(screenId);
            } else {
                console.warn('Screen not found: screen-' + screenId);
            }
        }

        function goBack() {
            if (_history.length > 1) _history.pop();
            showScreen(_history[_history.length - 1]);
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') goBack();
        });
        """

    def _js_sidebar(self) -> str:
        return """
        function showScreen(screenId) {
            document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
            const target = document.getElementById('screen-' + screenId);
            if (target) target.classList.add('active');
            // Подсвечиваем активный пункт nav
            document.querySelectorAll('.nav-item').forEach(btn => {
                const fn = btn.getAttribute('onclick') || '';
                btn.classList.toggle('active', fn.includes("'" + screenId + "'"));
            });
        }

        function goBack() { /* no-op in sidebar */ }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                const first = document.querySelector('.nav-item');
                if (first) first.click();
            }
        });
        """

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _darken(hex_color: str, amount: float) -> str:
        """Делает hex-цвет темнее на amount (0..1)."""
        try:
            h = hex_color.lstrip("#")
            if len(h) != 6:
                return hex_color
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            r = max(0, int(r * (1 - amount)))
            g = max(0, int(g * (1 - amount)))
            b = max(0, int(b * (1 - amount)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color
