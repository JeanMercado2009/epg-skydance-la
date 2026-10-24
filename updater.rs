use std::collections::HashMap;
use std::env;
use reqwest::Client;
use serde::Deserialize;
use std::sync::Mutex;
use once_cell::sync::Lazy;

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

async fn fetch_tmdb_still(client: &Client, series_title: &str, season_str: &str, ep_str: &str, ep_title_en: &str, lang: &str) -> String {
    if series_title.is_empty() {
        return "".to_string();
    }

    let clean_title = series_title.split(':').next().unwrap_or(series_title)
        .split('-').next().unwrap_or(series_title).trim();

    let cache_key = format!("{}|{}|{}|{}|{}", clean_title, season_str, ep_str, ep_title_en, lang);
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

    let res = client.get("https://api.themoviedb.org/3/search/tv")
        .query(&[("query", clean_title), ("language", tmdb_lang)])
        .header("accept", "application/json")
        .header("Authorization", &auth_header)
        .send()
        .await;

    if let Ok(resp) = res {
        if resp.status().is_success() {
            if let Ok(search_data) = resp.json::<TMDBResponse>().await {
                if !search_data.results.is_empty() {
                    let tv_id = search_data.results[0].id;
                    let s_opt = season_str.parse::<u32>();
                    let e_opt = ep_str.parse::<u32>();

                    // 1. Intento principal por número
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

                    // 2. Respaldo por título exacto en inglés dentro de la temporada
                    if let Ok(s) = s_opt {
                        if !ep_title_en.is_empty() {
                            let season_url = format!(
                                "https://api.themoviedb.org/3/tv/{}/season/{}?language=en-US",
                                tv_id, s
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
                                                    if name.trim().eq_ignore_ascii_case(ep_title_en.trim()) {
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
                }
            }
        }
    }

    "".to_string()
}

#[tokio::main]
async fn main() {
    println!("==========================================");
    println!("EPG Rust optimizado con doble validación.");
    println!("==========================================");
}
