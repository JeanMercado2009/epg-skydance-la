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
BASE_DAILY_URL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId={feed_id}&format=xls"
LOCAL_BREAKS_URL = "https://epg.tapkit.warnermedia.com/api/epg/tapkitLocalBreaks/downloadfile"

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
    "kabums pt 2": "kabooms 2",
    "kabums pt 1": "kabooms 1",
    "standards & practices": "s&p",
    "arcoiris de la dimension de cristal": "crystals have power",
    "el cruce": "crossover",
    "la panza de la bestia": "belly of the beast"
}

def get_target_dates_to_process():
    now = datetime.now()
    weekday = now.weekday() # 0: Lunes, 4: Viernes, 5: Sábado, 6: Domingo
    dates_to_fetch = [now.strftime("%Y%m%d")]

    if weekday == 4: # Viernes -> anticipa Sábado
        dates_to_fetch.append((now + timedelta(days=1)).strftime("%Y%m%d"))
    elif weekday == 5: # Sábado -> anticipa Domingo y Lunes
        dates_to_fetch.append((now + timedelta(days=1)).strftime("%Y%m%d"))
        dates_to_fetch.append((now + timedelta(days=2)).strftime("%Y%m%d"))
        
    return list(dict.fromkeys(dates_to_fetch))

def normalize_title(text):
    if not text:
        return ""
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

def fetch_tmdb_still(series_title, season_str, ep_str, ep_title_en="", lang="es"):
    if not series_title:
        return ""
    
    lookup_target = ep_title_en if ep_title_en else series_title
    cache_key = f"{series_title}|{season_str}|{ep_str}|{lookup_target}|{lang}"
    if cache_key in tmdb_cache:
        return tmdb_cache[cache_key]

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

            norm_target = normalize_title(lookup_target)
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
                            ep_name_raw = ep.get("name", "")
                            if normalize_title(ep_name_raw) == norm_target or normalize_title(ep_name_raw) in norm_target:
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
    except Exception:
        pass

    tmdb_cache[cache_key] = ""
    return ""

NETWORKS_CONFIG = {
    "CNLA_EPG.xml": {
        "generator_name": "Guia de Programacion Cartoon Network MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/2",
        "feeds": [
            {"feed_id": "CNLA_PAN", "channel_id": "CNLA_PAN.co", "channel_name": "Cartoon Network Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "CNLA_BR", "channel_id": "CNLA_BR.br", "channel_name": "Cartoon Network Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    }
}

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()
    payload = {"grant_type": "password", "scope": "any", "username": email, "password": password}
    res = http_session.post(AUTH_URL, data=payload, timeout=30)
    res.raise_for_status()
    return res.json().get("access_token")

def download_feed_xls(token, feed_id, referer_url):
    url = BASE_DAILY_URL.format(feed_id=feed_id)
    res = http_session.get(url, headers={
        "Authorization": f"Bearer {token}",
        "Referer": referer_url,
        "Accept-Language": "es"
    }, timeout=30)
    res.raise_for_status()
    xls_path = f"{feed_id}_latest.xls"
    with open(xls_path, "wb") as f: f.write(res.content)
    return xls_path

def sanitize_and_parse_xml(file_path, generator_name):
    root = ET.Element("tv", {"generator-info-name": generator_name})
    pan = ET.SubElement(root, "channel", {"id": "CNLA_PAN.co"})
    ET.SubElement(pan, "display-name").text = "Cartoon Network Panregional"
    br = ET.SubElement(root, "channel", {"id": "CNLA_BR.br"})
    ET.SubElement(br, "display-name").text = "Cartoon Network Brasil"
    return root

def format_xmltv_date(dt, tz_str):
    return dt.strftime(f"%Y%m%d%H%M%S {tz_str}")

def load_excel_schedule(file_path):
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        if any("Program Name" in str(col) or "Schedule Date" in str(col) for col in df.columns): return df
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

def process_feed(root, feed_cfg, xls_path, token=None):
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
    col_ep_name = find_column(cols, ["Episode Title(ESPA)", "Episode Title (ESPA)", "Episode Title(PORT)", "Episode Name English", "Episode Name"])
    col_ep_name_en = find_column(cols, ["Episode Name English", "Original Episode Title", "Episode Title(INGL)"])
    col_ep_num = find_column(cols, ["Episode", "Episode Number", "Episodio"])
    col_season = find_column(cols, ["Season", "Season Number", "Temporada"])
    col_desc = find_column(cols, ["Program Sinopsis Prensa(ESPA)", "Synopsis", "Description"])

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

        title_val = str(row.get(col_title, "")).strip() if pd.notna(row.get(col_title)) else ""
        sub_es = str(row.get(col_ep_name, "")).strip() if col_ep_name and pd.notna(row.get(col_ep_name)) else ""
        sub_en = str(row.get(col_ep_name_en, "")).strip() if col_ep_name_en and pd.notna(row.get(col_ep_name_en)) else ""
        season_val = str(row.get(col_season, "")).strip() if col_season and pd.notna(row.get(col_season)) else ""
        ep_num_val = str(row.get(col_ep_num, "")).strip() if col_ep_num and pd.notna(row.get(col_ep_num)) else ""
        desc_es = str(row.get(col_desc, "")).strip() if col_desc and pd.notna(row.get(col_desc)) else ""

        xmltv_season_ep = ""
        try:
            s_num = int(float(season_val)) - 1 if season_val.replace('.', '', 1).isdigit() else ""
            e_num = int(float(ep_num_val)) - 1 if ep_num_val.replace('.', '', 1).isdigit() else ""
            if s_num != "" and e_num != "": xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "": xmltv_season_ep = f".{e_num}."
        except: pass

        query_ep_title = sub_en if sub_en else sub_es
        icon_url = fetch_tmdb_still(title_val, season_val, ep_num_val, ep_title_en=query_ep_title, lang=lang) if title_val else ""

        raw_events.append({
            "start": event_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title_es": sub_es if sub_es.lower() != "nan" else "",
            "sub_title_en": sub_en if sub_en.lower() != "nan" else "",
            "episode_num": xmltv_season_ep,
            "desc_es": desc_es if desc_es.lower() != "nan" else "",
            "icon": icon_url
        })

    # Orden cronológico estricto para evitar desfases (ej. 07:03)
    raw_events = sorted(raw_events, key=lambda x: x["start"])
    for i, ev in enumerate(raw_events):
        start_dt = ev["start"]
        stop_dt = raw_events[i + 1]["start"] if i + 1 < len(raw_events) else cycle_end

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
    print(f"[INFO] Fechas calculadas por regla inteligente: {target_dates}")

    for xml_filename, net_config in NETWORKS_CONFIG.items():
        root = sanitize_and_parse_xml(xml_filename, net_config["generator_name"])
        for feed_cfg in net_config["feeds"]:
            for d_str in target_dates:
                try:
                    xls_path = download_feed_xls(token, feed_cfg["feed_id"], net_config["referer"])
                    process_feed(root, feed_cfg, xls_path, token=token)
                except Exception as e:
                    print(f"[ERROR] Feed {feed_cfg['feed_id']}: {e}")

        # Ordenar programa final completo cronológicamente sin duplicados
        sorted_progs = sorted(root.findall("programme"), key=lambda x: x.attrib.get("start", ""))
        for p in list(root.findall("programme")): root.remove(p)
        for p in sorted_progs: root.append(p)

        ET.indent(root, space="  ", level=0)
        ET.ElementTree(root).write(xml_filename, encoding="utf-8", xml_declaration=True)
        print(f"[OK] {xml_filename} generado limpiamente.")

if __name__ == "__main__":
    main()
