<#
.SYNOPSIS
    CODM Attachments Bot - Windows Deployment Script
    
.DESCRIPTION
    Equivalent of deploy.sh for Windows.
    Handles setup, execution, and management of the bot locally.
#>

$ErrorActionPreference = "Stop"

# --- Helper Functions ---
function Show-Header {
    Clear-Host
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "    CODM Attachments Bot - Windows Manager" -ForegroundColor White
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Success { param($Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Show-Error { param($Msg) Write-Host "[ERROR] $Msg" -ForegroundColor Red }
function Show-Info { param($Msg) Write-Host "[INFO] $Msg" -ForegroundColor Cyan }
function Show-Warning { param($Msg) Write-Host "[WARN] $Msg" -ForegroundColor Yellow }

function Suspend-Script {
    Write-Host ""
    Write-Host "Press any key to return to menu..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Test-Python {
    try {
        $null = python --version 2>&1
        return $true
    }
    catch {
        return $false
    }
}

# --- Main Operations ---

function Install-Bot {
    Show-Header
    Write-Host "Installing/Updating Bot..." -ForegroundColor Yellow

    # 1. Check Python
    if (-not (Test-Python)) {
        Show-Error "Python not found! Please install Python 3.10+ and add to PATH."
        Suspend-Script
        return
    }

    # 2. Setup VENV
    $venvPath = Join-Path $PSScriptRoot "venv"
    if (-not (Test-Path $venvPath)) {
        Show-Info "Creating virtual environment..."
        python -m venv $venvPath
    }

    # 3. Install Requirements
    Show-Info "Installing dependencies..."
    $pip = Join-Path $venvPath "Scripts\pip.exe"
    & $pip install --upgrade pip | Out-Null
    & $pip install -r (Join-Path $PSScriptRoot "requirements.txt") | Out-Null
    Show-Success "Dependencies installed."

    # 4. Database Setup
    Show-Info "Setting up Database..."
    $dbPass = Read-Host "Enter local PostgreSQL Password"
    $env:POSTGRES_PASSWORD = $dbPass
    
    # Run setup script
    $python = Join-Path $venvPath "Scripts\python.exe"
    $setupScript = Join-Path $PSScriptRoot "scripts\setup_database.py"
    & $python $setupScript

    # 5. .env Setup
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Show-Warning ".env file created from example."
        Write-Host "Please edit .env file to add your BOT_TOKEN." -ForegroundColor Yellow
        Start-Process "notepad.exe" ".env"
    }

    Show-Success "Installation Complete!"
    Suspend-Script
}

function Start-Bot {
    Show-Header
    
    if (-not (Test-Path "venv")) {
        Show-Error "Bot is not installed. Please run Install first."
        Suspend-Script
        return
    }

    Show-Info "Starting Bot..."
    $python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    
    # Check for token
    $token = Get-Content .env | Select-String "BOT_TOKEN=YOUR_BOT_TOKEN_HERE"
    if ($token) {
        Show-Error "You must configure BOT_TOKEN in .env file first!"
        Start-Process "notepad.exe" ".env"
        Suspend-Script
        return
    }

    & $python main.py
    
    Write-Host ""
    Show-Warning "Bot stopped."
    Suspend-Script
}

function Edit-Config {
    if (Test-Path ".env") {
        Start-Process "notepad.exe" ".env"
    }
    else {
        Show-Error ".env file not found."
    }
}

# --- Main Loop ---

while ($true) {
    Show-Header
    Write-Host "1. [Install] Setup venv, Dependencies and Database" -ForegroundColor Green
    Write-Host "2. [Start]   Run the Bot" -ForegroundColor Cyan
    Write-Host "3. [Config]  Edit .env File" -ForegroundColor Yellow
    Write-Host "4. [Exit]    Close" -ForegroundColor Gray
    Write-Host ""
    
    $choice = Read-Host "Select an option"

    switch ($choice) {
        "1" { Install-Bot }
        "2" { Start-Bot }
        "3" { Edit-Config }
        "4" { exit }
        default { }
    }
}
