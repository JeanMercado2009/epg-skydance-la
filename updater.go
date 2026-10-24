package main

import (
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"

	"golang.org/x/text/transform"
	"golang.org/x/text/unicode/norm"
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

type TMDBDetailResponse struct {
	NumberOfSeasons int `json:"number_of_seasons"`
}

type TMDBEpisode struct {
	Name      string `json:"name"`
	StillPath string `json:"still_path"`
}

type TMDBSeasonResponse struct {
	Episodes []TMDBEpisode `json:"episodes"`
}

func normalizeTitle(text string) string {
	if text == "" {
		return ""
	}
	t := transform.Chain(norm.NFD, transform.RemoveFunc(func(r rune) bool {
		return unicode.Is(unicode.Mn, r)
	}), norm.NFC)
	noAccent, _, _ := transform.String(t, text)
	clean := strings.ToLower(strings.TrimSpace(noAccent))

	rePt := regexp.MustCompile(`\bpt\.?\s*(\d+)`)
	clean = rePt.ReplaceAllString(clean, "($1)")
	rePart := regexp.MustCompile(`\bpart\.?\s*(\d+)`)
	clean = rePart.ReplaceAllString(clean, "($1)")
	
	rePlural := regexp.MustCompile(`s\b`)
	clean = rePlural.ReplaceAllString(clean, "")

	reAlnum := regexp.MustCompile(`[^a-z0-9]`)
	clean = reAlnum.ReplaceAllString(clean, "")
	return clean
}

func FetchTmdbStill(seriesTitle, seasonStr, epStr, epTitleEn, lang string) string {
	if seriesTitle == "" {
		return ""
	}
	cacheKey := fmt.Sprintf("%s|%s|%s|%s|%s", seriesTitle, seasonStr, epStr, epTitleEn, lang)
	if val, ok := tmdbCache[cacheKey]; ok {
		return val
	}

	lowerTitle := strings.ToLower(seriesTitle)
	if strings.Contains(lowerTitle, "submarine jim") || strings.Contains(lowerTitle, "el submarino de jim") {
		img := "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg"
		tmdbCache[cacheKey] = img
		return img
	}
	if strings.Contains(lowerTitle, "aquaman: rage of atlantis") || strings.Contains(lowerTitle, "lego dc") {
		img := "https://media.themoviedb.org/t/p/w220_and_h330_face/8BqoJXMhrV9KfKmodPtyi67VgBG.jpg"
		tmdbCache[cacheKey] = img
		return img
	}
	if strings.Contains(lowerTitle, "spider-man") && strings.Contains(lowerTitle, "un nuevo universo") {
		img := "https://media.themoviedb.org/t/p/w220_and_h330_face/iiZZdoQBEYBv6id8su7ImL0oCbD.jpg"
		tmdbCache[cacheKey] = img
		return img
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

	searchQueries := []string{seriesTitle}
	reDashColon := regexp.MustCompile(`[:\-].*`)
	cleanTitle := strings.TrimSpace(reDashColon.ReplaceAllString(seriesTitle, ""))
	if cleanTitle != "" && !strings.EqualFold(cleanTitle, seriesTitle) {
		searchQueries = append(searchQueries, cleanTitle)
	}

	var tvID int = 0
	numberOfSeasons := 10

	for _, q := range searchQueries {
		apiURL := fmt.Sprintf("https://api.themoviedb.org/3/search/tv?query=%s&language=%s", url.QueryEscape(q), tmdbLang)
		req, err := http.NewRequest("GET", apiURL, nil)
		if err != nil {
			continue
		}
		req.Header.Set("accept", "application/json")
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		} else if apiKey != "" {
			req.Header.Set("Authorization", "Bearer "+apiKey)
		}

		resp, err := httpClient.Do(req)
		if err != nil || resp.StatusCode != 200 {
			if resp != nil {
				resp.Body.Close()
			}
			continue
		}

		var searchRes TMDBResponse
		json.NewDecoder(resp.Body).Decode(&searchRes)
		resp.Body.Close()

		if len(searchRes.Results) > 0 {
			tvID = searchRes.Results[0].ID
			detailURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d", tvID)
			detailReq, err := http.NewRequest("GET", detailURL, nil)
			if err == nil {
				if token != "" {
					detailReq.Header.Set("Authorization", "Bearer "+token)
				}
				detailResp, err := httpClient.Do(detailReq)
				if err == nil && detailResp.StatusCode == 200 {
					var detailData TMDBDetailResponse
					json.NewDecoder(detailResp.Body).Decode(&detailData)
					if detailData.NumberOfSeasons > 0 {
						numberOfSeasons = detailData.NumberOfSeasons
					}
					detailResp.Body.Close()
				}
			}
			break
		}
	}

	if tvID != 0 {
		sNum, errS := strconv.Atoi(seasonStr)
		normTarget := normalizeTitle(epTitleEn)

		if normTarget != "" {
			var seasonsToCheck []int
			if errS == nil {
				seasonsToCheck = append(seasonsToCheck, sNum)
			}
			for s := 1; s <= numberOfSeasons; s++ {
				found := false
				for _, existing := range seasonsToCheck {
					if existing == s {
						found = true
						break
					}
				}
				if !found {
					seasonsToCheck = append(seasonsToCheck, s)
				}
			}
			seasonsToCheck = append(seasonsToCheck, 0)

			for _, sCheck := range seasonsToCheck {
				seasonURL := fmt.Sprintf("https://api.themoviedb.org/3/tv/%d/season/%d?language=en-US", tvID, sCheck)
				seasonReq, err := http.NewRequest("GET", seasonURL, nil)
				if err != nil {
					continue
				}
				if token != "" {
					seasonReq.Header.Set("Authorization", "Bearer "+token)
				}
				seasonResp, err := httpClient.Do(seasonReq)
				if err == nil && seasonResp.StatusCode == 200 {
					var seasonData TMDBSeasonResponse
					json.NewDecoder(seasonResp.Body).Decode(&seasonData)
					seasonResp.Body.Close()

					for _, ep := range seasonData.Episodes {
						if normalizeTitle(ep.Name) == normTarget && ep.StillPath != "" {
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
