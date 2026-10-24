use std::collections::HashMap;
use std::env;
use reqwest::Client;
use serde::Deserialize;
use std::sync::Mutex;
use once_cell::sync::Lazy;
use unicode_normalization::UnicodeNormalization;
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
struct TVDetailResponse {
    number_of_seasons: Option<u32>,
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
    let no_accent: String = text.nfd().filter(|c| !c.is_ascii_punctuation() && !unicode_normalization::UnicodeNormalization::is_decoding_isolated(*c)).collect();
    // Simplified normalization cleaner
    let lower = text.to_lowercase();
    let re_pt = Regex::new(r"\bpt\.?\s*(\d+)").unwrap();
    let clean = re_pt.replace_all(&lower, "($1)");
    let re_part = Regex::new(r"\bpart\.?\s*(\d+)").unwrap();
    let clean = re_part.replace_all(&clean, "($1)");
    let re_alnum = Regex::new(r"[^a-z0-9]").unwrap();
    re_alnum.replace_all(&clean, "").to_string()
}

async fn fetch_tmdb_still(client: &Client, series_title: &str, season_str: &str, ep_str: &str, ep_title_en: &str, lang: &str) -> String {
    if series_title.is_empty() {
        return "".to_string();
    }

    let cache_key = format!("{}|{}|{}|{}|{}", series_title, season_str, ep_str, ep_title_en, lang);
    if let Ok(cache) = TMDB_CACHE.lock() {
        if let Some(val) = cache.get(&cache_key) {
            return val.clone();
        }
    }

    let token = env::var("TMDB_TOKEN").unwrap_or_default();
    let api_key = env::var("TMDB_API_KEY").unwrap_or_default();
    if token.is_empty() && api_key.is_empty() {
        return "".to_string();
    }

    let tmdb_lang = if lang == "pt" { "pt-BR" } else { "es-ES" };
    let auth_header = if !token.is_empty {
        format!("Bearer {}", token)
    } else {
        format!("Bearer {}", api_key)
    };

    let mut search_queries = vec![series_title.to_string()];
    if let Some(clean) = series_title.split(':').next().map(|s| s.trim()) {
        if !clean.is_empty() && !clean.eq_ignore_ascii_case(series_title) {
            search_queries.push(clean.to_string());
        }
    }

    let mut tv_id: u64 = 0;
    let mut number_of_seasons: u32 = 10;

    for query in search_queries {
        let res = client.get("https://api.themoviedb.org/3/search/tv")
            .query(&[("query", query.as_str()), ("language", tmdb_lang)])
            .header("accept", "application/json")
            .header("Authorization", &auth_header)
            .send()
            .await;

        if let Ok(resp) = res {
            if resp.status().is_success() {
                if let Ok(search_data) = resp.json::<TMDBResponse>().await {
                    if !search_data.results.is_empty() {
                        tv_id = search_data.results[0].id;
                        // Obtener número de temporadas
                        let detail_url = format!("https://api.themoviedb.org/3/tv/{}", tv_id);
                        if let Ok(detail_resp) = client.get(&detail_url).header("Authorization", &auth_header).send().await {
                            if let Ok(detail_data) = detail_resp.json::<TVDetailResponse>().await {
                                if let Some(seasons) = detail_data.number_of_seasons {
                                    if seasons > 0 {
                                        number_of_seasons = seasons;
                                    }
                                }
                            }
                        }
                        break;
                    }
                }
            }
        }
    }

    if tv_id != 0 {
        let s_opt = season_str.parse::<u32>();
        let norm_target = normalize_title(ep_title_en);

        // Prioridad 1: Barrido global de temporadas por título normalizado
        if !norm_target.is_empty() {
            let mut seasons_to_check = Vec::new();
            if let Ok(s) = s_opt {
                seasons_to_check.push(s);
            }
            for s in 1..=number_of_seasons {
                if !seasons_to_check.contains(&s) {
                    seasons_to_check.push(s);
                }
            }
            if !seasons_to_check.contains(&0) {
                seasons_to_check.push(0);
            }

            for s_check in seasons_to_check {
                let season_url = format!(
                    "https://api.themoviedb.org/3/tv/{}/season/{}?language=en-US",
                    tv_id, s_check
                );
                let season_res = client.get(&season_url)
                    .header("accept", "application/json")
                    .header("Authorization", &auth_header)
                    .send()
                    .await;

                if let Ok(season_resp) = season_res {
                    if season_resp.status().is_success() {
                        if let Ok(season_data) = season_resp.json::<SeasonResponse>().await {
                            if let Some(episodes) = season_data.episodes {
                                for ep in episodes {
                                    if let Some(name) = ep.name {
                                        if normalize_title(&name) == norm_target {
                                            if let Some(mut still) = ep.still_path {
                                                if !still.starts_with('/') {
                                                    still = format!("/{}", still);
                                                }
                                                let img_url = format!("https://media.themoviedb.org/t/p/w500{}", still);
                                                if let Ok(mut cache) = TMDB_CACHE.lock() {
                                                    cache.insert(cache_key, img_url.clone());
                                                }
                                                return img_url;
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

        // Prioridad 2: Respaldo por número de episodio
        let e_opt = ep_str.parse::<u32>();
        if let (Ok(s), Ok(e)) = (s_opt, e_opt) {
            let ep_url = format!(
                "https://api.themoviedb.org/3/tv/{}/season/{}/episode/{}?language={}",
                tv_id, s, e, tmdb_lang
            );
            let ep_res = client.get(&ep_url)
                .header("accept", "application/json")
                .header("Authorization", &auth_header)
                .send()
                .await;

            if let Ok(ep_resp) = ep_res {
                if ep_resp.status().is_success() {
                    if let Ok(ep_data) = ep_resp.json::<EpisodeResponse>().await {
                        if let Some(mut still) = ep_data.still_path {
                            if !still.starts_with('/') {
                                still = format!("/{}", still);
                            }
                            let img_url = format!("https://media.themoviedb.org/t/p/w500{}", still);
                            if let Ok(mut cache) = TMDB_CACHE.lock() {
                                cache.insert(cache_key, img_url.clone());
                            }
                            return img_url;
                        }
                    }
                }
            }
        }
    }

    "".to_string()
}

#[tokio::main]
async fn main() {
    println!("updater.rs sincronizado.");
}
