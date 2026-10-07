# Run locally after reviewing. Keeps the existing tunnel/origin; no new public tunnel.
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskListener = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8790 -State Listen)
if ($taskListener.Count -ne 1) { throw 'Expected one contribution listener on 8790.' }
$taskProc = Get-CimInstance Win32_Process -Filter "ProcessId = $($taskListener[0].OwningProcess)"
if ($taskProc.CommandLine -notmatch 'contribution_server\.py.*--team-open' -or $taskProc.ExecutablePath -notmatch 'python(?:313)?\.exe$') { throw 'Unexpected process; no process stopped.' }
$taskOriginMatch = [regex]::Match($taskProc.CommandLine, '--origin\s+(https://[a-z0-9-]+\.trycloudflare\.com)')
if (-not $taskOriginMatch.Success) { throw 'Existing origin not recognized; no process stopped.' }
$taskOrigin = $taskOriginMatch.Groups[1].Value
Stop-Process -Id $taskProc.ProcessId
Wait-Process -Id $taskProc.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
Start-Process -FilePath $taskProc.ExecutablePath -ArgumentList @('contribution_server.py','--team-open','--port','8790','--admin-port','8792','--origin',$taskOrigin) -WorkingDirectory $taskRoot -WindowStyle Hidden
Write-Host 'Contribution service restarted. Refresh the existing team page. Local admin: http://127.0.0.1:8792/'
