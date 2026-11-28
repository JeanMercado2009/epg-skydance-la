import os
import re
import io
import calendar
import zipfile
from datetime import datetime, timedelta, timezone, date
import lxml.etree as ET
import pandas as pd
import requests
import unicodedata

RETENTION_DAYS_PAST = 0
RETENTION_DAYS_FUTURE = 1

AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
DOWNLOAD_FILE_URL = "https://epg.tapkit.warnermedia.com/api/epg/tapkitFrontEnd/networksepg/downloadfiles"
REGISTER_DOWNLOAD_URL = "https://epg.tapkit.warnermedia.com/api/domain/users/register/downloaded/file"

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

http_session = requests.Session()
http_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36 Edg/158.0.0.0",
    "Accept": "application/json, text/plain, */*"
})

tmdb_cache = {}


def normalize_title(text):
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    no_accent = "".join([c for c in nfkd if not unicodedata.combining(c)])
    clean = no_accent.lower().strip()
    clean = re.sub(r"\bpt\.?\s*(\d+)", r"(\1)", clean)
    clean = re.sub(r"\bpart\.?\s*(\d+)", r"(\1)", clean)
    clean = re.sub(r"[^a-z0-9]", "", clean)
    return clean


def _tmdb_headers():
    token = TMDB_TOKEN or TMDB_API_KEY
    if not token:
        return None
    return {
        "accept": "application/json",
        "Authorization": f"Bearer {token}"
    }


def _build_tmdb_image_url(path_val, size="w500"):
    if not path_val:
        return ""
    p = str(path_val).strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return f"https://media.themoviedb.org/t/p/{size}{p}"


def fetch_tmdb_still(series_title, season_str, ep_str, ep_title_en="", lang="es"):
    if not series_title:
        return ""

    cache_key = f"{series_title}|{season_str}|{ep_str}|{ep_title_en}|still|{lang}"
    if cache_key in tmdb_cache:
        return tmdb_cache[cache_key]

    headers = _tmdb_headers()
    if not headers:
        return ""

    tmdb_lang = "pt-BR" if lang == "pt" else "es-ES"

    try:
        url_tv = "https://api.themoviedb.org/3/search/tv"
        search_queries = [series_title]
        clean_title = re.sub(r"[:\-].*", "", series_title).strip()
        if clean_title and clean_title.lower() != series_title.lower():
            search_queries.append(clean_title)

        tv_id = None
        for query in search_queries:
            res = http_session.get(
                url_tv,
                headers=headers,
                params={"query": query, "language": tmdb_lang},
                timeout=4
            )
            if res.status_code == 200 and res.json().get("results"):
                tv_id = res.json()["results"][0]["id"]
                break

        if tv_id:
            s_num = int(float(season_str)) if season_str and str(season_str).replace(".", "", 1).isdigit() else None
            e_num = int(float(ep_str)) if ep_str and str(ep_str).replace(".", "", 1).isdigit() else None

            if s_num is not None and e_num is not None:
                ep_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_num}/episode/{e_num}"
                ep_res = http_session.get(
                    ep_url,
                    headers=headers,
                    params={"language": tmdb_lang},
                    timeout=4
                )
                if ep_res.status_code == 200:
                    img_url = _build_tmdb_image_url(ep_res.json().get("still_path"), "w500")
                    if img_url:
                        tmdb_cache[cache_key] = img_url
                        return img_url

            norm_target = normalize_title(ep_title_en) if ep_title_en else ""
            if norm_target and s_num is not None:
                season_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{s_num}"
                season_res = http_session.get(
                    season_url,
                    headers=headers,
                    params={"language": "en-US"},
                    timeout=4
                )
                if season_res.status_code == 200:
                    for ep in season_res.json().get("episodes", []):
                        if normalize_title(ep.get("name", "")) == norm_target:
                            found_still = _build_tmdb_image_url(ep.get("still_path"), "w500")
                            if found_still:
                                tmdb_cache[cache_key] = found_still
                                return found_still
    except Exception:
        pass

    tmdb_cache[cache_key] = ""
    return ""


