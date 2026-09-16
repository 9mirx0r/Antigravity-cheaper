"""High-legibility Dark Mode hand-drawn architectural diagram generator using PIL and Windows TrueType fonts.
Matches GitHub Dark Mode (#0d1117 / #161b22) with large, crisp, high-contrast typography.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)


def _load_font(path_str: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path_str, size)
    except Exception:
        try:
            return ImageFont.load_default()
        except Exception:
            return None


# Standard Fonts with fallbacks
FONT_MONO_XL = _load_font(r"C:\Windows\Fonts\consolab.ttf", 32)
FONT_MONO_LG = _load_font(r"C:\Windows\Fonts\consolab.ttf", 24)
FONT_MONO_MD = _load_font(r"C:\Windows\Fonts\consolab.ttf", 20)
FONT_MONO_SM = _load_font(r"C:\Windows\Fonts\consola.ttf", 17)

FONT_SANS_XL = _load_font(r"C:\Windows\Fonts\segoeuib.ttf", 46)
FONT_SANS_LG = _load_font(r"C:\Windows\Fonts\segoeuib.ttf", 30)
FONT_SANS_MD = _load_font(r"C:\Windows\Fonts\segoeuib.ttf", 22)
FONT_SANS_REG = _load_font(r"C:\Windows\Fonts\segoeui.ttf", 20)
FONT_SANS_SM = _load_font(r"C:\Windows\Fonts\segoeui.ttf", 16)


def render_dark_banner():
    w, h = 1200, 320
    # Background: GitHub Dark #0d1117
    img = Image.new("RGB", (w, h), (13, 17, 23))
    draw = ImageDraw.Draw(img)

    # Outer border: #30363d
    draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=16, fill="#0d1117", outline="#30363d", width=3)

    # Top terminal bar: #161b22
    draw.rounded_rectangle([28, 26, w - 28, 26 + 54], radius=10, fill="#161b22", outline="#30363d", width=2)
    draw.ellipse([50, 42, 50 + 22, 42 + 22], fill="#f85149")
    draw.ellipse([82, 42, 82 + 22, 42 + 22], fill="#d29922")
    draw.ellipse([114, 42, 114 + 22, 42 + 22], fill="#2ea043")
    draw.text((156, 40), "antigravity-cheaper / context-guard-engine (v1.0.0)", font=FONT_MONO_MD, fill="#8b949e")

    # Main title: #f0f6fc
    draw.text((50, 104), "Antigravity-Cheaper", font=FONT_SANS_XL, fill="#f0f6fc")
    draw.text((50, 168), "Token economization toolkit & FastMCP symbol server for Google Antigravity.", font=FONT_SANS_REG, fill="#8b949e")

    # Technical pills (Large & high contrast)
    pills = [
        ("AST Skeletons", 50, 240, "#1f2937", "#38bdf8", "#38bdf8"),
        ("PageRank Symbol Map", 310, 290, "#1f2937", "#38bdf8", "#38bdf8"),
        ("FastMCP stdio Server", 620, 270, "#064e3b", "#34d399", "#34d399"),
        ("Prefix Cache Lock (>85%)", 910, 260, "#064e3b", "#34d399", "#34d399"),
    ]
    for text, x, width, fill, outline, text_color in pills:
        draw.rounded_rectangle([x, 222, x + width, 222 + 60], radius=10, fill=fill, outline=outline, width=2)
        draw.text((x + 20, 238), text, font=FONT_MONO_MD, fill=text_color)

    img.save(ASSETS / "banner.png", quality=95)
    print("Dark mode banner.png rendered.")


def render_dark_architecture():
    w, h = 1320, 780
    img = Image.new("RGB", (w, h), (13, 17, 23))
    draw = ImageDraw.Draw(img)

    # Outer border: #30363d
    draw.rounded_rectangle([12, 12, w - 12, h - 12], radius=18, fill="#0d1117", outline="#30363d", width=3)

    # Diagram Title
    draw.text((45, 34), "SYSTEM ARCHITECTURE & DATA FLOW", font=FONT_SANS_LG, fill="#f0f6fc")
    draw.text((45, 74), "How Antigravity-Cheaper isolates context and preserves the Gemini prompt cache.", font=FONT_SANS_REG, fill="#8b949e")

    # ==================== COL 1: WORKSPACE INPUT ====================
    # x=45, w=300, y=125, h=615
    draw.rounded_rectangle([45, 125, 45 + 300, 125 + 615], radius=14, fill="#161b22", outline="#30363d", width=3)
    draw.text((68, 150), "WORKSPACE INPUT", font=FONT_MONO_LG, fill="#f0f6fc")
    draw.text((68, 185), "Unbounded disk data & traces", font=FONT_SANS_SM, fill="#8b949e")
    draw.line([68, 215, 325, 215], fill="#30363d", width=2)

    # Item 1: Source Code
    draw.rounded_rectangle([65, 235, 65 + 260, 235 + 115], radius=10, fill="#21262d", outline="#30363d", width=2)
    draw.text((85, 248), "Source Code", font=FONT_SANS_MD, fill="#f0f6fc")
    draw.text((85, 282), "2,500+ LOC across modules", font=FONT_SANS_SM, fill="#8b949e")
    draw.text((85, 310), "Unbounded: ~150k tokens", font=FONT_MONO_SM, fill="#f85149")

    # Item 2: Terminal Logs
    draw.rounded_rectangle([65, 370, 65 + 260, 370 + 115], radius=10, fill="#21262d", outline="#30363d", width=2)
    draw.text((85, 383), "Terminal Failure Logs", font=FONT_SANS_MD, fill="#f0f6fc")
    draw.text((85, 417), "Verbose test failure dumps", font=FONT_SANS_SM, fill="#8b949e")
    draw.text((85, 445), "Noise: up to 35,000 lines", font=FONT_MONO_SM, fill="#f85149")

    # Item 3: System Rules
    draw.rounded_rectangle([65, 505, 65 + 260, 505 + 115], radius=10, fill="#21262d", outline="#30363d", width=2)
    draw.text((85, 518), "System Invariants", font=FONT_SANS_MD, fill="#f0f6fc")
    draw.text((85, 552), "Static instructions & rules", font=FONT_SANS_SM, fill="#8b949e")
    draw.text((85, 580), "Prefix: > 2,048 tokens", font=FONT_MONO_SM, fill="#58a6ff")

    draw.text((68, 680), "Without filter: O(N^2) runaway", font=FONT_MONO_SM, fill="#f85149")

    # ==================== COL 2: CONTEXT GUARD FILTERS ====================
    # x=385, w=450, y=125
    filters = [
        ("1. AST Skeletonizer (ast.py)", "Strips bodies with '...' preserving types", "< 50 tokens per file skeleton", 135),
        ("2. PageRank RepoMap (repomap.py)", "Symbol dependency graph centrality", "< 1,200 token budget symbol map", 275),
        ("3. Bounded Slicer (pack.py)", "Extracts exact error frames + 5 lines context", "-14.7% input noise chars ingested", 415),
        ("4. Prefix Lock (prefix_lock.py)", "Merkle SHA-256 byte-identical validation", "> 85% Gemini context cache hit rate", 555),
    ]
    for title, desc, metric, y in filters:
        draw.rounded_rectangle([385, y, 385 + 450, y + 120], radius=12, fill="#161b22", outline="#1f6feb", width=3)
        draw.text((410, y + 18), title, font=FONT_MONO_MD, fill="#58a6ff")
        draw.text((410, y + 54), desc, font=FONT_SANS_SM, fill="#c9d1d9")
        draw.text((410, y + 84), metric, font=FONT_MONO_SM, fill="#58a6ff")

    # Wires Col 1 -> Col 2
    draw.line([345, 290, 385, 195], fill="#8b949e", width=3)
    draw.line([345, 425, 385, 475], fill="#8b949e", width=3)
    draw.line([345, 560, 385, 615], fill="#8b949e", width=3)

    # ==================== COL 3: FASTMCP SERVER ====================
    # x=875, w=235, y=170, h=330
    draw.rounded_rectangle([875, 170, 875 + 235, 170 + 330], radius=14, fill="#04261b", outline="#238636", width=3)
    draw.text((898, 196), "FastMCP Server", font=FONT_MONO_LG, fill="#3fb950")
    draw.text((898, 230), "agy_mcp_server.py", font=FONT_MONO_SM, fill="#2ea043")
    draw.line([898, 255, 1085, 255], fill="#238636", width=2)
    draw.text((898, 280), "- get_repo_map", font=FONT_MONO_MD, fill="#7ee787")
    draw.text((898, 320), "- get_file_skeleton", font=FONT_MONO_MD, fill="#7ee787")
    draw.text((898, 360), "- get_bounded_slice", font=FONT_MONO_MD, fill="#7ee787")
    draw.text((898, 400), "- get_symbol_subgraph", font=FONT_MONO_MD, fill="#7ee787")
    draw.rounded_rectangle([898, 442, 898 + 190, 442 + 42], radius=8, fill="#1b472e", outline="#238636", width=2)
    draw.text((922, 452), "stdio JSON-RPC", font=FONT_MONO_MD, fill="#3fb950")

    # Wires Col 2 -> Col 3
    draw.line([835, 195, 875, 335], fill="#8b949e", width=3)
    draw.line([835, 335, 875, 335], fill="#8b949e", width=3)
    draw.line([835, 475, 875, 335], fill="#8b949e", width=3)
    draw.line([835, 615, 875, 335], fill="#8b949e", width=3)

    # ==================== COL 4: LLM AGENT ====================
    # x=1145, w=145, y=160, h=350
    draw.rounded_rectangle([1145, 160, 1145 + 145, 160 + 350], radius=14, fill="#2b1d03", outline="#9e6a03", width=3)
    draw.text((1165, 186), "LLM AGENT", font=FONT_MONO_LG, fill="#e3b341")
    draw.text((1165, 220), "Antigravity", font=FONT_MONO_SM, fill="#d29922")
    draw.line([1165, 245, 1265, 245], fill="#9e6a03", width=2)
    draw.text((1165, 265), "Protected", font=FONT_SANS_SM, fill="#e3b341")
    draw.text((1165, 288), "Context", font=FONT_SANS_SM, fill="#e3b341")

    # Stat 1
    draw.rounded_rectangle([1155, 320, 1155 + 124, 320 + 72], radius=8, fill="#3d2b02", outline="#d29922", width=2)
    draw.text((1165, 332), "-17.2%", font=FONT_MONO_LG, fill="#f2cc60")
    draw.text((1165, 362), "Thinking Tok", font=FONT_MONO_SM, fill="#e3b341")

    # Stat 2
    draw.rounded_rectangle([1155, 408, 1155 + 124, 408 + 72], radius=8, fill="#04261b", outline="#238636", width=2)
    draw.text((1165, 420), "-38.4%", font=FONT_MONO_LG, fill="#3fb950")
    draw.text((1165, 450), "Task Cost", font=FONT_MONO_SM, fill="#7ee787")

    # Arrow Col 3 -> Col 4
    draw.line([1110, 335, 1145, 335], fill="#238636", width=4)

    img.save(ASSETS / "architecture.png", quality=95)
    print("Dark mode architecture.png rendered.")


if __name__ == "__main__":
    render_dark_banner()
    render_dark_architecture()
