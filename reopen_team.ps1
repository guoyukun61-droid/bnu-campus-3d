# User-run complete restart. -CheckOnly never stops or starts a process.
[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$taskCloud = Join-Path $taskRoot 'data/life/tools/cloudflared.exe'
$taskServer = Join-Path $taskRoot 'contribution_server.py'
$taskPython = 'C:\Users\gyk11\AppData\Local\Programs\Python\Python313\python.exe'
$taskPrivate = Join-Path $taskRoot 'data/life/contributions'
foreach ($taskFile in @($taskCloud, $taskServer, $taskPython)) {
    if (-not (Test-Path -LiteralPath $taskFile -PathType Leaf)) { throw "Missing dependency: $taskFile" }
}
if (-not (Test-Path -LiteralPath $taskPrivate -PathType Container)) { throw 'Private contribution directory is missing.' }

# Validate every affected process before stopping any process.
$taskListeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 8790,8792 })
$taskServices = @()
$taskServerPattern = '(?:^|\s)"?(?:' + [regex]::Escape($taskRoot + '\') + ')?contribution_server\.py"?(?=\s|$)'
foreach ($taskOwner in @($taskListeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
    $taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $taskOwner"
    if (-not $taskProcess -or $taskProcess.ExecutablePath -ne $taskPython -or
        $taskProcess.CommandLine -notmatch $taskServerPattern -or
        $taskProcess.CommandLine -notmatch '--team-open(?:\s|$)' -or
        $taskProcess.CommandLine -notmatch '--port\s+8790(?:\s|$)' -or
        $taskProcess.CommandLine -notmatch '--admin-port\s+8792(?:\s|$)') {
        throw "Port 8790/8792 is occupied by an unexpected process ($taskOwner). Nothing was stopped."
    }
    $taskServices += $taskProcess
}
if ($taskServices.Count -gt 1 -or @($taskListeners | Where-Object LocalAddress -ne '127.0.0.1').Count) {
    throw 'Unexpected listener layout. Nothing was stopped.'
}
$taskTunnels = @(Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" | Where-Object {
    $_.ExecutablePath -eq $taskCloud -and $_.CommandLine -match '\btunnel\b' -and
    $_.CommandLine -match '--url\s+"?http://127\.0\.0\.1:8790"?(?:\s|$)'
})
Write-Host ('Validated service PIDs: ' + (($taskServices | ForEach-Object ProcessId) -join ', '))
Write-Host ('Validated tunnel PIDs: ' + (($taskTunnels | ForEach-Object ProcessId) -join ', '))
if ($CheckOnly) { Write-Host 'CHECK ONLY passed. No process or data changed.'; return }

$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$taskLog = Join-Path $taskPrivate "tunnel-$taskStamp.log"
$taskStdout = Join-Path $taskPrivate "server-$taskStamp.out.log"
$taskStderr = Join-Path $taskPrivate "server-$taskStamp.err.log"
try {
    foreach ($taskProcess in @($taskTunnels) + @($taskServices)) {
        Stop-Process -Id $taskProcess.ProcessId
        Wait-Process -Id $taskProcess.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
        if (Get-Process -Id $taskProcess.ProcessId -ErrorAction SilentlyContinue) { throw 'An old process did not exit.' }
    }
    Write-Host 'Starting a new tunnel...'
    $taskNewTunnel = Start-Process -FilePath $taskCloud -ArgumentList @(
        'tunnel','--url','http://127.0.0.1:8790','--no-autoupdate','--logfile',('"' + $taskLog + '"')
    ) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru
    $taskOrigin = ''
    $taskDeadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $taskDeadline) {
        if ($taskNewTunnel.HasExited) { throw 'Tunnel exited before creating a URL.' }
        if (Test-Path -LiteralPath $taskLog) {
            $taskText = Get-Content -LiteralPath $taskLog -Raw -ErrorAction SilentlyContinue
            $taskOrigin = [regex]::Match([string]$taskText, 'https://[a-z0-9-]+\.trycloudflare\.com').Value
            if ($taskOrigin) { break }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $taskOrigin) { throw 'No tunnel URL received within 60 seconds.' }
    Write-Host 'Starting contribution service with the new address...'
    $taskNewService = Start-Process -FilePath $taskPython -ArgumentList @(
        'contribution_server.py','--team-open','--port','8790','--admin-port','8792','--origin',$taskOrigin
    ) -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput $taskStdout -RedirectStandardError $taskStderr -PassThru
    $taskReady = $false
    $taskReason = ''
    $taskDeadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $taskDeadline) {
        if ($taskNewService.HasExited) { throw "Contribution service exited. Check $taskStderr" }
        if ($taskNewTunnel.HasExited) { throw 'Tunnel exited during verification.' }
        try {
            $taskPage = Invoke-WebRequest -Uri ($taskOrigin + '/') -UseBasicParsing -TimeoutSec 8
            $taskScript = Invoke-WebRequest -Uri ($taskOrigin + '/app.js') -UseBasicParsing -TimeoutSec 8
            $taskAdmin = Invoke-WebRequest -Uri 'http://127.0.0.1:8792/' -UseBasicParsing -TimeoutSec 5
            if ($taskPage.StatusCode -eq 200 -and $taskPage.Content.Contains('id="login-form"') -and
                $taskScript.StatusCode -eq 200 -and $taskScript.Content.Contains('onlyChanged') -and $taskAdmin.StatusCode -eq 200) {
                $taskReady = $true; break
            }
            $taskReason = 'Unexpected page content.'
        } catch { $taskReason = $_.Exception.Message }
        Start-Sleep -Seconds 2
    }
    if (-not $taskReady) { throw "Public verification failed: $taskReason" }
    $taskStatus = [ordered]@{
        verified_at = (Get-Date).ToString('o'); origin = $taskOrigin
        tunnel_pid = $taskNewTunnel.Id; service_pid = $taskNewService.Id
        tunnel_log = $taskLog; server_error_log = $taskStderr
    }
    $taskStatusPath = Join-Path $taskPrivate "team-runtime-$taskStamp.json"
    [IO.File]::WriteAllText($taskStatusPath, ($taskStatus | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Write-Host ''
    Write-Host 'READY - public page and local admin verified.' -ForegroundColor Green
    Write-Host "Team URL: $taskOrigin"
    Write-Host 'Local admin: http://127.0.0.1:8792/'
    Write-Host 'Processes run in the background. Keep this computer awake and connected.'
    Write-Host "Runtime record: $taskStatusPath"
} catch {
    Write-Host 'NOT READY. Do not share an unverified URL.' -ForegroundColor Red
    Write-Host "Tunnel log: $taskLog"
    Write-Host "Service error log: $taskStderr"
    throw
}
