from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
import io
import base64
import json
from typing import Optional, Union, Dict, Any
import datetime
import httpx
from dotenv import load_dotenv

load_dotenv()

from watermark_engine import add_apple_watermark, parse_exif, get_gps_from_exif, parse_ios_metadata, get_semantic_params

app = FastAPI(title="Leica Style Watermark Engine (Pro)")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 挂载静态资源
if not os.path.exists(STATIC_DIR): os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

async def fetch_amap_location(lat: float, lon: float) -> str:
    key = os.getenv("AMAP_KEY", "")
    if not key: return f"{lat:.4f}, {lon:.4f}"
    url = f"https://restapi.amap.com/v3/geocode/regeo?location={lon},{lat}&key={key}&extensions=all"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=4.0)
            data = resp.json()
            if data.get("status") == "1":
                regeo = data.get("regeocode", {})
                ac = regeo.get("addressComponent", {})
                pois = regeo.get("pois", [])
                core_name = ""
                # 优先级识别
                for p in pois:
                    p_type = str(p.get("type", ""))
                    if any(x in p_type for x in ["风景名胜", "名胜古迹", "公园"]):
                        core_name = str(p.get("name", ""))
                        break
                if not core_name and pois: core_name = str(pois[0].get("name", ""))
                suffix = ac.get("district") or ac.get("city") or ""
                if core_name: return f"{core_name} · {suffix}"
                return regeo.get("formatted_address", f"{lat:.2f}, {lon:.2f}")
    except: pass
    return f"{lat:.4f}, {lon:.4f}"

@app.post("/v1/watermark/json")
async def generate_pro_json_bar_endpoint(
    info: Dict[str, Any],
    theme: str = "light",
    logo_type: str = "Apple"
):
    """
    专门适配 iOS 快捷指令：接收原始 Metadata JSON 并返回无损 PNG 水印条。
    """
    now = datetime.datetime.now().strftime("%Y.%m.%d %H:%M")
    
    # 自动解包逻辑：应对快捷指令强制转文本的降级行为
    target_info = info
    raw_info = info.get("info")
    if raw_info:
        if isinstance(raw_info, dict): target_info = raw_info
        elif isinstance(raw_info, str):
            try: target_info = json.loads(raw_info)
            except: pass
    
    m = parse_ios_metadata(target_info)
    
    # 地位置动态解析
    f_loc = ""
    def try_float(v):
        try: return float(v)
        except: return None
    c_lat, c_lon = try_float(m.get('lat')), try_float(m.get('lon'))
    if c_lat and c_lon:
        f_loc = await fetch_amap_location(c_lat, c_lon)
    f_loc = f_loc or "CHINA"
    
    output_io = add_apple_watermark(
        None, 
        location=f_loc, 
        date_override=m.get('date') or now, 
        theme=theme, 
        logo_type=logo_type, 
        return_bar_only=True, 
        base_width=m.get('width') or 3000,
        base_height=m.get('height') or 2000,
        device_override=m.get('device', 'iPhone'),
        focal_length=m.get('focal_length'),
        f_value=m.get('f_value'),
        exposure=m.get('exposure'),
        iso=m.get('iso'),
        focal_35mm=m.get('focal_35mm')
    )

    return Response(content=output_io.read(), media_type="image/png")

@app.post("/v1/watermark/png")
async def generate_pro_png_bar_endpoint(
    file: Optional[UploadFile] = File(None),
    width: Optional[int] = Form(None),
    device: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    date_str: Optional[str] = Form(None),
    theme: str = Form("light"),
    logo_type: str = Form("Apple")
):
    """
    通用 PNG 水印条接口。
    """
    now = datetime.datetime.now().strftime("%Y.%m.%d %H:%M")
    if file:
        contents = await file.read()
        f_loc = location
        if not f_loc:
            c_lat, c_lon = get_gps_from_exif(contents)
            if c_lat: f_loc = await fetch_amap_location(c_lat, c_lon)
        f_loc = f_loc or "CHINA"
        output_io = add_apple_watermark(contents, f_loc, date_str, theme, logo_type, return_bar_only=True, base_width=width, device_override=device, params_override=params)
    else:
        output_io = add_apple_watermark(None, location=location or "CHINA", date_override=date_str or now, theme=theme, logo_type=logo_type, base_width=width, device_override=device, params_override=params)

    return Response(content=output_io.read(), media_type="image/png")
