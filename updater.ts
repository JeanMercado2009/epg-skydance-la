import axios, { AxiosInstance } from 'axios';

const client: AxiosInstance = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
});

const tmdbCache: Record<string, string> = {};

function normalizeTitle(text: string): string {
    if (!text) return "";
    const noAccent = text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    let clean = noAccent.toLowerCase().trim();
    clean = clean.replace(/\bpt\.?\s*(\d+)/g, "($1)");
    clean = clean.replace(/\bpart\.?\s*(\d+)/g, "($1)");
    clean = clean.replace(/s\b/g, ""); // Plural tolerance
    clean = clean.replace(/[^a-z0-9]/g, "");
    return clean;
}

async function fetchTmdbStill(seriesTitle: string, seasonStr: string, epStr: string, epTitleEn: string = "", lang: string = "es"): Promise<string> {
    if (!seriesTitle) return "";
    const cacheKey: string = `${seriesTitle}|${seasonStr}|${epStr}|${epTitleEn}|${lang}`;
    if (tmdbCache[cacheKey] !== undefined) return tmdbCache[cacheKey];

    const lowerTitle = seriesTitle.toLowerCase();
    if (lowerTitle.includes("submarine jim") || lowerTitle.includes("el submarino de jim")) {
        const img = "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg";
        tmdbCache[cacheKey] = img;
        return img;
    }
    if (lowerTitle.includes("aquaman: rage of atlantis") || lowerTitle.includes("lego dc")) {
        const img = "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg";
        tmdbCache[cacheKey] = img;
        return img;
    }
    if (lowerTitle.includes("spider-man") && lowerTitle.includes("un nuevo universo")) {
        const img = "https://media.themoviedb.org/t/p/w220_and_h330_face/iiZZdoQBEYBv6id8su7ImL0oCbD.jpg";
        tmdbCache[cacheKey] = img;
        return img;
    }

    const token: string = process.env.TMDB_TOKEN || "";
    const apiKey: string = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const tmdbLang: string = (lang === "pt") ? "pt-BR" : "es-ES";
    const headers: Record<string, string> = { "accept": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    else if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    try {
        const searchQueries: string[] = [seriesTitle];
        const cleanTitle = seriesTitle.replace(/[:\-].*/g, '').trim();
        if (cleanTitle && cleanTitle.toLowerCase() !== seriesTitle.toLowerCase()) {
            searchQueries.push(cleanTitle);
        }

        let tvId: number | null = null;
        let numberOfSeasons: number = 10;

        for (const query of searchQueries) {
            const searchRes = await client.get("https://api.themoviedb.org/3/search/tv", {
                headers, params: { query, language: tmdbLang }
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
            const sNum: number = parseInt(seasonStr, 10);
            const normTarget = epTitleEn ? normalizeTitle(epTitleEn) : "";

            if (normTarget) {
                const seasonsToCheck: number[] = [];
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
            }

            const eNum: number = parseInt(epStr, 10);
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
