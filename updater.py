import os
import re
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd
import requests

# -------------------------------------------------------------
# CONFIGURACIÓN GENERAL Y CANALES
# -------------------------------------------------------------
RETENTION_DAYS = 15

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
BASE_DAILY_URL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId={feed_id}&format=xls"

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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

def download_feed_xls(token, feed_id, referer_url):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        df = pd.read_excel(file_path, header=1, sheet_name=0)
    except Exception:
        df = pd.read_html(file_path, header=1)[0]
    return df

def find_column(cols_dict, possible_names):
    """Busca de forma segura una columna que coincida con alguna de las opciones dadas."""
    for name in possible_names:
        if name in cols_dict:
            return cols_dict[name]
    # Búsqueda parcial / insensible a mayúsculas
    for col_key, col_val in cols_dict.items():
        for name in possible_names:
            if name.lower() in col_key.lower():
                return col_val
    return None

def process_feed(root, feed_cfg, xls_path):
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
    
    # Mapeo flexible de columnas por nombre
    cols = {str(c).strip(): c for c in df.columns}
    
    col_date = find_column(cols, ["Schedule Date", "Date", "Fecha"]) or df.columns[0]
    col_time = find_column(cols, ["Title Start Time", "Start Time", "Hora"]) or df.columns[1]
    col_title = find_column(cols, ["Title Name", "Title", "Programa"]) or df.columns[2]
    
    # Columnas específicas para subtítulos, temporada y episodio
    col_ep_name = find_column(cols, ["Episode Name English", "Episode Name", "Sub-title"])
    col_ep_num = find_column(cols, ["Episode", "Episode Number", "Episodio"])
    col_season = find_column(cols, ["Season", "Season Number", "Temporada"])
    
    # Sinopsis
    col_desc = find_column(cols, ["Title Synopsis", "Synopsis", "Description"])
    col_ep_desc = find_column(cols, ["Episode Synopsis"])

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
        time_match = re.search(r"(\d{1,2}):(\d{2})", time_match.group(0) if time_match else "") or re.search(r"(\d{1,2}):(\d{2})", time_raw)

        if not date_match or not time_match:
            continue

        d, m, y = map(int, date_match.groups())
        hh, mm = map(int, time_match.groups())

        event_dt = datetime(y, m, d, hh, mm, 0, tzinfo=tz)
        if (d == d0 and m == m0 and y == y0) and hh < 6:
            event_dt += timedelta(days=1)

        if event_dt >= cycle_end:
            break

        title_val = str(row.get(col_title, "")).strip() if pd.notna(row.get(col_title)) else ""
        ep_name_val = str(row.get(col_ep_name, "")).strip() if col_ep_name and pd.notna(row.get(col_ep_name)) else ""
        
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

        raw_events.append({
            "start": event_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title": ep_name_val if ep_name_val.lower() != "nan" and ep_name_val.lower() != title_val.lower() else "",
            "episode_num": xmltv_season_ep,
            "desc": desc_val if desc_val.lower() != "nan" else ""
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

        if ev["episode_num"]:
            ep_tag = ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"})
            ep_tag.text = ev["episode_num"]

        if ev["desc"]:
            desc = ET.SubElement(prog, "desc", {"lang": lang})
            desc.text = ev["desc"]

        new_programmes.append(prog)

    existing_starts = {p.attrib.get("start") for p in root.findall("programme") if p.attrib.get("channel") == channel_id}
    for np in new_programmes:
        if np.attrib.get("start") not in existing_starts:
            root.append(np)

    print(f"[{channel_id}] Eventos procesados hoy: {len(new_programmes)}")

def main():
    token = login_and_get_token()

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
                process_feed(root, feed_cfg, xls_path)
            except Exception as e:
                print(f"[ERROR] Error al procesar feed {feed_cfg['feed_id']}: {e}")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        for p in list(root.findall("programme")):
            ch_id = p.attrib.get("channel")
            if ch_id not in active_channel_ids:
                root.remove(p)
                continue
            cfg = next((c for c in net_config["feeds"] if c["channel_id"] == ch_id), net_config["feeds"][0])
            stop_dt = parse_xmltv_date(p.attrib.get("stop", ""), cfg["tz"])
            if stop_dt and stop_dt < cutoff_date:
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
        print(f"[OK] Archivo {xml_filename} guardado con éxito. Total programas: {len(sorted_progs)}")

if __name__ == "__main__":
    main()
