<#
.SYNOPSIS
    Run the interview. Web page by default, so you can do it on your phone.

.DESCRIPTION
    Reads .env, then starts the app from the virtual environment setup.ps1
    built. Run setup.ps1 first if you have not.

.PARAMETER Terminal
    Do the interview here in this window instead, typing your answers.

.PARAMETER LocalOnly
    Serve on localhost only. No token needed, and no phone either.

.PARAMETER Port
    Which port to serve on. Default 8020.

.PARAMETER Name
    What the panel calls you.

.PARAMETER Questions
    How many questions. Default 20.

.PARAMETER Panel
    "full" is four panellists and a chair per question. "lean" is the chair on
    his own: about a fifth of the model calls, and blunter questions.

.EXAMPLE
    .\start.ps1
    .\start.ps1 -Terminal -Name Sam -Panel lean
#>
[CmdletBinding()]
param(
    [switch]$Terminal,
    [switch]$LocalOnly,
    [int]$Port = 8020,
    [string]$Name = "Friend",
    [int]$Questions = 20,
    [ValidateSet("full", "lean")]
    [string]$Panel = "full"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Die($text) {
    Write-Host "`n$text`n" -ForegroundColor Red
    exit 1
}

function Get-VenvPython($venvPath) {
    # $IsWindows only exists in PowerShell 6 and later. In Windows PowerShell
    # 5.1 the variable is absent, and that only ever runs on Windows anyway.
    $onWindows = $true
    if (Test-Path Variable:IsWindows) { $onWindows = $IsWindows }
    if ($onWindows) { return (Join-Path $venvPath "Scripts\python.exe") }
    return (Join-Path $venvPath "bin/python")
}

$venvPython = Get-VenvPython (Join-Path $PSScriptRoot ".venv")
if (-not (Test-Path $venvPython)) {
    Die "No virtual environment here yet. Run this first:`n  powershell -ExecutionPolicy Bypass -File .\setup.ps1"
}

if (-not (Test-Path ".env")) {
    Die "No .env file. Run setup.ps1, or copy .env.example to .env and put your key in it."
}

# Load .env into this process only. Nothing is written to your user or system
# environment, so the key disappears when this window closes.
foreach ($line in Get-Content -Path ".env") {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $pair = $line -split '=', 2
    $key = $pair[0].Trim()
    $value = $pair[1].Trim().Trim('"').Trim("'")
    if ($key) { Set-Item -Path ("Env:" + $key) -Value $value }
}

if (-not $env:OPENAI_API_KEY -or $env:OPENAI_API_KEY -eq "sk-...") {
    Die "OPENAI_API_KEY is not set in .env. Open it and put your key in."
}

if ($Terminal) {
    & $venvPython -m twenty_questions_of_life.main --name $Name --questions $Questions --panel $Panel
    exit $LASTEXITCODE
}

$bind = "0.0.0.0"
if ($LocalOnly) { $bind = "127.0.0.1" }

Write-Host "`n   Starting the web front end. Ctrl+C stops it." -ForegroundColor DarkGray
if (-not $LocalOnly) {
    Write-Host "   If Windows Firewall asks, allow it on private networks only.`n" -ForegroundColor DarkGray
}

& $venvPython -m twenty_questions_of_life.web --host $bind --port $Port
exit $LASTEXITCODE
