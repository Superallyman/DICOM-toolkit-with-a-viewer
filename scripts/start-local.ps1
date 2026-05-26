Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$ohifIndex = Join-Path $repoRoot ".runtime\ohif-dist\index.html"

if (-not (Test-Path $ohifIndex)) {
  Write-Host "OHIF dist is missing. Building the viewer first..."
  & (Join-Path $PSScriptRoot "build-ohif.ps1")
}

Push-Location $repoRoot
try {
  docker compose up -d --build
  docker compose ps
}
finally {
  Pop-Location
}

Write-Host "DICOM Toolkit App is available at http://localhost:8080"
