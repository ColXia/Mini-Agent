param(
    [string]$ChannelDir = "C:\Users\Conli\Mini-Agent\channels\wechat"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ChannelDir)) {
    throw "WeChat channel directory not found: $ChannelDir"
}

$envPath = Join-Path $ChannelDir ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "[Warn] .env not found. Please copy .env.example to .env and fill WECHAT_TOKEN first." -ForegroundColor Yellow
}

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq "node.exe" -and $_.CommandLine -match "channels\\wechat\\dist\\index\.js"
}
foreach ($proc in $existing) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}

$userApiKey = [Environment]::GetEnvironmentVariable("MINIMAX_API_KEY", "User")
if (-not [string]::IsNullOrWhiteSpace($userApiKey)) {
    $env:MINIMAX_API_KEY = $userApiKey
}

$cmd = "Set-Location '$ChannelDir'; if(-not (Test-Path '.\node_modules')){ npm install }; if(-not (Test-Path '.\dist\index.js')){ npm run build }; node .\dist\index.js"
Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-Command", $cmd | Out-Null

Write-Host "WeChat channel start command sent." -ForegroundColor Green
Write-Host "Dir: $ChannelDir" -ForegroundColor DarkGray
