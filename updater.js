const axios = require('axios');

const client = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
});

const tmdbCache = {};

const TITLE_ALIASES = {
    "equipo monstruo": "monster squad",
    "el malentendido": "the misunderstandings",
    "el origen parte 1": "the origins 1",
    "el origen parte 2": "the origins 2",
    "kabums pt 2": "kabooms 2",
    "kabums pt 1": "kabooms 1",
    "standards & practices": "s&p",
    "arcoiris de la dimension de cristal": "crystals have power",
    "el cruce": "crossover",
    "la panza de la bestia": "belly of the beast"
};

function normalizeTitle(text) {
    if (!text) return "";
    let cleanRaw = text.toLowerCase().trim();
    if (TITLE_ALIASES[cleanRaw]) {
        cleanRaw = TITLE_ALIASES[cleanRaw];
    }
    const noParen = cleanRaw.replace(/\(.*?\)/g, "");
    const noAccent = noParen.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    let clean = noAccent.trim();
    clean = clean.replace(/\b(?:pt\.?|part\.?)\s*(\d+)/g, "($1)");
    clean = clean.replace(/s\b/g, "");
    clean = clean.replace(/[^a-z0-9&]/g, "");
    return clean;
}

async function fetchTmdbStill(seriesTitle, seasonStr, epStr, epTitleEn = "", lang = "es") {
    if (!seriesTitle) return "";
    const lookupTarget = epTitleEn ? epTitleEn : seriesTitle;
    const cacheKey = `${seriesTitle}|${seasonStr}|${epStr}|${lookupTarget}|${lang}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const lowerTitle = seriesTitle.toLowerCase();
    if (lowerTitle.includes("submarine jim") || lowerTitle.includes("el submarino de jim")) {
        return "https://media.themoviedb.org/t/p/w220_and_h330_face/cHN9UE0cjsDByMWk0FgaPEkHNeJ.jpg";
    }
    if (lowerTitle.includes("aquaman: rage of atlantis") || lowerTitle.includes("lego dc")) {
        return "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg";
    }
    if (lowerTitle.includes("spider-man") && lowerTitle.includes("un nuevo universo")) {
        return "https://media.themoviedb.org/t/p/w220_and_h330_face/iiZZdoQBEYBv6id8su7ImL0oCbD.jpg";
    }

    const token = process.env.TMDB_TOKEN || "";
    const apiKey = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const tmdbLang = (lang === "pt") ? "pt-BR" : "es-ES";
    const headers = { "accept": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    else if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    try {
        const searchRes = await client.get("https://api.themoviedb.org/3/search/tv", {
            headers, params: { query: seriesTitle, language: tmdbLang }
        });
        const results = searchRes.data.results;
        if (results && results.length > 0) {
            const tvId = results[0].id;
            const seasonRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${seasonStr || 1}`, {
                headers, params: { language: "en-US" }
            });
            const episodes = seasonRes.data.episodes || [];
            const normTarget = normalizeTitle(lookupTarget);
            for (const ep of episodes) {
                if (ep.name && normalizeTitle(ep.name) === normTarget) {
                    if (ep.still_path) {
                        const img = `https://media.themoviedb.org/t/p/w500${ep.still_path}`;
                        tmdbCache[cacheKey] = img;
                        return img;
                    }
                }
            }
        }
    } catch (e) {}

    tmdbCache[cacheKey] = "";
    return "";
}
