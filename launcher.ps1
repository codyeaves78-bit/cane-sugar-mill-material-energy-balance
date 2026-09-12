# ============================================================
# MEB App Launcher
#
# What this does, every time it's run:
#   1. Checks for an internet connection.
#   2. If online: makes sure Git is installed, then clones the
#      app (first run) or pulls the latest version (later runs).
#      If offline and the app is already downloaded, skips this
#      step entirely and uses what's already on the machine.
#   3. Makes sure Python 3.12+ is installed (installs it if
#      online and missing).
#   4. Creates a virtual environment the first time, and
#      installs/updates dependencies whenever requirements.txt
#      changes (only when online).
#   5. Launches the Streamlit app.
#
# Safe to re-run any time - double-click run_meb_app.bat.
# ============================================================

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = "Stop"

$RepoUrl               = "https://github.com/codyeaves78-bit/cane-sugar-mill-material-energy-balance.git"
$RepoFolderName        = "cane-sugar-mill-material-energy-balance"
$PythonFallbackVersion = "3.12.7"   # only used if winget isn't available on this machine

$ScriptDir = $PSScriptRoot
$RepoDir   = Join-Path $ScriptDir $RepoFolderName
$VenvDir   = Join-Path $RepoDir "venv"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Internet {
    try {
        $null = Invoke-WebRequest -Uri "https://github.com" -Method Head -TimeoutSec 5 -UseBasicParsing
        return $true
    } catch {
        return $false
    }
}

function Update-SessionPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Test-GitInstalled {
    return [bool](Get-Command git -ErrorAction SilentlyContinue)
}

function Install-Git {
    Write-Step "Installing Git for Windows..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    } else {
        $api = "https://api.github.com/repos/git-for-windows/git/releases/latest"
        $release = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "meb-app-launcher" }
        $asset = $release.assets | Where-Object { $_.name -match "64-bit\.exe$" } | Select-Object -First 1
        if (-not $asset) {
            throw "Could not find a Git for Windows installer to download automatically."
        }
        $installerPath = Join-Path $env:TEMP $asset.name
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installerPath
        Start-Process -FilePath $installerPath `
            -ArgumentList "/VERYSILENT","/NORESTART","/NOCANCEL","/SP-","/SUPPRESSMSGBOXES" -Wait
        Remove-Item $installerPath -ErrorAction SilentlyContinue
    }
    Update-SessionPath
    if (-not (Test-GitInstalled)) {
        throw "Git installation didn't complete. Install it manually from https://git-scm.com/download/win and re-run this launcher."
    }
}

function Get-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $null = & py -3.12 --version 2>&1
        if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $verOut = (& python --version) 2>&1
        if ($verOut -match "Python (\d+)\.(\d+)") {
            $maj = [int]$Matches[1]
            $min = [int]$Matches[2]
            if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 12)) { return @("python") }
        }
    }
    return $null
}

function Invoke-PythonCommand {
    param([string[]]$ExtraArgs)
    if ($PyCmd.Length -gt 1) {
        & $PyCmd[0] $PyCmd[1] @ExtraArgs
    } else {
        & $PyCmd[0] @ExtraArgs
    }
}

function Install-Python {
    Write-Step "Installing Python $PythonFallbackVersion..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    } else {
        $pyUrl = "https://www.python.org/ftp/python/$PythonFallbackVersion/python-$PythonFallbackVersion-amd64.exe"
        $installerPath = Join-Path $env:TEMP "python-installer.exe"
        Invoke-WebRequest -Uri $pyUrl -OutFile $installerPath
        Start-Process -FilePath $installerPath `
            -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=1","Include_launcher=1" -Wait
        Remove-Item $installerPath -ErrorAction SilentlyContinue
    }
    Update-SessionPath
}

# ------------------------------------------------------------
# 0. Internet check
# ------------------------------------------------------------
Write-Step "Checking for an internet connection..."
$Online = Test-Internet
if ($Online) {
    Write-Host "Online - will check for updates."
} else {
    Write-Host "No internet detected - using what's already on this machine." -ForegroundColor Yellow
}

# ------------------------------------------------------------
# 1 & 2. Git + clone/pull
# ------------------------------------------------------------
$RepoExists = Test-Path (Join-Path $RepoDir ".git")

if (-not $RepoExists -and -not $Online) {
    Write-Host ""
    Write-Host "This app hasn't been downloaded to this machine yet, and there's no" -ForegroundColor Red
    Write-Host "internet connection right now. Connect to the internet and run this" -ForegroundColor Red
    Write-Host "launcher once to finish first-time setup." -ForegroundColor Red
    exit 1
}

if ($Online) {
    if (-not (Test-GitInstalled)) {
        Install-Git
    }
    if ($RepoExists) {
        Write-Step "Checking for app updates..."
        git -C $RepoDir pull
    } else {
        Write-Step "Downloading the app..."
        git clone $RepoUrl $RepoDir
    }
} else {
    Write-Step "Skipping update check (offline) - using the local copy."
}

# ------------------------------------------------------------
# 3. Python 3.12+
# ------------------------------------------------------------
Write-Step "Checking for Python 3.12+..."
$PyCmd = Get-PythonCommand
if (-not $PyCmd) {
    if (-not $Online) {
        Write-Host "Python 3.12+ isn't installed, and there's no internet connection to install it." -ForegroundColor Red
        exit 1
    }
    Install-Python
    $PyCmd = Get-PythonCommand
    if (-not $PyCmd) {
        throw "Python installation didn't complete. Install Python 3.12+ manually from https://www.python.org/downloads/ and re-run this launcher."
    }
}
Write-Host "Using: $($PyCmd -join ' ')"

# ------------------------------------------------------------
# 4. Virtual environment + dependencies
# ------------------------------------------------------------
$ReqsFile     = Join-Path $RepoDir "requirements.txt"
$ReqsHashFile = Join-Path $VenvDir ".reqs_hash"
$VenvExists   = Test-Path (Join-Path $VenvDir "Scripts\python.exe")

if (-not $VenvExists) {
    if (-not $Online) {
        Write-Host "First-time setup needs an internet connection to install Python packages." -ForegroundColor Red
        exit 1
    }
    Write-Step "Creating virtual environment..."
    Invoke-PythonCommand -ExtraArgs @("-m", "venv", $VenvDir)
}

$VenvPip       = Join-Path $VenvDir "Scripts\pip.exe"
$VenvStreamlit = Join-Path $VenvDir "Scripts\streamlit.exe"

if ($Online) {
    $CurrentHash  = (Get-FileHash $ReqsFile -Algorithm SHA256).Hash
    $PreviousHash = if (Test-Path $ReqsHashFile) { Get-Content $ReqsHashFile -Raw } else { "" }

    if ($CurrentHash -ne $PreviousHash) {
        Write-Step "Installing/updating dependencies..."
        & $VenvPip install --upgrade pip --quiet
        & $VenvPip install -r $ReqsFile
        Set-Content -Path $ReqsHashFile -Value $CurrentHash -NoNewline
    } else {
        Write-Host "Dependencies already up to date."
    }
} else {
    Write-Host "Skipping dependency check (offline)."
}

# ------------------------------------------------------------
# 5. Launch
# ------------------------------------------------------------
Write-Step "Launching the app - it'll open in your browser shortly..."
Set-Location $RepoDir
& $VenvStreamlit run "streamlit_app.py"
