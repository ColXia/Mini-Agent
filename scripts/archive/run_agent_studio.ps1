param(
    [int]$GatewayPort = 8008,
    [int]$FrontendPort = 5174,
    [switch]$DevSplit,
    [switch]$NoBuild,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontendDir = Join-Path $root "apps\agent_studio"
$userApiKey = [Environment]::GetEnvironmentVariable("MINIMAX_API_KEY", "User")
if (-not [string]::IsNullOrWhiteSpace($userApiKey)) {
    # Force child processes to use the latest user-level key, avoiding stale process env values.
    $env:MINIMAX_API_KEY = $userApiKey
}

if (-not (Test-Path $python)) {
    throw "Python venv not found: $python"
}

function Get-ListeningPid([int]$Port) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $conn) {
        return $null
    }
    return [int]$conn.OwningProcess
}

$existingGatewayPid = Get-ListeningPid -Port $GatewayPort
if ($null -ne $existingGatewayPid) {
    Write-Host "Error: Studio Gateway is already running on port $GatewayPort (PID: $existingGatewayPid)." -ForegroundColor Red
    Write-Host "Stop it first: taskkill /PID $existingGatewayPid /F" -ForegroundColor Yellow
    exit 1
}

if ($DevSplit) {
    $existingFrontendPid = Get-ListeningPid -Port $FrontendPort
    if ($null -ne $existingFrontendPid) {
        Write-Host "Error: Frontend dev server is already running on port $FrontendPort (PID: $existingFrontendPid)." -ForegroundColor Red
        Write-Host "Stop it first: taskkill /PID $existingFrontendPid /F" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "Starting Mini-Agent Studio..." -ForegroundColor Cyan
Write-Host "Root: $root" -ForegroundColor DarkGray

if ($DevSplit) {
    Write-Host "Mode: split dev (two processes, hot reload for frontend)." -ForegroundColor Yellow
    $gatewayCommand = "$env:PYTHONUTF8='1'; `$env:PYTHONIOENCODING='utf-8'; `$env:MINI_AGENT_STUDIO_HOST='127.0.0.1'; `$env:MINI_AGENT_STUDIO_PORT='$GatewayPort'; `$env:MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK='1'; `$k=[Environment]::GetEnvironmentVariable('MINIMAX_API_KEY','User'); if(-not [string]::IsNullOrWhiteSpace(`$k)){ `$env:MINIMAX_API_KEY=`$k }; Set-Location '$root'; & '$python' -m uvicorn apps.agent_studio_gateway.main:app --host 127.0.0.1 --port $GatewayPort --reload"
    Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-Command", $gatewayCommand | Out-Null

    $frontendCommand = "Set-Location '$frontendDir'; npm run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort"
    Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-Command", $frontendCommand | Out-Null

    Write-Host "Gateway: http://127.0.0.1:$GatewayPort" -ForegroundColor Green
    Write-Host "Frontend: http://127.0.0.1:$FrontendPort" -ForegroundColor Green
    return
}

Write-Host "Mode: single host (one process)." -ForegroundColor Green
if (-not $NoBuild) {
    Write-Host "Building frontend dist..." -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        npm run build
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Skip frontend build (--NoBuild)." -ForegroundColor Yellow
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:MINI_AGENT_STUDIO_HOST = "127.0.0.1"
$env:MINI_AGENT_STUDIO_PORT = "$GatewayPort"
$env:MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK = "1"

Set-Location $root
Write-Host "Studio URL: http://127.0.0.1:$GatewayPort" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray

$uvicornArgs = @(
    "-m",
    "uvicorn",
    "apps.agent_studio_gateway.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$GatewayPort"
)
if ($Reload) {
    $uvicornArgs += "--reload"
}

& $python @uvicornArgs
