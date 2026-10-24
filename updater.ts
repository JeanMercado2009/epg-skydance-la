import axios from 'axios';

// Cliente HTTP con conexiones persistentes (Keep-Alive) y pooling
const client = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
});

const tmdbCache: Record<string, string> = {};

async function fetchTmdbStill(seriesTitle: string, seasonStr: string, epStr: string, lang: string = "es"): Promise<string> {
    if (!seriesTitle) return "";
    const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
    const cacheKey = `${cleanTitle}|${seasonStr}|${epStr}|${lang}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const token = process.env.TMDB_TOKEN || "";
    const apiKey = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    // Idioma dinámico: portugués para Brasil, español para el resto
    const tmdbLang = (lang === "pt") ? "pt-BR" : "es-ES";
    const headers: Record<string, string> = { "accept": "application/json" };
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

            // Respaldo de póster general si el capítulo no cuenta con miniatura propia
            let posterPath = results[0].poster_path;
            if (posterPath) {
                if (!posterPath.startsWith('/')) posterPath = '/' + posterPath;
                const img = `https://media.themoviedb.org/t/p/w500${posterPath}`;
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
    console.log("EPG TypeScript optimizado y listo.");
    console.log("==========================================");
}

main();
