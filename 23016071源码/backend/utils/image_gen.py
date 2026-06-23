"""PPT 配套图片生成工具

使用 pygments 生成代码语法高亮图片
使用 PIL/Pillow 生成简单图表和流程图
"""

import os
from io import BytesIO
from pygments import highlight
from pygments.lexers import PythonLexer, get_lexer_by_name, guess_lexer
from pygments.formatters import ImageFormatter
from pygments.styles import get_style_by_name
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ppts", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 尝试加载中文字体
_FONT_PATH = None
for fp in [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]:
    if os.path.exists(fp):
        _FONT_PATH = fp
        break


def code_to_image(code: str, language: str = "python") -> str:
    """将代码渲染为语法高亮的PNG图片

    Returns:
        str: 图片文件路径
    """
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        lexer = PythonLexer(stripall=True)

    style = get_style_by_name("monokai")

    # 生成图片
    formatter = ImageFormatter(
        style=style,
        line_numbers=False,
        font_size=18,
        line_pad=4,
        hl_lines=[],
    )
    result = highlight(code, lexer, formatter)

    # 保存
    filename = f"code_{hash(code) & 0x7FFFFFFF:08x}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(result)
    return filepath


def comparison_table(left_title: str, left_items: list[str],
                     right_title: str, right_items: list[str]) -> str:
    """生成对比表格图片"""
    img_width = 1000
    row_height = 32
    header_height = 42
    rows = max(len(left_items), len(right_items)) + 1
    img_height = header_height + rows * row_height + 20

    img = Image.new("RGB", (img_width, img_height), "#1a1a2e")
    draw = ImageDraw.Draw(img)

    font_title = _get_font(22)
    font_body = _get_font(16)

    mid_x = img_width // 2

    # 标题
    draw.rectangle([0, 0, mid_x - 1, header_height], fill="#2d1f4e")
    draw.rectangle([mid_x + 1, 0, img_width, header_height], fill="#2d1f4e")
    draw.text((mid_x // 2, 10), left_title, fill="#bdbbff", anchor="ma", font=font_title)
    draw.text((mid_x + mid_x // 2, 10), right_title, fill="#bdbbff", anchor="ma", font=font_title)

    # 分隔线
    draw.line([mid_x, 0, mid_x, img_height], fill="#444", width=1)

    # 内容
    for i in range(rows - 1):
        y = header_height + i * row_height + 4
        if i % 2 == 0:
            draw.rectangle([0, y - 2, mid_x - 1, y + row_height - 2], fill="#1e1e3a")
            draw.rectangle([mid_x + 1, y - 2, img_width, y + row_height - 2], fill="#1e1e3a")

        if i < len(left_items):
            draw.text((mid_x // 2, y), left_items[i], fill="#e0e0e0", anchor="ma", font=font_body)
        if i < len(right_items):
            draw.text((mid_x + mid_x // 2, y), right_items[i], fill="#e0e0e0", anchor="ma", font=font_body)

    filename = f"table_{hash(str(left_items)) & 0x7FFFFFFF:08x}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "PNG")
    return filepath


def bullet_list_image(title: str, items: list[str]) -> str:
    """生成带标题的要点列表图片（适合PPT中展示）"""
    img_width = 900
    title_height = 50
    item_height = 36
    padding = 24
    img_height = title_height + len(items) * item_height + padding * 2

    img = Image.new("RGB", (img_width, img_height), "#1a1a2e")
    draw = ImageDraw.Draw(img)

    font_title = _get_font(28)
    font_body = _get_font(18)

    # 标题
    draw.rectangle([0, 0, img_width, title_height], fill="#2d1f4e")
    draw.text((padding, 12), title, fill="#bdbbff", font=font_title)

    # 要点
    for i, item in enumerate(items):
        y = title_height + padding + i * item_height
        draw.text((padding + 8, y), f"● {item}", fill="#e0e0e0", font=font_body)

    filename = f"bullets_{hash(str(items)) & 0x7FFFFFFF:08x}.png"
    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "PNG")
    return filepath


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取字体"""
    if _FONT_PATH:
        return ImageFont.truetype(_FONT_PATH, size)
    return ImageFont.load_default()
