package main

import (
	"embed"

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"
	"github.com/wailsapp/wails/v2/pkg/options/windows"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	app := NewApp()

	err := wails.Run(&options.App{
		Title:            "Movie Maker",
		Width:            1280,
		Height:           840,
		MinWidth:         960,
		MinHeight:        640,
		BackgroundColour: &options.RGBA{R: 0, G: 0, B: 0, A: 1},
		AssetServer:      &assetserver.Options{Assets: assets},
		OnStartup:        app.startup,
		OnShutdown:       app.shutdown,
		Bind:             []interface{}{app},
		Windows: &windows.Options{
			Theme: windows.Dark,
		},
	})
	if err != nil {
		println("Error:", err.Error())
	}
}
