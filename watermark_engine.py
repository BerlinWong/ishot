import io
import os
import exifread
import datetime
import piexif
import base64
import random
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageOps, ImageChops, ImageFilter
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

def beautify_model(make, model):
    m, md = str(make).upper(), str(model).strip()
    if 'SONY' in m:
        md = md.replace('ILCE-', 'α').replace('7M4', '7 IV').replace('7M3', '7 III').replace('7C2', '7C II').replace('7RM5', '7R V')
        return md if 'SONY' in md.upper() else f"Sony {md}"
    if 'LEICA' in m:
        md = md.replace('LEICA CAMERA AG', '').replace('LEICA', '').strip()
        return f"Leica {md}"
    if 'APPLE' in m or 'IPHONE' in md.upper():
        return md.replace('iPhone', 'iPhone ')
    return f"{make} {model}".strip() if str(make).lower() not in str(model).lower() else model

def parse_ios_metadata(info):
    def find_key(d, target):
        t = target.lower()
        if target in d: return d[target]
        for k in d.keys():
            if k.lower().replace('{','').replace('}','') == t: return d[k]
        return {}
    tiff, exif, gps = find_key(info, "tiff"), find_key(info, "exif"), find_key(info, "gps")
    def get_v(keys, default="??"):
        # 优先级：根节点 info (通常包含当前实际尺寸) > gps > exif > tiff
        sources = [info, gps, exif, tiff]
        for s in sources:
            if not isinstance(s, dict): continue
            for k in keys:
                # 首先尝试完全匹配
                if k in s: return s[k]
                # 然后尝试忽略大小写的匹配
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
        'device': beautify_model(make, model),
        'iso': iso_val, 'f_value': f_num, 'exposure': exposure,
        'focal_length': focal, 'focal_35mm': focal_35,
        'date': date_formatted, 'brightness': safe_f(brightness),
        'lat': safe_f(get_v(["Latitude"])), 'lon': safe_f(get_v(["Longitude"])),
        'width': int(float(str(width or 3000))), 'height': int(float(str(height or 2000)))
    }

def parse_exif(image_bytes):
    if not image_bytes: return {}
    tags = exifread.process_file(io.BytesIO(image_bytes), details=False)
    make, model = str(tags.get('Image Make', 'Apple')).strip(), str(tags.get('Image Model', 'iPhone')).strip()
    iso, f_val, exp, fl = str(tags.get('EXIF ISOSpeedRatings', '??')), '??', 0.01, 24
    if 'EXIF FNumber' in tags: f_val = tags['EXIF FNumber'].values[0].num / tags['EXIF FNumber'].values[0].den if tags['EXIF FNumber'].values[0].den != 0 else '??'
    if 'EXIF ExposureTime' in tags: exp = tags['EXIF ExposureTime'].values[0].num / tags['EXIF ExposureTime'].values[0].den if tags['EXIF ExposureTime'].values[0].den != 0 else 0.01
    if 'EXIF FocalLength' in tags: fl = tags['EXIF FocalLength'].values[0].num / tags['EXIF FocalLength'].values[0].den if tags['EXIF FocalLength'].values[0].den != 0 else 24
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
    return { 'make': make, 'model': model, 'device': beautify_model(make, model), 'iso': iso, 'f_value': f_val, 'exposure': exp, 'focal_length': fl, 'focal_35mm': f_35, 'date': date_formatted, 'brightness': bv }

def get_semantic_params(focal_length, f_value, exposure, iso, focal_35mm=None):
    zoom = ""
    def safe_float(v):
        try: return float(str(v))
        except: return None
    fl_f, f35_f = safe_float(focal_length), safe_float(focal_35mm)
    if fl_f and f35_f:
        try:
            r = f35_f / 24.0
            if r > 0 and r != 1.0: zoom = f"({r:.1f}x)"
        except: pass
    p = []
    if fl_f: p.append(f"{fl_f:.0f}mm {zoom}".strip())
    fv_f = safe_float(f_value)
    if fv_f: p.append(f"f/{fv_f:.2f}")
    exp_f = safe_float(exposure)
    if exp_f: 
        if exp_f < 1: p.append(f"1/{int(1.0/exp_f)}s")
        else: p.append(f"{exp_f}s")
    iso_f = safe_float(iso)
    if iso_f: p.append(f"ISO{int(iso_f)}")
    return "  ".join(p)

