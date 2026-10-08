from datetime import datetime
import os
import requests

BASE_VIMN_URL = "https://epgs.vimn.com/nickelodeon_north/xmltvlegal/las/{date_str}.xml"

def update_skydance_epg():
    os.makedirs("nickelodeon", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    url = BASE_VIMN_URL.format(date_str=today_str)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"Descargando EPG de Skydance / Nickelodeon para la fecha: {today_str}...")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            filepath = os.path.join("nickelodeon", "Nickelodeon_LA.xml")
            with open(filepath, "wb") as f:
                f.write(response.content)
            print(f"[OK] Archivo guardado exitosamente en: {filepath}")
        else:
            print(f"[WARN] No se encontró el XML para la fecha {today_str}. Código HTTP: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Ocurrió un error al descargar la EPG: {e}")

if __name__ == "__main__":
    update_skydance_epg()
