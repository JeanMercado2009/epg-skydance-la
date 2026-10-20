import os
import re
import io
import zipfile
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd
import requests

# -------------------------------------------------------------
# CONFIGURACIÓN GENERAL Y CANALES
# -------------------------------------------------------------
RETENTION_DAYS_PAST = 5     # Días hacia atrás a conservar en la grilla
RETENTION_DAYS_FUTURE = 15   # Ventana activa de 15 días hacia adelante

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
BASE_DAILY_URL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId={feed_id}&format=xls"

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

NETWORKS_CONFIG = {
    "CNLA_EPG.xml": {
        "generator_name": "Guia de Programacion Cartoon Network MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/2",
        "feeds": [
            {
                "feed_id": "CNLA_PAN",
                "channel_id": "CNLA_PAN.co",
                "channel_name": "Cartoon Network Panregional",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500"
            },
            {
                "feed_id": "CNLA_BR",
                "channel_id": "CNLA_BR.br",
                "channel_name": "Cartoon Network Brasil",
                "lang": "pt",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300"
            }
        ]
    },
    "WARNERLA_EPG.xml": {
        "generator_name": "Guia de Programacion Warner Channel MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/warner",
        "feeds": [
            {
                "feed_id": "WARNERLA_CO",
                "channel_id": "WARNER_CO.co",
                "channel_name": "Warner Channel Colombia",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500"
            },
            {
                "feed_id": "WARNERLA_MX",
                "channel_id": "WARNER_MX.mx",
                "channel_name": "Warner Channel México",
                "lang": "es",
                "tz": timezone(timedelta(hours=-6)),
                "tz_str": "-0600"
            },
            {
                "feed_id": "WARNERLA_AR",
                "channel_id": "WARNER_AR.ar",
                "channel_name": "Warner Channel Argentina",
                "lang": "es",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300"
            },
            {
                "feed_id": "WARNERLA_CH",
                "channel_id": "WARNER_CL.cl",
                "channel_name": "Warner Channel Chile",
                "lang": "es",
                "tz": timezone(timedelta(hours=-4)),
                "tz_str": "-0400"
            },
            {
                "feed_id": "WARNERLA_VE",
                "channel_id": "WARNER_VE.ve",
                "channel_name": "Warner Channel Venezuela",
                "lang": "es",
                "tz": timezone(timedelta(hours=-4)),
                "tz_str": "-0400"
            },
            {
                "feed_id": "WARNERLA_AN",
                "channel_id": "WARNER_AN.co",
                "channel_name": "Warner Channel Andes",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500"
            },
            {
                "feed_id": "WARNERLA_BH",
                "channel_id": "WARNER_BR.br",
                "channel_name": "Warner Channel Brasil",
                "lang": "pt",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300"
            }
        ]
    },
    "TNTLA_EPG.xml": {
        "generator_name": "Guia de Programacion TNT MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/14",
        "feeds": [
            {
                "feed_id": "TNTLA_MX",
                "channel_id": "TNT_MX.mx",
                "channel_name": "TNT México",
                "lang": "es",
                "tz": timezone(timedelta(hours=-6)),
                "tz_str": "-0600"
            },
            {
                "feed_id": "TNTLA_CO",
                "channel_id": "TNT_CO.co",
                "channel_name": "TNT Colombia",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500"
            },
            {
                "feed_id": "TNTLA_PAN",
                "channel_id": "TNT_PAN.co",
                "channel_name": "TNT Panregional",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500"
            },
            {
                "feed_id": "TNTLA_BR",
                "channel_id": "TNT_BR.br",
                "channel_name": "TNT Brasil HD",
                "lang": "pt",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300"
            },
            {
                "feed_id": "TNTLA_AR",
                "channel_id": "TNT_AR.ar",
                "channel_name": "TNT Argentina",
                "lang": "es",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300"
            },
            {
                "feed_id": "TNTLA_CL",
                "channel_id": "TNT_CL.cl",
                "channel_name": "TNT Chile",
                "lang": "es",
                "tz": timezone(timedelta(hours=-4)),
                "tz_str": "-0400"
            }
        ]
    }
}

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es",
    "Origin": "https://epg.tapkit.warnermedia.com",
    "Referer": "https://epg.tapkit.warnermedia.com/login"
}

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()

    if not email or not password:
        raise Exception("Faltan TAPKIT_EMAIL o TAPKIT_PASSWORD en los Secrets de GitHub.")

    payload = {
        "grant_type": "password",
        "scope": "any",
        "username": email,
        "password": password
    }

    res = requests.post(AUTH_URL, data=payload, headers=COMMON_HEADERS, timeout=30)
    if res.status_code != 200:
        raise Exception(f"Error en login. Código HTTP: {res.status_code} | Respuesta: {res.text}")

    data = res.json()
    token = data.get("access_token")
    if not token:
        raise Exception(f"No se encontró 'access_token' en la respuesta: {data}")

    print("[OK] Sesión iniciada y token obtenido exitosamente.")
    return token

