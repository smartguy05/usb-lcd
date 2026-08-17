param(
    [Parameter(Mandatory=$true)][string]$PayloadDir,
    [Parameter(Mandatory=$true)][string]$Version
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$sdk = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Directory |
    Where-Object { $_.Name -match '^\d+\.\d+' } | Sort-Object Name -Descending | Select-Object -First 1
if (-not $sdk) { throw "Windows SDK tools were not found" }
$tools = Join-Path $sdk.FullName "x64"
$makeAppx = Join-Path $tools "makeappx.exe"
$signTool = Join-Path $tools "signtool.exe"
$manifestTool = Join-Path $tools "mt.exe"
foreach ($tool in @($makeAppx, $signTool, $manifestTool)) {
    if (-not (Test-Path $tool)) { throw "Required Windows SDK tool missing: $tool" }
}

$subject = "CN=USB LCD Dashboard Personal"
$certificate = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $subject -and $_.NotAfter -gt (Get-Date).AddDays(30) } |
    Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $certificate) {
    $certificate = New-SelfSignedCertificate -Type CodeSigningCert -Subject $subject `
        -CertStoreLocation Cert:\CurrentUser\My -KeyExportPolicy NonExportable `
        -NotAfter (Get-Date).AddYears(5)
}

$identityDir = Join-Path $PayloadDir "identity-build"
if (Test-Path $identityDir) { Remove-Item -LiteralPath $identityDir -Recurse -Force }
New-Item -ItemType Directory -Path $identityDir | Out-Null
$fourPartVersion = ($Version.Split('.') + @('0','0','0','0'))[0..3] -join '.'
$manifest = (Get-Content (Join-Path $root "identity\AppxManifest.xml.in") -Raw).Replace("@VERSION@", $fourPartVersion)
Set-Content -LiteralPath (Join-Path $identityDir "AppxManifest.xml") -Value $manifest -Encoding utf8
$exeManifest = (Get-Content (Join-Path $root "identity\pythonw.exe.manifest.in") -Raw).Replace("@VERSION@", $fourPartVersion)
$exeManifestPath = Join-Path $identityDir "pythonw.exe.manifest"
Set-Content -LiteralPath $exeManifestPath -Value $exeManifest -Encoding utf8

& $manifestTool -manifest $exeManifestPath "-outputresource:$PayloadDir\pythonw.exe;#1"
if ($LASTEXITCODE) { throw "mt.exe failed with exit code $LASTEXITCODE" }
Copy-Item (Join-Path (Split-Path $root -Parent) "..\screencap.png") (Join-Path $PayloadDir "screencap.png") -Force
Copy-Item (Join-Path $PayloadDir "screencap.png") (Join-Path $identityDir "screencap.png") -Force
$package = Join-Path $PayloadDir "USB-LCD-Dashboard.Identity.msix"
& $makeAppx pack /o /nv /d $identityDir /p $package
if ($LASTEXITCODE) { throw "makeappx.exe failed with exit code $LASTEXITCODE" }
& $signTool sign /fd SHA256 /sha1 $certificate.Thumbprint $package
if ($LASTEXITCODE) { throw "signtool.exe failed with exit code $LASTEXITCODE" }
Export-Certificate -Cert $certificate -FilePath (Join-Path $PayloadDir "USB-LCD-Dashboard.Identity.cer") -Force | Out-Null
Remove-Item -LiteralPath $identityDir -Recurse -Force
