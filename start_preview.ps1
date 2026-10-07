# Manual local launcher. Never invoked automatically after a denied launch.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$previewRoot=[IO.Path]::GetFullPath($PSScriptRoot)
$previewPython='C:\Users\gyk11\AppData\Local\Programs\Python\Python313\python.exe'
$previewCloud=Join-Path $previewRoot 'data/life/tools/cloudflared.exe'
foreach($file in @($previewPython,$previewCloud,(Join-Path $previewRoot 'app_server.py'))){
    if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw "Missing dependency: $file"}
}
if(Get-NetTCPConnection -State Listen -LocalPort 8794 -ErrorAction SilentlyContinue){throw '8794 is occupied. No process was stopped.'}
$previewStamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$previewLog=Join-Path $previewRoot "data/life/preview-$previewStamp-tunnel.log"
$previewOut=Join-Path $previewRoot "data/life/preview-$previewStamp-server.out.log"
$previewErr=Join-Path $previewRoot "data/life/preview-$previewStamp-server.err.log"
$previewTunnel=$null
$previewServer=$null
try{
    $previewTunnel=Start-Process -FilePath $previewCloud -ArgumentList @('tunnel','--url','http://127.0.0.1:8794','--no-autoupdate','--loglevel','info','--logfile',('"'+$previewLog+'"')) -WorkingDirectory $previewRoot -WindowStyle Hidden -PassThru
    $previewDeadline=(Get-Date).AddSeconds(60)
    $previewOrigin=''
    while((Get-Date) -lt $previewDeadline){
        if($previewTunnel.HasExited){throw 'Tunnel exited before URL generation.'}
        if(Test-Path -LiteralPath $previewLog){
            $previewOrigin=[regex]::Match([string](Get-Content -LiteralPath $previewLog -Raw),'https://[a-z0-9-]+\.trycloudflare\.com').Value
            if($previewOrigin){break}
        }
        Start-Sleep -Milliseconds 500
    }
    if(-not $previewOrigin){throw 'No temporary URL was returned within 60 seconds.'}
    if(Get-NetTCPConnection -State Listen -LocalPort 8794 -ErrorAction SilentlyContinue){throw '8794 became occupied; no existing process will be stopped.'}
    $previewServer=Start-Process -FilePath $previewPython -ArgumentList @('app_server.py','--port','8794','--preview-origin',$previewOrigin) -WorkingDirectory $previewRoot -WindowStyle Hidden -RedirectStandardOutput $previewOut -RedirectStandardError $previewErr -PassThru
    $previewReady=$false
    $previewDeadline=(Get-Date).AddSeconds(60)
    while((Get-Date) -lt $previewDeadline){
        if($previewServer.HasExited -or $previewTunnel.HasExited){throw 'Preview process exited; inspect private logs.'}
        try{
            $page=Invoke-WebRequest ($previewOrigin+'/explore/') -UseBasicParsing -TimeoutSec 8
            $status=Invoke-RestMethod ($previewOrigin+'/api/agent/status') -TimeoutSec 8
            if($page.StatusCode -eq 200 -and $page.Content.Contains('id="ask-form"') -and $status.preview -and -not $status.configured){$previewReady=$true;break}
        }catch{}
        Start-Sleep -Seconds 1
    }
    if(-not $previewReady){throw 'Public HTTP verification failed; no usable link is being claimed.'}
    Write-Host 'READY: map, menu and rule-based candidates; AI chat disabled.' -ForegroundColor Green
    Write-Host ($previewOrigin+'/explore/')
    Write-Host ('Expires approximately: '+(Get-Date).AddHours(2).ToString('yyyy-MM-dd HH:mm'))
    Write-Host "Preview server PID: $($previewServer.Id); tunnel PID: $($previewTunnel.Id)"
    Write-Host 'Keep this computer awake. The URL is accessible to anyone who receives it.'
    Write-Host 'Public HTTP verified; mobile network, model loading and API behavior still need browser testing.'
}catch{
    foreach($ownedProcess in @($previewServer,$previewTunnel)){
        if($null -ne $ownedProcess -and -not $ownedProcess.HasExited){$ownedProcess.Kill()}
    }
    throw
}
