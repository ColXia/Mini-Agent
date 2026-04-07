param(
    [string]$Python = "",
    [string]$AdapterBaseUrl = "http://127.0.0.1:8010",
    [string]$GatewayBaseUrl = "http://127.0.0.1:8008",
    [string]$OpenWebUIApiKey = "mini-agent-openwebui-token",
    [string]$StudioToken = "studio-smoke-token",
    [string]$OpenWebUIModel = "",
    [double]$OpenWebUITimeout = 300,
    [double]$AdapterGatewayTimeout = 300,
    [int]$AdapterStartupTimeoutSeconds = 90,
    [int]$MaxAttempts = 2,
    [int]$RetryDelaySeconds = 8,
    [switch]$SkipStartLocalGateway
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$pythonCmd = if (-not [string]::IsNullOrWhiteSpace($Python)) {
    $Python
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
} elseif (Test-Path $venvPython) {
    $venvPython
} else {
    throw "No Python interpreter found. Pass -Python explicitly."
}

if ([string]::IsNullOrWhiteSpace($OpenWebUIApiKey)) {
    throw "OpenWebUIApiKey cannot be empty."
}

$adapterRoot = $AdapterBaseUrl.Trim().TrimEnd("/")
if ($adapterRoot.ToLower().EndsWith("/v1")) {
    $adapterRoot = $adapterRoot.Substring(0, $adapterRoot.Length - 3).TrimEnd("/")
}
if ([string]::IsNullOrWhiteSpace($adapterRoot)) {
    throw "AdapterBaseUrl is invalid."
}

$adapterUri = [Uri]$adapterRoot
$adapterHealthUrl = "$adapterRoot/health"
$adapterHost = if (-not [string]::IsNullOrWhiteSpace($adapterUri.Host)) { $adapterUri.Host } else { "127.0.0.1" }
$adapterPort = if ($adapterUri.IsDefaultPort) { if ($adapterUri.Scheme -eq "https") { 443 } else { 80 } } else { $adapterUri.Port }
$model = if ([string]::IsNullOrWhiteSpace($OpenWebUIModel)) { "mini-agent" } else { $OpenWebUIModel.Trim() }

$srcPath = Join-Path $root "src"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $srcPath
} else {
    $env:PYTHONPATH = "$srcPath$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$env:MINI_AGENT_GATEWAY_URL = $GatewayBaseUrl.Trim()
$env:MINI_AGENT_OPENWEBUI_API_KEYS = $OpenWebUIApiKey.Trim()
$env:MINI_AGENT_OPENWEBUI_PRIMARY_API_KEY = $OpenWebUIApiKey.Trim()
$env:MINI_AGENT_OPENWEBUI_DEFAULT_MODEL = $model
$env:MINI_AGENT_OPENWEBUI_MODELS = $model
$env:MINI_AGENT_OPENWEBUI_TIMEOUT_SECONDS = [string]([Math]::Max(1, [int][Math]::Round($AdapterGatewayTimeout)))

function Test-AdapterHealthy([string]$Url) {
    try {
        $resp = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 3
        return ($null -ne $resp)
    } catch {
        return $false
    }
}

function Wait-AdapterHealthy([string]$Url, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-AdapterHealthy -Url $Url) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

$adapterProc = $null
$adapterStartedHere = $false
$gateExit = 1

$releaseGateArgs = @(
    "scripts/release_gate.py",
    "--openwebui-run-smoke",
    "--openwebui-no-dry-run",
    "--openwebui-adapter-base-url", $adapterRoot,
    "--openwebui-api-key", $OpenWebUIApiKey.Trim(),
    "--openwebui-timeout", [string]$OpenWebUITimeout,
    "--studio-token", $StudioToken.Trim()
)
if (-not $SkipStartLocalGateway) {
    $releaseGateArgs += "--start-local-gateway"
}
if (-not [string]::IsNullOrWhiteSpace($OpenWebUIModel)) {
    $releaseGateArgs += @("--openwebui-model", $model)
}

Write-Host "Repo: $root" -ForegroundColor DarkGray
Write-Host "Python: $pythonCmd" -ForegroundColor DarkGray
Write-Host "OpenWebUI adapter: $adapterRoot" -ForegroundColor DarkGray
Write-Host "Gateway: $GatewayBaseUrl" -ForegroundColor DarkGray

try {
    if (Test-AdapterHealthy -Url $adapterHealthUrl) {
        Write-Host "OpenWebUI adapter already healthy: $adapterHealthUrl" -ForegroundColor Green
    } else {
        $logDir = Join-Path $root "workspace\release_gate"
        New-Item -Path $logDir -ItemType Directory -Force | Out-Null
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $adapterOut = Join-Path $logDir "openwebui_adapter_$stamp.out.log"
        $adapterErr = Join-Path $logDir "openwebui_adapter_$stamp.err.log"

        Write-Host "Starting OpenWebUI adapter on $adapterHost`:$adapterPort ..." -ForegroundColor Cyan
        $adapterProc = Start-Process -FilePath $pythonCmd -ArgumentList @(
            "-m", "uvicorn", "apps.open_webui.main:app", "--host", $adapterHost, "--port", "$adapterPort"
        ) -WorkingDirectory $root -RedirectStandardOutput $adapterOut -RedirectStandardError $adapterErr -PassThru
        $adapterStartedHere = $true

        if (-not (Wait-AdapterHealthy -Url $adapterHealthUrl -TimeoutSeconds $AdapterStartupTimeoutSeconds)) {
            throw "OpenWebUI adapter failed health check: $adapterHealthUrl"
        }
        Write-Host "OpenWebUI adapter is healthy." -ForegroundColor Green
    }

    for ($attempt = 1; $attempt -le [Math]::Max(1, $MaxAttempts); $attempt++) {
        Write-Host "Running release gate attempt $attempt/$([Math]::Max(1, $MaxAttempts)) ..." -ForegroundColor Cyan
        Push-Location $root
        try {
            & $pythonCmd @releaseGateArgs
            $gateExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($gateExit -eq 0) {
            break
        }
        if ($attempt -lt [Math]::Max(1, $MaxAttempts)) {
            Write-Host "Attempt $attempt failed (exit $gateExit). Retrying in $RetryDelaySeconds seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds ([Math]::Max(0, $RetryDelaySeconds))
        }
    }
} finally {
    if ($adapterStartedHere -and $adapterProc -and -not $adapterProc.HasExited) {
        Write-Host "Stopping OpenWebUI adapter (PID=$($adapterProc.Id))." -ForegroundColor DarkGray
        Stop-Process -Id $adapterProc.Id -Force
    }
}

if ($gateExit -eq 0) {
    Write-Host "Release gate completed: PASS" -ForegroundColor Green
} else {
    Write-Host "Release gate completed: FAIL (exit $gateExit)" -ForegroundColor Red
}

exit $gateExit
