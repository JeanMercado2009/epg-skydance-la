package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
	"unicode"

	"golang.org/x/text/transform"
	"golang.org/x/text/unicode/norm"
)

var tmdbCache = make(map[string]string)

var titleAliases = map[string]string{
	"equipo monstruo":       "monster squad",
	"el malentendido":      "the misunderstandings",
	"el origen parte 1":    "the origins 1",
	"el origen parte 2":    "the origins 2",
	"kabums pt 2":          "kabooms 2",
	"kabums pt 1":          "kabooms 1",
	"standards & practices": "s&p",
	"arcoiris de la dimension de cristal": "crystals have power",
	"el cruce":             "crossover",
	"la panza de la bestia": "belly of the beast",
}

var httpClient = &http.Client{Timeout: 6 * time.Second}

func normalizeTitle(text string) string {
	if text == "" {
		return ""
	}
	cleanRaw := strings.ToLower(strings.TrimSpace(text))
	if alias, ok := titleAliases[cleanRaw]; ok {
		cleanRaw = alias
	}

	reParen := regexp.MustCompile(`\(.*?\)`)
	cleanRaw = reParen.ReplaceAllString(cleanRaw, "")

	t := transform.Chain(norm.NFD, transform.RemoveFunc(func(r rune) bool {
		return unicode.Is(unicode.Mn, r)
	}), norm.NFC)
	noAccent, _, _ := transform.String(t, cleanRaw)
	clean := strings.TrimSpace(noAccent)

	rePart := regexp.MustCompile(`\b(?:pt\.?|part\.?)\s*(\d+)`)
	clean = rePart.ReplaceAllString(clean, "($1)")

	rePlural := regexp.MustCompile(`s\b`)
	clean = rePlural.ReplaceAllString(clean, "")

	reAlnum := regexp.MustCompile(`[^a-z0-9&]`)
	clean = reAlnum.ReplaceAllString(clean, "")
	return clean
}

func FetchTmdbStill(seriesTitle, seasonStr, epStr, epTitleEn, lang string) string {
	if seriesTitle == "" {
		return ""
	}
	lookupTarget := epTitleEn
	if lookupTarget == "" {
		lookupTarget = seriesTitle
	}

	cacheKey := fmt.Sprintf("%s|%s|%s|%s|%s", seriesTitle, seasonStr, epStr, lookupTarget, lang)
	if val, ok := tmdbCache[cacheKey]; ok {
		return val
	}

	lowerTitle := strings.ToLower(seriesTitle)
	if strings.Contains(lowerTitle, "submarine jim") || strings.Contains(lowerTitle, "el submarino de jim") {
		return "https://media.themoviedb.org/t/p/w220_and_h330_face/cHN9UE0cjsDByMWk0FgaPEkHNeJ.jpg"
	}
	if strings.Contains(lowerTitle, "aquaman: rage of atlantis") || strings.Contains(lowerTitle, "lego dc") {
		return "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg"
	}
	if strings.Contains(lowerTitle, "spider-man") && strings.Contains(lowerTitle, "un nuevo universo") {
		return "https://media.themoviedb.org/t/p/w220_and_h330_face/iiZZdoQBEYBv6id8su7ImL0oCbD.jpg"
	}

	token := strings.TrimSpace(os.Getenv("TMDB_TOKEN"))
	apiKey := strings.TrimSpace(os.Getenv("TMDB_API_KEY"))
	if token == "" && apiKey == "" {
		return ""
	}

	apiURL := fmt.Sprintf("https://api.themoviedb.org/3/search/tv?query=%s&language=es-ES", url.QueryEscape(seriesTitle))
	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("accept", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	} else {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := httpClient.Do(req)
	if err != nil || resp.StatusCode != 200 {
		return ""
	}
	defer resp.Body.Close()

	var searchRes struct {
		Results []struct {
			ID int `json:"id"`
		} `json:"results"`
	}
	json.NewDecoder(resp.Body).Decode(&searchRes)

	if len(searchRes.Results) > 0 {
		tvID := searchRes.Results[0].ID
		seasonURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d/season/%s?language=en-US", tvID, seasonStr)
		seasonReq, err := http.NewRequest("GET", seasonURL, nil)
		if err == nil {
			if token != "" {
				seasonReq.Header.Set("Authorization", "Bearer "+token)
			}
			seasonResp, err := httpClient.Do(seasonReq)
			if err == nil && seasonResp.StatusCode == 200 {
				defer seasonResp.Body.Close()
				var seasonData struct {
					Episodes []struct {
						Name      string `json:"name"`
						StillPath string `json:"still_path"`
					} `json:"episodes"`
				}
				json.NewDecoder(seasonResp.Body).Decode(&seasonData)
				normTarget := normalizeTitle(lookupTarget)
				for _, ep := range seasonData.Episodes {
					if normalizeTitle(ep.Name) == normTarget && ep.StillPath != "" {
						imgURL := "https://media.themoviedb.org/t/p/w500" + ep.StillPath
						tmdbCache[cacheKey] = imgURL
						return imgURL
					}
				}
			}
		}
	}

	tmdbCache[cacheKey] = ""
	return ""
}
