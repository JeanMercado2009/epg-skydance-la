async function fetchTmdbStill(seriesTitle: string, seasonStr: string, epStr: string, epTitleEn: string = "", lang: string = "es"): Promise<string> {
    if (!seriesTitle) return "";
    const cleanTitle: string = seriesTitle.replace(/[:\-].*/g, '').trim();
    const cacheKey: string = `${cleanTitle}|${seasonStr}|${epStr}|${epTitleEn}|${lang}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const token: string = process.env.TMDB_TOKEN || "";
    const apiKey: string = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const tmdbLang: string = (lang === "pt") ? "pt-BR" : "es-ES";
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
            const tvId: number = results[0].id;
            const sNum: number = parseInt(seasonStr, 10);
            const eNum: number = parseInt(epStr, 10);

            // Prioridad 1: Búsqueda directa por título exacto en inglés escaneando la temporada
            if (!isNaN(sNum) && epTitleEn) {
                try {
                    const seasonRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}`, {
                        headers, params: { language: "en-US" }
                    });
                    const episodes = seasonRes.data.episodes || [];
                    for (const ep of episodes) {
                        if (ep.name && ep.name.trim().toLowerCase() === epTitleEn.trim().toLowerCase()) {
                            let stillPath: string | undefined = ep.still_path;
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

            // Prioridad 2: Respaldo por número de episodio
            if (!isNaN(sNum) && !isNaN(eNum)) {
                try {
                    const epRes = await client.get(`https://api.themoviedb.org/3/tv/${tvId}/season/${sNum}/episode/${eNum}`, {
                        headers, params: { language: tmdbLang }
                    });
                    let stillPath: string | undefined = epRes.data && epRes.data.still_path;
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
