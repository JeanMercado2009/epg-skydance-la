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

def fetch_tmdb_episode_details(series_title, season_str, ep_str, ep_title_en="", lang="es"):
    if not series_title or (not TMDB_TOKEN and not TMDB_API_KEY):
        return {}

    cache_key = f"{series_title}|{season_str}|{ep_str}|{ep_title_en}|ep_details"
    if cache_key in tmdb_cache:
        return tmdb_cache[cache_key]

    headers = {"accept": "application/json"}
    if TMDB_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_TOKEN}"
    elif TMDB_API_KEY:
        headers["Authorization"] = f"Bearer {TMDB_API_KEY}"

    tmdb_lang = "es-ES" 
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

            e_num = None
            if ep_str and str(ep_str).replace('.', '', 1).isdigit():
                e_num = int(float(ep_str))

            if s_num is not None and e_num is not None:
                ep_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_num}/episode/{e_num}"
                ep_res = http_session.get(ep_url, headers=headers, params={"language": tmdb_lang}, timeout=4)
                if ep_res.status_code == 200:
                    data = ep_res.json()
                    t_name = data.get("name", "")
                    t_overview = data.get("overview", "")
                    if t_name or t_overview:
                        result = {"title": t_name, "overview": t_overview}
                        tmdb_cache[cache_key] = result
                        return result

            norm_target = normalize_title(ep_title_en) if ep_title_en else ""
            if norm_target:
                seasons_to_check = [s_num] if s_num is not None else []
                for s in range(1, number_of_seasons + 1):
                    if s not in seasons_to_check:
                        seasons_to_check.append(s)
                seasons_to_check.append(0)

                for s_check in seasons_to_check:
                    season_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_check}"
                    season_res = http_session.get(season_url, headers=headers, params={"language": tmdb_lang}, timeout=4)
                    if season_res.status_code == 200:
                        for ep in season_res.json().get("episodes", []):
                            if normalize_title(ep.get("name", "")) == norm_target:
                                result = {"title": ep.get("name", ""), "overview": ep.get("overview", "")}
                                tmdb_cache[cache_key] = result
                                return result
    except Exception:
        pass

    tmdb_cache[cache_key] = {}
    return {}

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
                                    "title": "Pausa Comercial", "desc": "Espacio publicitario.",
                                    "category": "Comercial", "type": "break"
                                })
                            in_time = None
        except Exception:
            pass
    return breaks_events

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
    "WARNERLA_EPG.xml": {
        "generator_name": "Guia de Programacion Warner Channel MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/api/networks/warner",
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
        "referer": "https://epg.tapkit.warnermedia.com/api/networks/24",
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
        "referer": "https://epg.tapkit.warnermedia.com/api/networks/15",
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
                    try:
                        df_grid = pd.read_excel(content_bytes)
                    except Exception:
                        try:
                            df_grid = pd.read_html(content_bytes)[0]
                        except:
                            continue

                if df_grid is not None and not df_grid.empty:
                    for _, row in df_grid.iterrows():
                        d_raw = standardize_date_str(row.get("SCHEDULE_DATE") or row.get("Date"))
                        s_time = str(row.get("START_TIME") or row.get("Start Time") or "").strip()
                        if not d_raw or not s_time:
                            continue
                        
                        t_match = re.search(r"(\d{1,2}):(\d{2})", s_time)
                        if not t_match:
                            continue
                        hh, mm = t_match.groups()
                        time_key = f"{d_raw} {int(hh):02d}:{int(mm):02d}"

                        series = str(row.get("SERIES_NAME") or row.get("Series Name") or "").strip()
                        title = str(row.get("TITLE_NAME") or row.get("Title Name") or "").strip()
                        desc = str(row.get("PROGRAMME_DESCRIPTION") or row.get("Description") or "").strip()
                        l_series = str(row.get("LOCAL_SERIES_NAME") or "").strip()
                        l_prog = str(row.get("LOCAL_PROGRAM_NAME") or "").strip()
                        l_desc = str(row.get("LOCAL_PROGRAM_DESCRIPTION") or "").strip()
                        season = str(row.get("SEASON_NUMBER") or "").strip()
                        episode = str(row.get("EPISODE_NUMBER") or "").strip()
                        year_prod = str(row.get("YEAR_OF_PRODUCTION") or "").strip()

                        combined_dict[time_key] = {
                            "series": series if series.lower() != "nan" else "",
                            "title": title if title.lower() != "nan" else "",
                            "desc": desc if desc.lower() != "nan" else "",
                            "local_series": l_series if l_series.lower() != "nan" else "",
                            "local_prog": l_prog if l_prog.lower() != "nan" else "",
                            "local_desc": l_desc if l_desc.lower() != "nan" else "",
                            "season": season if season.lower() != "nan" else "",
                            "episode": episode if episode.lower() != "nan" else "",
                            "year": year_prod if year_prod.lower() != "nan" else ""
                        }
            except Exception:
                pass
    return combined_dict

def sanitize_and_parse_xml(file_path, generator_name):
    if not os.path.exists(file_path):
        return ET.Element("tv", {"generator-info-name": generator_name})
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return ET.fromstring(content)
    except Exception:
        return ET.Element("tv", {"generator-info-name": generator_name})

def format_xmltv_date(dt, tz_str):
    return dt.strftime(f"%Y%m%d%H%M%S {tz_str}")

def main():
    try:
        token = login_and_get_token()
    except Exception as e:
        print(f"[ERROR] No se pudo autenticar en Tapkit: {e}")
        return

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=RETENTION_DAYS_PAST)
    end_date = today + timedelta(days=RETENTION_DAYS_FUTURE)

    for xml_filename, net_config in NETWORKS_CONFIG.items():
        print(f"\n==========================================")
        print(f"Procesando red: {xml_filename}")
        print(f"==========================================")

        root = sanitize_and_parse_xml(xml_filename, net_config["generator_name"])
        active_channel_ids = {cfg["channel_id"] for cfg in net_config["feeds"]}

        # Limpieza segura de canales obsoletos
        for ch in list(root.findall("channel")):
            if ch.attrib.get("id") not in active_channel_ids:
                if ch in root:
                    root.remove(ch)

        for feed_cfg in net_config["feeds"]:
            feed_id = feed_cfg["feed_id"]
            channel_id = feed_cfg["channel_id"]
            channel_name = feed_cfg["channel_name"]
            lang = feed_cfg["lang"]
            tz = feed_cfg["tz"]
            tz_str = feed_cfg["tz_str"]

            if not any(ch.attrib.get("id") == channel_id for ch in root.findall("channel")):
                ch_node = ET.SubElement(root, "channel", {"id": channel_id})
                ET.SubElement(ch_node, "display-name").text = channel_name

            print(f"[{feed_id}] Descargando metadatos mensuales...")
            net_prefix = "CNLA" if "CN" in feed_id else ("CTOOLA" if "CTOO" in feed_id else ("WARNERLA" if "WARNER" in feed_id else ("TNTLA" if "TNT" in feed_id else "TOONLA")))
            feed_type = "BR" if "BR" in feed_id else ("TVEGO" if "TVEGO" in feed_id else "PAN")
            lang_code = "POR" if lang == "pt" else "SPA"
            
            monthly_meta = download_and_load_monthly_metadata(token, network=net_prefix, lang=lang_code, feed_type=feed_type)

            all_events = []
            curr_d = start_date
            while curr_d <= end_date:
                d_str = curr_d.strftime("%Y-%m-%d")
                url = BASE_DAILY_URL.format(feed_id=feed_id) + f"&date={d_str}"
                headers = {"Authorization": f"Bearer {token}", "Referer": net_config["referer"]}
                try:
                    res = http_session.get(url, headers=headers, timeout=15)
                    if res.status_code == 200 and len(res.content) > 0:
                        content_bytes = io.BytesIO(res.content)
                        df_daily = None
                        if zipfile.is_zipfile(content_bytes):
                            with zipfile.ZipFile(content_bytes) as z:
                                for z_name in z.namelist():
                                    if z_name.endswith((".xlsx", ".xls", ".csv")):
                                        with z.open(z_name) as f:
                                            try: df_daily = pd.read_excel(f)
                                            except: df_daily = pd.read_html(f)[0]
                        else:
                            try:
                                df_daily = pd.read_excel(content_bytes)
                            except:
                                try:
                                    df_daily = pd.read_html(content_bytes)[0]
                                except:
                                    pass

                        if df_daily is not None and not df_daily.empty:
                            for _, row in df_daily.iterrows():
                                time_raw = str(row.get("START_TIME") or row.get("Start Time") or "").strip()
                                t_match = re.search(r"(\d{1,2}):(\d{2})", time_raw)
                                if not t_match:
                                    continue
                                hh, mm = t_match.groups()
                                event_dt = datetime(curr_d.year, curr_d.month, curr_d.day, int(hh), int(mm), 0, tzinfo=tz)

                                end_time_raw = str(row.get("END_TIME") or row.get("End Time") or "").strip()
                                stop_dt = None
                                end_match = re.search(r"(\d{1,2}):(\d{2})", end_time_raw)
                                if end_match:
                                    ehh, emm = end_match.groups()
                                    stop_dt = datetime(curr_d.year, curr_d.month, curr_d.day, int(ehh), int(emm), 0, tzinfo=tz)
                                    if stop_dt <= event_dt:
                                        stop_dt += timedelta(days=1)

                                time_key = f"{d_str} {int(hh):02d}:{int(mm):02d}"
                                meta = monthly_meta.get(time_key, {})

                                series = meta.get("series") or str(row.get("SERIES_NAME") or "").strip()
                                title = meta.get("title") or str(row.get("TITLE_NAME") or "").strip()
                                desc = meta.get("desc") or str(row.get("PROGRAMME_DESCRIPTION") or "").strip()
                                l_series = meta.get("local_series") or str(row.get("LOCAL_SERIES_NAME") or "").strip()
                                l_prog = meta.get("local_prog") or str(row.get("LOCAL_PROGRAM_NAME") or "").strip()
                                l_desc = meta.get("local_desc") or str(row.get("LOCAL_PROGRAM_DESCRIPTION") or "").strip()
                                season = meta.get("season") or str(row.get("SEASON_NUMBER") or "").strip()
                                episode = meta.get("episode") or str(row.get("EPISODE_NUMBER") or "").strip()
                                year_prod = meta.get("year") or str(row.get("YEAR_OF_PRODUCTION") or "").strip()

                                title_val = l_series if l_series and l_series.lower() != "nan" else series
                                sub_es = l_prog if l_prog and l_prog.lower() != "nan" else ""
                                sub_en = title if title and title.lower() != "nan" else ""
                                final_desc = l_desc if l_desc and l_desc.lower() != "nan" else desc

                                tmdb_det = fetch_tmdb_episode_details(title_val, season, episode, ep_title_en=sub_en, lang=lang)
                                if tmdb_det.get("title") and not sub_es:
                                    sub_es = tmdb_det["title"]
                                if tmdb_det.get("overview") and not final_desc:
                                    final_desc = tmdb_det["overview"]

                                xmltv_season_ep = ""
                                try:
                                    s_num = int(float(season)) - 1 if season.replace('.', '', 1).isdigit() else ""
                                    e_num = int(float(episode)) - 1 if episode.replace('.', '', 1).isdigit() else ""
                                    if s_num != "" and e_num != "": xmltv_season_ep = f"{s_num}.{e_num}."
                                    elif e_num != "": xmltv_season_ep = f".{e_num}."
                                except: pass

                                icon_url = fetch_tmdb_still(title_val, season, episode, ep_title_en=sub_en, lang=lang) if title_val else ""

                                all_events.append({
                                    "start": event_dt,
                                    "stop": stop_dt,
                                    "title": title_val if title_val.lower() != "nan" else "",
                                    "sub_title_es": sub_es if sub_es.lower() != "nan" and sub_es.lower() != title_val.lower() else "",
                                    "sub_title_en": sub_en if sub_en.lower() != "nan" and sub_en.lower() != sub_es.lower() else "",
                                    "episode_num": xmltv_season_ep,
                                    "desc": final_desc if final_desc.lower() != "nan" else "",
                                    "year": year_prod.split('.')[0] if year_prod and year_prod.replace('.', '', 1).isdigit() else "",
                                    "icon": icon_url
                                ”})
                except Exception:
                    pass
                curr_d += timedelta(days=1)

            # Insertar eventos de forma limpia y segura evitando duplicados o errores de lista
            all_events = sorted(all_events, key=lambda x: x["start"])
            new_programmes = []
            total_evs = len(all_events)

            for i in range(total_evs):
                ev = all_events[i]
                start_dt = ev["start"]
                stop_dt = ev.get("stop") or (all_events[i + 1]["start"] if i + 1 < total_evs else start_dt + timedelta(minutes=30))
                if stop_dt <= start_dt:
                    stop_dt = start_dt + timedelta(minutes=1)

                start_str = format_xmltv_date(start_dt, tz_str)
                stop_str = format_xmltv_date(stop_dt, tz_str)
                start_utc_str = format_xmltv_date(start_dt.astimezone(timezone.utc), "+0000")
                stop_utc_str = format_xmltv_date(stop_dt.astimezone(timezone.utc), "+0000")

                prog = ET.Element("programme", {
                    "start": start_str,
                    "stop": stop_str,
                    "channel": channel_id
                })

                if ev["title"]: ET.SubElement(prog, "title", {"lang": lang}).text = ev["title"]
                if ev["sub_title_es"]: ET.SubElement(prog, "sub-title", {"lang": lang}).text = ev["sub_title_es"]
                if ev["sub_title_en"]: ET.SubElement(prog, "sub-title", {"lang": "en"}).text = ev["sub_title_en"]
                if ev["desc"]: ET.SubElement(prog, "desc", {"lang": lang}).text = ev["desc"]
                if ev["year"]: ET.SubElement(prog, "date").text = ev["year"]
                ET.SubElement(prog, "category", {"lang": lang}).text = "Series"
                if ev["episode_num"]: ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"}).text = ev["episode_num"]
                if ev["icon"]: ET.SubElement(prog, "icon", {"src": ev["icon"]})

                new_programmes.append(prog)

            existing_progs_map = {p.attrib.get("start"): p for p in root.findall("programme") if p.attrib.get("channel") == channel_id}
            for np in new_programmes:
                start_key = np.attrib.get("start")
                if start_key in existing_progs_map:
                    old_p = existing_progs_map[start_key]
                    if old_p in root:
                        root.remove(old_p)
                root.append(np)

            print(f"[{channel_id}] Eventos procesados: {len(new_programmes)}")

        # Ordenar programa global final y limpieza segura
        sorted_progs = sorted(root.findall("programme"), key=lambda x: x.attrib.get("start", ""))
        for p in list(root.findall("programme")):
            if p in root:
                root.remove(p)
        for p in sorted_progs:
            root.append(p)

        ET.indent(root, space="  ", level=0)
        ET.ElementTree(root).write(xml_filename, encoding="utf-8", xml_declaration=True)
        print(f"[OK] {xml_filename} guardado correctamente. Total programas: {len(sorted_progs)}")

if __name__ == "__main__":
    main()