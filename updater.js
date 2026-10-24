const axios = require('axios');
const fs = require('fs');
const xlsx = require('xlsx');

const AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token";
const BASE_DAILY_URL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId={feed_id}&format=xls";

const TAPKIT_EMAIL = process.env.TAPKIT_EMAIL || "";
const TAPKIT_PASSWORD = process.env.TAPKIT_PASSWORD || "";

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
                    if (epRes.data && epRes.data.still_path) {
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

async function loginAndGetToken() {
    if (!TAPKIT_EMAIL || !TAPKIT_PASSWORD) {
        throw new Error("Faltan TAPKIT_EMAIL o TAPKIT_PASSWORD en los Secrets de GitHub.");
    }

    const params = new URLSearchParams();
    params.append("grant_type", "password");
    params.append("scope", "any");
    params.append("username", TAPKIT_EMAIL);
    params.append("password", TAPKIT_PASSWORD);

    const res = await axios.post(AUTH_URL, params, {
        headers: {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    });

    return res.data.access_token;
}

async function main() {
    try {
        const token = await loginAndGetToken();
        console.log("[OK] Sesión iniciada en Node.js");
    } catch (err) {
        console.error("[ERROR]", err.message);
    }
}

main();
