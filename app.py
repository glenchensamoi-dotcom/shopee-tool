# -*- coding: utf-8 -*-
"""
蝦皮商品圖批次處理工具 v28
功能：
- 拖曳上傳圖片
- 4 顆核心操作按鈕：去背、四角 Logo 偵測、辨識圖文字、處理並下載
- AI 去背等級選擇（快速、標準、精緻）
- 四角 Logo 搜尋範圍滑桿控制 (5% ~ 30%)
- 勾選文字一鍵循環切換和諧配色、動態全選/取消全選
- 即時大圖效果預覽、縮圖輪播切換（100% 寬度對齊）
- 文字替換 (支援本機/雲端字體)、補邊與輸出壓縮
"""

import io
import hashlib
import zipfile
import urllib.request
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# ----------------------------------------------------------------------
# 基本設定
# ----------------------------------------------------------------------
CANVAS_SIZE = 800
DEFAULT_PADDING_RATIO = 0.05
RESULT_PREVIEW_COUNT = 6
REMBG_WORK_SIZE = 1024
RESAMPLE = Image.Resampling.LANCZOS

POS_KEYS = [
    "左上", "中上", "右上",
    "左中", "正中", "右中",
    "左下", "中下", "右下"
]

POSITIONS = {
    "左上": (0.0, 0.0), "中上": (0.5, 0.0), "右上": (1.0, 0.0),
    "左中": (0.0, 0.5), "正中": (0.5, 0.5), "右中": (1.0, 0.5),
    "左下": (0.0, 1.0), "中下": (0.5, 1.0), "右下": (1.0, 1.0),
}

QUALITY_LEVELS = {"低": 70, "中": 85, "高": 92}

REMBG_MODELS = {
    "快速（速度最快）": "u2netp",
    "標準（平衡推薦）": "u2net",
    "精緻（最精細，較慢）": "isnet-general-use",
}

FONT_SPECS = {
    "Chiron GoRound TC": {
        "keywords": ["chirongoround", "chirongoroundtc", "chiron"],
        "urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/chirongoroundtc/ChironGoRoundTC%5Bwght%5D.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/chirongoroundhk/ChironGoRoundHK%5Bwght%5D.ttf",
        ],
    },
    "Noto Sans Traditional Chinese": {
        "keywords": ["notosanstc", "notosans", "noto-sans-tc"],
        "urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf",
            "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf",
        ],
    },
    "Noto Serif Traditional Chinese": {
        "keywords": ["notoseriftc", "notoserif", "noto-serif-tc", "notoserifhk"],
        "urls": [
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifhk/NotoSerifHK%5Bwght%5D.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notoseriftc/NotoSerifTC%5Bwght%5D.ttf",
        ],
    },
}

