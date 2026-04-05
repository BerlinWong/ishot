import io
import os
import exifread
import datetime
import piexif
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageOps
import pillow_heif

# 注册 HEIC 解析器，以便 PIL 可以直接打开 iPhone 的 HEIC 格式图片
pillow_heif.register_heif_opener()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

def _convert_to_degrees(value):
    try:
        d, m, s = value.values
        return d.num / d.den + (m.num / m.den / 60.0) + (s.num / s.den / 3600.0)
    except: return None

def get_gps_from_exif(image_bytes):
    tags = exifread.process_file(io.BytesIO(image_bytes), details=False)
    try:
        if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
            lat = _convert_to_degrees(tags['GPS GPSLatitude'])
            lon = _convert_to_degrees(tags['GPS GPSLongitude'])
            if lat is None or lon is None: return None, None
            lat_ref = str(tags.get('GPS GPSLatitudeRef', 'N'))
            lon_ref = str(tags.get('GPS GPSLongitudeRef', 'E'))
            if 'S' in lat_ref: lat = -lat
            if 'W' in lon_ref: lon = -lon
            return lat, lon
    except: pass
    return None, None

def get_font(size, bold=False, mono=False, require_chinese=False):
    """
    优先使用本地 ./fonts/ 目录下的字体文件。
    """
    local_fonts_dir = os.path.join(BASE_DIR, "fonts")
    
    # 定义搜索顺序
    local_font_candidates = []
    
    if bold:
        local_font_candidates = ["PingFang Bold.ttf", "PingFang Heavy.ttf", "PingFang Medium.ttf"]
    elif require_chinese:
        local_font_candidates = ["PingFang Medium.ttf", "PingFang Regular.ttf"]
    else:
        local_font_candidates = ["PingFang Regular.ttf", "PingFang Light.ttf", "PingFang ExtraLight.ttf"]
    
    # 1. 尝试本地字体
    for font_name in local_font_candidates:
        f_path = os.path.join(local_fonts_dir, font_name)
        if os.path.exists(f_path):
            try:
                return ImageFont.truetype(f_path, size)
            except: pass
            
    # 2. 系统残留兜底逻辑 (便携性兼容)
    if require_chinese:
        paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf"
        ]
        index = 1 if bold else 0
    elif mono:
        paths = ["/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Monaco.ttf", "/System/Library/Fonts/Menlo.ttc"]
        index = 0
    elif bold:
        paths = ["/System/Library/Fonts/SFProDisplay-Bold.ttf", "/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/PingFang.ttc"]
        index = 1
    else:
        paths = ["/System/Library/Fonts/SFProDisplay-Regular.ttf", "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/PingFang.ttc"]
        index = 0
        
    for path in paths:
        if os.path.exists(path):
            try:
                if path.endswith('.ttc'):
                    use_index = 4 if ("Helvetica" in path and bold) else index
                    return ImageFont.truetype(path, size, index=use_index)
                return ImageFont.truetype(path, size)
            except: pass
    return ImageFont.load_default()

def parse_ios_metadata(info):
    def find_key(d, target):
        t = target.lower()
        if target in d: return d[target]
        for k in d.keys():
            if k.lower().replace('{','').replace('}','') == t: return d[k]
        return {}

    tiff = find_key(info, "tiff")
    exif = find_key(info, "exif")
    gps = find_key(info, "gps")
    
    def get_v(keys, default="??"):
        sources = [gps, exif, tiff, info]
        for s in sources:
            if not isinstance(s, dict): continue
            for k in keys:
                for sk in s.keys():
                    if sk.lower() == k.lower(): return s[sk]
        return default

    make = get_v(["Make"], "Apple")
    model = get_v(["Model"], "iPhone")
    iso_val = get_v(["ISOSpeedRatings", "ISO"])
    if isinstance(iso_val, list) and iso_val: iso_val = iso_val[0]
    
    exposure = get_v(["ExposureTime"])
    f_num = get_v(["FNumber", "ApertureValue"])
    focal = get_v(["FocalLength"])
    focal_35 = get_v(["FocalLenIn35mmFilm"])
    
    date_str = get_v(["DateTimeOriginal", "DateTime"])
    date_formatted = ""
    if date_str and date_str != "??":
        try:
            dt = datetime.datetime.strptime(str(date_str)[:19], "%Y:%m:%d %H:%M:%S")
            date_formatted = dt.strftime("%Y.%m.%d %H:%M")
        except: date_formatted = str(date_str)

    brightness = get_v(["BrightnessValue"])
    width = get_v(["PixelXDimension", "PixelWidth", "width"])
    height = get_v(["PixelYDimension", "PixelHeight", "height"])
    orientation = get_v(["Orientation"], 1)

    if orientation in [6, 8]: width, height = height, width

    def safe_int(v, default=None):
        try: return int(float(str(v)))
        except: return default
    def safe_float(v, default=None):
        try: return float(str(v))
        except: return default

    return {
        'make': make, 'model': model,
        'device': f"{make} {model}".strip() if str(make).lower() not in str(model).lower() else model,
        'iso': iso_val, 'f_value': f_num, 'exposure': exposure,
        'focal_length': focal, 'focal_35mm': focal_35,
        'date': date_formatted, 'brightness': safe_float(brightness),
        'lat': safe_float(get_v(["Latitude"])), 'lon': safe_float(get_v(["Longitude"])),
        'width': safe_int(width, 3000), 'height': safe_int(height, 2000)
    }

