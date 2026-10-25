import os
import re
import io
import zipfile
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import unicodedata

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
MONTHLY_FILES_URL = "https://epg.tapkit.warnermedia.com/api/epg/tapkitFrontEnd/networksepg/downloadfiles"

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
})

tmdb_cache = {}

TITLE_ALIASES = {
    "equipo monstruo": "monster squad",
    "el malentendido": "the misunderstandings",
    "el origen parte 1": "the origins 1",
    "el origen parte 2": "the origins 2",
    "kabums pt 2": "kabooms (2)",
    "kabúms pt 2": "kabooms (2)",
    "kabums pt 1": "kabooms (1)",
    "kabúms pt 1": "kabooms (1)",
    "standards & practices": "s&p",
    "arcoiris de la dimension de cristal": "crystals have power",
    "el cruce": "crossover",
    "la panza de la bestia": "belly of the beast"
}

def get_target_dates_to_process():
    now = datetime.now()
    weekday = now.weekday() # 0: Lun, 1: Mar, 2: Mié, 3: Jue, 4: Vie, 5: Sáb, 6: Dom
    dates_to_fetch = [now.strftime("%Y-%m-%d")]

    if weekday == 4: # Viernes -> Viernes y Sábado
        dates_to_fetch.append((now + timedelta(days=1)).strftime("%Y-%m-%d"))
    elif weekday == 5: # Sábado -> Sábado, Domingo y Lunes
        dates_to_fetch.append((now + timedelta(days=1)).strftime("%Y-%m-%d"))
        dates_to_fetch.append((now + timedelta(days=2)).strftime("%Y-%m-%d"))
        
    return list(dict.fromkeys(dates_to_fetch))

def normalize_title(text):
    if not text: return ""
    clean_raw = text.lower().strip()
    if clean_raw in TITLE_ALIASES:
        text = TITLE_ALIASES[clean_raw]
    text = re.sub(r'\(.*?\)', '', text)
    nfkd = unicodedata.normalize('NFKD', text)
    no_accent = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = no_accent.lower().strip()
    clean = re.sub(r'\b(?:pt\.?|part\.?)\s*(\d+)', r'(\1)', clean)
    clean = re.sub(r's\b', '', clean)
    clean = re.sub(r'[^a-z0-9&]', '', clean)
    return clean

def fetch_tmdb_still(series_title, season_str, ep_str, ep_title_en="", ep_title_es="", lang="es"):
    if not series_title: return ""
    raw_target = ep_title_en if ep_title_en and ep_title_en.lower() != "nan" else ep_title_es
    lookup_target = TITLE_ALIASES.get(raw_target.lower().strip(), raw_target)
    
    cache_key = f"{series_title}|{season_str}|{ep_str}|{lookup_target}|{lang}"
    if cache_key in tmdb_cache: return tmdb_cache[cache_key]

    lower_title = series_title.lower()
    if "submarine jim" in lower_title or "el submarino de jim" in lower_title:
        img = "https://media.themoviedb.org/t/p/w220_and_h330_face/cHN9UE0cjsDByMWk0FgaPEkHNeJ.jpg"
        tmdb_cache[cache_key] = img
        return img
    if "aquaman: rage of atlantis" in lower_title or "lego dc" in lower_title:
        img = "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg"
        tmdb_cache[cache_key] = img
        return img
    if "spider-man" in lower_title and "un nuevo universo" in lower_title:
        img = "https://media.themoviedb.org/t/p/w220_and_h330_face/iiZZdoQBEYBv6id8su7ImL0oCbD.jpg"
        tmdb_cache[cache_key] = img
        return img

    if not TMDB_TOKEN and not TMDB_API_KEY: return ""
    tmdb_lang = "pt-BR" if lang == "pt" else "es-ES"
    headers = {"accept": "application/json"}
    if TMDB_TOKEN: headers["Authorization"] = f"Bearer {TMDB_TOKEN}"
    elif TMDB_API_KEY: headers["Authorization"] = f"Bearer {TMDB_API_KEY}"

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
            norm_target = normalize_title(lookup_target)
            if norm_target:
                seasons_to_check = []
                if s_num is not None: seasons_to_check.append(s_num)
                for s in range(1, number_of_seasons + 1):
                    if s not in seasons_to_check: seasons_to_check.append(s)
                seasons_to_check.append(0)

                found_still = ""
                for s_check in seasons_to_check:
                    season_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_check}"
                    season_res = http_session.get(season_url, headers=headers, params={"language": "en-US"}, timeout=4)
                    if season_res.status_code == 200:
                        for ep in season_res.json().get("episodes", []):
                            ep_name_raw = ep.get("name", "")
                            if normalize_title(ep_name_raw) == norm_target or norm_target in normalize_title(ep_name_raw):
                                still_path = ep.get("still_path")
                                if still_path:
                                    if not still_path.startswith('/'): still_path = '/' + still_path
                                    found_still = f"https://media.themoviedb.org/t/p/w500{still_path}"
                                    break
                    if found_still: break
                if found_still:
                    tmdb_cache[cache_key] = found_still
                    return found_still
    except Exception: pass
    tmdb_cache[cache_key] = ""
    return ""

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()
    payload = {"grant_type": "password", "scope": "any", "username": email, "password": password}
    res = http_session.post(AUTH_URL, data=payload, timeout=30)
    res.raise_for_status()
    return res.json().get("access_token")

