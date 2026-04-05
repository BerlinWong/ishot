import os
import io
import base64
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Variables for colors derived from demo.png
C_MAIN = "#454545"      # Dark gray for main text
C_SUB = "#b3b3b3"       # Light gray for secondary text
C_BG_LIGHT = "#ffffff"  # White background
C_BG_DARK = "#050505"   # Black background
C_MAIN_DARK = "#fefefe" # Light text on dark bg

# Logos Paths
APPLE_LOGO_PATH = "M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.09997 22C7.78997 22.05 6.79997 20.68 5.95997 19.47C4.24997 17 2.93997 12.45 4.69997 9.39C5.56997 7.87 7.12997 6.91 8.81997 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5ZM13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z"
SONY_LOGO_PATH = "M12.6,35h-8.2v2h3.5v7h-3.5v2h8.2v-2h-3.5v-7h3.5V35z M29.5,35h-3.1 c-4.4,0-7.5,2.7-7.5,7c0,4.3,3.1,7,7.5,7c4.4,0,7.5-2.7,7.5-7C37,37.7,33.9,35,29.5,35z M29.5,47c-2.4,0-4.4-1.3-4.4-5 c0-3.7,2.1-5,4.4-5s4.4,1.3,4.4,5C33.9,45.7,31.9,47,29.5,47z M56.8,35h-3.1l-9.1,10.8V35h-3.1v14h3.1l9.1-10.8V49h3.1V35z M73,35h-3.3 l-5.1,6V35h-3.1v14h3.1l5.1-6V49H73V35z M85.2,35h-3.1l-6,7V35H73v14h3.1l6-7v7h3.1V35z" # Clean Sony Path

def generate_histogram_svg(thumb_b64: str, color_fill: str = "#b3b3b3") -> str:
    if not thumb_b64: return ""
    try:
        if "," in thumb_b64: thumb_b64 = thumb_b64.split(",")[1]
        img_data = base64.b64decode(thumb_b64)
        img = Image.open(io.BytesIO(img_data)).convert("L")
        img = img.resize((128, 128))
        hist = img.histogram()
        bins = 64
        step = len(hist) // bins
        binned_hist = [sum(hist[i*step:(i+1)*step]) for i in range(bins)]
        max_val = max(binned_hist) or 1
        width, height = 400, 100
        dx = width / bins
        points = [f"{i*dx:.1f},{height - (val/max_val*height*0.8):.1f}" for i, val in enumerate(binned_hist)]
        path_d = f"M 0,{height} L " + " L ".join(points) + f" L {width},{height} Z"
        return f'<path d="{path_d}" fill="{color_fill}" opacity="0.4" />'
    except: return ""

def get_sig_base64() -> str:
    paths = [os.path.join(STATIC_DIR, "sig copy.png"), os.path.join(STATIC_DIR, "sig.png")]
    for path in paths:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    return ""

def generate_pro_svg(
    device: str, params: str, date_str: str, location: str, thumb_b64: str, theme: str = "light", camera_make: str = "Apple"
) -> str:
    is_dark = (theme == "dark")
    bg_color = C_BG_DARK if is_dark else C_BG_LIGHT
    t_main = C_MAIN_DARK if is_dark else C_MAIN
    t_sub = "#777777" if is_dark else C_SUB
    
    sig_b64 = get_sig_base64()
    sig_tag = f'<image href="data:image/png;base64,{sig_b64}" x="0" y="0" width="300" height="105" opacity="1.0"/>' if sig_b64 else ""
    
    brand = str(camera_make).upper()
    safe_device = device if device else "iPhone"
    if brand == 'APPLE' and not safe_device.lower().startswith("shot on"): safe_device = f"Shot on {safe_device}"
    
    safe_params, safe_date, safe_loc = params or "", date_str or "", location or "SHANGHAI · CHINA"
    font_family = "'PingFang SC', 'PingFang', sans-serif"
    bold_font_family = "'PingFang SC Semibold', 'PingFang SC', 'PingFang Bold', sans-serif"
    
    # 动态渲染 Logo
    if brand == 'SONY':
        logo_svg = f'<g transform="translate(0, -85) scale(2.0)"><path d="{SONY_LOGO_PATH}"/></g>'
        group_x = 1450 # Sony 较长，起点偏移
    else:
        logo_svg = f'<g transform="translate(0, -55) scale(3.5)"><path d="{APPLE_LOGO_PATH}"/></g>'
        group_x = 1290 # Apple 原有起点
        
    template = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3000 300" width="3000" height="300">
    <rect width="3000" height="300" fill="{bg_color}" />
    <g transform="translate(100, 0)">
        <text x="0" y="115" font-family="{bold_font_family}" font-weight="bold" font-size="52" fill="{t_main}">{safe_device}</text>
        <text x="0" y="185" font-family="{font_family}" font-weight="normal" font-size="34" fill="{t_sub}">{safe_params}</text>
    </g>
    <g transform="translate({group_x}, 150)">
        <g transform="translate(0, 0)" fill="{t_main}">{logo_svg}</g>
        <g transform="translate(120, -42)">{sig_tag}</g>
    </g>
    <g transform="translate(2900, 0)">
        <text x="0" y="115" text-anchor="end" font-family="{bold_font_family}" font-weight="bold" font-size="42" fill="{t_main}" letter-spacing="0.05em">{safe_loc}</text>
        <text x="0" y="185" text-anchor="end" font-family="{font_family}" font-weight="normal" font-size="34" fill="{t_sub}">{safe_date}</text>
    </g>
</svg>"""
    return template