def get_semantic_params(make, model, focal_length, f_value, exposure, iso, focal_35mm=None):
    zoom_str = ""
    if focal_35mm:
        try:
            ratio = float(focal_35mm) / 24.0
            if ratio > 0 and ratio != 1.0: zoom_str = f"{ratio:.1f}x"
        except: pass
    
    p_list = []
    if focal_length: 
        try: p_list.append(f"{float(focal_length):.0f}mm")
        except: pass
    if zoom_str and p_list: p_list[0] = f"{p_list[0]} ({zoom_str})"
    if f_value: 
        try: p_list.append(f"f/{float(str(f_value).replace('f/','')):.2f}")
        except: pass
    if exposure: 
        try:
            exp_f = float(exposure)
            if exp_f < 1: p_list.append(f"1/{int(1.0/exp_f)}s")
            else: p_list.append(f"{exp_f}s")
        except: pass
    if iso: 
        try: p_list.append(f"ISO{int(float(iso))}")
        except: pass
    
    params_str = "  ".join(p_list)
    return "Main Camera", params_str

def parse_exif(image_bytes):
    if not image_bytes: return {}
    tags = exifread.process_file(io.BytesIO(image_bytes), details=False)
    make = str(tags.get('Image Make', 'Apple')).strip()
    model = str(tags.get('Image Model', 'iPhone')).strip()
    iso = str(tags.get('EXIF ISOSpeedRatings', '??'))
    f_value = '??'
    if 'EXIF FNumber' in tags:
        fn = tags['EXIF FNumber'].values[0]
        if fn.den != 0: f_value = fn.num / fn.den
    exposure = 0.01
    if 'EXIF ExposureTime' in tags:
        exp = tags['EXIF ExposureTime'].values[0]
        if exp.den != 0: exposure = exp.num / exp.den
    focal_length = 24
    if 'EXIF FocalLength' in tags:
        fl = tags['EXIF FocalLength'].values[0]
        if fl.den != 0: focal_length = fl.num / fl.den
    f_35 = tags.get('EXIF FocalLengthIn35mmFilm')
    f_35 = f_35.values[0] if f_35 else None
    
    date_str = str(tags.get('EXIF DateTimeOriginal', ''))
    date_formatted = date_str
    try:
        dt = datetime.datetime.strptime(date_str[:19], "%Y:%m:%d %H:%M:%S")
        date_formatted = dt.strftime("%Y.%m.%d %H:%M")
    except: pass

    bv = None
    if 'EXIF BrightnessValue' in tags:
        b = tags['EXIF BrightnessValue'].values[0]
        if b.den != 0: bv = b.num / b.den

    return { 'make': make, 'model': model, 'device': f"{make} {model}".strip(), 'iso': iso, 'f_value': f_value, 'exposure': exposure, 'focal_length': focal_length, 'focal_35mm': f_35, 'date': date_formatted, 'brightness': bv }

def get_text_w(font, text, fallback):
    try: return font.getbbox(text or "A")[2] - font.getbbox(text or "A")[0]
    except: return fallback * len(str(text))
def get_text_h(font, text, fallback):
    try: return font.getbbox(text or "A")[3] - font.getbbox(text or "A")[1]
    except: return fallback

def get_theme_colors(image: Image.Image, force_theme="auto"):
    is_light = (force_theme != 'dark')
    if is_light: return { 'bg': (255,255,255), 'text_main': (0,0,0), 'text_sub': (153,153,153) }
    return { 'bg': (5,5,5), 'text_main': (240,240,240), 'text_sub': (119,119,119) }