def get_target_months():
    now = datetime.now()
    year_curr, month_curr = now.year, now.month
    year_next, month_next = (year_curr + 1, 1) if month_curr == 12 else (year_curr, month_curr + 1)
    return [(year_curr, month_curr), (year_next, month_next)]

def standardize_date_str(date_val):
    if not date_val or pd.isna(date_val): return ""
    d_str = str(date_val).strip().split()[0]
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})|(\d{1,2})[-/](\d{1,2})[-/](\d{4})", d_str)
    if match:
        groups = match.groups()
        if groups[0]: y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
        else: d, m, y = int(groups[3]), int(groups[4]), int(groups[5])
        return f"{y:04d}-{m:02d}-{d:02d}"
    return d_str

def download_and_load_monthly_rows(token, target_dates, network="CNLA", lang="SPA", feed_type="PAN"):
    months = get_target_months()
    all_rows = []
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
                res = http_session.post(MONTHLY_FILES_URL, json=payload, headers=headers, timeout=20)
                if res.status_code != 200: continue
                content_bytes = io.BytesIO(res.content)
                df_grid = None
                if zipfile.is_zipfile(content_bytes):
                    with zipfile.ZipFile(content_bytes) as z:
                        for z_name in z.namelist():
                            if z_name.endswith((".xlsx", ".xls")):
                                with z.open(z_name) as f:
                                    try: df_grid = pd.read_excel(f, header=1)
                                    except: df_grid = pd.read_html(f)[0]
                else:
                    try: df_grid = pd.read_excel(content_bytes, header=1)
                    except: df_grid = pd.read_html(content_bytes)[0]
                if df_grid is not None:
                    for _, row in df_grid.iterrows():
                        all_rows.append(row)
            except Exception: pass
    return all_rows

