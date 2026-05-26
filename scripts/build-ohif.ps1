Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$ohifVersion = "v3.12.2"
$sourceRoot = Join-Path $repoRoot ".external\ohif-viewer"
$distRoot = Join-Path $repoRoot ".runtime\ohif-dist"

if (-not (Test-Path (Join-Path $sourceRoot "package.json"))) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $sourceRoot) | Out-Null
  git clone --depth 1 --branch $ohifVersion https://github.com/OHIF/Viewers.git $sourceRoot
}

Push-Location $sourceRoot
try {
  if (-not (Test-Path "node_modules")) {
    yarn install --frozen-lockfile
  }

  yarn run build
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
