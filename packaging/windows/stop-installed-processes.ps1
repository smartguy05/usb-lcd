param([Parameter(Mandatory=$true)][string]$InstallDir)
$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\') + '\'

function Get-InstalledProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $path = $_.ExecutablePath
        $path -and $path.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)
    })
}

# The daemon normally exits through its control socket before this helper runs.
# MCP servers and hook interpreters can be longer lived, so stop only processes
# whose executable is physically inside this application's install directory.
Get-InstalledProcesses | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if ((Get-InstalledProcesses).Count -eq 0) { exit 0 }
    Start-Sleep -Milliseconds 250
}

$remaining = Get-InstalledProcesses
Write-Error ("Processes still running from {0}: {1}" -f $InstallDir, (($remaining.ProcessId) -join ', '))
exit 1