NETWORKS_CONFIG = {
    "CNLA_EPG.xml": {
        "generator_name": "Guia de Programacion Cartoon Network MultiFeed",
        "feeds": [
            {"feed_id": "CNLA_PAN", "channel_id": "CNLA_PAN.co", "channel_name": "Cartoon Network Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "CNLA_BR", "channel_id": "CNLA_BR.br", "channel_name": "Cartoon Network Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    }
}

def sanitize_and_parse_xml(generator_name):
    root = ET.Element("tv", {"generator-info-name": generator_name})
    pan = ET.SubElement(root, "channel", {"id": "CNLA_PAN.co"})
    ET.SubElement(pan, "display-name").text = "Cartoon Network Panregional"
    br = ET.SubElement(root, "channel", {"id": "CNLA_BR.br"})
    ET.SubElement(br, "display-name").text = "Cartoon Network Brasil"
    return root

def format_xmltv_date(dt, tz_str):
    return dt.strftime(f"%Y%m%d%H%M%S {tz_str}")

def process_single_day_feed(root, feed_cfg, monthly_rows, target_date_str):
    channel_id = feed_cfg["channel_id"]
    lang = feed_cfg["lang"]
    tz = feed_cfg["tz"]
    tz_str = feed_cfg["tz_str"]

    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    cycle_start = datetime(target_dt.year, target_dt.month, target_dt.day, 6, 0, 0, tzinfo=tz)
    cycle_end = cycle_start + timedelta(days=1)

    raw_events = []
    for row in monthly_rows:
        date_raw = standardize_date_str(row.get("Schedule Date") or row.get("Date"))
        time_raw = str(row.get("Title Start Time") or "").strip()[:5]
        
        time_match = re.search(r"(\d{1,2}):(\d{2})", time_raw)
        if not date_raw or not time_match: continue

        try:
            parts = date_raw.split("-")
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        except: continue

        hh, mm = map(int, time_match.groups())
        event_dt = datetime(y, m, d, hh, mm, 0, tzinfo=tz)

        if hh < 6 and event_dt.date() == cycle_start.date():
            event_dt += timedelta(days=1)

        if event_dt < cycle_start or event_dt >= cycle_end:
            continue

        prog_name_val = str(row.get("Title Name") or "").strip()
        if prog_name_val.upper() == "LOS COLORADO": prog_name_val = "El Chapulín Y Los Colorado"

        press_title_val = str(row.get("Press Title (ESPA)") or "").strip()
        ep_name_es = str(row.get("Episode Name") or "").strip()
        ep_name_en = str(row.get("Episode Name English") or "").strip()
        season_val = str(row.get("Season") or "").strip()
        ep_num_val = str(row.get("Episode") or "").strip()
        desc_es = str(row.get("Episode Synopsis") or "").strip()

        if prog_name_val.lower() == "cine cartoon":
            movie_title = press_title_val or ep_name_es
            title_val = f"{movie_title} (Cine Cartoon)" if movie_title and movie_title.lower() != "nan" else "Cine Cartoon"
            ep_name_es, ep_name_en = "", ""
            desc_es = "Cartoon Network trae los clásicos del cine a la pantalla de TV."
        else:
            title_val = prog_name_val

        if ep_name_es.lower() == title_val.lower() or ep_name_es.lower() == "nan":
            ep_name_es = ""

        xmltv_season_ep = ""
        try:
            s_num = int(float(season_val)) - 1 if season_val.replace('.', '', 1).isdigit() else ""
            e_num = int(float(ep_num_val)) - 1 if ep_num_val.replace('.', '', 1).isdigit() else ""
            if s_num != "" and e_num != "": xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "": xmltv_season_ep = f".{e_num}."
        except: pass

        query_ep_en = ep_name_en if ep_name_en and ep_name_en.lower() != "nan" else ""
        query_ep_es = ep_name_es if ep_name_es and ep_name_es.lower() != "nan" else ""
        
        icon_url = fetch_tmdb_still(
            title_val, season_val, ep_num_val, 
            ep_title_en=query_ep_en, 
            ep_title_es=query_ep_es, 
            lang=lang
        ) if title_val and "Cine Cartoon" not in title_val else ""

        raw_events.append({
            "start": event_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title_es": ep_name_es if ep_name_es.lower() != "nan" else "",
            "sub_title_en": query_ep_en,
            "episode_num": xmltv_season_ep,
            "desc_es": desc_es if desc_es.lower() != "nan" else "",
            "icon": icon_url
        })

    raw_events = sorted(raw_events, key=lambda x: x["start"])
    total = len(raw_events)

    for i in range(total):
        ev = raw_events[i]
        start_dt = ev["start"]
        stop_dt = raw_events[i + 1]["start"] if i + 1 < total else cycle_end

        prog = ET.Element("programme", {
            "start": format_xmltv_date(start_dt, tz_str),
            "stop": format_xmltv_date(stop_dt, tz_str),
            "channel": channel_id
        })

        if ev["title"]: ET.SubElement(prog, "title", {"lang": lang}).text = ev["title"]
        if ev["sub_title_es"]: ET.SubElement(prog, "sub-title", {"lang": lang}).text = ev["sub_title_es"]
        if ev["sub_title_en"]: ET.SubElement(prog, "sub-title", {"lang": "en"}).text = ev["sub_title_en"]
        if ev["desc_es"]: ET.SubElement(prog, "desc", {"lang": lang}).text = ev["desc_es"]
        if ev["episode_num"]: ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"}).text = ev["episode_num"]
        if ev["icon"]: ET.SubElement(prog, "icon", {"src": ev["icon"]})

        root.append(prog)

def main():
    token = login_and_get_token()
    target_dates = get_target_dates_to_process()
    print(f"[INFO] Fechas objetivo estrictas: {target_dates}")

    feed_type_map = {"CNLA_PAN": "PAN", "CNLA_BR": "BR"}

    for xml_filename, net_config in NETWORKS_CONFIG.items():
        root = sanitize_and_parse_xml(net_config["generator_name"])
        for feed_cfg in net_config["feeds"]:
            f_type = feed_type_map.get(feed_cfg["feed_id"], "PAN")
            lang_code = "POR" if feed_cfg["lang"] == "pt" else "SPA"
            monthly_rows = download_and_load_monthly_rows(token, target_dates, network="CNLA", lang=lang_code, feed_type=f_type)
            
            for d_str in target_dates:
                process_single_day_feed(root, feed_cfg, monthly_rows, d_str)

        sorted_progs = sorted(root.findall("programme"), key=lambda x: x.attrib.get("start", ""))
        for p in list(root.findall("programme")): root.remove(p)
        for p in sorted_progs: root.append(p)

        ET.indent(root, space="  ", level=0)
        ET.ElementTree(root).write(xml_filename, encoding="utf-8", xml_declaration=True)
        print(f"[OK] {xml_filename} generado correctamente.")

if __name__ == "__main__":
    main()
