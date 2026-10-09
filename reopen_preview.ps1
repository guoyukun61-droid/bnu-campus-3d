# Manual recovery after an execution-environment denial. Do not invoke automatically.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$previewRoot=[IO.Path]::GetFullPath($PSScriptRoot)
$previewCloud=[IO.Path]::GetFullPath((Join-Path $previewRoot 'data/life/tools/cloudflared.exe'))
$previewPython='C:\Users\gyk11\AppData\Local\Programs\Python\Python313\python.exe'
$previewLaunch=Join-Path $previewRoot 'start_preview.ps1'
foreach($previewFile in @($previewCloud,$previewPython,$previewLaunch)){
    if(-not(Test-Path -LiteralPath $previewFile -PathType Leaf)){throw "Missing dependency: $previewFile"}
}
# Resolve and validate every target before stopping anything. Never touch 8793/8795.
$previewListeners=@(Get-NetTCPConnection -State Listen -LocalPort 8794 -ErrorAction SilentlyContinue)
$previewTargets=@()
foreach($previewOwner in @($previewListeners.OwningProcess | Select-Object -Unique)){
    $previewProc=Get-CimInstance Win32_Process -Filter "ProcessId=$previewOwner"
    if(-not $previewProc -or $previewProc.ExecutablePath -ne $previewPython -or
       $previewProc.CommandLine -notmatch 'app_server\.py\s+--port\s+8794\s+--preview-origin\s+https://[a-z0-9-]+\.trycloudflare\.com\s*$'){
        throw 'Port 8794 is owned by an unrecognized process. Nothing stopped.'
    }
    $previewTargets+=$previewProc
}
$previewTargets+=@(Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" | Where-Object {
    $_.ExecutablePath -eq $previewCloud -and $_.CommandLine -match '--url\s+http://127\.0\.0\.1:8794(?:\s|$)'
})
foreach($previewProc in $previewTargets){
    $previewCurrent=Get-CimInstance Win32_Process -Filter "ProcessId=$($previewProc.ProcessId)"
    if(-not $previewCurrent){continue}
    if($previewCurrent.CreationDate -ne $previewProc.CreationDate -or $previewCurrent.CommandLine -ne $previewProc.CommandLine){
        throw 'Process identity changed. Recovery stopped.'
    }
    Stop-Process -Id $previewProc.ProcessId -ErrorAction Stop
    Write-Host "Stopped verified preview process: $($previewProc.ProcessId)"
}
& $previewLaunch
if(-not $?){throw 'Preview launch did not complete.'}
Write-Host 'For the atelier test, append ?art=atelier to the /explore/ link shown above.'