def add_apple_watermark(image_bytes_or_pil, location="", date_override=None, theme='auto', logo_type="", return_bar_only=False, base_width=None, base_height=None, device_override=None, params_override=None, thumb_b64=None, **kwargs):
    if image_bytes_or_pil is not None:
        original = image_bytes_or_pil if isinstance(image_bytes_or_pil, Image.Image) else Image.open(io.BytesIO(image_bytes_or_pil))
        original = ImageOps.exif_transpose(original)
        meta = parse_exif(image_bytes_or_pil if not isinstance(image_bytes_or_pil, Image.Image) else None)
    else:
        original, meta = None, {'device': device_override or 'iPhone'}
        if thumb_b64:
            try:
                if ',' in thumb_b64: thumb_b64 = thumb_b64.split(',')[1]
                original = Image.open(io.BytesIO(base64.b64decode(thumb_b64)))
            except: pass
    
    base_w = original.size[0] if (original and not (base_width and not image_bytes_or_pil)) else (base_width or 4000)
    if base_width and not image_bytes_or_pil: base_w = base_width
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
    
    # 磨砂质感 (Frosted Glass) 实现
    if 'glass' in final_th:
        if original:
            # 在线模式：采样并模糊
            sample_h = int(original.height * 0.1)
            bottom_edge = original.crop((0, original.height - sample_h, original.width, original.height))
            v_bg = ImageOps.flip(bottom_edge).resize((v_w, v_h), Image.LANCZOS)
            v_bg = v_bg.filter(ImageFilter.GaussianBlur(radius=int(50 * S)))
            v_canvas = v_bg.convert('RGBA')
            alpha = 160 if 'dark' in final_th else 180
        else:
            # 离线模式：生成半透明纯色底 (Shortcut 本地叠加会产生透底效果)
            alpha = 210 if 'dark' in final_th else 230
            v_canvas = Image.new('RGBA', (v_w, v_h), (colors['bg'][0], colors['bg'][1], colors['bg'][2], 0))
            
        # 叠加带有质感的主题色 (RGBA 合并)
        mask = Image.new('RGBA', (v_w, v_h), (colors['bg'][0], colors['bg'][1], colors['bg'][2], alpha))
        v_canvas = Image.alpha_composite(v_canvas.convert('RGBA'), mask)
        
        # 增加磨砂颗粒感 (Grain Noise) - 极速版 (利用底层 C 运算，数万次循环合并为 1 次底层计算)
        noise_raw = os.urandom(v_w * v_h)
        noise_img = Image.frombuffer('L', (v_w, v_h), noise_raw, 'raw', 'L', 0, 1)
        noise_img = ImageOps.colorize(noise_img, (0,0,0), (50,50,50)).convert("RGBA")
        v_canvas = ImageChops.soft_light(v_canvas, noise_img)
    else:
        v_canvas = Image.new('RGB', (v_w, v_h), color=colors['bg'])
    
    v_draw = ImageDraw.Draw(v_canvas)
    v_font_main, v_font_sub = get_font(int(52*v_S), bold=True), get_font(int(34*v_S))
    ref_h = int(115*v_S)
    logo_char = '' if brand=='APPLE' else brand
    logo_font = get_font(ref_h, bold=(brand!='APPLE'))
    
    l_img, l_w, l_h_val = None, 0, 0
    if brand == 'SONY':
        sp = os.path.join(STATIC_DIR, "sony.png")
        if os.path.exists(sp):
            s_raw = Image.open(sp).convert("RGBA")
            bg = Image.new('RGBA', s_raw.size, (0,0,0,0))
            diff = ImageChops.difference(s_raw, bg)
            bbox = diff.getbbox()
            if bbox: s_raw = s_raw.crop(bbox)
            if colors['bg'][0] < 50:
                s_raw.putdata([(240, 240, 240, d[3]) for d in s_raw.getdata()])
            lw_px = int(300 * v_S)
            lh_px = int(lw_px * s_raw.size[1] / s_raw.size[0])
            l_img = s_raw.resize((lw_px, lh_px), Image.LANCZOS)
            l_w = lw_px
            
    if not l_img:
        bbox = logo_font.getbbox(logo_char)
        l_w = bbox[2] - bbox[0]
        l_h_val = bbox[3] - bbox[1]
    
    sig_path = os.path.join(STATIC_DIR, "sig copy.png")
    if not os.path.exists(sig_path): sig_path = os.path.join(STATIC_DIR, "sig.png")
    si, sw, sh = None, 0, 0
    if os.path.exists(sig_path):
        sig = Image.open(sig_path).convert("RGBA")
        if colors['bg'][0] < 50: # 如果是 Dark 背景，反色签名
            data = sig.getdata()
            new_data = []
            for item in data:
                if item[3] > 0: new_data.append((255, 255, 255, item[3]))
                else: new_data.append(item)
            sig.putdata(new_data)
        sh = int(105 * v_S)
        sw = int(sh * sig.size[0]/sig.size[1])
        si = sig.resize((sw, sh), Image.LANCZOS)
    
    gap = int(120 * v_S)
    start_x_logo = (v_w - l_w) // 2
    center_y = v_h // 2
    
    # 调优：向下 45px (由 向下 60px 向上回调 15px 得来)
    y_o = int(20 * v_S) if brand == 'SONY' else 0
    tx = int(100 * v_S)
    
    if l_img:
        v_canvas.paste(l_img, (start_x_logo, int(center_y - l_img.size[1] // 2 + y_o)), l_img)
    else:
        v_o = int(-25 * v_S) if brand == 'APPLE' else int(-15 * v_S)
        v_draw.text((start_x_logo, int(center_y - l_h_val // 2 + y_o + v_o)), logo_char, font=logo_font, fill=c_main)
    
    if si:
        v_canvas.paste(si, (start_x_logo + l_w + gap, int(center_y - sh // 2 + (12 * v_S))), si)

    device_n = device_override or meta.get('device', 'iPhone')
    if brand=='APPLE' and not device_n.lower().startswith("shot on"): device_n = f"Shot on {device_n}"
    v_draw.text((tx, int(v_h*0.45 - 30*v_S)), device_n, font=v_font_main, fill=c_main)
    p_str = params_override or get_semantic_params(kwargs.get('focal_length') or meta.get('focal_length'), kwargs.get('f_value') or meta.get('f_value'), kwargs.get('exposure') or meta.get('exposure'), kwargs.get('iso') or meta.get('iso'), kwargs.get('focal_35mm') or meta.get('focal_35mm'))
    v_draw.text((tx, int(v_h*0.45 + 35*v_S)), p_str, font=v_font_sub, fill=c_sub)
    loc, fl_font, fs_font = location or "SHANGHAI · CHINA", get_font(int(42*v_S), bold=True, require_chinese=True), get_font(int(34*v_S), require_chinese=True)
    lw = fl_font.getbbox(loc)[2] - fl_font.getbbox(loc)[0]
    v_draw.text((v_w - lw - tx, int(v_h*0.45 - 30*v_S)), loc, font=fl_font, fill=c_main)
    dt_str = date_override or meta.get('date', '')
    if dt_str:
        dw = fs_font.getbbox(dt_str)[2] - fs_font.getbbox(dt_str)[0]
        v_draw.text((v_w - dw - tx, int(v_h*0.45 + 35*v_S)), dt_str, font=fs_font, fill=c_sub)
    if return_bar_only:
        out = io.BytesIO(); v_canvas.resize((base_w, wm_h), Image.LANCZOS).save(out, format='PNG'); out.seek(0); return out
    
    final = Image.new('RGB', (original.size[0], original.size[1] + wm_h))
    final.paste(original, (0,0))
    final.paste(v_canvas.resize((original.size[0], wm_h), Image.LANCZOS), (0, original.size[1]))
    
    # 核心修复：EXIF 注入
    exif_bytes = None
    if isinstance(image_bytes_or_pil, bytes):
        try:
            exif_dict = piexif.load(image_bytes_or_pil)
            if "0th" in exif_dict:
                exif_dict["0th"][piexif.ImageIFD.ImageWidth] = final.width
                exif_dict["0th"][piexif.ImageIFD.ImageLength] = final.height
                exif_dict["0th"][piexif.ImageIFD.Orientation] = 1 
            if "Exif" in exif_dict:
                exif_dict["Exif"][piexif.ExifIFD.PixelXDimension] = final.width
                exif_dict["Exif"][piexif.ExifIFD.PixelYDimension] = final.height
            exif_bytes = piexif.dump(exif_dict)
        except: pass

    output = io.BytesIO()
    final.save(output, format='JPEG', quality=95, exif=exif_bytes) if exif_bytes else final.save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

def get_theme_colors(image, theme):
    if 'dark' in theme: return { 'bg': (27,28,30), 'text_main': (240,240,240), 'text_sub': (119,119,119) }
    return { 'bg': (255,255,255), 'text_main': (0,0,0), 'text_sub': (153,153,153) }