def get_target_months():
    now = datetime.now()
    year_curr, month_curr = now.year, now.month
    
    if month_curr == 12:
        year_next = year_curr + 1
        month_next = 1
    else:
        year_next = year_curr
        month_next = month_curr + 1

    return [(year_curr, month_curr), (year_next, month_next)]

def download_and_load_monthly_metadata(token, network="CNLA", lang="SPA", feed_type="PAN"):
    months = get_target_months()
    combined_dict = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://epg.tapkit.warnermedia.com",
        "Referer": "https://epg.tapkit.warnermedia.com/epg/networks/2"
    }

    url = "https://epg.tapkit.warnermedia.com/api/epg/tapkitFrontEnd/networksepg/downloadfiles"

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
                res = requests.post(url, json=payload, headers=headers, timeout=30)
                if res.status_code != 200:
                    continue

                content_bytes = io.BytesIO(res.content)
                df_grid = None

                if zipfile.is_zipfile(content_bytes):
                    with zipfile.ZipFile(content_bytes) as z:
                        for z_name in z.namelist():
                            if z_name.endswith((".xlsx", ".xls")):
                                with z.open(z_name) as f:
                                    try:
                                        df_grid = pd.read_excel(f)
                                    except:
                                        df_grid = pd.read_html(f)[0]
                else:
                    try:
                        df_grid = pd.read_excel(content_bytes)
                    except:
                        df_grid = pd.read_html(content_bytes)[0]

                if df_grid is not None:
                    if any("Program Name" in str(col) or "Schedule Date" in str(col) for col in df_grid.columns):
                        pass
                    elif len(df_grid) > 0 and any("Program Name" in str(val) for val in df_grid.iloc[0].values):
                        df_grid.columns = df_grid.iloc[0]
                        df_grid = df_grid[1:].reset_index(drop=True)

                    count = 0
                    for _, row in df_grid.iterrows():
                        orig_title = str(row.get("Original Title", row.get("Original Episode Title", ""))).strip().upper()
                        orig_ep = str(row.get("Original Episode Title", "")).strip().upper()
                        
                        es_title = str(row.get("Press Title (ESPA)", row.get("Episode Title (ESPA)", row.get("Episode Title(ESPA)", "")))).strip()
                        es_desc = str(row.get("Episode Sinopsis Prensa(ESPA)", row.get("Episode Synopsis VOD (ESPA)", row.get("Program Sinopsis Prensa(ESPA)", "")))).strip()
                        year_val = str(row.get("Year", row.get("Año", ""))).strip()

                        meta_data = {
                            "title": es_title if es_title and es_title.lower() != "nan" else "",
                            "desc": es_desc if es_desc and es_desc.lower() != "nan" else "",
                            "year": year_val if year_val and year_val.lower() != "nan" and year_val.isdigit() else ""
                        }

                        if orig_ep and orig_ep != "NAN":
                            combined_dict[orig_ep] = meta_data
                            combined_dict[orig_ep.upper()] = meta_data
                        if orig_title and orig_title != "NAN":
                            combined_dict[orig_title] = meta_data
                            combined_dict[orig_title.upper()] = meta_data
                        if es_title and es_title != "NAN":
                            combined_dict[es_title.upper()] = meta_data

                        count += 1

                print(f"[OK] {filename} indexado con éxito ({count} registros).")
            except Exception:
                pass

    print(f"[ÉXITO] Metadatos mensuales activos indexados: {len(combined_dict)} elementos.")
    return combined_dict

