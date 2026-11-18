import os
import re
import io
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd
import requests

RETENTION_DAYS_PAST = 5
RETENTION_DAYS_FUTURE = 15

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
DOWNLOAD_FILE_URL = "https://epg.tapkit.warnermedia.com/api/domain/users/register/downloaded/file"

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
})

DISCOVERY_CONFIG = {
    "DKLA_EPG.xml": {
        "generator_name": "Guia de Programacion Discovery Kids MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/api/networks/47",
        "feeds": [
            {
                "feed_id": "DKLA_PAN", 
                "file_id": "10587908", 
                "channel_id": "DKLA_PAN.co", 
                "channel_name": "Discovery Kids Panregional", 
                "lang": "es", 
                "tz": timezone(timedelta(hours=-5)), 
                "tz_str": "-0500",
                "expected_tz_col": "Colombia"
            },
            {
                "feed_id": "DKLA_CAR", 
                "file_id": "10587948", 
                "channel_id": "DKLA_CAR.co", 
                "channel_name": "Discovery Kids Caribe", 
                "lang": "es", 
                "tz": timezone(timedelta(hours=-5)), 
                "tz_str": "-0500",
                "expected_tz_col": "Colombia"
            },
            {
                "feed_id": "DKLA_MX", 
                "file_id": "10587962", 
                "channel_id": "DKLA_MX.mx", 
                "channel_name": "Discovery Kids Mexico", 
                "lang": "es", 
                "tz": timezone(timedelta(hours=-6)), 
                "tz_str": "-0600",
                "expected_tz_col": "Mexico"
            },
            {
                "feed_id": "DKLA_BR", 
                "file_id": "10587870", 
                "channel_id": "DKLA_BR.br", 
                "channel_name": "Discovery Kids Brasil", 
                "lang": "pt", 
                "tz": timezone(timedelta(hours=-3)), 
                "tz_str": "-0300",
                "expected_tz_col": "Brasilia"
            }
        ]
    }
}

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()
    payload = {"grant_type": "password", "scope": "any", "username": email, "password": password}
    res = http_session.post(AUTH_URL, data=payload, timeout=30)
    res.raise_for_status()
    print("[OK] Token obtenido para Discovery Kids.")
    return res.json().get("access_token")

def download_discovery_file(token, feed_cfg):
    file_id = feed_cfg["file_id"]
    feed_id = feed_cfg["feed_id"]
    xls_path = f"{feed_id}_discovery.csv"

    headers = {
        "Authorization": f"Bearer {token}",
        "Referer": "https://epg.tapkit.warnermedia.com/api/networks/47",
        "Accept-Language": "es"
    }

    current_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    files = {
        'user-token': (None, token),
        'file-id': (None, str(file_id)),
        'downloaded-date': (None, current_date_str)
    }
    res = http_session.post(DOWNLOAD_FILE_URL, headers=headers, files=files, timeout=30)
    res.raise_for_status()
    
    with open(xls_path, "wb") as f:
        f.write(res.content)
    return xls_path

def sanitize_and_parse_xml(file_path, generator_name):
    if not os.path.exists(file_path): 
        return ET.Element("tv", {"generator-info-name": generator_name})
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f: 
            content = f.read()
        return ET.fromstring(content)
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

