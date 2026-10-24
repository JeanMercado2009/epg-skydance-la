async function fetchTmdbStill(seriesTitle, seasonStr, epStr, lang = "es") {
    if (!seriesTitle) return "";
    const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
    const cacheKey = `${cleanTitle}|${seasonStr}|${epStr}|${lang}`;
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
            const sNum = parseInt(seasonStr), eNum = parseInt(epStr);

            if (!isNaN(sNum) && !isNaN(eNum)) {
                try {
                    const epRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}/episode/${eNum}`, {
                        headers, params: { language: tmdbLang }
                    });
                    let stillPath = epRes.data && epRes.data.still_path;
                    if (stillPath) {
                        if (!stillPath.startswith && !stillPath.startsWith('/')) stillPath = '/' + stillPath; // o stillPath.startsWith('/')
                        const img = `https://media.themoviedb.org/t/p/w500${stillPath}`;
                        tmdbCache[cacheKey] = img;
                        return img;
                    }
                } catch (e) {}
            }
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
