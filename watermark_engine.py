import io
import os
import exifread
import datetime
import piexif
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageOps
import pillow_heif

# 注册 HEIC 解析器，以便 PIL 可以直接打开 iPhone 的 HEIC 格式图片
pillow_heif.register_heif_opener()

def get_font(size, bold=False, mono=False, require_chinese=False):
    if require_chinese:
        paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf"
        ]
        index = 1 if bold else 0
    elif mono:
        paths = [
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/SFCompact.ttf",
            "/System/Library/Fonts/Monaco.ttf",
            "/System/Library/Fonts/Menlo.ttc",
            "/Library/Fonts/Courier New Bold.ttf",
            "/Library/Fonts/Courier New.ttf"
        ]
        index = 0
    elif bold:
        paths = [
            "/System/Library/Fonts/SFProDisplay-Bold.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Bold.ttf"
        ]
        index = 1 # try bold index
    else:
        paths = [
            "/System/Library/Fonts/SFProDisplay-Regular.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial.ttf"
        ]
        index = 0
        
    for path in paths:
        if os.path.exists(path):
            try:
                if path.endswith('.ttc'):
                    # specific tuning for typical Helvetica
                    use_index = 4 if ("Helvetica" in path and bold) else index
                    return ImageFont.truetype(path, size, index=use_index)
                return ImageFont.truetype(path, size)
            except:
                pass
    return ImageFont.load_default()

def _convert_to_degrees(value):
    try:
        d, m, s = value.values
        return d.num / d.den + (m.num / m.den / 60.0) + (s.num / s.den / 3600.0)
    except:
        return None

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
    except:
        pass
    return None, None

def parse_exif(image_bytes):
    tags = exifread.process_file(io.BytesIO(image_bytes), details=False)
    
    make = str(tags.get('Image Make', 'Unknown')).strip()
    model = str(tags.get('Image Model', 'Unknown')).strip()
    if model.lower().startswith(make.lower()):
        make = ""
    
    iso = str(tags.get('EXIF ISOSpeedRatings', '??'))
    f_value = '??'
    if 'EXIF FNumber' in tags:
        fn = tags['EXIF FNumber'].values[0]
        if fn.den != 0:
            f_value = f"f/{fn.num / fn.den:.1f}"

    exposure = '??'
    if 'EXIF ExposureTime' in tags:
        exp = tags['EXIF ExposureTime'].values[0]
        if exp.den != 0:
            if exp.num == 1:
                exposure = f"1/{exp.den}"
            else:
                exposure = f"{exp.num / exp.den:.3f}"
                
    focal_length = '??'
    if 'EXIF FocalLength' in tags:
        fl = tags['EXIF FocalLength'].values[0]
        if fl.den != 0:
            focal_length = f"{fl.num / fl.den:.0f}mm"
            
    zoom = ""
    focal_35 = tags.get('EXIF FocalLengthIn35mmFilm')
    if focal_35:
        f35_val = focal_35.values[0]
        ratio = f35_val / 24.0
        if ratio > 0:
            if ratio < 0.8: zoom = f"{ratio:.1f}x"
            elif 0.8 <= ratio <= 1.2: zoom = ""
            else: zoom = f"{ratio:.1f}x"
    else:
        lens_model = str(tags.get('EXIF LensModel', ''))
        if 'Ultra Wide' in lens_model or '13mm' in lens_model: zoom = ""
        elif 'Telephoto' in lens_model and '77mm' in lens_model: zoom = "3x"
        elif 'Telephoto' in lens_model and '120mm' in lens_model: zoom = "5x"

    date_str = str(tags.get('EXIF DateTimeOriginal', ''))
    date_formatted = ""
    if date_str:
        try:
            dt = datetime.datetime.strptime(date_str[:19], "%Y:%m:%d %H:%M:%S")
            date_formatted = dt.strftime("%Y.%m.%d %I:%M:%S %p")
        except:
            date_formatted = date_str

    device_name = f"{make} {model}".strip() if make else model

    return {
        'make': make,
        'device': device_name,
        'iso': iso,
        'f_value': f_value,
        'exposure': exposure,
        'focal_length': focal_length,
        'zoom': zoom.replace('.0x', 'x'),
        'date': date_formatted
    }

def get_text_h(font, text, fallback_size):
    try:
        bbox = font.getbbox(text or "A")
        return bbox[3] - bbox[1]
    except:
        return fallback_size

