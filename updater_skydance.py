from datetime import datetime, timedelta, timezone
import os
import re
import xml.etree.ElementTree as ET
import requests
import unicodedata

RETENTION_DAYS_PAST = 5
RETENTION_DAYS_FUTURE = 15

BASE_VIMN_URL = "https://epgs.vimn.com/nickelodeon_north/xmltvlegal/las/{date_str}.xml"

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
})

tmdb_cache = {}

def normalize_title(text):
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    no_accent = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = no_accent.lower().strip()
    clean = re.sub(r'\bpt\.?\s*(\d+)', r'(\1)', clean)
    clean = re.sub(r'\bpart\.?\s*(\d+)', r'(\1)', clean)
    clean = re.sub(r'[^a-z0-9]', '', clean)
    return clean

def fetch_tmdb_still(series_title, season_str, ep_str, ep_title_en="", lang="es"):
    if not series_title:
        return ""
    
    cache_key = f"{series_title}|{season_str}|{ep_str}|{ep_title_en}|still|{lang}"
    if cache_key in tmdb_cache:
        return tmdb_cache[cache_key]

    if not TMDB_TOKEN and not TMDB_API_KEY:
        return ""

    tmdb_lang = "pt-BR" if lang == "pt" else "es-ES"
    headers = {"accept": "application/json"}
    if TMDB_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_TOKEN}"
    elif TMDB_API_KEY:
        headers["Authorization"] = f"Bearer {TMDB_API_KEY}"

    try:
        url_tv = "https://api.themoviedb.org/3/search/tv"
        search_queries = [series_title]
        clean_title = re.sub(r'[:\-].*', '', series_title).strip()
        if clean_title and clean_title.lower() != series_title.lower():
            search_queries.append(clean_title)

        tv_id = None
        number_of_seasons = 10 
        for query in search_queries:
            res = http_session.get(url_tv, headers=headers, params={"query": query, "language": tmdb_lang}, timeout=4)
            if res.status_code == 200 and res.json().get("results"):
                show_data = res.json()["results"][0]
                tv_id = show_data["id"]
                detail_res = http_session.get(f"https://api.themoviedb.org/3/tv/{tv_id}", headers=headers, timeout=4)
                if detail_res.status_code == 200:
                    number_of_seasons = detail_res.json().get("number_of_seasons", 10)
                break

        if tv_id:
            s_num = None
            if season_str and str(season_str).replace('.', '', 1).isdigit():
                s_num = int(float(season_str))

            norm_target = normalize_title(ep_title_en) if ep_title_en else ""

            if norm_target:
                seasons_to_check = []
                if s_num is not None:
                    seasons_to_check.append(s_num)
                for s in range(1, number_of_seasons + 1):
                    if s not in seasons_to_check:
                        seasons_to_check.append(s)
                seasons_to_check.append(0)

                found_still = ""
                for s_check in seasons_to_check:
                    season_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_check}"
                    season_res = http_session.get(season_url, headers=headers, params={"language": "en-US"}, timeout=4)
                    if season_res.status_code == 200:
                        for ep in season_res.json().get("episodes", []):
                            if normalize_title(ep.get("name", "")) == norm_target:
                                still_path = ep.get("still_path")
                                if still_path:
                                    if not still_path.startswith('/'):
                                        still_path = '/' + still_path
                                    found_still = f"https://media.themoviedb.org/t/p/w500{still_path}"
                                    break
                    if found_still:
                        break

                if found_still:
                    tmdb_cache[cache_key] = found_still
                    return found_still

            e_num = None
            if ep_str and str(ep_str).replace('.', '', 1).isdigit():
                e_num = int(float(ep_str))

            if s_num is not None and e_num is not None:
                ep_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_num}/episode/{e_num}"
                ep_res = http_session.get(ep_url, headers=headers, params={"language": tmdb_lang}, timeout=4)
                if ep_res.status_code == 200:
                    still_path = ep_res.json().get("still_path")
                    if still_path:
                        if not still_path.startswith('/'):
                            still_path = '/' + still_path
                        img_url = f"https://media.themoviedb.org/t/p/w500{still_path}"
                        tmdb_cache[cache_key] = img_url
                        return img_url
    except Exception:
        pass

    tmdb_cache[cache_key] = ""
    return ""