def fetch_tmdb_movie_image(movie_title, year_str="", lang="es"):
    if not movie_title:
        return ""

    cache_key = f"{movie_title}|{year_str}|movie|{lang}"
    if cache_key in tmdb_cache:
        return tmdb_cache[cache_key]

    headers = _tmdb_headers()
    if not headers:
        return ""

    tmdb_lang = "pt-BR" if lang == "pt" else "es-ES"

    try:
        url_movie = "https://api.themoviedb.org/3/search/movie"
        search_queries = [movie_title]
        clean_title = re.sub(r"[:\-].*", "", movie_title).strip()
        if clean_title and clean_title.lower() != movie_title.lower():
            search_queries.append(clean_title)

        year_clean = year_str.strip() if year_str and re.match(r"^\d{4}$", str(year_str).strip()) else ""

        for query in search_queries:
            params = {"query": query, "language": tmdb_lang}
            if year_clean:
                params["year"] = year_clean
            res = http_session.get(url_movie, headers=headers, params=params, timeout=4)
            if res.status_code == 200 and res.json().get("results"):
                top = res.json()["results"][0]
                img_url = (
                    _build_tmdb_image_url(top.get("backdrop_path"), "w780")
                    or _build_tmdb_image_url(top.get("poster_path"), "w500")
                )
                if img_url:
                    tmdb_cache[cache_key] = img_url
                    return img_url
    except Exception:
        pass

    tmdb_cache[cache_key] = ""
    return ""


