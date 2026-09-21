$ErrorActionPreference = 'Stop'
$campusReady = $false
try { $campusReady = (Invoke-RestMethod 'http://127.0.0.1:8786/api/health' -TimeoutSec 2).storage -eq 'SQLite' } catch {}
if (-not $campusReady) {
    $campusScript = Join-Path $PSScriptRoot 'campus_server.py'
    Start-Process -FilePath 'C:\Users\gyk11\AppData\Local\Programs\Python\Python313\python.exe' -ArgumentList @(('"' + $campusScript + '"'), '--port', '8786') -WindowStyle Hidden
    Start-Sleep -Milliseconds 900
}
Start-Process 'http://127.0.0.1:8786/information/index.html'