def get_text_w(font, text, fallback_size):
    try:
        bbox = font.getbbox(text or "A")
        return bbox[2] - bbox[0]
    except:
        return fallback_size * len(str(text))

def get_theme_colors(image: Image.Image, force_theme="auto"):
    is_light_bg = True
    if force_theme in ['light', 'dark']:
        is_light_bg = (force_theme == 'light')
    else:
        width, height = image.size
        crop_h = max(1, int(height * 0.05))
        bottom_crop = image.crop((0, height - crop_h, width, height))
        stat = ImageStat.Stat(bottom_crop)
        if len(stat.mean) >= 3:
            r, g, b = stat.mean[:3]
            y_brightness = 0.299 * r + 0.587 * g + 0.114 * b
        else:
            y_brightness = stat.mean[0]
        is_light_bg = y_brightness > 140
        
    if is_light_bg:
        return {
            'bg': (255, 255, 255),
            'text_main': (0, 0, 0),
            'text_sub': (153, 153, 153),
            'divider': (224, 224, 224)
        }
    else:
        return {
            'bg': (5, 5, 5),
            'text_main': (240, 240, 240),
            'text_sub': (119, 119, 119),
            'divider': (51, 51, 51)
        }

def add_apple_watermark(image_bytes, location=None, date_override=None, theme="auto", logo_type=""):
    original = Image.open(io.BytesIO(image_bytes))
    
    # 彻底修正方向和 EXIF：防止苹果手机图片方向问题导致横拼变侧边
    if 'exif' in original.info:
        try:
            exif_dict = piexif.load(original.info['exif'])
            if piexif.ImageIFD.Orientation in exif_dict["0th"]:
                exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
            exif_info = piexif.dump(exif_dict)
        except:
            exif_info = original.info.get('exif', b'')
    else:
        exif_info = b''

    original = ImageOps.exif_transpose(original)
    if original.mode != 'RGB':
        original = original.convert('RGB')
        
    meta = parse_exif(image_bytes)
    
    if date_override: meta['date'] = date_override
    if location is None: location = ""
        
    base_width, base_height = original.size
    
    # 尺寸核心机制：以图片真实宽度 W (base_width) 作为绝对缩放基准
    ratio = base_width / float(base_height)
    is_landscape = ratio > 1.0 # >1.0 为横屏 (Landscape)，<=1.0 为竖屏 (Portrait)
    
    # 根据横竖屏区分高度占比
    if is_landscape:
        wm_height = int(base_width * 0.085)
    else:
        wm_height = int(base_width * 0.115) # 竖屏控制在 11.5%W
    
    if wm_height < 180: wm_height = 180
    
    # 字体与Logo计算公式 (体系化常数：主字号1.85%，副字号1.15%，Logo 3.20%)
    size_main = max(10, int(base_width * 0.0185))
    size_sub = max(8, int(base_width * 0.0115))
    logo_h = max(16, int(base_width * 0.032))
    
    padding_x = int(base_width * 0.045)
    gap_y = int(base_width * 0.012) # 行距基准 1.20%W
    
    colors = get_theme_colors(original, force_theme=theme)
    
    transparent = Image.new('RGB', (base_width, base_height + wm_height), color=colors['bg'])
    transparent.paste(original, (0, 0))
    draw = ImageDraw.Draw(transparent)
    
    font_main = get_font(size_main, bold=True)
    font_sub_zh = get_font(size_sub, bold=False, require_chinese=True) 
    font_params = get_font(size_main, bold=True, mono=True)
        
    color_main = colors['text_main']
    color_sub = colors['text_sub']
    color_divider = colors['divider']
    
    # 构建基础文本数据
    left_str_top = meta['device']
    brand_hint = logo_type.lower() if logo_type else (meta['make'] + " " + meta['device']).lower()
    
    if 'apple' in brand_hint or 'iphone' in brand_hint or 'ipad' in brand_hint: 
        brand = 'APPLE'
        if not left_str_top.lower().startswith('shot on'):
            left_str_top = f"Shot on {left_str_top}"
    elif 'leica' in brand_hint or 'xiaomi' in brand_hint or 'mi ' in brand_hint or 'redmi' in brand_hint: brand = 'LEICA'
    elif 'zeiss' in brand_hint or 'vivo' in brand_hint or 'iqoo' in brand_hint: brand = 'ZEISS'
    elif 'hasselblad' in brand_hint or 'oppo' in brand_hint or 'oneplus' in brand_hint: brand = 'HASSELBLAD'
    elif 'samsung' in brand_hint: brand = 'SAMSUNG'
    else: brand = 'TEXT'

    left_str_bottom = meta['date']

    params_arr = []
    if meta['focal_length'] != '??': 
        focus = f"{meta['focal_length']}"
        if meta['zoom']: focus += f" ({meta['zoom']})"
        params_arr.append(focus)
    if meta['f_value'] != '??': params_arr.append(meta['f_value'])
    if meta['exposure'] != '??': params_arr.append(f"{meta['exposure']}s")
    if meta['iso'] != '??': params_arr.append(f"ISO{meta['iso']}")
    
    right_str_top = "  ".join(params_arr)
    right_str_bottom = location
    
    # 动态构建Logo绘制函数
    logo_radius = int(logo_h / 2)
    brand_custom_text = meta.get('make', 'CAMERA').strip().upper() or 'CAMERA'
    if brand == 'APPLE':
        logo_font = get_font(int(logo_h * 1.3), bold=False)
        logo_w = get_text_w(logo_font, "", logo_h)
    elif brand in ('LEICA', 'ZEISS'):
        logo_w = logo_h
    elif brand == 'HASSELBLAD':
        logo_font = get_font(int(logo_h * 0.4), bold=True)
        logo_w = get_text_w(logo_font, "HASSELBLAD", logo_h)
    elif brand == 'SAMSUNG':
        logo_font = get_font(int(logo_h * 0.5), bold=True)
        logo_w = get_text_w(logo_font, "SAMSUNG", logo_h)
    else:
        logo_font = get_font(int(logo_h * 0.5), bold=True)
        logo_w = get_text_w(logo_font, brand_custom_text, logo_h)

    def draw_brand_logo(center_x, center_y, brand_name):
        def _draw_ct(fnt, t, clr, y_off=0):
            tw = get_text_w(fnt, t, logo_h)
            th = get_text_h(fnt, t, logo_h)
            draw.text((center_x - tw//2, center_y - th//2 + y_off), t, font=fnt, fill=clr)
            
        if brand_name == 'APPLE':
            _draw_ct(logo_font, "", color_main, y_off=-int(logo_h*0.1))
        elif brand_name == 'LEICA':
            draw.ellipse([center_x - logo_radius, center_y - logo_radius, center_x + logo_radius, center_y + logo_radius], fill=(227, 38, 54))
            f_in = get_font(int(logo_radius * 0.75), bold=True)
            _draw_ct(f_in, "Leica", (255,255,255), y_off=-int(logo_radius*0.1))
        elif brand_name == 'ZEISS':
            draw.ellipse([center_x - logo_radius, center_y - logo_radius, center_x + logo_radius, center_y + logo_radius], fill=(0, 85, 165))
            f_in = get_font(int(logo_radius * 0.6), bold=True)
            _draw_ct(f_in, "ZEISS", (255,255,255), y_off=-int(logo_radius*0.1))
        elif brand_name == 'HASSELBLAD':
            _draw_ct(logo_font, "HASSELBLAD", color_main)
        elif brand_name == 'SAMSUNG':
            _draw_ct(logo_font, "SAMSUNG", color_main)
        else:
            _draw_ct(logo_font, brand_custom_text, color_main)
            
    # 地址强制拦截超限溢出（针对全体，尤其是竖屏保护）
    if right_str_bottom:
        w_loc = get_text_w(font_sub_zh, right_str_bottom, size_sub)
        if w_loc > base_width * 0.40:
            parts = right_str_bottom.split("·")
            if len(parts) >= 2:
                right_str_bottom = parts[0].strip()
            
    # 横屏与竖屏的具体排版策略
    if is_landscape:
        # ------- 横屏：左右对称拉开模式 -------
        h_left_top = get_text_h(font_main, left_str_top, size_main)
        h_left_sub = get_text_h(font_sub_zh, left_str_bottom, size_sub)

        total_left_h = h_left_top + gap_y + h_left_sub
        left_y_top = base_height + (wm_height - total_left_h) // 2
        left_y_bottom = left_y_top + h_left_top + gap_y

        draw.text((padding_x, left_y_top), left_str_top, font=font_main, fill=color_main)
        if left_str_bottom:
            draw.text((padding_x, left_y_bottom), left_str_bottom, font=font_sub_zh, fill=color_sub)

        w_params = get_text_w(font_params, right_str_top, size_main)
        w_loc = get_text_w(font_sub_zh, right_str_bottom, size_sub) if right_str_bottom else 0
        text_max_w = max(w_params, w_loc)
        
        gap_logo_div = int(base_width * 0.015)
        gap_div_text = int(base_width * 0.015)
        divider_w = max(2, int(base_width * 0.001))
        
        entire_w = logo_w + gap_logo_div + divider_w + gap_div_text + text_max_w
        start_x = base_width - padding_x - entire_w
        
        block_center_y = base_height + wm_height // 2
        logo_center_x = start_x + logo_w // 2
        
        draw_brand_logo(logo_center_x, block_center_y, brand)
        
        div_h = int(logo_h * 1.2)
        div_x = start_x + logo_w + gap_logo_div
        div_y = base_height + (wm_height - div_h) // 2
        draw.rectangle([div_x, div_y, div_x + divider_w, div_y + div_h], fill=color_divider)
        
        text_start_x = div_x + divider_w + gap_div_text
        h_params = get_text_h(font_params, right_str_top, size_main)
        total_text_h = h_params + gap_y + h_left_sub
        
        text_y_top = base_height + (wm_height - total_text_h) // 2
        text_y_bottom = text_y_top + h_params + gap_y
        
        draw.text((text_start_x, text_y_top), right_str_top, font=font_params, fill=color_main)
        if right_str_bottom:
            draw.text((text_start_x, text_y_bottom), right_str_bottom, font=font_sub_zh, fill=color_sub)
            
    else:
        # ------- 竖屏：双行双轴布局 (Dual-Row Dual-Axis) -------
        h_device = get_text_h(font_main, left_str_top, size_main)
        h_date = get_text_h(font_sub_zh, left_str_bottom, size_sub)
        
        row1_h = h_device
        row2_h = max(logo_h, h_date)
        
        total_stack_h = row1_h + gap_y + row2_h
        upper_y = base_height + (wm_height - total_stack_h) // 2
        lower_y = upper_y + row1_h + gap_y
        
        # 首行 (Row 1): [Left] System / Device  ----  [Right] Params
        draw.text((padding_x, upper_y), left_str_top, font=font_main, fill=color_main)
        
        w_params = get_text_w(font_params, right_str_top, size_main)
        draw.text((base_width - padding_x - w_params, upper_y), right_str_top, font=font_params, fill=color_main)

        # 次行 (Row 2): [Left] Date  ----  [Right] Address | Divider | Logo
        # 靠左部分
        if left_str_bottom:
            # lower_y 对于日期可能会显得稍微靠上，需对齐底端，或直接写入
            date_y_adj = lower_y + (row2_h - h_date) // 2
            draw.text((padding_x, date_y_adj), left_str_bottom, font=font_sub_zh, fill=color_sub)
            
        # 靠右部分（从右向左推演计算排版）
        current_xr = base_width - padding_x
        
        # 1. 绘制地址
        if right_str_bottom:
            w_loc = get_text_w(font_sub_zh, right_str_bottom, size_sub)
            h_loc = get_text_h(font_sub_zh, right_str_bottom, size_sub)
            loc_x = current_xr - w_loc
            loc_y_adj = lower_y + (row2_h - h_loc) // 2
            draw.text((loc_x, loc_y_adj), right_str_bottom, font=font_sub_zh, fill=color_sub)
            current_xr = loc_x
            
        # 2. 绘制分割线
        gap_div_text = int(base_width * 0.015)
        gap_logo_div = int(base_width * 0.015)
        divider_w = max(2, int(base_width * 0.001))
        div_h = int(logo_h * 1.2)
        
        if right_str_bottom:
            current_xr -= gap_div_text
            div_x = current_xr - divider_w
            div_y = lower_y + (row2_h - div_h) // 2
            draw.rectangle([div_x, div_y, div_x + divider_w, div_y + div_h], fill=color_divider)
            current_xr = div_x - gap_logo_div
            
        # 3. 绘制Logo
        logo_center_x = current_xr - logo_w // 2
        logo_center_y = lower_y + row2_h // 2
        draw_brand_logo(logo_center_x, logo_center_y, brand)
            
    output = io.BytesIO()
    transparent.save(output, format='JPEG', quality=95, exif=exif_info)
    return output
