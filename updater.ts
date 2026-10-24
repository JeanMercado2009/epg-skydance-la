import axios, { AxiosInstance } from 'axios';

const client: AxiosInstance = axios.create({
    timeout: 15000,
    headers: { 
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
        "Accept": "application/json, text/plain, */*" 
    }
});

const tmdbCache: Record<string, string> = {};

const TITLE_ALIASES: Record<string, string> = {
    "equipo monstruo": "monster squad",
    "el malentendido": "the misunderstandings",
    "el origen parte 1": "the origins 1",
    "el origen parte 2": "the origins 2",
    "kabums pt 2": "kabooms (2)",
    "kabúms pt 2": "kabooms (2)",
    "kabums pt 1": "kabooms (1)",
    "kabúms pt 1": "kabooms (1)",
    "standards & practices": "s&p",
    "arcoiris de la dimension de cristal": "crystals have power",
    "el cruce": "crossover",
    "la panza de la bestia": "belly of the beast"
};

function getTargetDatesToProcess(): string[] {
    const now = new Date();
    const weekday = now.getDay(); // 0: Dom, 1: Lun, ..., 5: Vie, 6: Sáb
    const formatDate = (d: Date) => d.toISOString().split('T')[0];
    
    const dates = [formatDate(now)];
    if (weekday === 5) { // Viernes -> Viernes y Sábado
        const sat = new Date(now); sat.setDate(now.getDate() + 1);
        dates.push(formatDate(sat));
    } else if (weekday === 6) { // Sábado -> Sábado, Domingo, Lunes
        const sun = new Date(now); sun.setDate(now.getDate() + 1);
        const mon = new Date(now); mon.setDate(now.getDate() + 2);
        dates.push(formatDate(sun), formatDate(mon));
    }
    return Array.from(new Set(dates));
}

function normalizeTitle(text: string): string {
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

async function fetchTmdbStill(seriesTitle: string, seasonStr: string, epStr: string, epTitleEn: string = "", epTitleEs: string = "", lang: string = "es"): Promise<string> {
    if (!seriesTitle) return "";
    const rawTarget = (epTitleEn && epTitleEn.toLowerCase() !== "nan") ? epTitleEn : epTitleEs;
    const lookupTarget = TITLE_ALIASES[rawTarget.toLowerCase().trim()] || rawTarget;
    
    const cacheKey: string = `${seriesTitle}|${seasonStr}|${epStr}|${lookupTarget}|${lang}`;
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

    const token: string = process.env.TMDB_TOKEN || "";
    const apiKey: string = process.env.TMDB_API_KEY || "";
    if (!token && !apiKey) return "";

    const tmdbLang: string = (lang === "pt") ? "pt-BR" : "es-ES";
    const headers: Record<string, string> = { "accept": "application/json" };
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
                if (ep.name && (normalizeTitle(ep.name) === normTarget || normTarget.includes(normalizeTitle(ep.name)))) {
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
