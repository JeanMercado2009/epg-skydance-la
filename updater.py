import os
import re
import io
import zipfile
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import unicodedata
import openpyxl

RETENTION_DAYS_PAST = 5
RETENTION_DAYS_FUTURE = 15

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
BASE_DAILY_URL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId={feed_id}&format=xls"
DOWNLOAD_FILE_URL = "https://epg.tapkit.warnermedia.com/api/domain/users/register/downloaded/file"
LOCAL_BREAKS_URL = "https://epg.tapkit.warnermedia.com/api/epg/tapkitLocalBreaks/downloadfile"

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
    
    cache_key = f"{series_title}|{season_str}|{ep_str}|{ep_title_en}|{lang}"
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

def download_and_parse_local_breaks(token, date_str, tz_info, feed_code="CTNPRH"):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://epg.tapkit.warnermedia.com",
        "Referer": "https://epg.tapkit.warnermedia.com/epg/networks/2"
    }
    breaks_events = []
    for break_num in range(1, 10):
        filename = f"{date_str}_{feed_code}_CNLH Break {break_num}_1.csv"
        path = f"fromCueToneReport/done{filename}"
        payload = {"name": filename, "path": path}
        try:
            res = http_session.post(LOCAL_BREAKS_URL, json=payload, headers=headers, timeout=10)
            if res.status_code == 200 and len(res.content) > 0:
                df_break = pd.read_csv(io.BytesIO(res.content), sep=';')
                in_time = None
                for _, row in df_break.iterrows():
                    type_val = str(row.get("Type") or "").strip().upper()
                    date_offset = str(row.get("Log Date + Offset") or "").strip()
                    
                    if "IN" in type_val:
                        m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", date_offset)
                        if m:
                            y, mo, d, h, mi, s = map(int, m.groups())
                            in_time = datetime(y, mo, d, h, mi, s, tzinfo=tz_info)
                    elif "OUT" in type_val and in_time:
                        m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", date_offset)
                        if m:
                            y, mo, d, h, mi, s = map(int, m.groups())
                            out_time = datetime(y, mo, d, h, mi, s, tzinfo=tz_info)
                            if out_time > in_time:
                                breaks_events.append({
                                    "start": in_time, "stop": out_time,
                                    "title": "Pausa Comercial", "desc": "Espacio publicitario y promos de la señal.",
                                    "category": "Comercial", "type": "break"
                                })
                            in_time = None
        except Exception:
            pass
    return breaks_events

