from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
import io
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

from watermark_engine import add_apple_watermark, parse_exif, get_gps_from_exif

app = FastAPI(title="Apple Style Watermark Engine")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

async def fetch_amap_location(lat: float, lon: float) -> str:
    key = os.getenv("AMAP_KEY", "")
    if not key:
        return f"{lat:.4f}, {lon:.4f}"
    
    url = f"https://restapi.amap.com/v3/geocode/regeo?location={lon},{lat}&key={key}&extensions=all"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=4.0)
            data = resp.json()
            if data.get("status") == "1":
                regeo = data.get("regeocode", {})
                ac = regeo.get("addressComponent", {})
                province = ac.get("province", "")
                city = ac.get("city", "")
                district = ac.get("district", "")
                
                # 直辖市处理：当 city 为空或为列表时，将其等同于 province
                if not city or isinstance(city, list):
                    city = province
                    
                pois = regeo.get("pois", [])
                core_name = ""
                
                # 第一优先级：景区/公园/名胜古迹
                for p in pois:
                    p_type = str(p.get("type", ""))
                    if "风景名胜" in p_type or "名胜古迹" in p_type or "公园" in p_type:
                        core_name = str(p.get("name", ""))
                        break
                        
                # 第二优先级：商圈或首位 POI
                if not core_name:
                    business_areas = ac.get("businessAreas", [])
                    if business_areas and isinstance(business_areas[0], dict):
                        core_name = str(business_areas[0].get("name", ""))
                    elif pois:
                        core_name = str(pois[0].get("name", ""))
                        
                # 确定后缀
                suffix = district if (isinstance(district, str) and district) else city
                if isinstance(suffix, list): suffix = ""
                
                if core_name and suffix:
                    if len(core_name) > 12: core_name = core_name[:11] + "..."
                    return f"{core_name} · {suffix}"
                    
                # 第三优先级：行政区划 fallback
                parts = []
                if isinstance(province, str) and province: parts.append(province)
                if isinstance(city, str) and city and city != province: parts.append(city)
                if isinstance(district, str) and district: parts.append(district)
                
                if parts:
                    return "·".join(parts)
                
                formatted = regeo.get("formatted_address", "")
                if formatted:
                    return formatted
                else:
                    return ""
            else:
                return f"{lat:.4f}, {lon:.4f}"
    except Exception:
        return f"{lat:.4f}, {lon:.4f}"

@app.post("/v1/watermark")
async def process_watermark_v1(
    file: UploadFile = File(...),
    theme: Optional[str] = Form("auto"),
    logo_type: Optional[str] = Form(""),
    location: Optional[str] = Form(None),
    date_override: Optional[str] = Form(None)
):
    contents = await file.read()
    
    final_location = location
    if not final_location:
        lat, lon = get_gps_from_exif(contents)
        if lat is not None and lon is not None:
            final_location = await fetch_amap_location(lat, lon)
        else:
            final_location = ""
            
    try:
        output_io = add_apple_watermark(contents, final_location, date_override, theme, logo_type)
        output_io.seek(0)
        return Response(content=output_io.read(), media_type="image/jpeg", headers={
            "Content-Disposition": f'attachment; filename="watermarked_{file.filename}"'
        })
    except Exception as e:
        return Response(content=str(e), status_code=500)
