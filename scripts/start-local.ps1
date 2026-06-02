Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$ohifIndex = Join-Path $repoRoot ".runtime\ohif-dist\index.html"

function Invoke-CheckedNative {
  param(
    [Parameter(Mandatory = $true)]
    [scriptblock] $Command,
    [Parameter(Mandatory = $true)]
    [string] $Description
  )

  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

if (-not (Test-Path $ohifIndex)) {
  Write-Host "OHIF dist is missing. Building the viewer first..."
  & (Join-Path $PSScriptRoot "build-ohif.ps1")
}

Push-Location $repoRoot
try {
  Invoke-CheckedNative { docker compose up -d --build } "Docker Compose startup"
  Invoke-CheckedNative { docker compose ps } "Docker Compose status"
}
finally {
  Pop-Location
}

Write-Host "DICOM Toolkit App is available at http://localhost:8080"
