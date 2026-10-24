package main

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

var tmdbCache = make(map[string]string)

var httpClient = &http.Client{
	Timeout: 6 * time.Second,
	Transport: &http.Transport{
		DialContext: (&net.Dialer{
			Timeout:   3 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		IdleConnTimeout:     90 * time.Second,
	},
}

type TMDBResponse struct {
	Results []struct {
		ID int `json:"id"`
	} `json:"results"`
}

type TMDBEpisode struct {
	Name      string `json:"name"`
	StillPath string `json:"still_path"`
}

type TMDBSeasonResponse struct {
	Episodes []TMDBEpisode `json:"episodes"`
}

func FetchTmdbStill(seriesTitle, seasonStr, epStr, epTitleEn, lang string) string {
	if seriesTitle == "" {
		return ""
	}
	cleanTitle := strings.TrimSpace(strings.Split(strings.Split(seriesTitle, ":")[0], "-")[0])
	cacheKey := fmt.Sprintf("%s|%s|%s|%s|%s", cleanTitle, seasonStr, epStr, epTitleEn, lang)
	if val, ok := tmdbCache[cacheKey]; ok {
		return val
	}

	token := strings.TrimSpace(os.Getenv("TMDB_TOKEN"))
	apiKey := strings.TrimSpace(os.Getenv("TMDB_API_KEY"))
	if token == "" && apiKey == "" {
		return ""
	}

	tmdbLang := "es-ES"
	if lang == "pt" {
		tmdbLang = "pt-BR"
	}

	apiURL := fmt.Sprintf("https://api.themoviedb.org/3/search/tv?query=%s&language=%s", url.QueryEscape(cleanTitle), tmdbLang)
	req, err := http.NewRequest("GET", apiURL, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("accept", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	} else if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := httpClient.Do(req)
	if err != nil || resp.StatusCode != 200 {
		return ""
	}
	defer resp.Body.Close()

	var searchRes TMDBResponse
	if json.NewDecoder(resp.Body).Decode(&searchRes) != nil || len(searchRes.Results) == 0 {
		return ""
	}

	tvID := searchRes.Results[0].ID
	sNum, errS := strconv.Atoi(seasonStr)
	eNum, errE := strconv.Atoi(epStr)

	// 1. Intento principal por número
	if errS == nil && errE == nil {
		epURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d/season/%d/episode/%d?language=%s", tvID, sNum, eNum, tmdbLang)
		epReq, err := http.NewRequest("GET", epURL, nil)
		if err == nil {
			if token != "" {
				epReq.Header.Set("Authorization", "Bearer "+token)
			}
			epResp, err := httpClient.Do(epReq)
			if err == nil && epResp.StatusCode == 200 {
				var epData TMDBEpisode
				if json.NewDecoder(epResp.Body).Decode(&epData) == nil && epData.StillPath != "" {
					stillPath := epData.StillPath
					if !strings.HasPrefix(stillPath, "/") {
						stillPath = "/" + stillPath
					}
					imgURL := "https://media.themoviedb.org/t/p/w500" + stillPath
					tmdbCache[cacheKey] = imgURL
					return imgURL
				}
			}
		}
	}

	// 2. Respaldo por título exacto en inglés dentro de la temporada
	if errS == nil && epTitleEn != "" {
		seasonURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d/season/%d?language=en-US", tvID, sNum)
		seasonReq, err := http.NewRequest("GET", seasonURL, nil)
		if err == nil {
			if token != "" {
				seasonReq.Header.Set("Authorization", "Bearer "+token)
			}
			seasonResp, err := httpClient.Do(seasonReq)
			if err == nil && seasonResp.StatusCode == 200 {
				var seasonData TMDBSeasonResponse
				if json.NewDecoder(seasonResp.Body).Decode(&seasonData) == nil {
					for _, ep := range seasonData.Episodes {
						if strings.EqualFold(strings.TrimSpace(ep.Name), strings.TrimSpace(epTitleEn)) && ep.StillPath != "" {
							stillPath := ep.StillPath
							if !strings.HasPrefix(stillPath, "/") {
								stillPath = "/" + stillPath
							}
							imgURL := "https://media.themoviedb.org/t/p/w500" + stillPath
							tmdbCache[cacheKey] = imgURL
							return imgURL
						}
					}
				}
			}
		}
	}

	tmdbCache[cacheKey] = ""
	return ""
}

func main() {
	fmt.Println("==========================================")
	fmt.Println("EPG Golang optimizado con doble validación.")
	fmt.Println("==========================================")
}
