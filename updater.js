const axios = require('axios');

const client = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
});

const tmdbCache = {};

function normalizeTitle(text) {
    if (!text) return "";
    const noAccent = text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    let clean = noAccent.toLowerCase().trim();
    clean = clean.replace(/\bpt\.?\s*(\d+)/g, "($1)");
    clean = clean.replace(/\bpart\.?\s*(\d+)/g, "($1)");
    clean = clean.replace(/[^a-z0-9]/g, "");
    return clean;
}

async function fetchTmdbStill(seriesTitle, seasonStr, epStr, epTitleEn = "", lang = "es") {
    if (!seriesTitle) return "";
    const cacheKey = `${seriesTitle}|${seasonStr}|${epStr}|${epTitleEn}|${lang}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const token = process.env.TMDB_TOKEN || "";
    const apiKey = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const tmdbLang = (lang === "pt") ? "pt-BR" : "es-ES";
    const headers = { "accept": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    else if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    try {
        const searchQueries = [seriesTitle];
        const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
        if (cleanTitle && cleanTitle.toLowerCase() !== seriesTitle.toLowerCase()) {
            searchQueries.push(cleanTitle);
        }

        let tvId = null;
        let numberOfSeasons = 10;

        for (const query of searchQueries) {
            const searchRes = await client.get("https://api.themoviedb.org/3/search/tv", {
                headers,
                params: { query, language: tmdbLang }
            });
            const results = searchRes.data.results;
            if (results && results.length > 0) {
                tvId = results[0].id;
                try {
                    const detailRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}`, { headers });
                    if (detailRes.data && detailRes.data.number_of_seasons) {
                        numberOfSeasons = detailRes.data.number_of_seasons;
                    }
                } catch (e) {}
                break;
            }
        }

        if (tvId) {
            const sNum = parseInt(seasonStr, 10);
            const normTarget = epTitleEn ? normalizeTitle(epTitleEn) : "";

            // Prioridad 1: Barrido global por título en inglés normalizado
            if (normTarget) {
                const seasonsToCheck = [];
                if (!isNaN(sNum)) seasonsToCheck.push(sNum);
                for (let s = 1; s <= numberOfSeasons; s++) {
                    if (!seasonsToCheck.includes(s)) seasonsToCheck.push(s);
                }
                if (!seasonsToCheck.includes(0)) seasonsToCheck.push(0);

                for (const sCheck of seasonsToCheck) {
                    try {
                        const seasonRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sCheck}`, {
                            headers, params: { language: "en-US" }
                        });
                        const episodes = seasonRes.data.episodes || [];
                        for (const ep of episodes) {
                            if (ep.name && normalizeTitle(ep.name) === normTarget) {
                                let stillPath = ep.still_path;
                                if (stillPath) {
                                    if (!stillPath.startsWith('/')) stillPath = '/' + stillPath;
                                    const img = `https://media.themoviedb.org/t/p/w500${stillPath}`;
                                    tmdbCache[cacheKey] = img;
                                    return img;
                                }
                            }
                        }
                    } catch (e) {}
                }
            }

            // Prioridad 2: Respaldo por número de episodio
            const eNum = parseInt(epStr, 10);
            if (!isNaN(sNum) && !isNaN(eNum)) {
                try {
                    const epRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}/episode/${eNum}`, {
                        headers, params: { language: tmdbLang }
                    });
                    let stillPath = epRes.data && epRes.data.still_path;
                    if (stillPath) {
                        if (!stillPath.startsWith('/')) stillPath = '/' + stillPath;
                        const img = `https://media.themoviedb.org/t/p/w500${stillPath}`;
                        tmdbCache[cacheKey] = img;
                        return img;
                    }
                } catch (e) {}
            }
        }
    } catch (e) {}

    tmdbCache[cacheKey] = "";
    return "";
}

async function main() {
    console.log("updater.js sincronizado.");
}
main();