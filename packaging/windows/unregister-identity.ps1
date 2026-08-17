param([Parameter(Mandatory=$true)][string]$CertificatePath)
$ErrorActionPreference = "Stop"
Get-AppxPackage -Name "USBLCDDashboard.Personal" -ErrorAction SilentlyContinue | Remove-AppxPackage
if (Test-Path -LiteralPath $CertificatePath) {
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CertificatePath)
    $installed = "Cert:\LocalMachine\TrustedPeople\" + $certificate.Thumbprint
    if (Test-Path -LiteralPath $installed) {
        # certutil avoids certificate-provider UI during uninstall.
        & certutil.exe -delstore TrustedPeople $certificate.Thumbprint | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not remove the notification identity certificate (certutil exit $LASTEXITCODE)" }
    }
}
