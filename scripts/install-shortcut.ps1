<#
    Puts a "UK Inflation Dashboard" shortcut on the desktop.

        powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1

    Run it again at any time to repair or update the shortcut. Pass -Remove to
    delete it.
#>

param(
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Desktop = [Environment]::GetFolderPath('Desktop')
$LinkPath = Join-Path $Desktop 'UK Inflation Dashboard.lnk'
$Launcher = Join-Path $Root 'scripts\start-dashboard.ps1'
$Icon = Join-Path $Root 'assets\dashboard.ico'

if ($Remove) {
    if (Test-Path -LiteralPath $LinkPath) {
        Remove-Item -LiteralPath $LinkPath -Force
        Write-Host "Removed $LinkPath"
    } else {
        Write-Host "Nothing to remove."
    }
    return
}

if (-not (Test-Path $Launcher)) {
    throw "Launcher not found at $Launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($LinkPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
# The launcher path is quoted: this project's folder contains spaces, and an
# unquoted -File argument gets split at the first one.
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $Launcher + '"'
$shortcut.WorkingDirectory = $Root
$shortcut.Description = 'Open the UK Inflation & Monetary Policy dashboard'
$shortcut.WindowStyle = 7   # minimised, so no console window flashes up
if (Test-Path $Icon) {
    $shortcut.IconLocation = "$Icon,0"
}
$shortcut.Save()

Write-Host "Created $LinkPath"
Write-Host "  -> $($shortcut.TargetPath)"
Write-Host "  -> launcher: $Launcher"
