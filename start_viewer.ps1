param([ValidateSet('v5','reference','white')][string]$Edition = 'v5')
$ErrorActionPreference = 'Stop'
$viewerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$viewerPort = 8765
$viewerUrl = "http://127.0.0.1:$viewerPort/index.html?view=roofs&v=20260905v5"
if ($Edition -eq 'reference') { $viewerUrl = "http://127.0.0.1:$viewerPort/reference/index.html" }
if ($Edition -eq 'white') { $viewerUrl = "http://127.0.0.1:$viewerPort/white/index.html" }

$portReady = $false
try {
    $probe = Invoke-WebRequest -Uri $viewerUrl -Method Head -TimeoutSec 1 -UseBasicParsing
    $portReady = $probe.StatusCode -ge 200
} catch {
    $portReady = $false
}

if (-not $portReady) {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        Start-Process -FilePath $pythonLauncher.Source -ArgumentList @('-m', 'http.server', $viewerPort, '--bind', '127.0.0.1', '--directory', "`"$viewerRoot`"") -WindowStyle Hidden
    } else {
        $python = Get-Command python -ErrorAction Stop
        Start-Process -FilePath $python.Source -ArgumentList @('-m', 'http.server', $viewerPort, '--bind', '127.0.0.1', '--directory', "`"$viewerRoot`"") -WindowStyle Hidden
    }
    Start-Sleep -Milliseconds 900
}

Start-Process $viewerUrl