NETWORKS_CONFIG = {
    "Skydance_LA.xml": {
        "generator_name": "Guia de Programacion Skydance / Nickelodeon",
        "type": "vimn",
        "feeds": [
            {"feed_id": "nickelodeon_north", "channel_id": "Nickelodeon_LA.co", "channel_name": "Nickelodeon Latinoamerica", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"}
        ]
    }
}

def parse_xmltv_date(date_str, tz_info):
    if not date_str:
        return None
    clean = re.sub(r"[^\d\s\+\-]", "", str(date_str).strip())
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", clean)
    if not m:
        return None
    y, mo, d, h, mi, s = map(int, m.groups())
    return datetime(y, mo, d, min(h, 23), min(mi, 59), min(s, 59), tzinfo=tz_info)

def update_skydance_epg():
    os.makedirs("nickelodeon", exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    
    for xml_filename, net_config in NETWORKS_CONFIG.items():
        print(f"\n==========================================")
        print(f"Procesando: {xml_filename}")
        print(f"==========================================")
        
        feed_cfg = net_config["feeds"][0]
        url = BASE_VIMN_URL.format(date_str=today_str)
        
        print(f"Descargando EPG de Skydance/Nickelodeon para la fecha: {today_str}...")
        try:
            response = http_session.get(url, timeout=30)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                
                # Enriquecer programas con imágenes de TMDB usando los elementos del feed original
                for prog in root.findall("programme"):
                    title_elem = prog.find("title")
                    subtitle_elem = prog.find("sub-title")
                    episode_elem = prog.find("episode-num")
                    
                    series_title = title_elem.text if title_elem is not None else ""
                    ep_title_en = subtitle_elem.text if subtitle_elem is not None else ""
                    
                    season_str, ep_str = "", ""
                    if episode_elem is not None and episode_elem.attrib.get("system") == "xmltv_ns":
                        parts = episode_elem.text.split(".")
                        if len(parts) >= 2 and parts[0].isdigit():
                            season_str = str(int(parts[0]) + 1)
                        if len(parts) >= 2 and parts[1].isdigit():
                            ep_str = str(int(parts[1]) + 1)

                    # Buscar e insertar imagen de TMDB si no la trae el feed
                    if not prog.find("icon") and series_title:
                        img_url = fetch_tmdb_still(series_title, season_str, ep_str, ep_title_en=ep_title_en, lang=feed_cfg["lang"])
                        if img_url:
                            ET.SubElement(prog, "icon", {"src": img_url})

                # Retención de fechas pasada y futura
                now_utc = datetime.now(timezone.utc)
                cutoff_past = now_utc - timedelta(days=RETENTION_DAYS_PAST)
                cutoff_future = now_utc + timedelta(days=RETENTION_DAYS_FUTURE)

                for p in list(root.findall("programme")):
                    stop_dt = parse_xmltv_date(p.attrib.get("stop", ""), feed_cfg["tz"])
                    start_dt = parse_xmltv_date(p.attrib.get("start", ""), feed_cfg["tz"])
                    if stop_dt and stop_dt.astimezone(timezone.utc) < cutoff_past:
                        root.remove(p)
                    elif start_dt and start_dt.astimezone(timezone.utc) > cutoff_future:
                        root.remove(p)

                # Ordenar programas cronológicamente
                sorted_progs = sorted(root.findall("programme"), key=lambda x: x.attrib.get("start", ""))
                for p in list(root.findall("programme")):
                    root.remove(p)
                for p in sorted_progs:
                    root.append(p)

                ET.indent(root, space="  ", level=0)
                filepath = os.path.join("nickelodeon", xml_filename)
                ET.ElementTree(root).write(filepath, encoding="utf-8", xml_declaration=True)
                print(f"[OK] Archivo guardado y actualizado exitosamente en: {filepath}")
            else:
                print(f"[WARN] No se encontró el XML para la fecha {today_str}. Código HTTP: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Ocurrió un error al procesar la EPG: {e}")

if __name__ == "__main__":
    update_skydance_epg()