def fetch_tmdb_synopsis(title):
    if not title or (not TMDB_TOKEN and not TMDB_API_KEY):
        return ""
    
    headers = {"accept": "application/json"}
    if TMDB_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_TOKEN}"
    elif TMDB_API_KEY:
        headers["Authorization"] = f"Bearer {TMDB_API_KEY}"

    clean_title_main = re.sub(r'[:\-].*', '', title).strip()
    search_queries = [clean_title_main, title] if clean_title_main != title else [title]

    for query_str in search_queries:
        if not query_str:
            continue
            
        params = {"query": query_str, "language": "es-ES"}
        try:
            url_tv = "https://api.themoviedb.org/3/search/tv"
            res = requests.get(url_tv, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                results = res.json().get("results", [])
                if results and results[0].get("overview"):
                    return results[0].get("overview")
                    
            url_movie = "https://api.themoviedb.org/3/search/movie"
            res = requests.get(url_movie, headers=headers, params=params, timeout=10)
            if res.status_code == 200:
                results = res.json().get("results", [])
                if results and results[0].get("overview"):
                    return results[0].get("overview")
        except Exception:
            pass
            
    return ""

def download_feed_xls(token, feed_id, referer_url):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es",
        "Authorization": f"Bearer {token}",
        "Referer": referer_url
    })

    url = BASE_DAILY_URL.format(feed_id=feed_id)
    res = session.get(url, timeout=60)
    res.raise_for_status()

    xls_path = f"{feed_id}_latest.xls"
    with open(xls_path, "wb") as f:
        f.write(res.content)

    print(f"[OK] XLS descargado exitosamente para {feed_id}.")
    return xls_path

def sanitize_and_parse_xml(file_path, generator_name):
    if not os.path.exists(file_path):
        return ET.Element("tv", {"generator-info-name": generator_name})

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        cleaned_lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in ["JUEVES", "VIERNES", "SÁBADO", "SABADO", "DOMINGO", "LUNES", "MARTES", "MIÉRCOLES", "MIERCOLES"] or (any(net in stripped for net in ["PANREGIONAL", "WARNER", "TNT", "CARTOON"]) and not stripped.startswith("<")):
                continue
            cleaned_lines.append(line)

        cleaned_content = "\n".join(cleaned_lines)
        return ET.fromstring(cleaned_content)
    except Exception:
        return ET.Element("tv", {"generator-info-name": generator_name})

def parse_xmltv_date(date_str, tz_info):
    if not date_str:
        return None
    clean_str = re.sub(r"[^\d\s\+\-]", "", str(date_str).strip())
    match = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", clean_str)
    if not match:
        return None

    year, month, day, hour, minute, second = map(int, match.groups())
    hour, minute, second = min(hour, 23), min(minute, 59), min(second, 59)
    return datetime(year, month, day, hour, minute, second, tzinfo=tz_info)

def format_xmltv_date(dt, tz_str):
    return dt.strftime(f"%Y%m%d%H%M%S {tz_str}")

def load_excel_schedule(file_path):
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        if any("Program Name" in str(col) or "Schedule Date" in str(col) for col in df.columns):
            return df
        return pd.read_excel(file_path, header=1, sheet_name=0)
    except Exception:
        try:
            df = pd.read_html(file_path)[0]
            if not any("Program Name" in str(col) or "Schedule Date" in str(col) for col in df.columns):
                df = pd.read_html(file_path, header=1)[0]
            return df
        except:
            return pd.read_html(file_path, header=1)[0]

def find_column(cols_dict, possible_names):
    for name in possible_names:
        if name in cols_dict:
            return cols_dict[name]
    for col_key, col_val in cols_dict.items():
        for name in possible_names:
            if name.lower() in col_key.lower():
                return col_val
    return None

