import os
import re
import io
import zipfile
from datetime import datetime, timedelta, timezone
import lxml.etree as ET
import pandas as pd
import requests
import unicodedata

RETENTION_DAYS_PAST = 5
RETENTION_DAYS_FUTURE = 15

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
GET_EPAK_CSV_URL = "https://epg.tapkit.warnermedia.com/api/domain/networkgrids/getepakfiles?networkId=47&format=csv"
GET_EPAK_XLSX_URL = "https://epg.tapkit.warnermedia.com/api/domain/networkgrids/getepakfiles?networkId=47&format=xlsx"
DOWNLOAD_FILE_URL = "https://epg.tapkit.warnermedia.com/api/epg/tapkitFrontEnd/networksepg/downloadfiles"
REGISTER_DOWNLOAD_URL = "https://epg.tapkit.warnermedia.com/api/domain/users/register/downloaded/file"

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0",
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
    "DKLA_EPG.xml": {
        "generator_name": "Guia de Programacion Discovery Kids MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/47",
        "feeds": [
            {"feed_id": "DKLA_PAN", "channel_id": "DK_PAN.co", "channel_name": "Discovery Kids Panregional", "lang": "es", "tz": timezone(timedelta(hours=-5)), "tz_str": "-0500"},
            {"feed_id": "DKLA_CAR", "channel_id": "DK_CAR.co", "channel_name": "Discovery Kids Caribe", "lang": "es", "tz": timezone(timedelta(hours=-4)), "tz_str": "-0400"},
            {"feed_id": "DKLA_MEX", "channel_id": "DK_MX.mx", "channel_name": "Discovery Kids México", "lang": "es", "tz": timezone(timedelta(hours=-6)), "tz_str": "-0600"},
            {"feed_id": "DKLA_BR", "channel_id": "DK_BR.br", "channel_name": "Discovery Kids Brasil", "lang": "pt", "tz": timezone(timedelta(hours=-3)), "tz_str": "-0300"}
        ]
    }
}

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()
    payload = {"grant_type": "password", "scope": "any", "username": email, "password": password}
    res = http_session.post(AUTH_URL, data=payload, timeout=30)
    res.raise_for_status()
    print("[OK] Sesión iniciada para Discovery Kids y token obtenido.")
    return res.json().get("access_token")

