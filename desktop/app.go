package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// Backend 는 프런트엔드가 Python 서버에 접속할 때 필요한 정보
type Backend struct {
	URL   string `json:"url"`
	Token string `json:"token"`
	Root  string `json:"root"`
	Error string `json:"error"`
}

type App struct {
	ctx     context.Context
	mu      sync.Mutex
	ready   chan struct{}
	backend Backend
	cmd     *exec.Cmd
	logFile *os.File
}

func NewApp() *App {
	return &App{ready: make(chan struct{})}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	go a.launch(a.ready)
}

func (a *App) shutdown(ctx context.Context) {
	a.stopBackend()
}

// ───────────── 프런트엔드에서 호출하는 메서드 ─────────────

// GetBackend 는 Python 서버가 준비될 때까지 기다린 뒤 접속 정보를 돌려준다.
func (a *App) GetBackend() Backend {
	a.mu.Lock()
	ch := a.ready
	a.mu.Unlock()
	<-ch
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.backend
}

// Restart 는 Python 서버를 다시 띄운다 (오류 화면의 '다시 시도').
func (a *App) Restart() Backend {
	a.stopBackend()
	a.mu.Lock()
	a.ready = make(chan struct{})
	a.backend = Backend{}
	ch := a.ready
	a.mu.Unlock()
	go a.launch(ch)
	return a.GetBackend()
}

// ChooseRoot 는 프로젝트 폴더(cli.py 가 있는 곳)를 직접 고르게 한다.
func (a *App) ChooseRoot() Backend {
	dir, err := runtime.OpenDirectoryDialog(a.ctx, runtime.OpenDialogOptions{
		Title: "youtube_movie_maker 폴더를 선택하세요 (cli.py 가 있는 폴더)",
	})
	if err != nil || dir == "" {
		return a.GetBackend()
	}
	if !isProjectRoot(dir) {
		a.mu.Lock()
		a.backend.Error = "선택한 폴더에 cli.py 와 webui 폴더가 없습니다: " + dir
		b := a.backend
		a.mu.Unlock()
		return b
	}
	saveRoot(dir)
	return a.Restart()
}

// OpenURL 은 외부 링크(YouTube 등)를 기본 브라우저로 연다.
func (a *App) OpenURL(url string) {
	if strings.HasPrefix(url, "https://") || strings.HasPrefix(url, "http://") {
		runtime.BrowserOpenURL(a.ctx, url)
	}
}

// ───────────── Python 서버 관리 ─────────────

func (a *App) setResult(ch chan struct{}, b Backend) {
	a.mu.Lock()
	a.backend = b
	a.mu.Unlock()
	close(ch)
}

func (a *App) launch(ch chan struct{}) {
	root, err := findRoot()
	if err != nil {
		a.setResult(ch, Backend{Error: err.Error()})
		return
	}
	python := filepath.Join(root, ".venv", "Scripts", "python.exe")
	if _, err := os.Stat(python); err != nil {
		a.setResult(ch, Backend{Root: root, Error: "Python 가상환경(.venv)이 없습니다.\n프로젝트 폴더의 '웹UI실행.bat' 을 한 번 실행해 설치한 뒤 다시 시도하세요."})
		return
	}

	port, err := freePort()
	if err != nil {
		a.setResult(ch, Backend{Root: root, Error: "사용 가능한 포트를 찾지 못했습니다: " + err.Error()})
		return
	}
	token := randomHex(24)

	_ = os.MkdirAll(filepath.Join(root, "logs"), 0o755)
	logFile, _ := os.Create(filepath.Join(root, "logs", "desktop_backend.log"))

	cmd := exec.Command(python, "-m", "webui.server")
	cmd.Dir = root
	cmd.Env = append(os.Environ(),
		"WEBUI_NO_BROWSER=1",
		fmt.Sprintf("WEBUI_PORT=%d", port),
		"WEBUI_TOKEN="+token,
		"PYTHONUTF8=1",
		"PYTHONIOENCODING=utf-8",
	)
	if logFile != nil {
		cmd.Stdout = logFile
		cmd.Stderr = logFile
	}
	hideWindow(cmd)
	if err := cmd.Start(); err != nil {
		a.setResult(ch, Backend{Root: root, Error: "Python 서버 실행 실패: " + err.Error()})
		return
	}
	attachToJob(cmd)

	a.mu.Lock()
	a.cmd = cmd
	a.logFile = logFile
	a.mu.Unlock()

	exited := make(chan error, 1)
	go func() { exited <- cmd.Wait() }()

	url := fmt.Sprintf("http://127.0.0.1:%d", port)
	client := &http.Client{Timeout: 2 * time.Second}
	deadline := time.Now().Add(90 * time.Second)
	for time.Now().Before(deadline) {
		select {
		case err := <-exited:
			a.setResult(ch, Backend{Root: root, Error: fmt.Sprintf("Python 서버가 시작 중에 종료되었습니다 (%v).\n로그: %s", err, filepath.Join(root, "logs", "desktop_backend.log"))})
			return
		default:
		}
		if resp, err := client.Get(url + "/health"); err == nil {
			resp.Body.Close()
			if resp.StatusCode == 200 {
				a.setResult(ch, Backend{URL: url, Token: token, Root: root})
				return
			}
		}
		time.Sleep(300 * time.Millisecond)
	}
	a.setResult(ch, Backend{Root: root, Error: "Python 서버가 90초 안에 응답하지 않았습니다.\n로그: " + filepath.Join(root, "logs", "desktop_backend.log")})
}

func (a *App) stopBackend() {
	a.mu.Lock()
	cmd, lf := a.cmd, a.logFile
	a.cmd, a.logFile = nil, nil
	a.mu.Unlock()
	if cmd != nil && cmd.Process != nil {
		killTree(cmd)
	}
	if lf != nil {
		lf.Close()
	}
}

// ───────────── 프로젝트 폴더 찾기 ─────────────

func isProjectRoot(dir string) bool {
	_, e1 := os.Stat(filepath.Join(dir, "cli.py"))
	_, e2 := os.Stat(filepath.Join(dir, "webui", "server.py"))
	return e1 == nil && e2 == nil
}

func rootConfigPath() string {
	dir, err := os.UserConfigDir()
	if err != nil {
		return ""
	}
	return filepath.Join(dir, "MovieMaker", "root.txt")
}

func saveRoot(dir string) {
	p := rootConfigPath()
	if p == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(p), 0o755)
	_ = os.WriteFile(p, []byte(dir), 0o644)
}

func findRoot() (string, error) {
	if env := os.Getenv("MM_ROOT"); env != "" && isProjectRoot(env) {
		return env, nil
	}
	var starts []string
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	for _, s := range starts {
		dir := s
		for i := 0; i < 6; i++ {
			if isProjectRoot(dir) {
				saveRoot(dir)
				return dir, nil
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	if p := rootConfigPath(); p != "" {
		if b, err := os.ReadFile(p); err == nil {
			dir := strings.TrimSpace(string(b))
			if isProjectRoot(dir) {
				return dir, nil
			}
		}
	}
	return "", errors.New("프로젝트 폴더(youtube_movie_maker)를 찾지 못했습니다.\n'폴더 선택' 버튼으로 cli.py 가 있는 폴더를 지정하세요.")
}

func freePort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func randomHex(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
