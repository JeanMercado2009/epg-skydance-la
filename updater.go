package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

// -------------------------------------------------------------
// CONFIGURACIÓN GENERAL Y CANALES
// -------------------------------------------------------------
const AuthURL = "https://epg.tapkit.warnermedia.com/api/security/oauth/token"
const BaseDailyURL = "https://epg.tapkit.warnermedia.com/api/daily/shows?feedId=%s&format=xls"

type TokenResponse struct {
	AccessToken string `json:"access_token"`
}

func LoginAndGetToken() (string, error) {
	email := strings.TrimSpace(os.Getenv("TAPKIT_EMAIL"))
	password := strings.TrimSpace(os.Getenv("TAPKIT_PASSWORD"))

	if email == "" || password == "" {
		return "", fmt.Errorf("faltan TAPKIT_EMAIL o TAPKIT_PASSWORD en los Secrets de GitHub")
	}

	data := url.Values{}
	data.Set("grant_type", "password")
	data.Set("scope", "any")
	data.Set("username", email)
	data.Set("password", password)

	req, err := http.NewRequest("POST", AuthURL, strings.NewReader(data.Encode()))
	if err != nil {
		return "", err
	}

	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Origin", "https://epg.tapkit.warnermedia.com")
	req.Header.Set("Referer", "https://epg.tapkit.warnermedia.com/login")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("error en login HTTP %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var tokenResp TokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return "", err
	}

	if tokenResp.AccessToken == "" {
		return "", fmt.Errorf("no se encontró access_token en la respuesta")
	}

	fmt.Println("[OK] Sesión iniciada y token obtenido exitosamente en Go.")
	return tokenResp.AccessToken, nil
}

func main() {
	fmt.Println("==========================================")
	fmt.Println("Iniciando EPG Updater en Golang (Go)")
	fmt.Println("==========================================")

	token, err := LoginAndGetToken()
	if err != nil {
		log.Fatalf("[ERROR CRÍTICO] %v", err)
	}

	// Aquí puedes continuar con la lógica de descarga de feeds XLS y procesamiento XML
	fmt.Printf("[OK] Token listo para usar: %s...\n", token[:15])
}
