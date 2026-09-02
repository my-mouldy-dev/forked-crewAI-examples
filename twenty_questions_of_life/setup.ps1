<#
.SYNOPSIS
    One-time setup on Windows: virtual environment, dependencies, .env file.

.DESCRIPTION
    Safe to run more than once. It only does the work that is still missing,
    so re-run it after pulling changes and it will just update the packages.

.PARAMETER Force
    Delete the existing virtual environment and build it again. Use this if an
    install went wrong halfway.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "   $text" -ForegroundColor DarkGray }
function Warn($text) { Write-Host "   $text" -ForegroundColor Yellow }
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

function Save-TextFile($path, $text) {
    # Set-Content in Windows PowerShell writes a byte order mark, which the
    # .env reader would hand back as part of the first key name.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($path, $text, $utf8NoBom)
}

# --------------------------------------------------------------- python

Step "Looking for a usable Python"

# crewAI 0.85 wants 3.10 to 3.12. The py launcher is asked for each of those in
# turn before falling back to whatever "python" happens to be.
$candidates = @(
    @{ Exe = "py";     Args = @("-3.12") },
    @{ Exe = "py";     Args = @("-3.11") },
    @{ Exe = "py";     Args = @("-3.10") },
    @{ Exe = "py";     Args = @("-3")    },
    @{ Exe = "python"; Args = @()        }
)

$python = $null
$pythonArgs = @()
$rejected = @()

foreach ($candidate in $candidates) {
    if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
    $probe = $candidate.Args + @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")
    $version = & $candidate.Exe @probe 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $version) { continue }

    $parts = "$version".Trim() -split '\.' 
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -eq 3 -and $minor -ge 10 -and $minor -le 12) {
        $python = $candidate.Exe
        $pythonArgs = $candidate.Args
        Note "Using $($candidate.Exe) $($candidate.Args) - Python $version"
        break
    }
    $rejected += "$($candidate.Exe) $($candidate.Args) is Python $version"
}

if (-not $python) {
    $detail = ""
    if ($rejected.Count -gt 0) { $detail = "`nFound, but not usable:`n  " + ($rejected -join "`n  ") }
    Die ("No Python between 3.10 and 3.12 was found, and crewAI 0.85 does not run on 3.13." +
         "$detail`nInstall 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and run this again.")
}

# ---------------------------------------------------------- environment

$venv = Join-Path $PSScriptRoot ".venv"
$venvPython = Get-VenvPython $venv

if ($Force -and (Test-Path $venv)) {
    Step "Removing the old virtual environment"
    Remove-Item -Path $venv -Recurse -Force
}

if (Test-Path $venvPython) {
    Step "Virtual environment already exists"
    Note "Delete .venv, or run this with -Force, to rebuild it"
} else {
    Step "Creating the virtual environment in .venv"
    $create = $pythonArgs + @("-m", "venv", ".venv")
    & $python @create
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { Die "Could not create the virtual environment." }
}

# ------------------------------------------------------------ packages

Step "Installing packages - this takes a few minutes the first time"

& $venvPython -m pip install --upgrade pip --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Die "Could not upgrade pip." }

# crewAI 0.85 imports pkg_resources, which setuptools removed in version 81.
# Without this pin every run dies on ModuleNotFoundError before it starts.
Note "Pinning setuptools below 81 - crewAI 0.85 still needs pkg_resources"
& $venvPython -m pip install "setuptools<81" --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Die "Could not install setuptools." }

Note "Installing the app and the web front end"
& $venvPython -m pip install -e ".[web]" --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Die "Package install failed. Scroll up for what pip said." }

Step "Checking it imports"
$env:OTEL_SDK_DISABLED = "true"
& $venvPython -c "import twenty_questions_of_life.web" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -c "import twenty_questions_of_life.web"
    Die "The package installed but will not import. The error is above."
}
Note "Good."

# ----------------------------------------------------------------- key

Step "Setting up .env"

if (-not (Test-Path ".env")) {
    Copy-Item -Path ".env.example" -Destination ".env"
    Note "Created .env from .env.example"
} else {
    Note ".env already exists and has been left alone"
}

$lines = @(Get-Content -Path ".env")
$placeholder = $false
foreach ($line in $lines) {
    if ($line -match '^\s*OPENAI_API_KEY\s*=\s*sk-\.\.\.\s*$') { $placeholder = $true }
}

if ($placeholder) {
    Write-Host ""
    Write-Host "   The app needs an OpenAI API key. Get one at https://platform.openai.com/api-keys"
    $key = Read-Host "   Paste it here, or press Enter to fill it in yourself later"
    if ($key.Trim()) {
        $updated = $lines | ForEach-Object {
            if ($_ -match '^\s*OPENAI_API_KEY\s*=') { "OPENAI_API_KEY=" + $key.Trim() } else { $_ }
        }
        Save-TextFile (Join-Path $PSScriptRoot ".env") (($updated -join "`r`n") + "`r`n")
        Note "Key written to .env"
    } else {
        Warn "Skipped. Open .env and replace sk-... before you run it."
    }
}

# --------------------------------------------------------------- done

Write-Host "`n== Ready" -ForegroundColor Green
Write-Host ""
Write-Host "   On this machine:      .\start.ps1 -Terminal"
Write-Host "   On your phone:        .\start.ps1"
Write-Host "   Run the tests:        $venvPython -m unittest discover tests"
Write-Host ""
Write-Host "   start.ps1 prints a link and a QR code. If Windows Firewall asks," -ForegroundColor DarkGray
Write-Host "   allow it on private networks only - that is what lets your phone in." -ForegroundColor DarkGray
Write-Host ""
