param(
    [string]$Workspace = "",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8008,
    [switch]$NoQqBot,
    [switch]$NoTui,
    [string]$Prompt = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = $root
}

Set-Location $root

$args = @(
    "run",
    "mini-agent",
    "stack",
    "up",
    "--workspace",
    $Workspace,
    "--host",
    $Host,
    "--port",
    "$Port"
)

if ($NoQqBot) {
    $args += "--no-qqbot"
}

if ($NoTui) {
    $args += "--no-tui"
}

if (-not [string]::IsNullOrWhiteSpace($Prompt)) {
    $args += "--tui-prompt"
    $args += $Prompt
}

& uv @args
