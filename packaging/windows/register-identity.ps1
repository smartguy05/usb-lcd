param(
    [Parameter(Mandatory=$true)][string]$ExternalLocation,
    [Parameter(Mandatory=$true)][string]$PackagePath,
    [Parameter(Mandatory=$true)][string]$CertificatePath
)
$ErrorActionPreference = "Stop"
# AppX accepts a self-signed package certificate from the local-machine
# TrustedPeople store. The installer runs elevated so certutil can update that
# store without invoking the certificate provider's interactive UI.
& certutil.exe -f -addstore TrustedPeople $CertificatePath | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not trust the notification identity certificate (certutil exit $LASTEXITCODE)" }
Get-AppxPackage -Name "USBLCDDashboard.Personal" -ErrorAction SilentlyContinue | Remove-AppxPackage
Add-AppxPackage -Path $PackagePath -ExternalLocation $ExternalLocation
