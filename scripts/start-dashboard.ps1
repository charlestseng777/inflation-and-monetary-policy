<#
    Opens the UK Inflation dashboard in one click.

    Behaviour, in order:
      1. If deployed-url.txt exists at the project root, just open that address.
         (Once the site is on Render, put its URL in that file and this script
         stops needing a local server at all.)
      2. If the local server is already running, just open the browser.
      3. Otherwise start it, wait until it answers, then open the browser.

    -Refresh  scrape the ONS and Bank of England for new data first (~1 minute)

    Everything is invoked by absolute path, so the "&" in this project's folder
    name never reaches a command interpreter that would misread it.
#>

param(
    [switch]$Refresh
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root 'web'
$Port = 5173
$Url = "http://localhost:$Port"


function Quote {
    # Start-Process -ArgumentList does NOT quote array elements for you, so any
    # path containing a space arrives at the target program split in two. Every
    # path below therefore goes through here. (This project's own path contains
    # both spaces and an "&", so it fails loudly without it.)
    param([string]$Value)
    return '"' + $Value + '"'
}

function Show-Problem {
    param([string]$Message)
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        $Message, 'UK Inflation Dashboard', 'OK', 'Warning') | Out-Null
    exit 1
}

function Test-ServerUp {
    # An HTTP request rather than a raw socket check, for two reasons: vite
    # binds to "localhost", which resolves to IPv6 ::1 here and not to
    # 127.0.0.1 (a default TcpClient is an IPv4 socket and never sees it); and
    # a real response proves the dev server is ready to serve, not merely that
    # the port is open.
    param([int]$OnPort)
    try {
        Invoke-WebRequest -Uri "http://localhost:$OnPort" -UseBasicParsing `
            -TimeoutSec 3 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        # Any HTTP response at all — even an error page — means it is listening.
        if ($_.Exception.Response) { return $true }
        return $false
    }
}

function Find-Node {
    $command = Get-Command node -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
        (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'nodejs\node.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe')
    )) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Find-Python {
    foreach ($candidate in @(
        (Join-Path $env:USERPROFILE 'anaconda3\python.exe'),
        (Join-Path $env:USERPROFILE 'miniconda3\python.exe')
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*WindowsApps*') { return $command.Source }
    return $null
}


# --- 1. already deployed? then there is nothing to run locally --------------
$deployedFile = Join-Path $Root 'deployed-url.txt'
if (Test-Path $deployedFile) {
    $deployed = (Get-Content $deployedFile -Raw).Trim()
    if ($deployed) {
        Start-Process $deployed
        exit 0
    }
}

# --- 2. already running? then just show it ----------------------------------
if (Test-ServerUp -OnPort $Port) {
    Start-Process $Url
    exit 0
}

# --- 3. start it ------------------------------------------------------------
$node = Find-Node
if (-not $node) {
    Show-Problem @"
Node.js could not be found, so the dashboard cannot start.

Install it from nodejs.org, then double-click this shortcut again.
"@
}

$vite = Join-Path $Web 'node_modules\vite\bin\vite.js'
if (-not (Test-Path $vite)) {
    # First run on a fresh copy of the project: install dependencies. npm is
    # called through node directly rather than npm.cmd, which would hand the
    # folder path to cmd.exe and choke on the "&".
    $npmCli = Join-Path (Split-Path -Parent $node) 'node_modules\npm\bin\npm-cli.js'
    if (-not (Test-Path $npmCli)) {
        Show-Problem "Could not find npm next to Node.js at $npmCli."
    }
    Start-Process -FilePath $node -ArgumentList "$(Quote $npmCli) install" `
        -WorkingDirectory $Web -Wait -WindowStyle Minimized
}
if (-not (Test-Path $vite)) {
    Show-Problem "Installing the dashboard's dependencies did not succeed. Open $Web and run npm install to see the error."
}

if ($Refresh) {
    $python = Find-Python
    if ($python) {
        Start-Process -FilePath $python `
            -ArgumentList "$(Quote (Join-Path $Root 'fetcher\fetch.py')) --no-llm" `
            -WorkingDirectory $Root -Wait -WindowStyle Minimized
    }
}

# Copy the latest data into the site, then start the server minimised.
Start-Process -FilePath $node -ArgumentList (Quote (Join-Path $Web 'scripts\sync-data.mjs')) `
    -WorkingDirectory $Web -Wait -WindowStyle Hidden

Start-Process -FilePath $node `
    -ArgumentList "$(Quote $vite) --port $Port --strictPort" `
    -WorkingDirectory $Web -WindowStyle Minimized | Out-Null

# Wait for it to answer before opening the browser, so the first click never
# lands on a "can't reach this page".
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    if (Test-ServerUp -OnPort $Port) {
        Start-Sleep -Milliseconds 600
        Start-Process $Url
        exit 0
    }
    Start-Sleep -Milliseconds 400
}

Show-Problem @"
The dashboard server did not start within 60 seconds.

Try opening $Url in your browser — it may just be slow. If that fails, open
the minimised console window on the taskbar to see the error.
"@
