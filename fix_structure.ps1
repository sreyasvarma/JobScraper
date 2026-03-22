# fix_structure.ps1
# Run this from inside your files\ folder:
#   cd C:\Users\sreya\Downloads\AppsIBuilt\JobTracker\files
#   powershell -ExecutionPolicy Bypass -File fix_structure.ps1

Write-Host ""
Write-Host "=== Fixing Job Alert folder structure ===" -ForegroundColor Cyan
Write-Host ""

# 1. Create scrapers\ subfolder
if (-not (Test-Path "scrapers")) {
    New-Item -ItemType Directory -Name "scrapers" | Out-Null
    Write-Host "[+] Created scrapers\" -ForegroundColor Green
} else {
    Write-Host "[=] scrapers\ already exists" -ForegroundColor Yellow
}

# 2. Create scrapers\__init__.py
$initContent = @'
from .base import BaseScraper, Job
from .generic import GenericStaticScraper, GenericJSScraper, scraper_for

__all__ = ["BaseScraper", "Job", "GenericStaticScraper", "GenericJSScraper", "scraper_for"]
'@
Set-Content -Path "scrapers\__init__.py" -Value $initContent
Write-Host "[+] Created scrapers\__init__.py" -ForegroundColor Green

# 3. Move base.py → scrapers\base.py
if (Test-Path "base.py") {
    Move-Item -Force "base.py" "scrapers\base.py"
    Write-Host "[+] Moved base.py -> scrapers\base.py" -ForegroundColor Green
} elseif (Test-Path "scrapers\base.py") {
    Write-Host "[=] scrapers\base.py already in place" -ForegroundColor Yellow
} else {
    Write-Host "[!] base.py not found - you'll need to re-download it" -ForegroundColor Red
}

# 4. Move generic.py → scrapers\generic.py
if (Test-Path "generic.py") {
    Move-Item -Force "generic.py" "scrapers\generic.py"
    Write-Host "[+] Moved generic.py -> scrapers\generic.py" -ForegroundColor Green
} elseif (Test-Path "scrapers\generic.py") {
    Write-Host "[=] scrapers\generic.py already in place" -ForegroundColor Yellow
} else {
    Write-Host "[!] generic.py not found - you'll need to re-download it" -ForegroundColor Red
}

# 5. Create dashboard\ subfolder and move index.html
if (-not (Test-Path "dashboard")) {
    New-Item -ItemType Directory -Name "dashboard" | Out-Null
    Write-Host "[+] Created dashboard\" -ForegroundColor Green
} else {
    Write-Host "[=] dashboard\ already exists" -ForegroundColor Yellow
}

if (Test-Path "index.html") {
    Move-Item -Force "index.html" "dashboard\index.html"
    Write-Host "[+] Moved index.html -> dashboard\index.html" -ForegroundColor Green
} elseif (Test-Path "dashboard\index.html") {
    Write-Host "[=] dashboard\index.html already in place" -ForegroundColor Yellow
} else {
    Write-Host "[!] index.html not found" -ForegroundColor Red
}

# 6. Move job-alert.yml into .github\workflows\
if (Test-Path "job-alert.yml") {
    if (-not (Test-Path ".github\workflows")) {
        New-Item -ItemType Directory -Path ".github\workflows" -Force | Out-Null
    }
    Move-Item -Force "job-alert.yml" ".github\workflows\job-alert.yml"
    Write-Host "[+] Moved job-alert.yml -> .github\workflows\job-alert.yml" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Final structure ===" -ForegroundColor Cyan
Get-ChildItem -Recurse | Where-Object { $_.Name -notlike "__pycache__*" -and $_.FullName -notlike "*__pycache__*" } | Select-Object FullName

Write-Host ""
Write-Host "=== Done! Now run: ===" -ForegroundColor Cyan
Write-Host "  python main.py --dry-run" -ForegroundColor White
Write-Host ""
