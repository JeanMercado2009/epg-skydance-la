use std::collections::HashMap;
use std::env;
use reqwest::Client;
use serde::Deserialize;
use std::sync::Mutex;
use once_cell::sync::Lazy;
use regex::Regex;

#[derive(Deserialize)]
struct TMDBResponse {
    results: Vec<TVResult>,
}

#[derive(Deserialize)]
struct TVResult {
    id: u64,
}

#[derive(Deserialize)]
struct EpisodeResponse {
    name: Option<String>,
    still_path: Option<String>,
}

#[derive(Deserialize)]
struct SeasonResponse {
    episodes: Option<Vec<EpisodeResponse>>,
}

static TMDB_CACHE: Lazy<Mutex<HashMap<String, String>>> = Lazy::new(|| Mutex::new(HashMap::new()));

fn normalize_title(text: &str) -> String {
    if text.is_empty() {
        return "".to_string();
    }
    let mut clean_raw = text.to_lowercase();
    
    if clean_raw == "equipo monstruo" { clean_raw = "monster squad".to_string(); }
    else if clean_raw == "el malentendido" { clean_raw = "the misunderstandings".to_string(); }
    else if clean_raw == "el origen parte 1" { clean_raw = "the origins 1".to_string(); }
    else if clean_raw == "el origen parte 2" { clean_raw = "the origins 2".to_string(); }
    else if clean_raw == "kabums pt 2" { clean_raw = "kabooms 2".to_string(); }
    else if clean_raw == "kabums pt 1" { clean_raw = "kabooms 1".to_string(); }
    else if clean_raw == "standards & practices" { clean_raw = "s&p".to_string(); }

    let re_paren = Regex::new(r"\(.*?\)").unwrap();
    let clean_raw = re_paren.replace_all(&clean_raw, "");

    let re_pt = Regex::new(r"\b(?:pt\.?|part\.?)\s*(\d+)").unwrap();
    let clean = re_pt.replace_all(&clean_raw, "($1)");
    let re_plural = Regex::new(r"s\b").unwrap();
    let clean = re_plural.replace_all(&clean, "");
    let re_alnum = Regex::new(r"[^a-z0-9&]").unwrap();
    re_alnum.replace_all(&clean, "").to_string()
}

async fn fetch_tmdb_still(client: &Client, series_title: &str, season_str: &str, ep_str: &str, ep_title_en: &str, lang: &str) -> String {
    if series_title.is_empty() {
        return "".to_string();
    }

    let lookup_target = if !ep_title_en.is_empty() { ep_title_en } else { series_title };

    let lower_title = series_title.to_lowercase();
    if lower_title.contains("submarine jim") || lower_title.contains("el submarino de jim") {
        return "https://media.themoviedb.org/t/p/w220_and_h330_face/cHN9UE0cjsDByMWk0FgaPEkHNeJ.jpg".to_string();
    }
    if lower_title.contains("aquaman: rage of atlantis") || lower_title.contains("lego dc") {
        return "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg".to_string();
    }
    if lower_title.contains("spider-man") && lower_title.contains("un nuevo universo") {
        return "https://media.themoviedb.org/t/p/w220_and_h330_face/iiZZdoQBEYBv6id8su7ImL0oCbD.jpg".to_string();
    }

    let token = env::var("TMDB_TOKEN").unwrap_or_default();
    let api_key = env::var("TMDB_API_KEY").unwrap_or_default();
    if token.is_empty() && api_key.is_empty() {
        return "".to_string();
    }

    let auth_header = if !token.is_empty { format!("Bearer {}", token) } else { format!("Bearer {}", api_key) };
    let tmdb_lang = if lang == "pt" { "pt-BR" } else { "es-ES" };

    let res = client.get("https://api.themoviedb.org/3/search/tv")
        .query(&[("query", series_title), ("language", tmdb_lang)])
        .header("accept", "application/json")
        .header("Authorization", &auth_header)
        .send()
        .await;

    if let Ok(resp) = res {
        if let Ok(search_data) = resp.json::<TMDBResponse>().await {
            if !search_data.results.is_empty() {
                let tv_id = search_data.results[0].id;
                let season_url = format!("https://api.themoviedb.org/3/tv/{}/season/{}?language=en-US", tv_id, season_str);
                if let Ok(season_resp) = client.get(&season_url).header("Authorization", &auth_header).send().await {
                    if let Ok(season_data) = season_resp.json::<SeasonResponse>().await {
                        if let Some(episodes) = season_data.episodes {
                            let norm_target = normalize_title(lookup_target);
                            for ep in episodes {
                                if let Some(name) = ep.name {
                                    if normalize_title(&name) == norm_target {
                                        if let Some(mut still) = ep.still_path {
                                            if !still.starts_with('/') { still = format!("/{}", still); }
                                            return format!("https://media.themoviedb.org/t/p/w500{}", still);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    "".to_string()
}
