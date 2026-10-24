package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

var tmdbCache = make(map[string]string)

type TMDBResponse struct {
	Results []struct {
		ID         int    `json:"id"`
		PosterPath string `json:"poster_path"`
	} `json:"results"`
}

type TMDBEpisode struct {
	StillPath string `json:"still_path"`
}

func FetchTmdbStill(seriesTitle, seasonStr, epStr string) string {
	if seriesTitle == "" {
		return ""
	}
	cleanTitle := strings.Split(seriesTitle, ":")[0]
	cleanTitle = strings.Split(cleanTitle, "-")[0]
	cleanTitle = strings.TrimSpace(cleanTitle)

	cacheKey := fmt.Sprintf("%s|%s|%s", cleanTitle, seasonStr, epStr)
	if val, ok := tmdbCache[cacheKey]; ok {
		return val
	}

	token := strings.TrimSpace(os.Getenv("TMDB_TOKEN"))
	apiKey := strings.TrimSpace(os.Getenv("TMDB_API_KEY"))
	if token == "" && apiKey == "" {
		return ""
	}

	client := &http.Client{Timeout: 5 * time.Second}
	apiURL := fmt.Sprintf("https://api.themoviedb.org/3/search/tv?query=%s&language=es-ES", url.QueryEscape(cleanTitle))

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

	resp, err := client.Do(req)
	if err != nil || resp.StatusCode != 200 {
		return ""
	}
	defer resp.Body.Close()

	var searchRes TMDBResponse
	if json.NewDecoder(resp.Body).Decode(&searchRes) != nil || len(searchRes.Results) == 0 {
		return ""
	}

	tvID := searchRes.Results[0].ID

	// Intentar obtener imagen de episodio específico si hay números de temporada/episodio
	if seasonStr != "" && epStr != "" {
		epURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d/season/%s/episode/%s?language=es-ES", tvID, seasonStr, epStr)
		epReq, err := http.NewRequest("GET", epURL, nil)
		if err == nil {
			if token != "" {
				epReq.Header.Set("Authorization", "Bearer "+token)
			}
			epResp, err := client.Do(epReq)
			if err == nil && epResp.StatusCode == 200 {
				var epData TMDBEpisode
				if json.NewDecoder(epResp.Body).Decode(&epData) == nil && epData.StillPath != "" {
					imgURL := "https://image.tmdb.org/t5/p/w500" + epData.StillPath
					tmdbCache[cacheKey] = imgURL
					return imgURL
				}
			}
		}
	}

	// Respaldo con póster general
	if searchRes.Results[0].PosterPath != "" {
		imgURL := "https://image.tmdb.org/t5/p/w500" + searchRes.Results[0].PosterPath
		tmdbCache[cacheKey] = imgURL
		return imgURL
	}

	tmdbCache[cacheKey] = ""
	return ""
}
