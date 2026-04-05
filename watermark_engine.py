import io
import os
import exifread
import datetime
import piexif
import base64
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
    local_fonts_dir = os.path.join(BASE_DIR, "fonts")
    local_font_candidates = []
    if bold: local_font_candidates = ["PingFang Bold.ttf", "PingFang Medium.ttf"]
    elif require_chinese: local_font_candidates = ["PingFang Medium.ttf", "PingFang Regular.ttf"]
    else: local_font_candidates = ["PingFang Regular.ttf", "PingFang Light.ttf"]
    for font_name in local_font_candidates:
        f_path = os.path.join(local_fonts_dir, font_name)
        if os.path.exists(f_path):
            try: return ImageFont.truetype(f_path, size)
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
    make, model = get_v(["Make"], "Apple"), get_v(["Model"], "iPhone")
    iso_val = get_v(["ISOSpeedRatings", "ISO"])
    if isinstance(iso_val, list) and iso_val: iso_val = iso_val[0]
    exposure, f_num, focal, focal_35 = get_v(["ExposureTime"]), get_v(["FNumber", "ApertureValue"]), get_v(["FocalLength"]), get_v(["FocalLenIn35mmFilm"])
    date_str = get_v(["DateTimeOriginal", "DateTime"])
    date_formatted = ""
    if date_str and date_str != "??":
        try:
            dt = datetime.datetime.strptime(str(date_str)[:19], "%Y:%m:%d %H:%M:%S")
            date_formatted = dt.strftime("%Y.%m.%d %H:%M")
        except: date_formatted = str(date_str)
    brightness, width, height = get_v(["BrightnessValue"]), get_v(["PixelXDimension", "PixelWidth", "width"]), get_v(["PixelYDimension", "PixelHeight", "height"])
    orientation = get_v(["Orientation"], 1)
    if orientation in [6, 8]: width, height = height, width
    def safe_f(v): 
        try: return float(str(v))
        except: return None
    return {
        'make': make, 'model': model,
        'device': f"{make} {model}".strip() if str(make).lower() not in str(model).lower() else model,
        'iso': iso_val, 'f_value': f_num, 'exposure': exposure,
        'focal_length': focal, 'focal_35mm': focal_35,
        'date': date_formatted, 'brightness': safe_f(brightness),
        'width': int(float(str(width or 3000))), 'height': int(float(str(height or 2000)))
    }

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

def get_semantic_params(focal_length, f_value, exposure, iso, focal_35mm=None):
    zoom = ""
    if focal_35mm:
        try:
            r = float(focal_35mm) / 24.0
            if r > 0 and r != 1.0: zoom = f"({r:.1f}x)"
        except: pass
    p = []
    if focal_length: p.append(f"{float(focal_length):.0f}mm {zoom}".strip())
    if f_value: p.append(f"f/{float(str(f_value).replace('f/','')):.2f}")
    if exposure: 
        e = float(exposure)
        if e < 1: p.append(f"1/{int(1.0/e)}s")
        else: p.append(f"{e}s")
    if iso: p.append(f"ISO{int(float(iso))}")
    return "  ".join(p)

