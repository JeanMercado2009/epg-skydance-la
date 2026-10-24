package main

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

var tmdbCache = make(map[string]string)

// Cliente HTTP con conexiones persistentes optimizadas para velocidad
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
	cleanTitle := strings.TrimSpace(strings.Split(strings.Split(seriesTitle, ":")[0], "-")[0])
	cacheKey := fmt.Sprintf("%s|%s|%s", cleanTitle, seasonStr, epStr)
	if val, ok := tmdbCache[cacheKey]; ok {
		return val
	}

	token := strings.TrimSpace(os.Getenv("TMDB_TOKEN"))
	apiKey := strings.TrimSpace(os.Getenv("TMDB_API_KEY"))
	if token == "" && apiKey == "" {
		return ""
	}

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
	if seasonStr != "" && epStr != "" {
		epURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d/season/%s/episode/%s?language=es-ES", tvID, seasonStr, epStr)
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
					// Uso explícito de media.themoviedb.org
					imgURL := "https://media.themoviedb.org/t/p/w500" + stillPath
					tmdbCache[cacheKey] = imgURL
					return imgURL
				}
			}
		}
	}

	if searchRes.Results[0].PosterPath != "" {
		posterPath := searchRes.Results[0].PosterPath
		if !strings.HasPrefix(posterPath, "/") {
			posterPath = "/" + posterPath
		}
		imgURL := "https://media.themoviedb.org/t/p/w500" + posterPath
		tmdbCache[cacheKey] = imgURL
		return imgURL
	}

	tmdbCache[cacheKey] = ""
	return ""
}

func main() {
	fmt.Println("==========================================")
	fmt.Println("EPG Golang optimizado con TMDB (media.themoviedb.org)")
	fmt.Println("==========================================")
}
