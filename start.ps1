# AssemblyVision op Windows starten. Gebruik: .\start.ps1  (of .\start.ps1 -TestBeelden)
# Eerste keer: zet een virtuele omgeving op en installeert de Python-pakketten.
param([switch]$TestBeelden)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Eerste start: Python-omgeving maken..."
    py -3 -m venv backend\.venv
    & $python -m pip install --upgrade pip
    & $python -m pip install -r backend\requirements.txt
}

if (-not (Test-Path "frontend\dist\index.html")) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location frontend; npm install; npm run build; Pop-Location
    } else {
        Write-Error "frontend\dist ontbreekt en npm is niet geinstalleerd. Gebruik de zip met een gebouwde frontend."
    }
}

if ($TestBeelden) {
    $env:ASSEMBLYVISION_TEST_SOURCE = "$PSScriptRoot\spike\scenes"
    & $python spike\make_scenes.py spike\scenes
    & $python spike\turn_clip.py spike\scenes
    & $python spike\demo_clip.py spike\scenes
}

Write-Host "AssemblyVision: http://127.0.0.1:8420 (stoppen met Ctrl+C)"
Set-Location backend
& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8420
