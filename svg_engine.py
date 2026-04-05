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

# Apple Logo path (from static/apple_logo.svg)
APPLE_LOGO_PATH = "M18.71 19.5C17.88 20.74 17 21.95 15.66 21.97C14.32 22 13.89 21.18 12.37 21.18C10.84 21.18 10.37 21.95 9.09997 22C7.78997 22.05 6.79997 20.68 5.95997 19.47C4.24997 17 2.93997 12.45 4.69997 9.39C5.56997 7.87 7.12997 6.91 8.81997 6.88C10.1 6.86 11.32 7.75 12.11 7.75C12.89 7.75 14.37 6.68 15.92 6.84C16.57 6.87 18.39 7.1 19.56 8.82C19.47 8.88 17.39 10.1 17.41 12.63C17.44 15.65 20.06 16.66 20.09 16.67C20.06 16.74 19.67 18.11 18.71 19.5ZM13 3.5C13.73 2.67 14.94 2.04 15.94 2C16.07 3.17 15.6 4.35 14.9 5.19C14.21 6.04 13.07 6.7 11.95 6.61C11.8 5.46 12.36 4.26 13 3.5Z"

def generate_histogram_svg(thumb_b64: str, color_fill: str = "#b3b3b3") -> str:
    if not thumb_b64:
        return ""
    try:
        if "," in thumb_b64:
            thumb_b64 = thumb_b64.split(",")[1]
        img_data = base64.b64decode(thumb_b64)
        img = Image.open(io.BytesIO(img_data)).convert("L")
        # Resize to speed up and smooth
        img = img.resize((128, 128))
        hist = img.histogram()
        
        # Smooth and group histogram into e.g. 64 bins
        bins = 64
        step = len(hist) // bins
        binned_hist = [sum(hist[i*step:(i+1)*step]) for i in range(bins)]
        
        max_val = max(binned_hist)
        if max_val == 0: max_val = 1
        
        width = 400
        height = 100
        dx = width / bins
        
        points = []
        for i, val in enumerate(binned_hist):
            x = i * dx
            y = height - (val / max_val * height * 0.8) # 80% max height for safety
            points.append(f"{x:.1f},{y:.1f}")
            
        path_d = f"M 0,{height} L " + " L ".join(points) + f" L {width},{height} Z"
        return f'<path d="{path_d}" fill="{color_fill}" opacity="0.4" />'
    except Exception as e:
        return ""

def get_sig_base64() -> str:
    path = os.path.join(STATIC_DIR, "sig.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

def generate_pro_svg(
    device: str, 
    params: str, 
    date_str: str, 
    location: str, 
    thumb_b64: str, 
    theme: str = "light",
    camera_make: str = "Apple"
) -> str:
    """
    完全参照 demo.png 布局重新定位
    """
    is_dark = (theme == "dark")
    bg_color = C_BG_DARK if is_dark else C_BG_LIGHT
    t_main = C_MAIN_DARK if is_dark else C_MAIN
    t_sub = "#777777" if is_dark else C_SUB
    
    sig_b64 = get_sig_base64()
    # 签名素材强制 1.0 不透明度（纯黑）
    sig_tag = f'<image href="data:image/png;base64,{sig_b64}" x="10" y="-80" width="300" opacity="1.0"/>' if sig_b64 else ""
    
    hist_svg = generate_histogram_svg(thumb_b64, t_sub)
    
    safe_device = device if device else "iPhone 17 Pro Max"
    safe_params = params if params else "48MP Pro Fusion camera system"
    safe_date = date_str if date_str else "2026.04.02 13:00"
    safe_loc = location if location else "SHANGHAI · CHINA"
    
    # 1. 严格参照布局设计：
    # 左侧 (X=100)：相机模组绘图 + 两行文本 (Device, Params)
    # 中间 (X=1500附近)：Logo + 签名 + 直方图
    # 右侧 (X=2900锚定)：两行文本 (Location, Date)
    
    template = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3000 300" width="3000" height="300">
    <rect width="3000" height="300" fill="{bg_color}" />
    
    <!-- LEFT ZONE: 整合了 shot.svg 的经典线框设计 -->
    <g transform="translate(100, 100)">
        <!-- 相机模组线框 -->
        <g transform="scale(0.8) translate(0, -20)">
            <rect x="0" y="0" width="200" height="110" rx="20" ry="20" fill="none" stroke="{t_main}" stroke-width="2.5"/>
            <rect x="5" y="5" width="190" height="100" rx="18" ry="18" fill="none" stroke="{t_main}" stroke-width="2"/>
            <circle cx="40" cy="35" r="20" fill="none" stroke="{t_main}" stroke-width="2.5"/>
            <circle cx="40" cy="80" r="20" fill="none" stroke="{t_main}" stroke-width="2.5"/>
            <circle cx="90" cy="60" r="20" fill="none" stroke="{t_main}" stroke-width="2.5"/>
            <circle cx="170" cy="35" r="12" fill="none" stroke="{t_main}" stroke-width="2.5"/>
            <circle cx="170" cy="80" r="12" fill="{t_main}"/>
        </g>
        
        <!-- 设备详参，相对于线框右移 -->
        <g transform="translate(185, 0)">
            <text x="50" y="40" font-family="'PingFang SC', sans-serif" font-weight="bold" font-size="52" fill="{t_main}">
                {safe_device}
            </text>
            <text x="50" y="105" font-family="'PingFang SC', sans-serif" font-weight="normal" font-size="34" fill="{t_sub}">
                {safe_params}
            </text>
        </g>
    </g>
    
    <!-- CENTER ZONE: 严格参照 demo，Logo 居中，签名紧贴 -->
    <g transform="translate(1500, 150)">
        <!-- Apple Logo -->
        <g transform="translate(-100, -35) scale(3.5)" fill="{t_main}">
            <path d="{APPLE_LOGO_PATH}"/>
        </g>
        
        <!-- 签名素材 -->
        <g transform="translate(40, 20)">
            {sig_tag}
        </g>
    </g>

    <!-- RIGHT ZONE: 原封不动参照 demo 的右对齐逻辑 -->
    <g transform="translate(2900, 100)">
        <!-- 地理位置 (首行右对齐) -->
        <text x="0" y="40" text-anchor="end" font-family="'PingFang SC', sans-serif" font-weight="bold" font-size="42" fill="{t_main}" letter-spacing="0.05em">
            {safe_loc}
        </text>
        <!-- 拍摄日期 (次行右对齐) -->
        <text x="0" y="105" text-anchor="end" font-family="'PingFang SC', sans-serif" font-weight="normal" font-size="34" fill="{t_sub}">
            {safe_date}
        </text>
    </g>
</svg>"""
    return template