def fetch_epak_files(token, referer_url):
    headers = {
        "Authorization": f"Bearer {token}",
        "Referer": referer_url,
        "Accept": "application/json, text/plain, */*"
    }
    all_files = []
    for url in [GET_EPAK_CSV_URL, GET_EPAK_XLSX_URL]:
        try:
            res = http_session.get(url, headers=headers, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    print(f"[INFO] EPAK ({url.split('format=')[-1]}): {len(data)} archivos encontrados.")
                    all_files.extend(data)
        except Exception as e:
            print(f"[WARN] No se pudo consultar EPAK desde {url}: {e}")
    return all_files

def download_feed_xls(token, feed_cfg, referer_url, epak_files):
    feed_id = feed_cfg["feed_id"]

    region_map = {
        "DKLA_PAN": "Latin",
        "DKLA_CAR": "Caribe",
        "DKLA_MEX": "Mexico",
        "DKLA_BR": "Brazil"
    }
    region = region_map.get(feed_id, "Latin")

    target_name = None
    target_path = None
    file_id_val = "10605612"

    for f_item in epak_files:
        name = f_item.get("name", "")
        if region.lower() in name.lower() or region in name:
            target_name = name
            target_path = f_item.get("path", f"network-files/DISCKIDS/EPAK/FULL/{name}")
            file_id_val = str(f_item.get("id", "10605612"))
            break

    if not target_name:
        target_name = f"FULL_DLA_Discovery_Kids_{region}_261101_261231.xlsx"
        target_path = f"network-files/DISCKIDS/EPAK/FULL/{target_name}"

    print(f"[{feed_id}] Descargando archivo: {target_name}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://epg.tapkit.warnermedia.com",
        "Referer": referer_url,
        "Accept": "application/json, text/plain, */*"
    }
    payload = [{"name": target_name, "path": target_path}]

    res = http_session.post(DOWNLOAD_FILE_URL, json=payload, headers=headers, timeout=30)
    res.raise_for_status()

    if res.content.startswith(b"PK") or zipfile.is_zipfile(io.BytesIO(res.content)):
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            file_list = z.namelist()
            print(f"[{feed_id}] ZIP detectado. Archivos internos: {file_list}")

            target_file = next(
                (f for f in file_list if f.lower().endswith(".csv")),
                next(
                    (f for f in file_list if f.lower().endswith((".xlsx", ".xls"))),
                    file_list[0]
                )
            )

            if target_file.lower().endswith(".csv"):
                extracted_file_path = f"{feed_id}_extracted_grid.csv"
            elif target_file.lower().endswith(".xls"):
                extracted_file_path = f"{feed_id}_extracted_grid.xls"
            else:
                extracted_file_path = f"{feed_id}_extracted_grid.xlsx"

            with z.open(target_file) as src, open(extracted_file_path, "wb") as dst:
                dst.write(src.read())

            print(f"[{feed_id}] Extraído '{target_file}' -> '{extracted_file_path}'")
    else:
        extracted_file_path = f"{feed_id}_extracted_grid.xlsx"
        with open(extracted_file_path, "wb") as f:
            f.write(res.content)
        print(f"[{feed_id}] Guardado directo -> '{extracted_file_path}'")

    current_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.835")
    form_data = {
        "user-token": token,
        "file-id": file_id_val,
        "downloaded-date": current_date_str
    }
    try:
        http_session.post(REGISTER_DOWNLOAD_URL, headers={
            "Authorization": f"Bearer {token}",
            "Referer": referer_url,
            "Origin": "https://epg.tapkit.warnermedia.com"
        }, data=form_data, timeout=10)
    except Exception:
        pass

    return extracted_file_path

def sanitize_and_parse_xml(file_path, generator_name):
    if not os.path.exists(file_path):
        return ET.Element("tv", {"generator-info-name": generator_name})
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return ET.fromstring(content.encode("utf-8"))
    except Exception as e:
        print(f"[WARN] No se pudo parsear XML existente '{file_path}': {e}. Creando nuevo raíz.")
        return ET.Element("tv", {"generator-info-name": generator_name})

def format_xmltv_date(dt, tz_str):
    return dt.strftime(f"%Y%m%d%H%M%S {tz_str}")

def load_schedule_dataframe(file_path):
    if file_path.lower().endswith(".csv"):
        for sep in ("\t", ";", ","):
            try:
                df = pd.read_csv(
                    file_path,
                    sep=sep,
                    encoding="utf-8-sig",
                    on_bad_lines="skip"
                )
                if len(df.columns) > 1:
                    print(f"[INFO] CSV '{file_path}' cargado con separador {repr(sep)} ({len(df)} filas).")
                    return df
            except Exception:
                pass
        raise ValueError(f"No fue posible detectar el separador del CSV en '{file_path}'")

    if file_path.lower().endswith(".xls"):
        return pd.read_excel(file_path, sheet_name=0)

    return pd.read_excel(file_path, sheet_name=0, engine="openpyxl")

def process_daily_feed(root, feed_cfg, file_path):
    channel_id = feed_cfg["channel_id"]
    channel_name = feed_cfg["channel_name"]
    lang = feed_cfg["lang"]
    tz = feed_cfg["tz"]
    tz_str = feed_cfg["tz_str"]

    if not any(ch.attrib.get("id") == channel_id for ch in root.findall("channel")):
        ch_node = ET.SubElement(root, "channel", {"id": channel_id})
        ET.SubElement(ch_node, "display-name").text = channel_name

    df = load_schedule_dataframe(file_path)

    if "BR" in channel_id:
        df = df[df['CHANNEL_NAME'].astype(str).str.contains("Brazil|Brasil", case=False, na=False)]
    elif "MX" in channel_id:
        df = df[df['CHANNEL_NAME'].astype(str).str.contains("Mexico|México", case=False, na=False)]
    elif "CAR" in channel_id:
        df = df[df['CHANNEL_NAME'].astype(str).str.contains("Caribe", case=False, na=False)]
    else:
        df = df[df['CHANNEL_NAME'].astype(str).str.contains("Latin", case=False, na=False)]

    raw_events = []
    for _, row in df.iterrows():
        date_raw = str(row.get("SCHEDULE_DATE", "")).strip()
        time_raw = str(row.get("START_TIME", "")).strip()
        end_time_raw = str(row.get("END_TIME", "")).strip()

        date_match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_raw)
        time_match = re.search(r"(\d{1,2}):(\d{2})", time_raw)

        if not date_match or not time_match:
            continue

        y, m, d = map(int, date_match.groups())
        hh, mm = map(int, time_match.groups())
        event_dt = datetime(y, m, d, hh, mm, 0, tzinfo=tz)

        stop_dt = None
        if end_time_raw:
            end_match = re.search(r"(\d{1,2}):(\d{2})", end_time_raw)
            if end_match:
                ehh, emm = map(int, end_match.groups())
                stop_dt = datetime(y, m, d, ehh, emm, 0, tzinfo=tz)
                if stop_dt <= event_dt:
                    stop_dt += timedelta(days=1)

        series_name = str(row.get("SERIES_NAME", "")).strip()
        title_en = str(row.get("TITLE_NAME", "")).strip()
        desc_en = str(row.get("PROGRAMME_DESCRIPTION", "")).strip()

        local_series = str(row.get("LOCAL_SERIES_NAME", "")).strip()
        local_prog = str(row.get("LOCAL_PROGRAM_NAME", "")).strip()
        desc_es = str(row.get("LOCAL_PROGRAM_DESCRIPTION", "")).strip()

        season_val = str(row.get("SEASON_NUMBER", "")).strip()
        ep_num_val = str(row.get("EPISODE_NUMBER", "")).strip()
        year_val = str(row.get("YEAR_OF_PRODUCTION", "")).strip()

        title_val = local_series if local_series and local_series.lower() != "nan" else series_name
        sub_es = local_prog if local_prog and local_prog.lower() != "nan" else ""
        sub_en = title_en if title_en and title_en.lower() != "nan" else ""

        if not desc_es:
            desc_es = desc_en

        xmltv_season_ep = ""
        try:
            s_num = int(float(season_val)) - 1 if season_val.replace('.', '', 1).isdigit() else ""
            e_num = int(float(ep_num_val)) - 1 if ep_num_val.replace('.', '', 1).isdigit() else ""
            if s_num != "" and e_num != "":
                xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "":
                xmltv_season_ep = f".{e_num}."
        except Exception:
            pass

        icon_url = fetch_tmdb_still(title_val, season_val, ep_num_val, ep_title_en=sub_en, lang=lang) if title_val else ""

        raw_events.append({
            "start": event_dt,
            "stop": stop_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title_es": sub_es if sub_es.lower() != "nan" and sub_es.lower() != title_val.lower() else "",
            "sub_title_en": sub_en if sub_en.lower() != "nan" and sub_en.lower() != sub_es.lower() else "",
            "episode_num": xmltv_season_ep,
            "desc_es": desc_es if desc_es.lower() != "nan" else "",
            "year": year_val.split('.')[0] if year_val and year_val.replace('.', '', 1).isdigit() else "",
            "icon": icon_url
        })

    raw_events = sorted(raw_events, key=lambda x: x["start"])
    new_programmes = []
    total_events = len(raw_events)

    for i in range(total_events):
        ev = raw_events[i]
        start_dt = ev["start"]
        stop_dt = ev.get("stop") or (raw_events[i + 1]["start"] if i + 1 < total_events else start_dt + timedelta(minutes=30))

        if stop_dt <= start_dt:
            stop_dt = start_dt + timedelta(minutes=1)

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

        if ev["title"]:
            ET.SubElement(prog, "title", {"lang": lang}).text = ev["title"]
        if ev["sub_title_es"]:
            ET.SubElement(prog, "sub-title", {"lang": lang}).text = ev["sub_title_es"]
        if ev["sub_title_en"]:
            ET.SubElement(prog, "sub-title", {"lang": "en"}).text = ev["sub_title_en"]
        if ev["desc_es"]:
            ET.SubElement(prog, "desc", {"lang": lang}).text = ev["desc_es"]

        if ev["year"]:
            ET.SubElement(prog, "date").text = ev["year"]
        ET.SubElement(prog, "category", {"lang": lang}).text = "Infantil"

        if ev["episode_num"]:
            ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"}).text = ev["episode_num"]
        if ev["icon"]:
            ET.SubElement(prog, "icon", {"src": ev["icon"]})

        new_programmes.append(prog)

    existing_progs_map = {p.attrib.get("start"): p for p in root.findall("programme") if p.attrib.get("channel") == channel_id}
    for np in new_programmes:
        start_key = np.attrib.get("start")
        if start_key in existing_progs_map:
            old_p = existing_progs_map[start_key]
            if old_p in root:
                root.remove(old_p)
        root.append(np)

    print(f"[{channel_id}] Eventos procesados para Discovery Kids: {len(new_programmes)}")

def main():
    token = login_and_get_token()

    for xml_filename, net_config in NETWORKS_CONFIG.items():
        print(f"\n==========================================")
        print(f"Procesando Discovery: {xml_filename}")
        print(f"==========================================")

        root = sanitize_and_parse_xml(xml_filename, net_config["generator_name"])
        active_channel_ids = {cfg["channel_id"] for cfg in net_config["feeds"]}
        for ch in list(root.findall("channel")):
            if ch.attrib.get("id") not in active_channel_ids:
                if ch in root:
                    root.remove(ch)

        epak_files = fetch_epak_files(token, net_config["referer"])

        for feed_cfg in net_config["feeds"]:
            try:
                file_path = download_feed_xls(token, feed_cfg, net_config["referer"], epak_files)
                process_daily_feed(root, feed_cfg, file_path)
            except Exception as e:
                print(f"[ERROR] Feed Discovery {feed_cfg['feed_id']}: {e}")

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