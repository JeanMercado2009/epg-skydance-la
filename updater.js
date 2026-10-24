const axios = require('axios');
const fs = require('fs');
const xlsx = require('xlsx');
const xml2js = require('xml2js');

// -------------------------------------------------------------
// CONFIGURACIÓN GENERAL Y CANALES
// -------------------------------------------------------------
const RETENTION_DAYS_PAST = 5;
const RETENTION_DAYS_FUTURE = 15;

const AUTH_URL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token";
const BASE_DAILY_URL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId={feed_id}&format=xls";

const TAPKIT_EMAIL = process.env.TAPKIT_EMAIL || "";
const TAPKIT_PASSWORD = process.env.TAPKIT_PASSWORD || "";

const NETWORKS_CONFIG = {
    "CNLA_EPG.xml": {
        generator_name: "Guia de Programacion Cartoon Network MultiFeed",
        referer: "https://epg.tapkit.warnermedia.com/epg/networks/2",
        feeds: [
            { feed_id: "CNLA_PAN", channel_id: "CNLA_PAN.co", channel_name: "Cartoon Network Panregional", lang: "es", tz_str: "-0500" },
            { feed_id: "CNLA_BR", channel_id: "CNLA_BR.br", channel_name: "Cartoon Network Brasil", lang: "pt", tz_str: "-0300" }
        ]
    }
};

const COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es",
    "Origin": "https://epg.tapkit.warnermedia.com",
    "Referer": "https://epg.tapkit.warnermedia.com/login"
};

async function loginAndGetToken() {
    if (!TAPKIT_EMAIL || !TAPKIT_PASSWORD) {
        throw new Error("Faltan TAPKIT_EMAIL o TAPKIT_PASSWORD en los Secrets de GitHub.");
    }

    const params = new URLSearchParams();
    params.append("grant_type", "password");
    params.append("scope", "any");
    params.append("username", TAPKIT_EMAIL);
    params.append("password", TAPKIT_PASSWORD);

    const res = await axios.post(AUTH_URL, params, { headers: COMMON_HEADERS });
    const token = res.data.access_token;
    if (!token) {
        throw new Error("No se encontró 'access_token' en la respuesta.");
    }

    console.log("[OK] Sesión iniciada y token obtenido en Node.js.");
    return token;
}

async function downloadFeedXls(token, feedId, refererUrl) {
    const url = BASE_DAILY_URL.replace("{feed_id}", feedId);
    const res = await axios.get(url, {
        headers: {
            ...COMMON_HEADERS,
            "Authorization": `Bearer ${token}`,
            "Referer": refererUrl
        },
        responseType: 'arraybuffer'
    });

    const filename = `${feedId}_latest.xls`;
    fs.writeFileSync(filename, res.data);
    console.log(`[OK] XLS descargado exitosamente para ${feedId}.`);
    return filename;
}

async function main() {
    try {
        const token = await loginAndGetToken();

        for (const [xmlFilename, netConfig] of Object.entries(NETWORKS_CONFIG)) {
            console.log(`\n==========================================`);
            console.log(`Procesando: ${xmlFilename} con Node.js`);
            console.log(`==========================================`);

            for (const feedCfg of netConfig.feeds) {
                try {
                    const xlsPath = await downloadFeedXls(token, feedCfg.feed_id, netConfig.referer);
                    
                    // Leer el archivo Excel descargado
                    const workbook = xlsx.readFile(xlsPath);
                    const sheetName = workbook.SheetNames[0];
                    const sheetData = xlsx.utils.sheet_to_json(workbook.Sheets[sheetName]);

                    console.log(`[${feedCfg.channel_id}] Filas leídas del Excel: ${sheetData.length}`);
                    
                    // Aquí procesarías los datos y construirías el XMLTV usando xml2js o estructuras directas
                } catch (err) {
                    console.error(`[ERROR] Falló el feed ${feedCfg.feed_id}:`, err.message);
                }
            }
        }
    } catch (error) {
        console.error("[ERROR CRÍTICO]:", error.message);
        process.exit(1);
    }
}

main();