def process_discovery_feed(root, feed_cfg, csv_path):
    channel_id = feed_cfg["channel_id"]
    channel_name = feed_cfg["channel_name"]
    lang = feed_cfg["lang"]
    tz = feed_cfg["tz"]
    tz_str = feed_cfg["tz_str"]

    if not any(ch.attrib.get("id") == channel_id for ch in root.findall("channel")):
        ch_node = ET.SubElement(root, "channel", {"id": channel_id})
        ET.SubElement(ch_node, "display-name").text = channel_name

    try:
        df = pd.read_csv(csv_path, sep='\t', encoding='utf-8', on_bad_lines='skip')
    except Exception as e:
        print(f"[ERROR] No se pudo leer el CSV de Discovery {channel_id}: {e}")
        return

    # Regla de transmisión: Antes de las 06:00 AM, el día operativo pertenece al día anterior
    now_local = datetime.now(tz)
    if now_local.hour < 6:
        target_date = (now_local - timedelta(days=1)).strftime("%Y/%m/%d")
    else:
        target_date = now_local.strftime("%Y/%m/%d")

    print(f"[{channel_id}] Procesando con Timezone {tz_str} | Día operativo exacto: {target_date}")

    raw_events = []
    for _, row in df.iterrows():
        sched_date = str(row.get("SCHEDULE_DATE", "")).strip()
        if sched_date != target_date:
            continue

        start_time_str = str(row.get("START_TIME", "")).strip()
        end_time_str = str(row.get("END_TIME", "")).strip()
        
        if not start_time_str or not end_time_str:
            continue

        try:
            sh, sm = map(int, start_time_str.split(':')[:2])
            eh, em = map(int, end_time_str.split(':')[:2])
            
            y, mo, d = map(int, target_date.split('/'))
            start_dt = datetime(y, mo, d, sh, sm, 0, tzinfo=tz)
            stop_dt = datetime(y, mo, d, eh, em, 0, tzinfo=tz)
            
            if stop_dt <= start_dt:
                stop_dt += timedelta(days=1)
        except Exception:
            continue

        series_name = str(row.get("SERIES_NAME", "")).strip()
        title_name = str(row.get("TITLE_NAME", "")).strip()
        desc = str(row.get("PROGRAMME_DESCRIPTION", "")).strip()
        local_title = str(row.get("LOCAL_PROGRAM_NAME", "")).strip()
        local_desc = str(row.get("LOCAL_PROGRAM_DESCRIPTION", "")).strip()
        year_val = str(row.get("YEAR_OF_PRODUCTION", "")).strip()
        season_num = str(row.get("SEASON_NUMBER", "")).strip()
        ep_num = str(row.get("EPISODE_NUMBER", "")).strip()

        final_title = series_name if series_name and series_name.lower() != "nan" else "Discovery Kids"
        final_subtitle = local_title if local_title and local_title.lower() != "nan" else (title_name if title_name and title_name.lower() != "nan" else "")
        final_desc = local_desc if local_desc and local_desc.lower() != "nan" else (desc if desc and desc.lower() != "nan" else "")

        xmltv_season_ep = ""
        try:
            s_num = int(float(season_num)) - 1 if season_num.replace('.', '', 1).isdigit() else ""
            e_num = int(float(ep_num)) - 1 if ep_num.replace('.', '', 1).isdigit() else ""
            if s_num != "" and e_num != "": xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "": xmltv_season_ep = f".{e_num}."
        except: pass

        raw_events.append({
            "start": start_dt,
            "stop": stop_dt,
            "title": final_title,
            "subtitle": final_subtitle,
            "desc": final_desc,
            "year": year_val if year_val.isdigit() else "",
            "episode_num": xmltv_season_ep
        })

    new_programmes = []
    for ev in raw_events:
        start_str = format_xmltv_date(ev["start"], tz_str)
        stop_str = format_xmltv_date(ev["stop"], tz_str)
        start_utc = format_xmltv_date(ev["start"].astimezone(timezone.utc), "+0000")
        stop_utc = format_xmltv_date(ev["stop"].astimezone(timezone.utc), "+0000")

        prog = ET.Element("programme", {
            "start": start_str,
            "stop": stop_str,
            "air_time_start": start_str,
            "air_time_end": stop_str,
            "start_utc": start_utc,
            "stop_utc": stop_utc,
            "channel": channel_id
        })

        if ev["title"]: ET.SubElement(prog, "title", {"lang": lang}).text = ev["title"]
        if ev["subtitle"] and ev["subtitle"].lower() != ev["title"].lower(): 
            ET.SubElement(prog, "sub-title", {"lang": lang}).text = ev["subtitle"]
        if ev["desc"]: ET.SubElement(prog, "desc", {"lang": lang}).text = ev["desc"]
        if ev["year"]: ET.SubElement(prog, "date").text = ev["year"]
        ET.SubElement(prog, "category", {"lang": lang}).text = "Animación"
        if ev["episode_num"]: 
            ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"}).text = ev["episode_num"]

        new_programmes.append(prog)

    existing_progs_map = {p.attrib.get("start"): p for p in root.findall("programme") if p.attrib.get("channel") == channel_id}
    for np in new_programmes:
        start_key = np.attrib.get("start")
        if start_key in existing_progs_map: root.remove(existing_progs_map[start_key])
        root.append(np)

    print(f"[{channel_id}] Programas de Discovery procesados: {len(new_programmes)}")

def main():
    token = login_and_get_token()

    for xml_filename, net_config in DISCOVERY_CONFIG.items():
        print(f"\n==========================================")
        print(f"Procesando Independiente: {xml_filename}")
        print(f"==========================================")
        
        root = sanitize_and_parse_xml(xml_filename, net_config["generator_name"])
        active_channel_ids = {cfg["channel_id"] for cfg in net_config["feeds"]}
        for ch in list(root.findall("channel")):
            if ch.attrib.get("id") not in active_channel_ids: root.remove(ch)

        for feed_cfg in net_config["feeds"]:
            try:
                csv_path = download_discovery_file(token, feed_cfg)
                process_discovery_feed(root, feed_cfg, csv_path)
            except Exception as e:
                print(f"[ERROR] Feed Discovery {feed_cfg['feed_id']}: {e}")

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