# -------------------------------------------------------------
# CONFIGURACIÓN COMPLETA DE TODAS TUS REDES Y CANALES
# -------------------------------------------------------------
NETWORKS_CONFIG = {
    "CNLA_EPG.xml": {
        "generator_name": "Guia de Programacion Cartoon Network MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/2",
        "type": "daily",
        "feeds": [
            {"feed_id": "CNLA_PAN", "channel_id": "CNLA_PAN.co", "channel_name": "Cartoon Network Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "CNLA_BR", "channel_id": "CNLA_BR.br", "channel_name": "Cartoon Network Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    },
    "CTOOLA_EPG.xml": {
        "generator_name": "Guia de Programacion Cartoonito MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/1",
        "type": "daily",
        "feeds": [
            {"feed_id": "CTOOLA_PAN", "channel_id": "CTOO_PAN.co", "channel_name": "Cartoonito Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "CTOOLA_TVEGO", "channel_id": "CTOO_PANTVEGO.co", "channel_name": "Cartoonito Panregional TVEGO", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "CTOOLA_BR", "channel_id": "CTOO_BR.br", "channel_name": "Cartoonito Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"},
        ]
    },
    "DKLA_EPG.xml": {
        "generator_name": "Guia de Programacion Discovery Kids MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/47",
        "type": "daily",
        "feeds": [
            {"feed_id": "DKLA_PAN", "file_id": "10587908", "channel_id": "DKLA_PAN.co", "channel_name": "Discovery Kids Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "DKLA_CAR", "file_id": "10587948", "channel_id": "DKLA_CAR.co", "channel_name": "Discovery Kids Caribe", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "DKLA_MX", "file_id": "10587962", "channel_id": "DKLA_MX.mx", "channel_name": "Discovery Kids Mexico", "lang": "es", "tz": timezone(timedelta(hours=-6)), "tz_str": "-0600"},
            {"feed_id": "DKLA_BR", "file_id": "10587870", "channel_id": "DKLA_BR.br", "channel_name": "Discovery Kids Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    },
    "WARNERLA_EPG.xml": {
        "generator_name": "Guia de Programacion Warner Channel MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/warner",
        "type": "daily",
        "feeds": [
            {"feed_id": "WARNERLA_CO", "channel_id": "WARNER_CO.co", "channel_name": "Warner Channel Colombia", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "WARNERLA_MX", "channel_id": "WARNER_MX.mx", "channel_name": "Warner Channel México", "lang": "es", "tz": timezone(timedelta(hours=-6)), "tz_str": "-0600"},
            {"feed_id": "WARNERLA_AR", "channel_id": "WARNER_AR.ar", "channel_name": "Warner Channel Argentina", "lang": "es", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"},
            {"feed_id": "WARNERLA_CH", "channel_id": "WARNER_CL.cl", "channel_name": "Warner Channel Chile", "lang": "es", "tz": timezone(timedelta(hours=-4)), "tz_str": "-0400"},
            {"feed_id": "WARNERLA_VE", "channel_id": "WARNER_VE.ve", "channel_name": "Warner Channel Venezuela", "lang": "es", "tz": timezone(timedelta(hours=-4)), "tz_str": "-0400"},
            {"feed_id": "WARNERLA_AN", "channel_id": "WARNER_AN.co", "channel_name": "Warner Channel Andes", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "WARNERLA_BH", "channel_id": "WARNER_BR.br", "channel_name": "Warner Channel Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    },
    "TNTLA_EPG.xml": {
        "generator_name": "Guia de Programacion TNT MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/14",
        "type": "daily",
        "feeds": [
            {"feed_id": "TNTLA_MX", "channel_id": "TNT_MX.mx", "channel_name": "TNT México", "lang": "es", "tz": timezone(timedelta(hours=-6)), "tz_str": "-0600"},
            {"feed_id": "TNTLA_CO", "channel_id": "TNT_CO.co", "channel_name": "TNT Colombia", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "TNTLA_PAN", "channel_id": "TNT_PAN.co", "channel_name": "TNT Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "TNTLA_BR", "channel_id": "TNT_BR.br", "channel_name": "TNT Brasil HD", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"},
            {"feed_id": "TNTLA_AR", "channel_id": "TNT_AR.ar", "channel_name": "TNT Argentina", "lang": "es", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"},
            {"feed_id": "TNTLA_CL", "channel_id": "TNT_CL.cl", "channel_name": "TNT Chile", "lang": "es", "tz": timezone(timedelta(hours=-4)), "tz_str": "-0400"}
        ]
    },
    "TNT_SPORTS.xml": {
        "generator_name": "Guia de Programacion TNT Sports MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/24",
        "type": "daily",
        "feeds": [
            {"feed_id": "TNTSPO_AR", "channel_id": "TNTSPO_AR.ar", "channel_name": "TNT Sports Argentina", "lang": "es", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"},
            {"feed_id": "CDFH_CL", "channel_id": "CDFH_CL.cl", "channel_name": "TNT Sports HD Chile", "lang": "es", "tz": timezone(timedelta(hours=0)), "tz_str": "+00:00"},
            {"feed_id": "CDFB_CL", "channel_id": "CDFB_CL.cl", "channel_name": "TNT Sports 3 Chile", "lang": "es", "tz": timezone(timedelta(hours=0)), "tz_str": "+00:00"},
            {"feed_id": "CDFP_CL", "channel_id": "CDFP_CL.cl", "channel_name": "TNT Sports 2 Chile", "lang": "es", "tz": timezone(timedelta(hours=0)), "tz_str": "+00:00"}
        ]
    },
    "TOONCAST_EPG.xml": {
        "generator_name": "Guia de Programacion Tooncast MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/15",
        "type": "daily",
        "feeds": [
            {"feed_id": "TOONLA_PAN", "channel_id": "TOONLA_PAN.co", "channel_name": "Tooncast Panregional", "lang": "es", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"},
            {"feed_id": "TOONLA_BR", "channel_id": "TOONLA_BR.br", "channel_name": "Tooncast Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    }
}

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()
    payload = {"grant_type": "password", "scope": "any", "username": email, "password": password}
    res = http_session.post(AUTH_URL, data=payload, timeout=30)
    res.raise_for_status()
    print("[OK] Sesión iniciada y token obtenido exitosamente.")
    return res.json().get("access_token")

def get_target_months():
    now = datetime.now()
    year_curr, month_curr = now.year, now.month
    if month_curr == 12:
        year_next, month_next = year_curr + 1, 1
    else:
        year_next, month_next = year_curr, month_curr + 1
    return [(year_curr, month_curr), (year_next, month_next)]

def standardize_date_str(date_val):
    if not date_val or pd.isna(date_val):
        return ""
    d_str = str(date_val).strip().split()[0]
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})|(\d{1,2})[-/](\d{1,2})[-/](\d{4})", d_str)
    if match:
        groups = match.groups()
        if groups[0]:
            y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
        else:
            d, m, y = int(groups[3]), int(groups[4]), int(groups[5])
        return f"{y:04d}-{m:02d}-{d:02d}"
    return d_str

def download_and_load_monthly_metadata(token, network="CNLA", lang="SPA", feed_type="PAN"):
    months = get_target_months()
    combined_dict = {}
    url = "https://epg.tapkit.warnermedia.com/api/epg/tapkitFrontEnd/networksepg/downloadfiles"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://epg.tapkit.warnermedia.com",
        "Referer": "https://epg.tapkit.warnermedia.com/epg/networks/2"
    }

    for year, month in months:
        month_str = f"{month:02d}"
        files_to_check = [
            f"{network}_{year}_{month_str}_grids_{lang}_{feed_type}.xls",
            f"{network}_{year}_{month_str}_grids_{lang}_TVEGO.xlsx"
        ]

        for filename in files_to_check:
            path = f"network-files/{network}/{year}/{month_str}/grids/{lang}/{filename}"
            payload = [{"name": filename, "path": path}]
            try:
                res = http_session.post(url, json=payload, headers=headers, timeout=20)
                if res.status_code != 200:
                    continue

                content_bytes = io.BytesIO(res.content)
                df_grid = None
                if zipfile.is_zipfile(content_bytes):
                    with zipfile.ZipFile(content_bytes) as z:
                        for z_name in z.namelist():
                            if z_name.endswith((".xlsx", ".xls")):
                                with z.open(z_name) as f:
                                    try: df_grid = pd.read_excel(f)
                                    except: df_grid = pd.read_html(f)[0]
                else:
                    try: df_grid = pd.read_excel(content_bytes)
                    except: df_grid = pd.read_html(content_bytes)[0]

                if df_grid is not None:
                    if not any("Program Name" in str(col) or "Schedule Date" in str(col) for col in df_grid.columns):
                        if len(df_grid) > 0 and any("Program Name" in str(val) for val in df_grid.iloc[0].values):
                            df_grid.columns = df_grid.iloc[0]
                            df_grid = df_grid[1:].reset_index(drop=True)

                    for _, row in df_grid.iterrows():
                        date_norm = standardize_date_str(row.get("Schedule Date") or row.get("Date"))
                        start_time = str(row.get("Program Start Time") or "").strip()[:5]
                        orig_ep = str(row.get("Original Episode Title") or row.get("Episode Title(INGL)") or "").strip().upper()
                        es_title = str(row.get("Episode Title(ESPA)") or row.get("Episode Title (ESPA)") or row.get("Episode Title(PORT)") or "").strip()
                        en_title = str(row.get("Original Episode Title") or row.get("Episode Title(INGL)") or "").strip()
                        es_desc = str(row.get("Episode Sinopsis Prensa(ESPA)") or row.get("Episode Sinopsis Prensa(PORT)") or row.get("Episode Synopsis VOD (ESPA)") or "").strip()
                        year_val = str(row.get("Year") or row.get("Año") or "").strip()

                        meta_data = {
                            "title_es": es_title if es_title and es_title.lower() != "nan" else "",
                            "title_en": en_title if en_title and en_title.lower() != "nan" else "",
                            "desc": es_desc if es_desc and es_desc.lower() != "nan" else "",
                            "year": year_val if year_val and year_val.lower() != "nan" and year_val.isdigit() else ""
                        }

                        if date_norm and start_time and orig_ep and orig_ep != "NAN":
                            combined_dict[f"{date_norm}|{start_time}|{orig_ep}"] = meta_data
                        if orig_ep and orig_ep != "NAN" and orig_ep not in combined_dict:
                            combined_dict[orig_ep] = meta_data
            except Exception:
                pass
    return combined_dict

def download_feed_xls(token, feed_cfg, referer_url):
    feed_id = feed_cfg["feed_id"]
    file_id = feed_cfg.get("file_id")
    xls_path = f"{feed_id}_latest.xls"

    headers = {
        "Authorization": f"Bearer {token}",
        "Referer": referer_url,
        "Accept-Language": "es"
    }

    if file_id:
        current_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        files = {
            'user-token': (None, token),
            'file-id': (None, str(file_id)),
            'downloaded-date': (None, current_date_str)
        }
        res = http_session.post(DOWNLOAD_FILE_URL, headers=headers, files=files, timeout=30)
    else:
        url = BASE_DAILY_URL.format(feed_id=feed_id)
        res = http_session.get(url, headers=headers, timeout=30)

    res.raise_for_status()
    with open(xls_path, "wb") as f:
        f.write(res.content)
    return xls_path

def sanitize_and_parse_xml(file_path, generator_name):
    if not os.path.exists(file_path): return ET.Element("tv", {"generator-info-name": generator_name})
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f: content = f.read()
        cleaned_lines = [l for l in content.splitlines() if l.strip() not in ["JUEVES", "VIERNES", "SÁBADO", "SABADO", "DOMINGO", "LUNES", "MARTES", "MIÉRCOLES", "MIERCOLES"]]
        return ET.fromstring("\n".join(cleaned_lines))
    except Exception:
        return ET.Element("tv", {"generator-info-name": generator_name})

def parse_xmltv_date(date_str, tz_info):
    if not date_str: return None
    clean = re.sub(r"[^\d\s\+\-]", "", str(date_str).strip())
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", clean)
    if not m: return None
    y, mo, d, h, mi, s = map(int, m.groups())
    return datetime(y, mo, d, min(h, 23), min(mi, 59), min(s, 59), tzinfo=tz_info)

def format_xmltv_date(dt, tz_str):
    return dt.strftime(f"%Y%m%d%H%M%S {tz_str}")

def load_excel_schedule(file_path):
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        if any("Program Name" in str(col) or "Schedule Date" in str(col) or "SCHEDULE_DATE" in str(col) for col in df.columns): return df
        return pd.read_excel(file_path, header=1, sheet_name=0)
    except Exception:
        return pd.read_html(file_path, header=1)[0]

def find_column(cols_dict, possible_names):
    for name in possible_names:
        if name in cols_dict: return cols_dict[name]
    for col_key, col_val in cols_dict.items():
        for name in possible_names:
            if name.lower() in col_key.lower(): return col_val
    return None

def fetch_tmdb_synopsis(title):
    if not title or (not TMDB_TOKEN and not TMDB_API_KEY): return ""
    headers = {"accept": "application/json"}
    if TMDB_TOKEN: headers["Authorization"] = f"Bearer {TMDB_TOKEN}"
    elif TMDB_API_KEY: headers["Authorization"] = f"Bearer {TMDB_API_KEY}"

    clean = re.sub(r'[:\-].*', '', title).strip()
    for q in [clean, title]:
        if not q: continue
        try:
            res = http_session.get("https://api.themoviedb.org/3/search/tv", headers=headers, params={"query": q, "language": "es-ES"}, timeout=4)
            if res.status_code == 200 and res.json().get("results"):
                ov = res.json()["results"][0].get("overview")
                if ov: return ov
            res = http_session.get("https://api.themoviedb.org/3/search/movie", headers=headers, params={"query": q, "language": "es-ES"}, timeout=4)
            if res.status_code == 200 and res.json().get("results"):
                ov = res.json()["results"][0].get("overview")
                if ov: return ov
        except Exception: pass
    return ""

def process_daily_feed(root, feed_cfg, xls_path, monthly_meta=None, token=None):
    channel_id = feed_cfg["channel_id"]
    channel_name = feed_cfg["channel_name"]
    lang = feed_cfg["lang"]
    tz = feed_cfg["tz"]
    tz_str = feed_cfg["tz_str"]

    if not any(ch.attrib.get("id") == channel_id for ch in root.findall("channel")):
        ch_node = ET.SubElement(root, "channel", {"id": channel_id})
        ET.SubElement(ch_node, "display-name").text = channel_name

    df = load_excel_schedule(xls_path)
    cols = {str(c).strip(): c for c in df.columns}
    
    col_date = find_column(cols, ["Schedule Date", "Date", "Fecha"]) or df.columns[0]
    col_time = find_column(cols, ["Program Start Time", "Title Start Time", "Start Time", "Hora"]) or df.columns[1]
    col_title = find_column(cols, ["Program Name", "Title Name", "Title", "Programa"]) or df.columns[2]
    col_press_title = find_column(cols, ["Press Title (ESPA)", "Press Title (PORT)", "Original Title"])
    col_ep_name = find_column(cols, ["Episode Title(ESPA)", "Episode Title (ESPA)", "Episode Title(PORT)", "Episode Name English", "Episode Name", "Sub-title"])
    col_ep_name_en = find_column(cols, ["Episode Name English", "Original Episode Title", "Episode Title(INGL)"])
    col_ep_num = find_column(cols, ["Episode", "Episode Number", "Episodio"])
    col_season = find_column(cols, ["Season", "Season Number", "Temporada"])
    col_year = find_column(cols, ["Year", "Año"])
    col_desc = find_column(cols, ["Program Sinopsis Prensa(ESPA)", "Program Sinopsis Prensa(PORT)", "Title Synopsis", "Synopsis", "Description"])
    col_ep_desc = find_column(cols, ["Episode Sinopsis Prensa(ESPA)", "Episode Sinopsis Prensa(PORT)", "Episode Synopsis"])
    col_is_new = find_column(cols, ["Is Premiere", "New Episode", "Premiere", "Estreno", "Title Classification", "Y/N"])
    col_genre = find_column(cols, ["Genre", "Género"])
    col_length = find_column(cols, ["Length", "Duración"])

    first_date_raw = str(df.iloc[0].get(col_date, "")).strip()
    match_init = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", first_date_raw)
    if not match_init: return

    d0, m0, y0 = map(int, match_init.groups())
    cycle_start = datetime(y0, m0, d0, 6, 0, 0, tzinfo=tz)
    cycle_end = cycle_start + timedelta(days=1)

    raw_events = []
    for _, row in df.iterrows():
        date_raw = str(row.get(col_date, "")).strip()
        time_raw = str(row.get(col_time, "")).strip()
        date_match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", date_raw)
        time_match = re.search(r"(\d{1,2}):(\d{2})", time_raw)
        if not time_match and date_match: time_match = re.search(r"(\d{1,2}):(\d{2})", date_raw)
        if not date_match or not time_match: continue

        d, m, y = map(int, date_match.groups())
        hh, mm = map(int, time_match.groups())
        event_dt = datetime(y, m, d, hh, mm, 0, tzinfo=tz)
        if (d == d0 and m == m0 and y == y0) and hh < 6: event_dt += timedelta(days=1)
        if event_dt >= cycle_end: break

        prog_name_val = str(row.get(col_title, "")).strip() if pd.notna(row.get(col_title)) else ""
        if prog_name_val.strip().upper() == "LOS COLORADO": prog_name_val = "El Chapulín Y Los Colorado"

        press_title_val = str(row.get(col_press_title, "")).strip() if col_press_title and pd.notna(row.get(col_press_title)) else ""
        ep_name_val = str(row.get(col_ep_name, "")).strip() if col_ep_name and pd.notna(row.get(col_ep_name)) else ""
        ep_name_en_val = str(row.get(col_ep_name_en, "")).strip() if col_ep_name_en and pd.notna(row.get(col_ep_name_en)) else ""
        year_val = str(row.get(col_year, "")).strip() if col_year and pd.notna(row.get(col_year)) else ""
        genre_val = str(row.get(col_genre, "")).strip() if col_genre and pd.notna(row.get(col_genre)) else ""
        length_val = str(row.get(col_length, "")).strip() if col_length and pd.notna(row.get(col_length)) else ""

        # Cálculo dinámico del stop usando la columna Length si está disponible
        stop_dt = None
        if length_val:
            try:
                parts = length_val.split(':')
                if len(parts) == 3:
                    h, m, s = map(int, [float(p) for p in parts])
                    stop_dt = event_dt + timedelta(hours=h, minutes=m, seconds=s)
            except:
                pass

        desc_es, desc_en = "", ""
        if prog_name_val.lower() == "cine cartoon":
            movie_title = press_title_val or ep_name_val
            title_val = f"{movie_title} (Cine Cartoon)" if movie_title and movie_title.lower() != "nan" else "Cine Cartoon"
            ep_name_val, ep_name_en_val = "", ""
            desc_es = "Cartoon Network trae los clásicos del cine a la pantalla de TV. Ahora podrás disfrutar de estas historias inolvidables en la comodidad de tu hogar."
            desc_en = "Cartoon Network brings classic cinematic tales to the TV screen."
        else:
            title_val = prog_name_val

        season_val = str(row.get(col_season, "")).strip() if col_season and pd.notna(row.get(col_season)) else ""
        ep_num_val = str(row.get(col_ep_num, "")).strip() if col_ep_num and pd.notna(row.get(col_ep_num)) else ""
        
        xmltv_season_ep = ""
        try:
            s_num = int(float(season_val)) - 1 if season_val.replace('.', '', 1).isdigit() else ""
            e_num = int(float(ep_num_val)) - 1 if ep_num_val.replace('.', '', 1).isdigit() else ""
            if s_num != "" and e_num != "": xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "": xmltv_season_ep = f".{e_num}."
        except: pass

        if not desc_es:
            if col_ep_desc and pd.notna(row.get(col_ep_desc)) and str(row.get(col_ep_desc)).strip():
                desc_es = str(row.get(col_ep_desc)).strip()
            elif col_desc and pd.notna(row.get(col_desc)) and str(row.get(col_desc)).strip():
                desc_es = str(row.get(col_desc)).strip()

        sub_es = ep_name_val if ep_name_val and ep_name_val.lower() != "nan" else ""
        sub_en = ep_name_en_val if ep_name_en_val and ep_name_en_val.lower() != "nan" else ""

        if monthly_meta:
            norm_date = standardize_date_str(date_raw)
            matched_info = monthly_meta.get(f"{norm_date}|{time_raw[:5]}|{sub_en.upper()}") or monthly_meta.get(sub_en.upper())
            if matched_info:
                if matched_info["title_es"]: sub_es = matched_info["title_es"]
                if matched_info["title_en"]: sub_en = matched_info["title_en"]
                if not desc_es and matched_info["desc"]: desc_es = matched_info["desc"]
                if matched_info["year"]: year_val = matched_info["year"]

        if not desc_es and title_val and "Cine Cartoon" not in title_val:
            desc_es = fetch_tmdb_synopsis(title_val)

        icon_url = fetch_tmdb_still(title_val, season_val, ep_num_val, ep_title_en=sub_en, lang=lang) if title_val and "Cine Cartoon" not in title_val else ""

        if col_is_new and pd.notna(row.get(col_is_new)) and str(row.get(col_is_new)).strip().upper() == "Y":
            if sub_es and sub_es.lower() != "nan": sub_es = f"{sub_es} (NUEVO EPISODIO)"
            elif title_val: title_val = f"{title_val} (NUEVO EPISODIO)"

        raw_events.append({
            "start": event_dt,
            "stop": stop_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title_es": sub_es if sub_es.lower() != "nan" and sub_es.lower() != title_val.lower() else "",
            "sub_title_en": sub_en if sub_en.lower() != "nan" and sub_en.lower() != sub_es.lower() else "",
            "episode_num": xmltv_season_ep,
            "desc_es": desc_es if desc_es.lower() != "nan" else "",
            "desc_en": desc_en if desc_en.lower() != "nan" else "",
            "year": year_val.split('.')[0] if year_val and year_val.replace('.', '', 1).isdigit() else "",
            "genre": genre_val if genre_val.lower() != "nan" else "",
            "icon": icon_url,
            "type": "show"
        })

    if token and "CNLA" in feed_cfg.get("feed_id", ""):
        date_str_fmt = f"{y0}{m0:02d}{d0:02d}"
        local_breaks = download_and_parse_local_breaks(token, date_str_fmt, tz)
        for lb in local_breaks:
            raw_events.append({
                "start": lb["start"],
                "stop": lb["stop"],
                "title": lb["title"],
                "desc": lb["desc"],
                "category": lb["category"],
                "type": "break"
            })

    raw_events = sorted(raw_events, key=lambda x: x["start"])
    new_programmes = []
    total_events = len(raw_events)

    for i in range(total_events):
        ev = raw_events[i]
        start_dt = ev["start"]
        stop_dt = ev.get("stop") or (raw_events[i + 1]["start"] if i + 1 < total_events else cycle_end)

        # Formatos XMLTV y UTC avanzados
        start_str = format_xmltv_date(start_dt, tz_str)
        stop_str = format_xmltv_date(stop_dt, tz_str)
        start_utc_str = format_xmltv_date(start_dt.astimezone(timezone.utc), "+0000")
        stop_utc_str = format_xmltv_date(stop_dt.astimezone(timezone.utc), "+0000")

        prog = ET.Element("programme", {
            "start": start_str,
            "stop": stop_str,
            "air_time_start": start_str,
            "air_time_end": stop_str,
            "start_utc": start_utc_str,
            "stop_utc": stop_utc_str,
            "air_time_start_utc": start_utc_str,
            "air_time_end_utc": stop_utc_str,
            "is_live": "false",
            "channel": channel_id
        })

        if ev.get("type") == "break":
            ET.SubElement(prog, "title", {"lang": lang}).text = ev["title"]
            ET.SubElement(prog, "desc", {"lang": lang}).text = ev["desc"]
            ET.SubElement(prog, "category", {"lang": lang}).text = ev["category"]
        else:
            if ev["title"]: ET.SubElement(prog, "title", {"lang": lang}).text = ev["title"]
            if ev["sub_title_es"]: ET.SubElement(prog, "sub-title", {"lang": lang}).text = ev["sub_title_es"]
            if ev["sub_title_en"]: ET.SubElement(prog, "sub-title", {"lang": "en"}).text = ev["sub_title_en"]
            if ev["desc_es"]: ET.SubElement(prog, "desc", {"lang": lang}).text = ev["desc_es"]
            if ev["desc_en"]: ET.SubElement(prog, "desc", {"lang": "en"}).text = ev["desc_en"]
            if ev["year"]: ET.SubElement(prog, "date").text = ev["year"]
            if ev["genre"]:
                for g in ev["genre"].split(','):
                    ET.SubElement(prog, "category", {"lang": lang}).text = g.strip()
            if ev["episode_num"]: ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"}).text = ev["episode_num"]
            if ev["icon"]: ET.SubElement(prog, "icon", {"src": ev["icon"]})

        new_programmes.append(prog)

    existing_progs_map = {p.attrib.get("start"): p for p in root.findall("programme") if p.attrib.get("channel") == channel_id}
    for np in new_programmes:
        start_key = np.attrib.get("start")
        if start_key in existing_progs_map: root.remove(existing_progs_map[start_key])
        root.append(np)

    print(f"[{channel_id}] Eventos y pausas procesadas hoy: {len(new_programmes)}")

def main():
    token = login_and_get_token()
    cn_monthly_meta = download_and_load_monthly_metadata(token, network="CNLA", lang="SPA", feed_type="PAN")

    for xml_filename, net_config in NETWORKS_CONFIG.items():
        print(f"\n==========================================")
        print(f"Procesando: {xml_filename}")
        print(f"==========================================")
        
        root = sanitize_and_parse_xml(xml_filename, net_config["generator_name"])
        active_channel_ids = {cfg["channel_id"] for cfg in net_config["feeds"]}
        for ch in list(root.findall("channel")):
            if ch.attrib.get("id") not in active_channel_ids: root.remove(ch)

        net_type = net_config.get("type", "daily")
        if net_type == "daily":
            for feed_cfg in net_config["feeds"]:
                try:
                    xls_path = download_feed_xls(token, feed_cfg, net_config["referer"])
                    use_meta = cn_monthly_meta if "CNLA" in xml_filename else None
                    process_daily_feed(root, feed_cfg, xls_path, monthly_meta=use_meta, token=token)
                except Exception as e:
                    print(f"[ERROR] Feed {feed_cfg['feed_id']}: {e}")

        now_utc = datetime.now(timezone.utc)
        cutoff_past = now_utc - timedelta(days=RETENTION_DAYS_PAST)
        cutoff_future = now_utc + timedelta(days=RETENTION_DAYS_FUTURE)

        for p in list(root.findall("programme")):
            ch_id = p.attrib.get("channel")
            if ch_id not in active_channel_ids:
                root.remove(p)
                continue
            cfg = next((c for c in net_config["feeds"] if c["channel_id"] == ch_id), net_config["feeds"][0])
            stop_dt = parse_xmltv_date(p.attrib.get("stop", ""), cfg["tz"])
            start_dt = parse_xmltv_date(p.attrib.get("start", ""), cfg["tz"])
            if stop_dt and stop_dt.astimezone(timezone.utc) < cutoff_past: root.remove(p)
            elif start_dt and start_dt.astimezone(timezone.utc) > cutoff_future: root.remove(p)

        sorted_progs = sorted(root.findall("programme"), key=lambda x: x.attrib.get("start", ""))
        for p in list(root.findall("programme")): root.remove(p)
        for p in sorted_progs: root.append(p)

        ET.indent(root, space="  ", level=0)
        ET.ElementTree(root).write(xml_filename, encoding="utf-8", xml_declaration=True)
        print(f"[OK] {xml_filename} guardado. Total programas: {len(sorted_progs)}")

if __name__ == "__main__":
    main()
