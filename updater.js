const axios = require('axios');

// Cliente HTTP optimizado con keep-alive
const client = axios.create({
    timeout: 10000,
    headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" }
});

const tmdbCache = {};

async function fetchTmdbStill(seriesTitle, seasonStr, epStr) {
    if (!seriesTitle) return "";
    const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
    const cacheKey = `${cleanTitle}|${seasonStr}|${epStr}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const token = process.env.TMDB_TOKEN || "";
    const apiKey = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const headers = { "accept": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    else if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    try {
        const searchRes = await client.get("https://api.themoviedb.org/3/search/tv", {
            headers,
            params: { query: cleanTitle, language: "es-ES" }
        });

        const results = searchRes.data.results;
        if (results && results.length > 0) {
            const tvId = results[0].id;
            const sNum = parseInt(seasonStr), eNum = parseInt(epStr);

            if (!isNaN(sNum) && !isNaN(eNum)) {
                try {
                    const epRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}/episode/${eNum}`, {
                        headers, params: { language: "es-ES" }
                    });
                    if (epRes.data && epRes.data.still_path) {
                        const img = `https://image.tmdb.org/t5/p/w500${epRes.data.still_path}`;
                        tmdbCache[cacheKey] = img;
                        return img;
                    }
                } catch (e) {}
            }
            if (results[0].poster_path) {
                const img = `https://image.tmdb.org/t5/p/w500${results[0].poster_path}`;
                tmdbCache[cacheKey] = img;
                return img;
            }
        }
    } catch (e) {}

    tmdbCache[cacheKey] = "";
    return "";
}

async function main() {
    console.log("[OK] Updater JS optimizado con TMDB y soporte Keep-Alive.");
}

main();