def add_apple_watermark(image_bytes_or_pil, location="", date_override=None, theme='auto', logo_type="", return_bar_only=False, base_width=None, base_height=None, device_override=None, params_override=None, **kwargs):
    if image_bytes_or_pil is not None:
        if isinstance(image_bytes_or_pil, Image.Image): original = image_bytes_or_pil
        else: original = Image.open(io.BytesIO(image_bytes_or_pil))
        original = ImageOps.exif_transpose(original)
        base_width = base_width or original.size[0]
        base_height = base_height or original.size[1]
        meta = parse_exif(image_bytes_or_pil if not isinstance(image_bytes_or_pil, Image.Image) else None)
    else:
        original = None
        base_width, base_height = base_width or 3000, base_height or 2000
        meta = {'device': device_override or 'iPhone'}

    S = base_width / 3000.0
    wm_height = max(150, int(300 * S))
    
    bv = meta.get('brightness')
    final_theme = theme
    if theme == 'auto' and bv is not None:
        final_theme = 'light' if bv < 0 else ('dark' if bv > 5 else 'light')
    
    colors = get_theme_colors(original if original else Image.new('RGB',(1,1)), final_theme)
    c_main, c_sub = colors['text_main'], colors['text_sub']
    
    brand_hint = (logo_type or meta.get('make','') + " " + meta.get('device','')).lower()
    brand = 'APPLE'
    if 'leica' in brand_hint: brand = 'LEICA'
    elif 'sony' in brand_hint: brand = 'SONY'

    # 超采样渲染：关键！解决糊的问题
    render_scale = 2
    v_S = S * render_scale
    v_width, v_height = int(base_width * render_scale), int(wm_height * render_scale)
    v_canvas = Image.new('RGB', (v_width, v_height), color=colors['bg'])
    v_draw = ImageDraw.Draw(v_canvas)

    v_font_main = get_font(int(52 * v_S), bold=True)
    v_font_params = get_font(int(34 * v_S))
    v_font_loc = get_font(int(42 * v_S), bold=True, require_chinese=True)
    v_font_sub = get_font(int(34 * v_S), require_chinese=True)
    
    v_ref_h = int(115 * v_S)
    brand_text = '' if brand=='APPLE' else brand
    # 如果本地 PingFang 不带苹果 logo，BOLD 模式可能显示更好或使用系统 fallback
    v_logo_font = get_font(v_ref_h, bold=(brand!='APPLE'))
    if brand == 'SONY': v_logo_font = get_font(int(v_ref_h*0.85), bold=True)
    
    l_w = get_text_w(v_logo_font, brand_text, v_ref_h)
    l_h = get_text_h(v_logo_font, brand_text, v_ref_h)
    
    safe_device = device_override or meta.get('device', 'iPhone')
    if brand=='APPLE': safe_device = f"Shot on {safe_device}"
    _, safe_params = get_semantic_params(None, None, kwargs.get('focal_length') or meta.get('focal_length'), kwargs.get('f_value') or meta.get('f_value'), kwargs.get('exposure') or meta.get('exposure'), kwargs.get('iso') or meta.get('iso'), kwargs.get('focal_35mm') or meta.get('focal_35mm'))
    safe_params = params_override or safe_params

    # 绘制比例对齐
    tx = int(100 * v_S)
    v_draw.text((tx, int(v_height*0.45 - 30*v_S)), safe_device, font=v_font_main, fill=c_main)
    v_draw.text((tx, int(v_height*0.45 + 35*v_S)), safe_params, font=v_font_params, fill=c_sub)
    
    # 中央区域：Logo 与 签名作为一个整体水平居中，且各自垂直居中
    sig_path = os.path.join(STATIC_DIR, "sig.png")
    si = None
    sw = 0
    sh = 0
    if os.path.exists(sig_path):
        sig = Image.open(sig_path).convert("RGBA")
        sh = int(105 * v_S) # 签名高度微调，与文字视觉高度更匹配
        sw = int(sh * sig.size[0]/sig.size[1])
        si = sig.resize((sw, sh), Image.LANCZOS)
    
    y_o = int(10*v_S) if brand=='SONY' else 0
    gap = int(45 * v_S) if si else 0
    total_group_w = l_w + gap + sw
    
    # 计算起始 X，使整个组居中
    group_start_x = (v_width - total_group_w) // 2
    
    # 绘制 Logo
    logo_x = group_start_x
    logo_y = int(v_height * 0.5 - l_h // 2 + y_o)
    v_draw.text((logo_x, logo_y), brand_text, font=v_logo_font, fill=c_main)
    
    # 绘制签名
    if si:
        sig_x = logo_x + l_w + gap
        sig_y = int(v_height * 0.5 - sh // 2)
        v_canvas.paste(si, (sig_x, sig_y), si)

    # 右侧日期地址
    rx = v_width - int(100 * v_S)
    safe_loc = location or "SHANGHAI · CHINA"
    safe_date = date_override or meta.get('date') or "2026.04.06"
    lw = get_text_w(v_font_loc, safe_loc, 40*v_S)
    dw = get_text_w(v_font_sub, safe_date, 30*v_S)
    v_draw.text((rx - lw, int(v_height*0.45 - 25*v_S)), safe_loc, font=v_font_loc, fill=c_main)
    v_draw.text((rx - dw, int(v_height*0.45 + 35*v_S)), safe_date, font=v_font_sub, fill=c_sub)

    # 下采样回目标尺寸并输出无损卷轴
    final_bar = v_canvas.resize((base_width, wm_height), Image.LANCZOS)
    output = io.BytesIO()
    final_bar.save(output, format="PNG")
    output.seek(0)
    return output