def process_feed(root, feed_cfg, xls_path, monthly_meta=None):
    channel_id = feed_cfg["channel_id"]
    channel_name = feed_cfg["channel_name"]
    lang = feed_cfg["lang"]
    tz = feed_cfg["tz"]
    tz_str = feed_cfg["tz_str"]

    existing_channels = [ch for ch in root.findall("channel") if ch.attrib.get("id") == channel_id]
    if not existing_channels:
        ch_node = ET.SubElement(root, "channel", {"id": channel_id})
        disp = ET.SubElement(ch_node, "display-name")
        disp.text = channel_name

    df = load_excel_schedule(xls_path)
    cols = {str(c).strip(): c for c in df.columns}
    
    col_date = find_column(cols, ["Schedule Date", "Date", "Fecha"]) or df.columns[0]
    col_time = find_column(cols, ["Program Start Time", "Title Start Time", "Start Time", "Hora"]) or df.columns[1]
    col_title = find_column(cols, ["Program Name", "Title Name", "Title", "Programa"]) or df.columns[2]
    col_press_title = find_column(cols, ["Press Title (ESPA)", "Original Title"])
    
    col_ep_name = find_column(cols, ["Episode Title(ESPA)", "Episode Title (ESPA)", "Episode Name English", "Episode Name", "Sub-title"])
    col_ep_num = find_column(cols, ["Episode", "Episode Number", "Episodio"])
    col_season = find_column(cols, ["Season", "Season Number", "Temporada"])
    col_year = find_column(cols, ["Year", "Año"])
    
    col_desc = find_column(cols, ["Program Sinopsis Prensa(ESPA)", "Title Synopsis", "Synopsis", "Description"])
    col_ep_desc = find_column(cols, ["Episode Sinopsis Prensa(ESPA)", "Episode Synopsis"])
    
    col_is_new = find_column(cols, ["Is Premiere", "New Episode", "Premiere", "Estreno", "Title Classification", "Y/N"])

    first_date_raw = str(df.iloc[0].get(col_date, "")).strip()
    match_init = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", first_date_raw)
    if not match_init:
        print(f"[WARN] No se pudo detectar la fecha inicial para {channel_id}.")
        return

    d0, m0, y0 = map(int, match_init.groups())
    cycle_start = datetime(y0, m0, d0, 6, 0, 0, tzinfo=tz)
    cycle_end = cycle_start + timedelta(days=1)

    raw_events = []
    total_rows = len(df)

    for i in range(total_rows):
        row = df.iloc[i]
        date_raw = str(row.get(col_date, "")).strip()
        time_raw = str(row.get(col_time, "")).strip()

        date_match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", date_raw)
        time_match = re.search(r"(\d{1,2}):(\d{2})", time_raw)
        if not time_match and date_match:
            time_match = re.search(r"(\d{1,2}):(\d{2})", date_raw)

        if not date_match or not time_match:
            continue

        d, m, y = map(int, date_match.groups())
        hh, mm = map(int, time_match.groups())

        event_dt = datetime(y, m, d, hh, mm, 0, tzinfo=tz)
        if (d == d0 and m == m0 and y == y0) and hh < 6:
            event_dt += timedelta(days=1)

        if event_dt >= cycle_end:
            break

        prog_name_val = str(row.get(col_title, "")).strip() if pd.notna(row.get(col_title)) else ""
        press_title_val = str(row.get(col_press_title, "")).strip() if col_press_title and pd.notna(row.get(col_press_title)) else ""
        ep_name_val = str(row.get(col_ep_name, "")).strip() if col_ep_name and pd.notna(row.get(col_ep_name)) else ""
        year_val = str(row.get(col_year, "")).strip() if col_year and pd.notna(row.get(col_year)) else ""

        if prog_name_val.lower() == "cine cartoon":
            movie_title = press_title_val or ep_name_val
            if movie_title and movie_title.lower() != "nan":
                title_val = f"{movie_title} (Cine Cartoon)"
            else:
                title_val = "Cine Cartoon"
            ep_name_val = ""
        else:
            title_val = prog_name_val

        season_val = str(row.get(col_season, "")).strip() if col_season and pd.notna(row.get(col_season)) else ""
        ep_num_val = str(row.get(col_ep_num, "")).strip() if col_ep_num and pd.notna(row.get(col_ep_num)) else ""
        
        xmltv_season_ep = ""
        try:
            s_num = int(float(season_val)) - 1 if season_val.replace('.', '', 1).isdigit() else ""
            e_num = int(float(ep_num_val)) - 1 if ep_num_val.replace('.', '', 1).isdigit() else ""
            if s_num != "" and e_num != "":
                xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "":
                xmltv_season_ep = f".{e_num}."
        except:
            xmltv_season_ep = ""

        desc_val = ""
        if col_ep_desc and pd.notna(row.get(col_ep_desc)) and str(row.get(col_ep_desc)).strip():
            desc_val = str(row.get(col_ep_desc)).strip()
        elif col_desc and pd.notna(row.get(col_desc)) and str(row.get(col_desc)).strip():
            desc_val = str(row.get(col_desc)).strip()

        # CRUCE MEJORADO Y ROBUSTO CON METADATOS MENSUALES (Forzar traducción al español)
        if feed_cfg["feed_id"] == "CNLA_PAN" and monthly_meta:
            search_keys = [ep_name_val.upper(), title_val.upper()]
            matched_info = None

            for key in search_keys:
                if key and key in monthly_meta:
                    matched_info = monthly_meta[key]
                    break

            if matched_info:
                if matched_info["title"] and matched_info["title"].lower() != title_val.lower() and not ("(Cine Cartoon)" in title_val):
                    ep_name_val = matched_info["title"]
                if not desc_val and matched_info["desc"]:
                    desc_val = matched_info["desc"]
                if not year_val and matched_info["year"]:
                    year_val = matched_info["year"]

        if not desc_val and title_val:
            desc_val = fetch_tmdb_synopsis(title_val.replace(" (Cine Cartoon)", ""))

        is_new_episode = False
        if col_is_new and pd.notna(row.get(col_is_new)):
            val_new = str(row.get(col_is_new)).strip().upper()
            if val_new == "Y":
                is_new_episode = True

        if is_new_episode:
            if ep_name_val and ep_name_val.lower() != "nan":
                ep_name_val = f"{ep_name_val} (NUEVO EPISODIO)"
            elif title_val and not "(NUEVO EPISODIO)" in title_val:
                title_val = f"{title_val} (NUEVO EPISODIO)"

        clean_year = year_val.split('.')[0] if year_val and year_val.replace('.', '', 1).isdigit() else ""

        raw_events.append({
            "start": event_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title": ep_name_val if ep_name_val.lower() != "nan" and ep_name_val.lower() != title_val.lower() else "",
            "episode_num": xmltv_season_ep,
            "desc": desc_val if desc_val.lower() != "nan" else "",
            "year": clean_year
        })

    raw_events = sorted(raw_events, key=lambda x: x["start"])
    new_programmes = []
    total_events = len(raw_events)

    for i in range(total_events):
        ev = raw_events[i]
        start_dt = ev["start"]
        stop_dt = raw_events[i + 1]["start"] if i + 1 < total_events else cycle_end

        prog = ET.Element("programme", {
            "start": format_xmltv_date(start_dt, tz_str),
            "stop": format_xmltv_date(stop_dt, tz_str),
            "channel": channel_id
        })

        title = ET.SubElement(prog, "title", {"lang": lang})
        if ev["title"]:
            title.text = ev["title"]

        if ev["sub_title"]:
            sub_title = ET.SubElement(prog, "sub-title", {"lang": lang})
            sub_title.text = ev["sub_title"]

        if ev["desc"]:
            desc = ET.SubElement(prog, "desc", {"lang": lang})
            desc.text = ev["desc"]

        if ev["year"]:
            date_elem = ET.SubElement(prog, "date")
            date_elem.text = ev["year"]

        if ev["episode_num"]:
            ep_tag = ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"})
            ep_tag.text = ev["episode_num"]

        new_programmes.append(prog)

    existing_progs_map = {p.attrib.get("start"): p for p in root.findall("programme") if p.attrib.get("channel") == channel_id}
    
    for np in new_programmes:
        start_key = np.attrib.get("start")
        if start_key in existing_progs_map:
            root.remove(existing_progs_map[start_key])
        root.append(np)

    print(f"[{channel_id}] Eventos procesados e integrados hoy: {len(new_programmes)}")

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
            if ch.attrib.get("id") not in active_channel_ids:
                root.remove(ch)

        for feed_cfg in net_config["feeds"]:
            try:
                xls_path = download_feed_xls(token, feed_cfg["feed_id"], net_config["referer"])
                use_meta = cn_monthly_meta if "CNLA" in xml_filename else None
                process_feed(root, feed_cfg, xls_path, monthly_meta=use_meta)
            except Exception as e:
                print(f"[ERROR] Error al procesar feed {feed_cfg['feed_id']}: {e}")

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
            
            if stop_dt and stop_dt.astimezone(timezone.utc) < cutoff_past:
                root.remove(p)
            elif start_dt and start_dt.astimezone(timezone.utc) > cutoff_future:
                root.remove(p)

        sorted_progs = sorted(
            root.findall("programme"),
            key=lambda x: x.attrib.get("start", "")
        )
        for p in list(root.findall("programme")):
            root.remove(p)
        for p in sorted_progs:
            root.append(p)

        ET.indent(root, space="  ", level=0)
        ET.ElementTree(root).write(xml_filename, encoding="utf-8", xml_declaration=True)
        print(f"[OK] Archivo {xml_filename} guardado con éxito. Total programas activos: {len(sorted_progs)}")

if __name__ == "__main__":
    main()
