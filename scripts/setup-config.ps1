# Mini-Agent configuration bootstrap for local repo usage on Windows.

$ErrorActionPreference = "Stop"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )

    $colorMap = @{
        "Red" = [ConsoleColor]::Red
        "Green" = [ConsoleColor]::Green
        "Yellow" = [ConsoleColor]::Yellow
        "Blue" = [ConsoleColor]::Blue
        "Cyan" = [ConsoleColor]::Cyan
        "White" = [ConsoleColor]::White
    }

    Write-Host $Message -ForegroundColor $colorMap[$Color]
}

function Copy-TemplateIfMissing {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$Label
    )

    if (!(Test-Path $Source)) {
        Write-ColorOutput "   [WARN] Missing template: $Label" -Color "Yellow"
        return
    }

    if (Test-Path $Destination) {
        Write-ColorOutput "   [SKIP] Exists: $Destination" -Color "Yellow"
        return
    }

    Copy-Item -LiteralPath $Source -Destination $Destination
    Write-ColorOutput "   [OK] Created: $Destination" -Color "Green"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$packageConfigDir = Join-Path $repoRoot "src\mini_agent\config"
$userConfigDir = Join-Path $env:USERPROFILE ".mini-agent\config"
$repoEnvExample = Join-Path $repoRoot ".env.local.example"
$repoEnvLocal = Join-Path $repoRoot ".env.local"

if (!(Test-Path $packageConfigDir)) {
    Write-ColorOutput "[ERROR] Cannot find src\\mini_agent\\config under repo root." -Color "Red"
    exit 1
}

Write-ColorOutput "==================================================" -Color "Cyan"
Write-ColorOutput "   Mini-Agent Local Config Bootstrap" -Color "Cyan"
Write-ColorOutput "==================================================" -Color "Cyan"
Write-Host ""

Write-ColorOutput "[1/2] Ensuring user config directory..." -Color "Blue"
New-Item -Path $userConfigDir -ItemType Directory -Force | Out-Null
Write-ColorOutput "   [OK] Ready: $userConfigDir" -Color "Green"
Write-Host ""

Write-ColorOutput "[2/2] Copying local templates if missing..." -Color "Blue"
Copy-TemplateIfMissing -Source (Join-Path $packageConfigDir "config-example.yaml") -Destination (Join-Path $userConfigDir "config.yaml") -Label "config.yaml"
Copy-TemplateIfMissing -Source (Join-Path $packageConfigDir "mcp-example.json") -Destination (Join-Path $userConfigDir "mcp.json") -Label "mcp.json"
Copy-TemplateIfMissing -Source (Join-Path $packageConfigDir "system_prompt.md") -Destination (Join-Path $userConfigDir "system_prompt.md") -Label "system_prompt.md"

Write-Host ""
Write-ColorOutput "==================================================" -Color "Green"
Write-ColorOutput "   Local Bootstrap Complete" -Color "Green"
Write-ColorOutput "==================================================" -Color "Green"
Write-Host ""
Write-Host "User config directory:"
Write-ColorOutput "  $userConfigDir" -Color "Cyan"
Write-Host ""
Write-Host "Preset provider keys:"
Write-ColorOutput "  OPENAI_API_KEY" -Color "Green"
Write-ColorOutput "  ANTHROPIC_API_KEY" -Color "Green"
Write-ColorOutput "  GEMINI_API_KEY" -Color "Green"
Write-ColorOutput "  MINIMAX_API_KEY" -Color "Green"
Write-Host ""
Write-Host "Current behavior:"
Write-Host "  - Runtime checks system environment variables first."
Write-Host "  - Repo-local fallback is .env.local."
Write-Host "  - .env.local.example is a template only and is not loaded."
Write-Host ""

if ((Test-Path $repoEnvExample) -and !(Test-Path $repoEnvLocal)) {
    Write-Host "Optional repo-local secret file:"
    Write-ColorOutput "  Copy-Item `"$repoEnvExample`" `"$repoEnvLocal`"" -Color "Green"
    Write-Host ""
}

Write-Host "Useful commands:"
Write-ColorOutput "  uv run mini" -Color "Green"
Write-ColorOutput "  uv run mini tui" -Color "Green"
Write-ColorOutput "  uv run mini qq" -Color "Green"
Write-ColorOutput "  uv run mini-agent doctor" -Color "Green"