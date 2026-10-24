import os
import re
import io
import zipfile
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import pandas as pd
import requests

RETENTION_DAYS_PAST = 5
RETENTION_DAYS_FUTURE = 15

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

def fetch_tmdb_still(series_title, season_str, ep_str, ep_title_en="", lang="es"):
    if not series_title:
        return ""
    clean_title = re.sub(r'[:\-].*', '', series_title).strip()
    cache_key = f"{clean_title}|{season_str}|{ep_str}|{ep_title_en}|{lang}"
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
        res = http_session.get(url_tv, headers=headers, params={"query": clean_title, "language": tmdb_lang}, timeout=4)
        if res.status_code == 200 and res.json().get("results"):
            tv_id = res.json()["results"][0]["id"]
            
            s_num, e_num = None, None
            if season_str and str(season_str).replace('.', '', 1).isdigit():
                s_num = int(float(season_str))
            if ep_str and str(ep_str).replace('.', '', 1).isdigit():
                e_num = int(float(ep_str))

            # 1. Intento principal por número de temporada y episodio
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

            # 2. Respaldo inteligente por el título exacto en inglés dentro de la temporada
            if s_num is not None and ep_title_en:
                season_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_num}"
                season_res = http_session.get(season_url, headers=headers, params={"language": "en-US"}, timeout=4)
                if season_res.status_code == 200:
                    for ep in season_res.json().get("episodes", []):
                        if ep.get("name", "").strip().lower() == ep_title_en.strip().lower():
                            still_path = ep.get("still_path")
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
                df_break = pd.read_csv(io.BytesIO(res.content))
                for _, row in df_break.iterrows():
                    start_raw = str(row.get("Start Time") or row.get("START_TIME") or "").strip()
                    end_raw = str(row.get("End Time") or row.get("END_TIME") or "").strip()
                    s_match = re.search(r"(\d{2}):(\d{2}):(\d{2})", start_raw)
                    e_match = re.search(r"(\d{2}):(\d{2}):(\d{2})", end_raw)
                    if s_match and e_match:
                        sh, sm, ss = map(int, s_match.groups())
                        eh, em, es = map(int, e_match.groups())
                        y, m, d = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:])
                        start_dt = datetime(y, m, d, sh, sm, ss, tzinfo=tz_info)
                        end_dt = datetime(y, m, d, eh, em, es, tzinfo=tz_info)
                        if end_dt <= start_dt:
                            end_dt += timedelta(days=1)
                        breaks_events.append({
                            "start": start_dt, "stop": end_dt,
                            "title": "Pausa Comercial", "desc": "Espacio publicitario y promos de la señal.",
                            "category": "Comercial", "type": "break"
                        })
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
    }
}

def login_and_get_token():
    email = os.environ.get("TAPKIT_EMAIL", "").strip()
    password = os.environ.get("TAPKIT_PASSWORD", "").strip()
    payload = {"grant_type": "password", "scope": "any", "username": email, "password": password}
    res = http_session.post(AUTH_URL, data=payload, timeout=30)
    res.raise_for_status()
    return res.json().get("access_token")

def main():
    token = login_and_get_token()
    print(f"Token obtenido correctamente: {token[:10]}...")

if __name__ == "__main__":
    main()