SYSTEM_FONT_FALLBACKS = [
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msjhbd.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

ERASE_MODES = ["整框修補", "整齊方塊"]

st.set_page_config(
    page_title="蝦皮商品圖批次處理工具",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化 Session State
if "logo_pos" not in st.session_state:
    st.session_state["logo_pos"] = "左上"
if "selected_preview_idx" not in st.session_state:
    st.session_state["selected_preview_idx"] = 0
st.session_state.setdefault("rembg_states", {})
st.session_state.setdefault("removed_logos", {})
st.session_state.setdefault("ocr_regions", {})
st.session_state.setdefault("ocr_ver", {})
st.session_state.setdefault("text_edits", {})

# ----------------------------------------------------------------------
# 外觀樣式
# ----------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Chiron+GoRound+TC:wght@400;700&family=Noto+Sans+TC:wght@400;500;700;800&family=Noto+Serif+TC:wght@400;700&display=swap');

:root { color-scheme: dark; }

html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not([class*="material"]):not(i) {
    font-family: "Chiron GoRound TC", "Noto Sans TC", "Noto Serif TC",
                 "PingFang TC", "Microsoft JhengHei", -apple-system, "Segoe UI", sans-serif;
}

/* 徹底修復上傳按鈕上的 upload 圖示字元重疊問題 & 完美置中 */
[data-testid="stFileUploaderDropzone"] button [data-testid="stIconMaterial"],
[data-testid="stFileUploaderDropzone"] button i,
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
}

.stApp [data-testid="stFileUploaderDropzone"] button {
    background: #7B3FF2 !important; 
    border: none !important; 
    border-radius: 10px !important;
    margin-top: 4px !important;
    padding: 0.45rem 1.4rem !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
    gap: 0 !important;
}
.stApp [data-testid="stFileUploaderDropzone"] button p,
.stApp [data-testid="stFileUploaderDropzone"] button span { 
    color: #FFFFFF !important; 
    margin: 0 !important;
    padding: 0 !important;
    text-align: center !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

html, body { background: #0E1117 !important; }
.stApp {
    background: #0E1117 !important;
    color: #E6EDF3 !important;
}
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {
    background: transparent !important;
}
[data-testid="stAppDeployButton"], #MainMenu, footer { display: none !important; }

.block-container { 
    padding-top: 1.6rem !important; 
    padding-bottom: 2rem !important;
    max-width: 880px; 
}

.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp p, .stApp li, .stApp label, .stApp span, .stApp small,
.stApp div[data-testid="stMarkdownContainer"] { color: #E6EDF3 !important; }
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] p,
.stApp [data-testid="stImageCaption"] { color: #8B949E !important; }

[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background: #161B22 !important; }
[data-testid="stSidebar"] { border-right: 1px solid #30363D; }
[data-testid="stSidebarContent"] { padding-top: 1.6rem !important; }

.stApp [data-testid="stSidebar"] h3 {
    font-size: 1.05rem !important; 
    font-weight: 700 !important;
    line-height: 1.3 !important;
    margin-top: 1.3rem !important; 
    margin-bottom: 0.5rem !important;
    padding: 0 !important;
}
.stApp [data-testid="stSidebar"] h3:first-of-type { margin-top: 0 !important; }
.stApp [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 0.85rem !important; font-weight: 500; color: #8B949E !important;
}

.st-key-card_upload {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 20px;
    padding: 24px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
}

.stApp [data-testid="stFileUploaderDropzone"] {
    background: #0E1117 !important;
    border: 1.5px dashed #30363D !important;
    border-radius: 16px !important;
    display: flex !important; 
    flex-direction: column !important;
    align-items: center !important; 
    justify-content: center !important;
    text-align: center !important;
    padding: 24px 20px !important;
    gap: 8px !important;
    min-height: 130px !important;
    transition: all .2s ease;
}
.stApp [data-testid="stFileUploaderDropzone"]:hover { 
    border-color: #7B3FF2 !important; 
    background: #121019 !important;
}

.stApp .stButton > button, .stApp .stDownloadButton > button {
    border-radius: 10px; font-weight: 600; padding: 0.5rem 1rem;
    border: 1px solid #30363D; background: #21262D; color: #C9D1D9;
}
.stApp button[data-testid="stBaseButton-primary"], .stApp button[kind="primary"] {
    background: #7B3FF2 !important; border: none !important;
}
.stApp button[data-testid="stBaseButton-primary"] p,
.stApp button[kind="primary"] p { color: #FFFFFF !important; }
.stApp button[data-testid="stBaseButton-primary"]:hover,
.stApp button[kind="primary"]:hover { background: #8E54F7 !important; }

.stApp [data-testid="stColorPickerBlock"],
.stApp [data-testid="stColorPicker"] div[data-baseweb="block"] {
    border: 1.5px solid #30363D !important;
    border-radius: 10px !important;
}
.stApp [data-testid="stSliderThumbValue"],
.stApp [data-testid="stSliderThumbValue"] * { color: #A774FF !important; font-weight: 600; }
.stApp [data-testid="stSlider"] div[role="slider"] { background-color: #7B3FF2 !important; }

[data-testid="stImage"] [data-testid="stElementToolbar"],
button[title="View fullscreen"], [data-testid="StyledFullScreenButton"] {
    display: none !important; visibility: hidden !important;
}

/* ========== 縮圖輪播：圖片與下方按鈕 100% 寬度齊平對齊 ========== */
.st-key-thumbnail_strip {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 14px !important;
    padding: 12px !important;
    margin-bottom: 16px !important;
}
.st-key-thumbnail_strip div[data-testid="stHorizontalBlock"] {
    overflow-x: auto !important;
    display: flex !important;
    gap: 12px !important;
}
.st-key-thumbnail_strip [data-testid="column"] {
    min-width: 70px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
}
.st-key-thumbnail_strip [data-testid="stImage"],
.st-key-thumbnail_strip [data-testid="stImage"] > div {
    width: 100% !important;
    max-width: 100% !important;
}
.st-key-thumbnail_strip [data-testid="stImage"] img {
    width: 100% !important;
    max-width: 100% !important;
    aspect-ratio: 1 / 1 !important;
    object-fit: cover !important;
    border-radius: 8px !important;
    border: 2px solid #30363D !important;
    cursor: pointer !important;
    box-sizing: border-box !important;
    display: block !important;
    transition: all 0.18s ease !important;
}
.st-key-thumbnail_strip [data-testid="column"]:has(button[kind="primary"]) [data-testid="stImage"] img {
    border-color: #7B3FF2 !important;
    box-shadow: 0 0 10px rgba(123, 63, 242, 0.6) !important;
}

/* ========== 固化標題高度與行距：檔名過長省略號截斷，留足高度不壓字 ========== */
.unified-header-title {
    height: 48px !important;
    min-height: 48px !important;
    max-height: 48px !important;
    margin-bottom: 12px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
}
.unified-header-title b {
    display: block !important;
    font-size: 0.9rem !important;
    line-height: 1.35 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}
.unified-header-title small {
    display: block !important;
    font-size: 0.8rem !important;
    color: #8B949E !important;
    line-height: 1.3 !important;
    margin-top: 2px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}

/* 左右兩側置頂對齊 */
.st-key-ocr_view_sticky {
    position: sticky !important;
    top: 3.2rem;
    z-index: 60;
    background: #161B22;
    padding: 10px 0 12px 0;
    margin-bottom: 12px;
    border-bottom: 1px solid #30363D;
}
.st-key-ocr_view_sticky [data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
}
.st-key-ocr_view_sticky [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
.st-key-ocr_view_sticky .st-key-main_preview_box {
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
}
.st-key-ocr_view_sticky img {
    max-height: 250px !important;
    width: auto !important;
    max-width: 100% !important;
    border-radius: 8px !important;
    object-fit: contain !important;
    margin-top: 0 !important;
}

/* 緊縮文字編輯排版 */
[data-testid="stExpander"] [data-testid="stHorizontalBlock"] {
    gap: 0.35rem !important;
    align-items: center !important;
    margin-bottom: -10px !important;
}
[data-testid="stExpander"] [data-testid="stTextInput"] {
    margin-bottom: 0 !important;
}
[data-testid="stExpander"] [data-testid="stSlider"] {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}
[data-testid="stExpander"] [data-testid="stCheckbox"] {
    margin-top: 4px !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 工具函式
# ----------------------------------------------------------------------
def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def file_key(f) -> str:
    return f"{f.name}|{f.size}"


def short_id(key: str) -> str:
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:8]


def open_as_rgba(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode == "CMYK":
        img = img.convert("RGB")
    return img.convert("RGBA")


@st.cache_resource(show_spinner="正在載入 AI 去背模型...")
def get_rembg_session(model_name: str = "u2netp"):
    from rembg import new_session
    return new_session(model_name)


def remove_background(img: Image.Image, session) -> Image.Image:
    from rembg import remove
    work = img.copy()
    work.thumbnail((REMBG_WORK_SIZE, REMBG_WORK_SIZE), RESAMPLE)
    return remove(work, session=session).convert("RGBA")


def fit_to_canvas(img: Image.Image, size: int, bg_rgba: tuple, allow_upscale: bool) -> Image.Image:
    w, h = img.size
    scale = min(size / w, size / h)
    if not allow_upscale:
        scale = min(scale, 1.0)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    resized = img.resize((new_w, new_h), RESAMPLE)

    canvas = Image.new("RGBA", (size, size), bg_rgba)
    canvas.alpha_composite(resized, ((size - new_w) // 2, (size - new_h) // 2))
    return canvas


def apply_glow_to_stamp(stamp: Image.Image, glow_radius: int, glow_rgb: tuple) -> tuple:
    if glow_radius <= 0:
        return stamp, 0
    pad = glow_radius * 2
    w, h = stamp.size
    alpha = stamp.getchannel("A")
    glow_mask = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    glow_mask.paste(alpha, (pad, pad))
    glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(glow_radius))

    glow_layer = Image.new("RGBA", glow_mask.size, (*glow_rgb, 255))
    glow_layer.putalpha(glow_mask)
    glow_layer.alpha_composite(stamp, (pad, pad))
    return glow_layer, pad


def build_logo_stamp(
    logo: Image.Image,
    size: int,
    scale_pct: int,
    opacity_pct: int,
    pad_pct: int = 5,
    glow_pct: int = 0,
    glow_hex: str = "#FFFFFF",
) -> tuple:
    pad = round(size * (pad_pct / 100))
    target_w = max(1, round(size * scale_pct / 100))
    target_h = max(1, round(logo.height * target_w / logo.width))

    max_side = max(1, size - 2 * pad)
    if target_h > max_side:
        shrink = max_side / target_h
        target_w, target_h = max(1, round(target_w * shrink)), max_side

    stamp = logo.resize((target_w, target_h), RESAMPLE)
    alpha = stamp.getchannel("A").point(lambda a: int(a * opacity_pct / 100))
    stamp.putalpha(alpha)

    orig_w, orig_h = stamp.size
    glow_pad = 0
    if glow_pct > 0:
        glow_radius = max(1, round(size * (glow_pct / 100.0) * 0.035))
        glow_rgb = hex_to_rgb(glow_hex)
        stamp, glow_pad = apply_glow_to_stamp(stamp, glow_radius=glow_radius, glow_rgb=glow_rgb)

    return stamp, orig_w, orig_h, glow_pad


def apply_logo(
    canvas: Image.Image,
    stamp: Image.Image,
    orig_w: int,
    orig_h: int,
    glow_pad: int,
    position: str,
    pad_pct: int = 5
) -> Image.Image:
    size = canvas.width
    pad = round(size * (pad_pct / 100))
    hx, vy = POSITIONS.get(position, (1.0, 1.0))

    target_x = pad + round((size - 2 * pad - orig_w) * hx)
    target_y = pad + round((size - 2 * pad - orig_h) * vy)

    stamp_x = target_x - glow_pad
    stamp_y = target_y - glow_pad

    stamp_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    stamp_layer.paste(stamp, (stamp_x, stamp_y))
    canvas.alpha_composite(stamp_layer)
    return canvas


# ----------------------------------------------------------------------
# 字體搜尋
# ----------------------------------------------------------------------
def find_local_user_font(label: str) -> Path:
    spec = FONT_SPECS.get(label)
    if not spec:
        return None
    search_dirs = [Path(__file__).parent / "fonts", Path(__file__).parent]
    exts = [".ttf", ".otf", ".ttc"]
    keywords = spec["keywords"]
    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for file in s_dir.iterdir():
            if file.is_file() and file.suffix.lower() in exts:
                fn = file.stem.lower().replace("-", "").replace("_", "").replace(" ", "")
                for kw in keywords:
                    if kw.replace("-", "") in fn:
                        return file
    return None


def find_system_font():
    for p in SYSTEM_FONT_FALLBACKS:
        if Path(p).exists():
            return Path(p)
    return None


@st.cache_data(show_spinner="正在載入字體...", max_entries=10)
def fetch_font_data(label: str) -> bytes:
    local_p = find_local_user_font(label)
    if local_p is not None:
        try:
            return local_p.read_bytes()
        except Exception:
            pass
            
    spec = FONT_SPECS.get(label, {})
    urls = spec.get("urls", [])
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if len(data) > 10_000:
                    return data
        except Exception:
            continue
    return b""


def font_status(label: str):
    local_p = find_local_user_font(label)
    if local_p is not None:
        st.caption(f"已成功載入本機字型：{local_p.name}")
        return
    data = fetch_font_data(label)
    if data:
        st.caption("已成功載入雲端字型")
        return
    if find_system_font() is not None:
        st.warning(f"「{label}」無本機檔案且連線失敗，目前改用系統內建字體。")
    else:
        st.error(f"「{label}」無法讀取且無系統字體，請將字體檔案放入 fonts/ 資料夾。")


def load_font(label: str, px: int, bold: bool):
    data = fetch_font_data(label)
    if data:
        try:
            font = ImageFont.truetype(io.BytesIO(data), px)
            try:
                font.set_variation_by_axes([700 if bold else 400])
            except Exception:
                pass
            return font
        except Exception:
            pass

    sys_path = find_system_font()
    if sys_path is not None:
        font = ImageFont.truetype(str(sys_path), px)
        try:
            font.set_variation_by_axes([700 if bold else 400])
        except Exception:
            pass
        return font
    return None


def render_text_layer(
    text: str, font_label: str, px: int, bold: bool,
    color_hex: str, opacity: int, stroke_px: int, stroke_hex: str,
) -> Image.Image:
    font = load_font(font_label, px, bold)
    if font is None:
        raise RuntimeError(f"字體「{font_label}」無法使用，請確認檔案已放置於目錄下。")

    draw0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = draw0.multiline_textbbox(
        (0, 0), text, font=font, stroke_width=stroke_px, align="center"
    )
    w, h = max(1, r - l), max(1, b - t)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).multiline_text(
        (-l, -t), text, font=font, align="center",
        fill=(*hex_to_rgb(color_hex), 255),
        stroke_width=stroke_px,
        stroke_fill=(*hex_to_rgb(stroke_hex), 255),
    )
    if opacity < 100:
        alpha = layer.getchannel("A").point(lambda a: int(a * opacity / 100))
        layer.putalpha(alpha)
    return layer


# ----------------------------------------------------------------------
# 原圖 Logo 四角精確偵測與消除（支援自訂角落範圍比例）
# ----------------------------------------------------------------------
def auto_detect_and_inpaint_logo(img_rgba: Image.Image, ratio_pct: int = 15) -> Image.Image:
    import cv2
    rgb = np.array(img_rgba.convert("RGB"))
    alpha = img_rgba.getchannel("A")
    H, W = rgb.shape[:2]
    
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ratio = ratio_pct / 100.0
    cw, ch = int(W * ratio), int(H * ratio)
    
    corners = [
        (0, 0, cw, ch),              # 左上
        (W - cw, 0, W, ch),          # 右上
        (0, H - ch, cw, H),          # 左下
        (W - cw, H - ch, W, H),      # 右下
    ]
    
    inpaint_mask = np.zeros((H, W), dtype=np.uint8)
    found = False
    
    for (x0, y0, x1, y1) in corners:
        roi = gray[y0:y1, x0:x1]
        edges = cv2.Canny(roi, 50, 160)
        if (edges > 0).mean() > 0.025:
            pts = np.argwhere(edges > 0)
            if len(pts) > 10:
                min_y, min_x = pts.min(axis=0)
                max_y, max_x = pts.max(axis=0)
                pad = 4
                bx0 = max(0, x0 + min_x - pad)
                by0 = max(0, y0 + min_y - pad)
                bx1 = min(W, x0 + max_x + pad)
                by1 = min(H, y0 + max_y + pad)
                cv2.rectangle(inpaint_mask, (bx0, by0), (bx1, by1), 255, -1)
                found = True
                
    if not found:
        return img_rgba
        
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    inpaint_mask = cv2.dilate(inpaint_mask, kernel, iterations=1)
    inpainted = cv2.inpaint(rgb, inpaint_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
    
    res = Image.fromarray(inpainted).convert("RGBA")
    res.putalpha(alpha)
    return res


# ----------------------------------------------------------------------
# OCR：辨識、擦除、重繪
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner="正在載入文字辨識模型...")
def get_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        from rapidocr import RapidOCR
    return RapidOCR()


def run_ocr(rgb: np.ndarray) -> list:
    engine = get_ocr_engine()
    out = engine(rgb)
    items = []
    if isinstance(out, tuple):
        for b, t, s in (out[0] or []):
            items.append((np.array(b, dtype=np.float32), t, float(s)))
    elif out is not None and getattr(out, "boxes", None) is not None:
        for b, t, s in zip(out.boxes, out.txts, out.scores):
            items.append((np.array(b, dtype=np.float32), t, float(s)))
    return items


def text_mask(roi: np.ndarray):
    import cv2
    h, w = roi.shape[:2]
    ring = max(1, min(h, w) // 8)
    border = np.concatenate([
        roi[:ring].reshape(-1, 3), roi[-ring:].reshape(-1, 3),
        roi[:, :ring].reshape(-1, 3), roi[:, -ring:].reshape(-1, 3),
    ])
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(roi.astype(np.float32) - bg, axis=2)
    d8 = np.clip(dist, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thr = float(np.clip(otsu * 0.5, 28, 60))
    mask = ((d8 > thr).astype(np.uint8)) * 255
    return mask, bg, dist


def estimate_text_color(rgb: np.ndarray, box: tuple) -> str:
    x0, y0, x1, y1 = box
    roi = rgb[y0:y1, x0:x1]
    if roi.size == 0 or min(roi.shape[:2]) < 3:
        return "#FFFFFF"
    mask, bg, dist = text_mask(roi)
    sel = mask > 0
    if sel.sum() < 5:
        return "#FFFFFF"
    import cv2
    dt = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    if dt.max() >= 1.5:
        core = dt >= dt.max() * 0.6
    else:
        core = sel & (dist >= np.percentile(dist[sel], 60))
    if core.sum() == 0:
        core = sel
    c = np.median(roi[core], axis=0).astype(int)
    return "#%02X%02X%02X" % tuple(int(v) for v in c)


def contrast_border(color_hex: str) -> str:
    r, g, b = hex_to_rgb(color_hex)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#0B3C6B" if lum > 150 else "#FFFFFF"


def detect_text_regions(img_rgba: Image.Image, min_score: float = 0.5) -> list:
    rgb = np.array(img_rgba.convert("RGB"))
    H, W = rgb.shape[:2]
    regions = []
    for poly, text, score in run_ocr(rgb):
        text = str(text).strip()
        if score < min_score or not text:
            continue
        x0 = int(max(0, poly[:, 0].min()))
        x1 = int(min(W, poly[:, 0].max()))
        y0 = int(max(0, poly[:, 1].min()))
        y1 = int(min(H, poly[:, 1].max()))
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        box = (x0, y0, x1, y1)
        color = estimate_text_color(rgb, box)
        regions.append(dict(
            box=box, text=text, score=round(score, 3),
            color=color, border_color=contrast_border(color),
        ))
    regions.sort(key=lambda r: (r["box"][1], r["box"][0]))
    return regions


def _fill_clean_rect(rgb: np.ndarray, box: tuple, grow: int, patch_hex=None):
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = box
    rx0, ry0 = max(0, x0 - grow), max(0, y0 - grow)
    rx1, ry1 = min(W, x1 + grow), min(H, y1 + grow)
    rw, rh = rx1 - rx0, ry1 - ry0
    if rw < 2 or rh < 2:
        return

    if patch_hex:
        fill = np.empty((rh, rw, 3), np.float32)
        fill[:] = hex_to_rgb(patch_hex)
    else:
        def sample(cx, cy):
            cx, cy = int(np.clip(cx, 0, W - 1)), int(np.clip(cy, 0, H - 1))
            patch = rgb[max(0, cy - 3):cy + 4, max(0, cx - 3):cx + 4]
            return np.median(patch.reshape(-1, 3), axis=0)

        off = 4
        tl, tr = sample(rx0 - off, ry0 - off), sample(rx1 + off, ry0 - off)
        bl, br = sample(rx0 - off, ry1 + off), sample(rx1 + off, ry1 + off)
        u = np.linspace(0, 1, rw, dtype=np.float32)[None, :, None]
        v = np.linspace(0, 1, rh, dtype=np.float32)[:, None, None]
        fill = (1 - v) * ((1 - u) * tl + u * tr) + v * ((1 - u) * bl + u * br)

    rgb[ry0:ry1, rx0:rx1] = np.clip(fill, 0, 255).astype(np.uint8)


def erase_text_regions(img_rgba: Image.Image, boxes: list, mode: str, dilate: int, patch_hex=None) -> Image.Image:
    import cv2
    rgb = np.array(img_rgba.convert("RGB"))
    alpha = img_rgba.getchannel("A")
    H, W = rgb.shape[:2]

    for (x0, y0, x1, y1) in boxes:
        if mode == "整齊方塊":
            _fill_clean_rect(rgb, (x0, y0, x1, y1), dilate + 2, patch_hex)
            continue
        pad = max(3, round((y1 - y0) * 0.08))
        X0, Y0, X1, Y1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
        m = max(8, int((Y1 - Y0) * 0.4))
        CX0, CY0, CX1, CY1 = max(0, X0 - m), max(0, Y0 - m), min(W, X1 + m), min(H, Y1 + m)
        ctx = rgb[CY0:CY1, CX0:CX1].copy()
        mask_ctx = np.zeros(ctx.shape[:2], np.uint8)

        mask_ctx[Y0 - CY0:Y1 - CY0, X0 - CX0:X1 - CX0] = 255
        radius = max(3, dilate)
        ctx = cv2.inpaint(ctx, mask_ctx, radius, cv2.INPAINT_TELEA)
        rgb[CY0:CY1, CX0:CX1] = ctx

    out = Image.fromarray(rgb).convert("RGBA")
    out.putalpha(alpha)
    return out


def apply_text_edits(img: Image.Image, edits: dict) -> Image.Image:
    style, items = edits["style"], edits["items"]
    if not items:
        return img
    img = erase_text_regions(
        img, [it["box"] for it in items], style["erase_mode"], style["dilate"], style.get("patch_hex"),
    )

    for it in items:
        text = it["new_text"].strip()
        if not text:
            continue
        x0, y0, x1, y1 = it["box"]
        bw, bh = x1 - x0, y1 - y0
        px = max(8, round(bh * 0.85 * it["scale"] / 100))

        def make(p):
            return render_text_layer(
                text, style["font"], p, style["bold"], it["color"], 100,
                round(p * style["stroke"] / 100) if it.get("border", True) else 0,
                it.get("border_hex", "#0B3C6B"),
            )

        layer = make(px)
        if style["fit_width"] and layer.width > bw:
            px = max(8, int(px * bw / layer.width))
            layer = make(px)

        x = (x0 + x1) // 2 - layer.width // 2
        y = (y0 + y1) // 2 - layer.height // 2
        tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
        tmp.paste(layer, (x, y))
        img = Image.alpha_composite(img, tmp)
    return img


def draw_ocr_boxes(img_rgba: Image.Image, regions: list, max_side: int = 640) -> bytes:
    base = img_rgba.convert("RGB")
    s = min(1.0, max_side / max(base.size))
    if s < 1:
        base = base.resize((round(base.width * s), round(base.height * s)), RESAMPLE)
    d = ImageDraw.Draw(base)
    try:
        f = ImageFont.load_default(size=16)
    except TypeError:
        f = ImageFont.load_default()
    for i, r in enumerate(regions):
        x0, y0, x1, y1 = [round(v * s) for v in r["box"]]
        d.rectangle((x0, y0, x1, y1), outline=(255, 64, 129), width=2)
        label = str(i + 1)
        tw = d.textlength(label, font=f)
        d.rectangle((x0, y0, x0 + tw + 8, y0 + 20), fill=(255, 64, 129))
        d.text((x0 + 4, y0 + 1), label, fill=(255, 255, 255), font=f)
    buf = io.BytesIO()
    base.save(buf, "PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------
# 輸出與預覽
# ----------------------------------------------------------------------
def encode_image(canvas: Image.Image, fmt: str, quality: int) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPG":
        rgb = Image.new("RGB", canvas.size, (255, 255, 255))
        rgb.paste(canvas, mask=canvas.getchannel("A"))
        rgb.save(buf, "JPEG", quality=quality, optimize=True)
    else:
        has_transparency = canvas.getchannel("A").getextrema()[0] < 255
        out = canvas if has_transparency else canvas.convert("RGB")
        out.save(buf, "WEBP", quality=quality, method=4)
    return buf.getvalue()


def unique_name(stem: str, ext: str, used: set) -> str:
    name, n = f"{stem}.{ext}", 1
    while name in used:
        name = f"{stem}_{n}.{ext}"
        n += 1
    used.add(name)
    return name


def make_logo_preview(
    sample_bytes,
    logo_bytes,
    scale_pct,
    opacity_pct,
    position,
    bg_hex,
    pad_pct,
    glow_pct,
    glow_hex,
    do_rembg=False,
    do_remove_logo=False,
    edits=None,
) -> bytes:
    size = 400
    bg = (*hex_to_rgb(bg_hex), 255)
    if sample_bytes:
        base = open_as_rgba(sample_bytes)
        if do_remove_logo:
            ratio_val = do_remove_logo if isinstance(do_remove_logo, int) else 15
            base = auto_detect_and_inpaint_logo(base, ratio_pct=ratio_val)
        if edits:
            base = apply_text_edits(base, edits)
        if do_rembg:
            model_key = do_rembg if isinstance(do_rembg, str) else "u2netp"
            base = remove_background(base, get_rembg_session(model_key))
        base.thumbnail((800, 800), RESAMPLE)
        canvas = fit_to_canvas(base, size, bg, True)
    else:
        canvas = Image.new("RGBA", (size, size), (22, 27, 34, 255))

    if logo_bytes:
        stamp, ow, oh, gp = build_logo_stamp(
            open_as_rgba(logo_bytes), size, scale_pct, opacity_pct, pad_pct, glow_pct, glow_hex
        )
        canvas = apply_logo(canvas, stamp, ow, oh, gp, position, pad_pct)

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


@st.cache_data(show_spinner=False, max_entries=100)
def make_strip_thumbnail(data: bytes) -> bytes:
    img = open_as_rgba(data)
    thumb = ImageOps.fit(img, (300, 300), method=RESAMPLE)
    bg = Image.new("RGBA", (300, 300), (22, 27, 34, 255))
    bg.alpha_composite(thumb)
    buf = io.BytesIO()
    bg.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ----------------------------------------------------------------------
# 側邊欄：僅保留尺寸、新 Logo 浮水印與輸出設定
# ----------------------------------------------------------------------
with st.sidebar:
    st.subheader("尺寸與底色")
    bg_hex = st.color_picker("底色", "#FFFFFF")
    allow_upscale = st.checkbox("小圖放大到 800*800px", value=True)

    st.subheader("Logo 浮水印")
    logo_file = st.file_uploader("上傳新 Logo（建議 PNG 透明底）", type=["png", "jpg", "jpeg", "webp"])

    logo_scale, logo_opacity, logo_padding = 20, 100, 5
    logo_glow_pct = 0
    glow_hex = "#FFFFFF"

    if logo_file is not None:
        logo_scale = st.slider("尺寸（%）", 10, 40, 20)
        logo_opacity = st.slider("不透明度（%）", 0, 100, 100)
        logo_padding = st.slider("邊距（上下左右 %）", 0, 20, 5)

        logo_glow_pct = st.slider("外發光 / 光暈（%）", 0, 100, 0)
        glow_hex = st.color_picker("光暈顏色", "#FFFFFF")

        st.caption("擺放位置（預設左上角）")
        curr_pos = st.session_state.get("logo_pos", "左上")
        grid_positions = [
            ["左上", "中上", "右上"],
            ["左中", "正中", "右中"],
            ["左下", "中下", "右下"],
        ]
        for row in grid_positions:
            cols = st.columns(3)
            for i, p in enumerate(row):
                btn_type = "primary" if curr_pos == p else "secondary"
                if cols[i].button(p, key=f"btn_pos_{p}", type=btn_type, use_container_width=True):
                    st.session_state["logo_pos"] = p
                    st.rerun()
        logo_pos = st.session_state.get("logo_pos", "左上")
    else:
        logo_pos = "左上"

    st.subheader("輸出設定")
    out_fmt = st.radio("格式", ["JPG", "WebP"], horizontal=True)

    quality_options = list(QUALITY_LEVELS.keys())
    quality_level = st.radio(
        "壓縮品質",
        quality_options,
        index=quality_options.index("高"),
        horizontal=True
    )
    quality = QUALITY_LEVELS[quality_level]

    dl_mode = st.radio("下載方式", ["ZIP 打包", "單張圖片"], index=1, horizontal=True)


# ----------------------------------------------------------------------
# 主畫面
# ----------------------------------------------------------------------
with st.container(key="card_upload"):
    files = st.file_uploader(
        "上傳商品圖",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="main_files",
    )

    logo_pos = st.session_state.get("logo_pos", "左上")
    sig = None
    edits_map = {}

    if files:
        cur_idx = st.session_state.get("selected_preview_idx", 0)
        if cur_idx >= len(files):
            cur_idx = 0
            st.session_state["selected_preview_idx"] = 0
        cur_file = files[cur_idx]
        cur_key = file_key(cur_file)
        kid = short_id(cur_key)

        preview_slot = st.container()
        ocr_preview_slot = None

        # ---------------- 縮圖輪播 ----------------
        if len(files) > 1:
            st.caption("點擊下方縮圖切換當前編輯圖片：")
            with st.container(key="thumbnail_strip"):
                display_count = min(len(files), 10)
                thumb_cols = st.columns(display_count)
                for idx in range(display_count):
                    f = files[idx]
                    is_active = (idx == cur_idx)
                    btn_type = "primary" if is_active else "secondary"
                    with thumb_cols[idx]:
                        st.image(make_strip_thumbnail(f.getvalue()), use_container_width=True)
                        if st.button(f"#{idx + 1}", key=f"thumb_btn_{idx}", type=btn_type, use_container_width=True):
                            st.session_state["selected_preview_idx"] = idx
                            st.rerun()

                st.components.v1.html(
                    """
                    <script>
                    const parentDoc = window.parent.document;
                    function setupThumbClicks() {
                        const strip = parentDoc.querySelector('.st-key-thumbnail_strip');
                        if (!strip) return;
                        const cols = strip.querySelectorAll('[data-testid="column"]');
                        cols.forEach(col => {
                            const img = col.querySelector('img');
                            const btn = col.querySelector('button');
                            if (img && btn && !img.dataset.hasThumbClick) {
                                img.dataset.hasThumbClick = "true";
                                img.onclick = () => btn.click();
                            }
                        });
                    }
                    setupThumbClicks();
                    setTimeout(setupThumbClicks, 200);
                    </script>
                    """,
                    height=0,
                    width=0,
                )

        # ---------------- 核心 4 按鈕工具列 ----------------
        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)

        # 1. 去背按鈕 (開關切換)
        is_rembg = st.session_state["rembg_states"].get(cur_key, False)
        rembg_label = "取消去背" if is_rembg else "AI 去背"
        if col_btn1.button(rembg_label, key="btn_toggle_rembg", use_container_width=True):
            st.session_state["rembg_states"][cur_key] = not is_rembg
            st.rerun()

        # 2. 偵測 Logo 按鈕 (開關切換)
        is_rm_logo = st.session_state["removed_logos"].get(cur_key, False)
        logo_label = "復原 Logo" if is_rm_logo else "偵測 Logo"
        if col_btn2.button(logo_label, key="btn_toggle_logo", use_container_width=True):
            st.session_state["removed_logos"][cur_key] = not is_rm_logo
            st.rerun()

        # 3. 辨識圖文字按鈕
        do_ocr = col_btn3.button("辨識圖文字", key="ocr_run", use_container_width=True)

        # 4. 下載按鈕 (直接執行批次處理並輸出)
        do_download = col_btn4.button("處理並下載", key="btn_download", type="primary", use_container_width=True)

        # 當開啟「AI 去背」或「偵測 Logo」時，顯示對應參數控制
        col_ctrl1, col_ctrl2 = st.columns(2)
        
        rembg_model_label = list(REMBG_MODELS.keys())[0]
        if is_rembg:
            with col_ctrl1:
                rembg_model_label = st.selectbox(
                    "去背等級（精緻度）",
                    options=list(REMBG_MODELS.keys()),
                    index=st.session_state.get(f"rembg_idx_{kid}", 0),
                    key=f"sel_rembg_{kid}",
                )
                st.session_state[f"rembg_idx_{kid}"] = list(REMBG_MODELS.keys()).index(rembg_model_label)

        logo_ratio = 15
        if is_rm_logo:
            target_col = col_ctrl2 if is_rembg else col_ctrl1
            with target_col:
                logo_ratio = st.slider(
                    "四角 Logo 搜尋範圍（%）", 5, 30, 
                    value=st.session_state.get(f"logo_ratio_{kid}", 15),
                    key=f"slider_logo_ratio_{kid}"
                )
                st.session_state[f"logo_ratio_{kid}"] = logo_ratio

        # ---------------- OCR 辨識邏輯 ----------------
        if do_ocr:
            try:
                with st.spinner("文字辨識中..."):
                    base_img = open_as_rgba(cur_file.getvalue())
                    regs = detect_text_regions(base_img)
                st.session_state["ocr_regions"][cur_key] = regs
                st.session_state["ocr_ver"][cur_key] = st.session_state["ocr_ver"].get(cur_key, 0) + 1
                st.session_state["text_edits"].pop(cur_key, None)
                if not regs:
                    st.info("這張圖沒有辨識到文字。")
            except Exception as e:
                st.error(f"文字辨識失敗：{e}")

        regs = st.session_state["ocr_regions"].get(cur_key)
        if regs:
            ver = st.session_state["ocr_ver"].get(cur_key, 0)

            # 置頂對齊預覽區
            with st.container(key="ocr_view_sticky"):
                vl, vr = st.columns(2)
                with vl:
                    st.markdown(
                        "<div class='unified-header-title'><b>辨識到的文字框</b><small>對應下方編號</small></div>", 
                        unsafe_allow_html=True
                    )
                    st.image(draw_ocr_boxes(open_as_rgba(cur_file.getvalue()), regs))
                with vr:
                    st.markdown(
                        f"<div class='unified-header-title'><b>即時效果預覽</b><small title='第 {cur_idx + 1} 張：{cur_file.name}'>第 {cur_idx + 1} 張：{cur_file.name}</small></div>", 
                        unsafe_allow_html=True
                    )
                    ocr_preview_slot = vr.container()

            # ---------------- 1. 文字內容編輯列表（移至上方） ----------------
            with st.expander(f"文字內容編輯（共 {len(regs)} 處辨識結果）", expanded=True):
                HARMONIOUS_PALETTES = [
                    ("auto", "auto", "原圖採樣色"),
                    ("#FFDE00", "#111111", "黃黑配"),
                    ("#1E88E5", "#FFEB3B", "藍黃配"),
                    ("#FFEB3B", "#0D47A1", "黃藍配"),
                    ("#FFFFFF", "#0B3C6B", "白藍配"),
                    ("#E53935", "#FFFFFF", "紅白配"),
                    ("#FFFFFF", "#E53935", "白紅配"),
                    ("#FF6F00", "#111111", "橘黑配"),
                    ("#FFFFFF", "#111111", "白黑配"),
                ]

                all_checked = all(
                    st.session_state.get(f"ocr_chk_{kid}_{ver}_{i}", False)
                    for i in range(len(regs))
                )

                t_col1, t_col2, _ = st.columns([1.5, 2.5, 6])
                
                # 全選 / 取消全選
                toggle_btn_label = "取消全選" if all_checked else "全選"
                if t_col1.button(toggle_btn_label, key=f"btn_toggle_sel_{kid}_{ver}"):
                    new_state = not all_checked
                    for i in range(len(regs)):
                        st.session_state[f"ocr_chk_{kid}_{ver}_{i}"] = new_state
                    st.rerun()

                # 切換配色
                if t_col2.button("切換配色", key=f"btn_cycle_color_{kid}_{ver}", type="primary"):
                    palette_key = f"palette_idx_{kid}_{ver}"
                    curr_idx = st.session_state.get(palette_key, 0)
                    next_idx = (curr_idx + 1) % len(HARMONIOUS_PALETTES)
                    st.session_state[palette_key] = next_idx
                    
                    c_text, c_border, p_name = HARMONIOUS_PALETTES[next_idx]
                    applied_count = 0
                    
                    for i, r in enumerate(regs):
                        if st.session_state.get(f"ocr_chk_{kid}_{ver}_{i}", False):
                            if c_text == "auto":
                                st.session_state[f"ocr_c_{kid}_{ver}_{i}"] = r["color"]
                                st.session_state[f"ocr_bc_{kid}_{ver}_{i}"] = r.get("border_color") or contrast_border(r["color"])
                            else:
                                st.session_state[f"ocr_c_{kid}_{ver}_{i}"] = c_text
                                st.session_state[f"ocr_bc_{kid}_{ver}_{i}"] = c_border
                            st.session_state[f"ocr_b_{kid}_{ver}_{i}"] = True
                            applied_count += 1
                            
                    if applied_count > 0:
                        st.toast(f"已套用【{p_name}】（共 {applied_count} 項）")
                    else:
                        st.warning("請先勾選左側要更換配色的項目。")
                    st.rerun()

                # 表頭
                RCOLS = [0.3, 0.35, 3.0, 0.65, 0.65, 0.65, 1.4]
                hd = st.columns(RCOLS)
                for h, name in zip(hd[1:], ["#", "文字內容", "字色", "邊框", "框色", "大小"]):
                    h.caption(name)

                items = []
                for i, r in enumerate(regs):
                    def_bc = r.get("border_color") or contrast_border(r["color"])
                    c_chk, c0, c1, c2, c3, c4, c5 = st.columns(RCOLS)

                    is_checked = c_chk.checkbox(
                        f"選擇 #{i + 1}", 
                        value=st.session_state.get(f"ocr_chk_{kid}_{ver}_{i}", False), 
                        key=f"ocr_chk_{kid}_{ver}_{i}", 
                        label_visibility="collapsed"
                    )
                    c0.markdown(f"**#{i + 1}**")

                    new_t = c1.text_input(
                        f"文字 #{i + 1}", value=r["text"], key=f"ocr_t_{kid}_{ver}_{i}",
                        label_visibility="collapsed",
                    )
                    col = c2.color_picker(
                        f"字色 #{i + 1}", value=r["color"], key=f"ocr_c_{kid}_{ver}_{i}",
                        label_visibility="collapsed",
                    )
                    bd = c3.checkbox(
                        f"邊框 #{i + 1}", value=True, key=f"ocr_b_{kid}_{ver}_{i}",
                        label_visibility="collapsed",
                    )
                    bcol = c4.color_picker(
                        f"框色 #{i + 1}", value=def_bc, key=f"ocr_bc_{kid}_{ver}_{i}",
                        label_visibility="collapsed", disabled=not bd,
                    )
                    sc = c5.slider(
                        f"大小 #{i + 1}", 50, 200, 100, key=f"ocr_s_{kid}_{ver}_{i}",
                        label_visibility="collapsed",
                    )

                    is_changed = (
                        new_t != r["text"] or 
                        col.upper() != r["color"].upper() or 
                        sc != 100 or 
                        (not bd) or 
                        bcol.upper() != def_bc.upper()
                    )

                    if is_checked or is_changed:
                        items.append(dict(
                            box=r["box"], new_text=new_t, color=col, scale=sc,
                            border=bd, border_hex=bcol,
                        ))

            # ---------------- 2. 字體、邊框與文字擦除設定（移至下方） ----------------
            with st.expander("字體、邊框與文字擦除設定", expanded=False):
                font_list = list(FONT_SPECS.keys())
                def_font_idx = font_list.index("Chiron GoRound TC") if "Chiron GoRound TC" in font_list else 0

                e1, e2 = st.columns(2)
                ed_font = e1.selectbox("新文字字體", font_list, index=def_font_idx, key="ed_font")
                ed_bold = e2.checkbox("粗體（僅可變字重字體有效）", value=True, key="ed_bold")
                font_status(ed_font)

                ed_stroke = st.slider("邊框粗細（%）", 0, 20, 8, key="ed_stroke")
                ed_dilate = st.slider("擦除範圍微調（像素）", 0, 20, 4, key="ed_dilate")

                ed_erase = st.radio("擦除方式", ERASE_MODES, horizontal=True, key="ed_erase")

                patch_color = None
                if ed_erase == "整齊方塊":
                    patch_color = st.color_picker("方塊底色", "#FFFFFF", key="ed_patch_hex")

                ed_fit = st.checkbox("自動縮放至邊框內", value=True, key="ed_fit")

            style = dict(
                font=ed_font, bold=ed_bold, stroke=ed_stroke,
                erase_mode=ed_erase, dilate=ed_dilate, fit_width=ed_fit,
                patch_hex=(patch_color if ed_erase == "整齊方塊" else None),
            )

            if items:
                st.session_state["text_edits"][cur_key] = {"style": style, "items": items}
            else:
                st.session_state["text_edits"].pop(cur_key, None)

        edits_map = dict(st.session_state["text_edits"])

        # ---------------- 大圖即時預覽 ----------------
        cur_edits = edits_map.get(cur_key)
        cur_rembg = st.session_state["rembg_states"].get(cur_key, False)
        cur_rm_logo = st.session_state["removed_logos"].get(cur_key, False)

        target_container = ocr_preview_slot if ocr_preview_slot is not None else preview_slot
        with target_container:
            if ocr_preview_slot is None:
                st.markdown(
                    f"<div class='unified-header-title'><b>即時效果預覽</b><small title='第 {cur_idx + 1} 張：{cur_file.name}'>第 {cur_idx + 1}/{len(files)} 張：{cur_file.name}</small></div>", 
                    unsafe_allow_html=True
                )
            try:
                main_preview_bytes = make_logo_preview(
                    cur_file.getvalue(),
                    logo_file.getvalue() if logo_file is not None else None,
                    logo_scale, logo_opacity, logo_pos, bg_hex,
                    logo_padding, logo_glow_pct, glow_hex,
                    do_rembg=(REMBG_MODELS[rembg_model_label] if cur_rembg else False),
                    do_remove_logo=(logo_ratio if cur_rm_logo else False),
                    edits=cur_edits,
                )
                with st.container(key="main_preview_box"):
                    st.image(main_preview_bytes)
            except Exception as e:
                st.warning(f"預覽產生失敗：{e}")

        # ---------------- 批次處理與下載 ----------------
        if do_download and files:
            stamp, orig_w, orig_h, glow_pad = None, 0, 0, 0
            if logo_file is not None:
                try:
                    logo_img = open_as_rgba(logo_file.getvalue())
                    stamp, orig_w, orig_h, glow_pad = build_logo_stamp(
                        logo_img, CANVAS_SIZE, logo_scale, logo_opacity, logo_padding, logo_glow_pct, glow_hex
                    )
                except Exception as e:
                    st.warning(f"Logo 讀取失敗，略過浮水印：{e}")

            bg_rgba = (*hex_to_rgb(bg_hex), 255)
            ext = "jpg" if out_fmt == "JPG" else "webp"
            zip_buf = io.BytesIO()
            used_names: set = set()
            failures: list = []
            previews: list = []
            out_files: list = []
            sizes: list = []
            progress = st.progress(0.0, text="準備處理...")

            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_STORED) as zf:
                for i, f in enumerate(files):
                    fkey = file_key(f)
                    progress.progress(i / len(files), text=f"處理中 ({i + 1}/{len(files)})：{f.name}")
                    try:
                        img = open_as_rgba(f.getvalue())

                        # 1. 偵測並移除四角原 Logo
                        if st.session_state["removed_logos"].get(fkey, False):
                            r_val = st.session_state.get(f"logo_ratio_{short_id(fkey)}", 15)
                            img = auto_detect_and_inpaint_logo(img, ratio_pct=r_val)

                        # 2. OCR 文字擦除替換
                        ed = edits_map.get(fkey)
                        if ed:
                            img = apply_text_edits(img, ed)

                        # 3. AI 去背（依設定等級執行）
                        if st.session_state["rembg_states"].get(fkey, False):
                            m_idx = st.session_state.get(f"rembg_idx_{short_id(fkey)}", 0)
                            m_name = list(REMBG_MODELS.values())[m_idx]
                            img = remove_background(img, get_rembg_session(m_name))

                        # 4. 等比例補邊
                        canvas = fit_to_canvas(img, CANVAS_SIZE, bg_rgba, allow_upscale)

                        # 5. 上傳新浮水印 Logo
                        if stamp is not None:
                            canvas = apply_logo(canvas, stamp, orig_w, orig_h, glow_pad, logo_pos, logo_padding)

                        data = encode_image(canvas, out_fmt, quality)
                        out_name = unique_name(Path(f.name).stem, ext, used_names)
                        zf.writestr(out_name, data)
                        out_files.append((out_name, data))
                        sizes.append(len(data))
                        if len(previews) < RESULT_PREVIEW_COUNT:
                            previews.append((f.name, data))
                    except Exception as e:
                        failures.append((f.name, str(e)))

            progress.empty()

            st.session_state["result"] = {
                "zip": zip_buf.getvalue(),
                "files": out_files,
                "ok": len(sizes),
                "failures": failures,
                "previews": previews,
                "max_kb": max(sizes) / 1024 if sizes else 0,
                "avg_kb": sum(sizes) / len(sizes) / 1024 if sizes else 0,
                "ext": ext,
            }

        # ---------------- 下載結果區 ----------------
        res = st.session_state.get("result")
        if res and res.get("ok", 0) > 0:
            st.write("---")
            if dl_mode == "ZIP 打包":
                st.download_button(
                    "下載打包 ZIP 檔案",
                    data=res["zip"],
                    file_name=f"shopee_images_{res['ext']}.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                )
            else:
                st.caption("單張下載：")
                mime = "image/jpeg" if res["ext"] == "jpg" else "image/webp"
                for i, (name, data) in enumerate(res["files"]):
                    c1, c2, c3 = st.columns([1, 4, 2])
                    c1.image(make_strip_thumbnail(data), width=48)
                    c2.caption(f"{name}・{len(data) / 1024:.0f} KB")
                    c3.download_button("下載", data=data, file_name=name, mime=mime, key=f"dl_one_{i}")