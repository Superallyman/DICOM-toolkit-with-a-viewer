Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$ohifVersion = "v3.12.2"
$lernaVersion = "9.0.4"
$bunVersion = "1.2.23"
$sourceRoot = Join-Path $repoRoot ".external\ohif-viewer"
$distRoot = Join-Path $repoRoot ".runtime\ohif-dist"

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

if (-not (Test-Path (Join-Path $sourceRoot "package.json"))) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $sourceRoot) | Out-Null
  Invoke-CheckedNative { git clone --depth 1 --branch $ohifVersion https://github.com/OHIF/Viewers.git $sourceRoot } "OHIF clone"
}

if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
  throw @"
Bun is required to build OHIF $ohifVersion, but 'bun' is not on PATH.

Install the pinned Bun version used by OHIF:
  npm install -g bun@$bunVersion

Then open a new PowerShell window and run:
  .\scripts\build-ohif.ps1
"@
}

Push-Location $sourceRoot
try {
  $lernaBin = Join-Path $sourceRoot "node_modules\.bin\lerna.cmd"
  if ((-not (Test-Path "node_modules")) -or (-not (Test-Path $lernaBin))) {
    Write-Host "Installing OHIF dependencies..."
    Invoke-CheckedNative { yarn install --frozen-lockfile --network-timeout 600000 } "OHIF dependency install"
  }

  if (-not (Test-Path $lernaBin)) {
    Write-Host "Installing pinned Lerna CLI..."
    Invoke-CheckedNative { yarn add --dev --ignore-workspace-root-check "lerna@$lernaVersion" --network-timeout 600000 } "OHIF Lerna install"
  }

  Invoke-CheckedNative { yarn run build } "OHIF build"
}
finally {
  Pop-Location
}

$sourceDist = Join-Path $sourceRoot "platform\app\dist"
$sourceIndex = Join-Path $sourceDist "index.html"
if (-not (Test-Path $sourceIndex)) {
  throw "OHIF build completed without creating $sourceIndex"
}

if (Test-Path $distRoot) {
  Remove-Item -LiteralPath $distRoot -Recurse -Force
}

New-Item -ItemType Directory -Force $distRoot | Out-Null
Copy-Item -Path (Join-Path $sourceDist "*") -Destination $distRoot -Recurse -Force

Write-Host "OHIF viewer build is ready at .runtime\ohif-dist"
