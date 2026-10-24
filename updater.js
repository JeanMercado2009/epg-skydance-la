const axios = require('axios');
const fs = require('fs');
const xml2js = require('xml2js');

// Cliente HTTP con conexiones persistentes optimizadas para velocidad
const client = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
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
                    let stillPath = epRes.data && epRes.data.still_path;
                    if (stillPath) {
                        // Asegurar slash inicial correcto
                        if (!stillPath.startsWith('/')) stillPath = '/' + stillPath;
                        const img = `https://image.tmdb.org/t5/p/w500${stillPath}`;
                        tmdbCache[cacheKey] = img;
                        return img;
                    }
                } catch (e) {}
            }
            let posterPath = results[0].poster_path;
            if (posterPath) {
                if (!posterPath.startsWith('/')) posterPath = '/' + posterPath;
                const img = `https://image.tmdb.org/t5/p/w500${posterPath}`;
                tmdbCache[cacheKey] = img;
                return img;
            }
        }
    } catch (e) {}

    tmdbCache[cacheKey] = "";
    return "";
}

async function main() {
    console.log("==========================================");
    console.log("EPG Node.js optimizado con TMDB y Localbreaks listo.");
    console.log("==========================================");
}

main();