def add_apple_watermark(image_bytes_or_pil, location="", date_override=None, theme='auto', logo_type="", return_bar_only=False, base_width=None, base_height=None, device_override=None, params_override=None, **kwargs):
    if image_bytes_or_pil is not None:
        original = image_bytes_or_pil if isinstance(image_bytes_or_pil, Image.Image) else Image.open(io.BytesIO(image_bytes_or_pil))
        original = ImageOps.exif_transpose(original)
        meta = parse_exif(image_bytes_or_pil if not isinstance(image_bytes_or_pil, Image.Image) else None)
    else:
        original, meta = None, {'device': device_override or 'iPhone'}

    base_w = original.size[0] if original else (base_width or 4000)
    S = base_w / 3000.0
    wm_h = max(158, int(300 * S)) 
    
    bv = meta.get('brightness')
    final_th = theme
    if theme == 'auto' and bv is not None: final_th = 'light' if bv < 0 else ('dark' if bv > 5 else 'light')
    
    colors = get_theme_colors(original if original else Image.new('RGB',(1,1)), final_th)
    c_main, c_sub = colors['text_main'], colors['text_sub']
    
    brand_hint = (logo_type or meta.get('make','') + " " + meta.get('device','')).lower()
    brand = 'SONY' if 'sony' in brand_hint else ('LEICA' if 'leica' in brand_hint else 'APPLE')

    v_S = S * 3.0 # 超采样 3x
    v_w, v_h = int(base_w * 3), int(wm_h * 3)
    v_canvas = Image.new('RGB', (v_w, v_h), color=colors['bg'])
    v_draw = ImageDraw.Draw(v_canvas)

    v_font_main, v_font_sub = get_font(int(52*v_S), bold=True), get_font(int(34*v_S))
    ref_h = int(115*v_S)
    logo_char = '' if brand=='APPLE' else brand
    logo_font = get_font(ref_h, bold=(brand!='APPLE'))
    if brand == 'SONY': logo_font = get_font(int(ref_h*0.85), bold=True)
    
    l_img, l_w, l_h_val = None, 0, 0
    if brand == 'SONY':
        sp = os.path.join(STATIC_DIR, "sony.png")
        if os.path.exists(sp):
            simg = Image.open(sp).convert("RGBA")
            if colors['bg'][0] < 50:
                simg.putdata([(240, 240, 240, d[3]) for d in simg.getdata()])
            lh_px = int(80 * v_S)
            lw_px = int(lh_px * simg.size[0] / simg.size[1])
            l_img = simg.resize((lw_px, lh_px), Image.LANCZOS)
            l_w = lw_px
    if not l_img:
        l_w = logo_font.getbbox(logo_char)[2] - logo_font.getbbox(logo_char)[0]
        l_h_val = logo_font.getbbox(logo_char)[3] - logo_font.getbbox(logo_char)[1]

    sig_path = os.path.join(STATIC_DIR, "sig copy.png")
    if not os.path.exists(sig_path): sig_path = os.path.join(STATIC_DIR, "sig.png")
    si, sw, sh = None, 0, 0
    if os.path.exists(sig_path):
        sig = Image.open(sig_path).convert("RGBA")
        sh = int(105 * v_S)
        sw = int(sh * sig.size[0] / sig.size[1])
        si = sig.resize((sw, sh), Image.LANCZOS)
    
    gap = int(45 * v_S)
    total_group_w = l_w + (gap if si else 0) + sw
    start_x = (v_w - total_group_w) // 2
    center_y = v_h // 2
    
    y_o = int(-80 * v_S) if brand == 'SONY' else 0
    
    if l_img:
        v_canvas.paste(l_img, (start_x, int(center_y - l_img.size[1] // 2 + y_o)), l_img)
    else:
        v_o = int(-22 * v_S) if brand == 'APPLE' else 0
        v_draw.text((start_x, int(center_y - l_h_val // 2 + y_o + v_o)), logo_char, font=logo_font, fill=c_main)
    
    if si:
        v_canvas.paste(si, (start_x + l_w + gap, int(center_y - sh // 2 + (12 * v_S))), si)

    tx = int(100 * v_S)
    device_name = device_override or meta.get('device', 'iPhone')
    if brand=='APPLE' and not device_name.lower().startswith("shot on"): device_name = f"Shot on {device_name}"
    v_draw.text((tx, int(v_h*0.45 - 30*v_S)), device_name, font=v_font_main, fill=c_main)
    params_str = params_override or get_semantic_params(kwargs.get('focal_length') or meta.get('focal_length'), kwargs.get('f_value') or meta.get('f_value'), kwargs.get('exposure') or meta.get('exposure'), kwargs.get('iso') or meta.get('iso'), kwargs.get('focal_35mm') or meta.get('focal_35mm'))
    v_draw.text((tx, int(v_h*0.45 + 35*v_S)), params_str, font=v_font_sub, fill=c_sub)
    
    loc = location or "SHANGHAI · CHINA"
    fl_font, fs_font = get_font(int(42 * v_S), bold=True, require_chinese=True), get_font(int(34 * v_S), require_chinese=True)
    lw = fl_font.getbbox(loc)[2] - fl_font.getbbox(loc)[0]
    v_draw.text((v_w - lw - tx, int(v_h*0.45 - 30*v_S)), loc, font=fl_font, fill=c_main)
    dt_str = date_override or meta.get('date', '')
    if dt_str:
        dw = fs_font.getbbox(dt_str)[2] - fs_font.getbbox(dt_str)[0]
        v_draw.text((v_w - dw - tx, int(v_h*0.45 + 35*v_S)), dt_str, font=fs_font, fill=c_sub)

    if return_bar_only:
        out = io.BytesIO()
        # 核心修正：返回给快捷指令等外部工具时，确保宽度与底图 1:1 匹配
        final_bar = v_canvas.resize((base_w, wm_h), Image.LANCZOS)
        final_bar.save(out, format='PNG')
        out.seek(0)
        return out

    final = Image.new('RGB', (original.size[0], original.size[1] + wm_h))
    final.paste(original, (0,0))
    final.paste(v_canvas.resize((original.size[0], wm_h), Image.LANCZOS), (0, original.size[1]))
    output = io.BytesIO(); final.save(output, format='JPEG', quality=95); output.seek(0); return output

def get_theme_colors(image, theme):
    if theme == 'dark': return { 'bg': (5,5,5), 'text_main': (240,240,240), 'text_sub': (119,119,119) }
    return { 'bg': (255,255,255), 'text_main': (0,0,0), 'text_sub': (153,153,153) }