NETWORKS_CONFIG = {
    "DKLA_EPG.xml": {
        "network_id": 47,
        "default_folder": "DISCKIDS",
        "default_file_id": "10605612",
        "default_category": "Infantil",
        "cineclub_enabled": True,
        "generator_name": "Guia de Programacion Discovery Kids MultiFeed",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/47",
        "feeds": [
            {
                "feed_id": "DKLA_PAN",
                "channel_id": "DK_PAN.co",
                "channel_name": "Discovery Kids Panregional",
                "region": "Latin",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500"
            },
            {
                "feed_id": "DKLA_CAR",
                "channel_id": "DK_CAR.co",
                "channel_name": "Discovery Kids Caribe",
                "region": "Caribe",
                "lang": "es",
                "tz": timezone(timedelta(hours=-4)),
                "tz_str": "-0400"
            },
            {
                "feed_id": "DKLA_MEX",
                "channel_id": "DK_MX.mx",
                "channel_name": "Discovery Kids México",
                "region": "Mexico",
                "lang": "es",
                "tz": timezone(timedelta(hours=-6)),
                "tz_str": "-0600"
            },
            {
                "feed_id": "DKLA_BR",
                "channel_id": "DK_BR.br",
                "channel_name": "Discovery Kids Brasil",
                "region": "Brazil",
                "lang": "pt",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300"
            }
        ]
    },
    "DHH_LA.xml": {
        "network_id": 38,
        "default_folder": "HAHD",
        "default_file_id": "10605638",
        "default_category": "Estilo de vida",
        "cineclub_enabled": False,
        "generator_name": "Guia de Programacion Discovery Home & Health",
        "referer": "https://epg.tapkit.warnermedia.com/epg/networks/38",
        "feeds": [
            {
                "feed_id": "DHH_LAT",
                "channel_id": "DHH_PAN.co",
                "channel_name": "Discovery Home & Health Panregional",
                "region": "Latin",
                "lang": "es",
                "tz": timezone(timedelta(hours=-5)),
                "tz_str": "-0500",
                "fallback_file_id": "10605638"
            },
            {
                "feed_id": "DHH_ARG",
                "channel_id": "DHH_AR.ar",
                "channel_name": "Discovery Home & Health Argentina",
                "region": "Argentina",
                "lang": "es",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300",
                "fallback_file_id": "10605632"
            },
            {
                "feed_id": "DHH_CAR",
                "channel_id": "DHH_CAR.co",
                "channel_name": "Discovery Home & Health Caribe",
                "region": "Caribe",
                "lang": "es",
                "tz": timezone(timedelta(hours=-4)),
                "tz_str": "-0400",
                "fallback_file_id": "10605652"
            },
            {
                "feed_id": "DHH_MEX",
                "channel_id": "DHH_MX.mx",
                "channel_name": "Discovery Home & Health México",
                "region": "Mexico",
                "lang": "es",
                "tz": timezone(timedelta(hours=-6)),
                "tz_str": "-0600",
                "fallback_file_id": "10605672"
            },
            {
                "feed_id": "DHH_BR",
                "channel_id": "DHH_BR.br",
                "channel_name": "Discovery Home & Health Brasil",
                "region": "Brazil",
                "lang": "pt",
                "tz": timezone(timedelta(hours=-3)),
                "tz_str": "-0300",
                "fallback_file_id": "10605628"
            },
            {
                "feed_id": "DHH_VZ_CL",
                "channel_id": "DHH_VZ_CL.co",
                "channel_name": "Discovery Home & Health Venezuela / Chile",
                "region": "Venezuela_Chile",
                "lang": "es",
                "tz": timezone(timedelta(hours=-4)),
                "tz_str": "-0400",
                "fallback_file_id": "10605710"
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
    print("[OK] Sesión iniciada en Tapkit y token obtenido.")
    return res.json().get("access_token")


def fetch_epak_files(token, network_id, referer_url):
    headers = {
        "Authorization": f"Bearer {token}",
        "Referer": referer_url,
        "Accept": "application/json, text/plain, */*"
    }
    all_files = []
    for fmt in ("csv", "xlsx"):
        url = f"https://epg.tapkit.warnermedia.com/api/domain/networkgrids/getepakfiles?networkId={network_id}&format={fmt}"
        try:
            res = http_session.get(url, headers=headers, timeout=20)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    print(f"[INFO] Network {network_id} EPAK ({fmt}): {len(data)} archivos encontrados.")
                    all_files.extend(data)
        except Exception as e:
            print(f"[WARN] No se pudo consultar EPAK ({fmt}) para networkId={network_id}: {e}")
    return all_files


def _parse_yymmdd(code_str):
    try:
        return datetime.strptime(code_str, "%y%m%d").date()
    except Exception:
        return None


def select_best_epak_file(epak_files, region, ref_date=None):
    if ref_date is None:
        ref_date = datetime.now(timezone.utc).date()

    region_tokens = [region.lower()]
    if region.lower() == "venezuela_chile":
        region_tokens.extend(["venezuela", "chile"])

    candidates = []
    for f_item in epak_files:
        raw_name = str(
            f_item.get("name")
            or f_item.get("fileName")
            or f_item.get("path")
            or ""
        )
        raw_lower = raw_name.lower()
        if any(tok in raw_lower for tok in region_tokens):
            normalized_item = dict(f_item)
            normalized_item["name"] = raw_name.split("/")[-1]
            candidates.append(normalized_item)

    if not candidates:
        return None

    scored = []
    for item in candidates:
        name = str(item.get("name", ""))
        matches = re.findall(r"(\d{6})", name)
        start_d = _parse_yymmdd(matches[0]) if len(matches) >= 1 else None
        end_d = _parse_yymmdd(matches[1]) if len(matches) >= 2 else None

        in_range = 0
        if start_d and end_d:
            if start_d <= ref_date <= end_d:
                in_range = 2
            elif start_d <= ref_date + timedelta(days=45):
                in_range = 1
        elif start_d:
            in_range = 1
        else:
            in_range = 1

        sort_key = end_d or start_d or date(1970, 1, 1)
        scored.append((in_range, sort_key, item))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def download_feed_xls(token, feed_cfg, net_config, epak_files):
    feed_id = feed_cfg["feed_id"]
    referer_url = net_config["referer"]
    folder = net_config["default_folder"]
    region = feed_cfg["region"]

    best_item = select_best_epak_file(epak_files, region)
    file_id_val = str(feed_cfg.get("fallback_file_id") or net_config["default_file_id"])

    if best_item:
        target_name = str(best_item.get("name", ""))
        raw_path = str(best_item.get("path") or f"network-files/{folder}/EPAK/FULL/{target_name}")
        target_path = raw_path if target_name in raw_path else f"{raw_path.rstrip('/')}/{target_name}"
        file_id_val = str(best_item.get("id", file_id_val))
    else:
        now_dt = datetime.now(timezone.utc)
        yy_curr = now_dt.strftime("%y")
        mm_curr = now_dt.strftime("%m")
        next_month_dt = (now_dt.replace(day=28) + timedelta(days=10)).replace(day=1)
        yy_next = next_month_dt.strftime("%y")
        mm_next = next_month_dt.strftime("%m")
        last_day_next = calendar.monthrange(next_month_dt.year, next_month_dt.month)[1]
        if folder == "HAHD":
            target_name = f"FULL_DLA_Disc_Home_Health_{region}_{yy_curr}{mm_curr}01_{yy_next}{mm_next}{last_day_next:02d}.csv"
        else:
            target_name = f"FULL_DLA_Discovery_Kids_{region}_{yy_curr}{mm_curr}01_{yy_next}{mm_next}{last_day_next:02d}.csv"
        target_path = f"network-files/{folder}/EPAK/FULL/{target_name}"

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
        content_type = res.headers.get("Content-Type", "").lower()
        looks_csv = (
            content_type in ("text/csv", "application/csv")
            or res.content.startswith(b"\xef\xbb\xbf")
            or b"," in res.content[:1024]
        )

        if looks_csv:
            extracted_file_path = f"{feed_id}_extracted_grid.csv"
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


def parse_xmltv_start_date(start_str):
    if not start_str:
        return None
    m = re.match(r"^(\d{8})", str(start_str).strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except Exception:
        return None


def load_schedule_dataframe(file_path):
    if file_path.lower().endswith(".csv"):
        df = None
        for sep in ("\t", ";", ","):
            try:
                candidate = pd.read_csv(
                    file_path,
                    sep=sep,
                    encoding="utf-8-sig",
                    on_bad_lines="skip"
                )
                if len(candidate.columns) > 1:
                    df = candidate
                    print(f"[INFO] CSV '{file_path}' cargado con separador {repr(sep)} ({len(df)} filas).")
                    break
            except Exception:
                pass
        if df is None:
            raise ValueError(f"No fue posible detectar el separador del CSV en '{file_path}'")
    elif file_path.lower().endswith(".xls"):
        df = pd.read_excel(file_path, sheet_name=0)
    else:
        df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")

    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", "_", regex=True)
    )

    if "CHANNEL_NAME" not in df.columns:
        raise ValueError(
            f"No existe CHANNEL_NAME. Columnas recibidas: {list(df.columns)}"
        )

    return df


def build_datetime_from_time(base_date, hour, minute, tz_info, raw_label="", allow_end_30=False):
    if 0 <= minute <= 59:
        if 0 <= hour <= 23:
            target_day = base_date
            adj_hour = hour
            adj_minute = minute
        elif 24 <= hour <= 29:
            target_day = base_date + timedelta(days=1)
            adj_hour = hour - 24
            adj_minute = minute
        elif hour == 30 and minute == 0 and allow_end_30:
            target_day = base_date + timedelta(days=1)
            adj_hour = 6
            adj_minute = 0
        else:
            print(f"[WARN] Hora no válida: {raw_label}")
            return None
    else:
        print(f"[WARN] Hora no válida: {raw_label}")
        return None

    return datetime(
        target_day.year, target_day.month, target_day.day,
        adj_hour, adj_minute, 0, tzinfo=tz_info
    )


def filter_dataframe_by_region(df, region):
    col = df["CHANNEL_NAME"].astype(str)
    r = region.lower()
    if r == "brazil":
        return df[col.str.contains("Brazil|Brasil", case=False, na=False)]
    if r == "mexico":
        return df[col.str.contains("Mexico|México", case=False, na=False)]
    if r == "caribe":
        return df[col.str.contains("Caribe", case=False, na=False)]
    if r == "argentina":
        return df[col.str.contains("Argentina", case=False, na=False)]
    if r == "venezuela_chile":
        return df[col.str.contains("Venezuela|Chile", case=False, na=False)]
    return df[col.str.contains("Latin", case=False, na=False)]


def process_daily_feed(root, feed_cfg, net_config, file_path):
    channel_id = feed_cfg["channel_id"]
    channel_name = feed_cfg["channel_name"]
    region = feed_cfg["region"]
    lang = feed_cfg["lang"]
    tz = feed_cfg["tz"]
    tz_str = feed_cfg["tz_str"]
    default_category = net_config.get("default_category", "Infantil")
    cineclub_enabled = bool(net_config.get("cineclub_enabled", False))

    target_local_day = datetime.now(tz).date()
    min_date = target_local_day - timedelta(days=RETENTION_DAYS_PAST)
    max_date = target_local_day + timedelta(days=RETENTION_DAYS_FUTURE)

    ch_node = next((ch for ch in root.findall("channel") if ch.attrib.get("id") == channel_id), None)
    if ch_node is None:
        ch_node = ET.SubElement(root, "channel", {"id": channel_id, "feed_id": feed_cfg["feed_id"]})
    if not any(dn.text == channel_name for dn in ch_node.findall("display-name")):
        ET.SubElement(ch_node, "display-name").text = channel_name

    df = load_schedule_dataframe(file_path)
    df = filter_dataframe_by_region(df, region)

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
        base_day = date(y, m, d)
        hh, mm = map(int, time_match.groups())

        event_dt = build_datetime_from_time(
            base_day, hh, mm, tz, raw_label=f"{date_raw} {time_raw}", allow_end_30=False
        )
        if not event_dt:
            continue

        if not (min_date <= event_dt.date() <= max_date):
            continue

        stop_dt = None
        if end_time_raw:
            end_match = re.search(r"(\d{1,2}):(\d{2})", end_time_raw)
            if end_match:
                ehh, emm = map(int, end_match.groups())
                stop_dt = build_datetime_from_time(
                    base_day, ehh, emm, tz, raw_label=f"{date_raw} {end_time_raw}", allow_end_30=True
                )
                if stop_dt and stop_dt <= event_dt:
                    stop_dt += timedelta(days=1)

        series_name = str(row.get("SERIES_NAME", "")).strip()
        prog_name = str(row.get("PROGRAM_NAME", "")).strip()
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
            s_num = int(float(season_val)) - 1 if season_val.replace(".", "", 1).isdigit() else ""
            e_num = int(float(ep_num_val)) - 1 if ep_num_val.replace(".", "", 1).isdigit() else ""
            if s_num != "" and e_num != "":
                xmltv_season_ep = f"{s_num}.{e_num}."
            elif e_num != "":
                xmltv_season_ep = f".{e_num}."
        except Exception:
            pass

        year_clean = year_val.split(".")[0] if year_val and year_val.replace(".", "", 1).isdigit() else ""
        prog_combined = f"{series_name} {prog_name} {local_prog}".lower()
        is_cineclub = cineclub_enabled and ("cineclub" in prog_combined)

        icon_url = ""
        if title_val:
            icon_url = fetch_tmdb_still(title_val, season_val, ep_num_val, ep_title_en=sub_en, lang=lang)
            if not icon_url and (is_cineclub or not season_val or not ep_num_val):
                movie_query = sub_es or sub_en or title_val
                icon_url = fetch_tmdb_movie_image(movie_query, year_str=year_clean, lang=lang)

        raw_events.append({
            "start": event_dt,
            "stop": stop_dt,
            "title": title_val if title_val.lower() != "nan" else "",
            "sub_title_es": sub_es if sub_es.lower() != "nan" and sub_es.lower() != title_val.lower() else "",
            "sub_title_en": sub_en if sub_en.lower() != "nan" and sub_en.lower() != sub_es.lower() else "",
            "episode_num": xmltv_season_ep,
            "desc_es": desc_es if desc_es.lower() != "nan" else "",
            "year": year_clean,
            "icon": icon_url,
            "is_cineclub": is_cineclub
        })

    raw_events = sorted(raw_events, key=lambda x: x["start"])
    new_programmes = []
    total_events = len(raw_events)

    for i in range(total_events):
        ev = raw_events[i]
        start_dt = ev["start"]
        stop_dt = ev.get("stop") or (
            raw_events[i + 1]["start"] if i + 1 < total_events else start_dt + timedelta(minutes=30)
        )

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

        ET.SubElement(prog, "category", {"lang": lang}).text = default_category
        if ev["is_cineclub"]:
            ET.SubElement(prog, "category", {"lang": lang}).text = "Cineclub"

        if ev["episode_num"]:
            ET.SubElement(prog, "episode-num", {"system": "xmltv_ns"}).text = ev["episode_num"]
        if ev["icon"]:
            ET.SubElement(prog, "icon", {"src": ev["icon"]})

        new_programmes.append(prog)

    existing_progs_map = {}
    for p in list(root.findall("programme")):
        if p.attrib.get("channel") == channel_id:
            p_date = parse_xmltv_start_date(p.attrib.get("start"))
            if p_date and not (min_date <= p_date <= max_date):
                if p in root:
                    root.remove(p)
            else:
                existing_progs_map[p.attrib.get("start")] = p

    for np in new_programmes:
        start_key = np.attrib.get("start")
        if start_key in existing_progs_map:
            old_p = existing_progs_map[start_key]
            if old_p in root:
                root.remove(old_p)
        root.append(np)

    print(f"[{channel_id}] Eventos procesados ({min_date} a {max_date}): {len(new_programmes)}")


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

        epak_files = fetch_epak_files(token, net_config["network_id"], net_config["referer"])

        for feed_cfg in net_config["feeds"]:
            try:
                file_path = download_feed_xls(token, feed_cfg, net_config, epak_files)
                process_daily_feed(root, feed_cfg, net_config, file_path)
            except Exception as e:
                print(f"[ERROR] Feed Discovery {feed_cfg['feed_id']}: {e}")

        sorted_progs = sorted(root.findall("programme"), key=lambda x: x.attrib.get("start", ""))
        for p in list(root.findall("programme")):
            if p in root:
                root.remove(p)
        for p in sorted_progs:
            root.append(p)

        ET.indent(root, space="  ", level=0)
        ET.ElementTree(root).write(
            xml_filename,
            encoding="utf-8",
            xml_declaration=True
        )
        print(
            f"[OK] {xml_filename} guardado correctamente. "
            f"Total programas: {len(sorted_progs)}"
        )


if __name__ == "__main__":
    main()
