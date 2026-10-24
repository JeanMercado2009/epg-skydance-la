const axios = require('axios');
const tmdbCache = {};

async function fetchTmdbStill(seriesTitle, seasonStr, epStr) {
    if (!seriesTitle) return "";
    const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
    const cacheKey = `${cleanTitle}|${seasonStr}|${epStr}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const tmdbToken = process.env.TMDB_TOKEN || "";
    const tmdbApiKey = process.env.TMDB_API_KEY || "";
    if (!tmdbToken && !tmdbApiKey) return "";

    const headers = { "accept": "application/json" };
    if (tmdbToken) headers["Authorization"] = `Bearer ${tmdbToken}`;
    else if (tmdbApiKey) headers["Authorization"] = `Bearer ${tmdbApiKey}`;

    try {
        const searchRes = await axios.get("https://api.themoviedb.org/3/search/tv", {
            headers,
            params: { query: cleanTitle, language: "es-ES" },
            timeout: 5000
        });

        const results = searchRes.data.results;
        if (results && results.length > 0) {
            const tvId = results[0].id;
            const sNum = parseInt(seasonStr);
            const eNum = parseInt(epStr);

            if (!isNaN(sNum) && !isNaN(eNum)) {
                try {
                    const epRes = await axios.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}/episode/${eNum}`, {
                        headers,
                        params: { language: "es-ES" },
                        timeout: 5000
                    });
                    if (epRes.data.still_path) {
                        const imgUrl = `https://image.tmdb.org/t5/p/w500${epRes.data.still_path}`;
                        tmdbCache[cacheKey] = imgUrl;
                        return imgUrl;
                    }
                } catch (e) {}
            }

            if (results[0].poster_path) {
                const imgUrl = `https://image.tmdb.org/t5/p/w500${results[0].poster_path}`;
                tmdbCache[cacheKey] = imgUrl;
                return imgUrl;
            }
        }
    } catch (e) {}

    tmdbCache[cacheKey] = "";
    return "";
}
