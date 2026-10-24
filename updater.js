const axios = require('axios');

const client = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
});

const tmdbCache = {};

async function fetchTmdbStill(seriesTitle, seasonStr, epStr, epTitleEn = "", lang = "es") {
    if (!seriesTitle) return "";
    const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
    const cacheKey = `${cleanTitle}|${seasonStr}|${epStr}|${epTitleEn}|${lang}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const token = process.env.TMDB_TOKEN || "";
    const apiKey = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const tmdbLang = (lang === "pt") ? "pt-BR" : "es-ES";
    const headers = { "accept": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    else if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    try {
        const searchRes = await client.get("https://api.themoviedb.org/3/search/tv", {
            headers,
            params: { query: cleanTitle, language: tmdbLang }
        });

        const results = searchRes.data.results;
        if (results && results.length > 0) {
            const tvId = results[0].id;
            const sNum = parseInt(seasonStr, 10);
            const eNum = parseInt(epStr, 10);

            // 1. Intento principal por número
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

            // 2. Respaldo por título exacto en inglés dentro de la temporada
            if (!isNaN(sNum) && epTitleEn) {
                try {
                    const seasonRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}`, {
                        headers, params: { language: "en-US" }
                    });
                    const episodes = seasonRes.data.episodes || [];
                    for (const ep of episodes) {
                        if (ep.name && ep.name.trim().toLowerCase() === epTitleEn.trim().toLowerCase()) {
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
    } catch (e) {}

    tmdbCache[cacheKey] = "";
    return "";
}

async function main() {
    console.log("==========================================");
    console.log("updater.js optimizado con doble validación.");
    console.log("==========================================");
}

main();
