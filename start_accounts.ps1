# User-operated launcher. No existing processes are stopped; no model secret file is written.
[CmdletBinding()]
param([switch]$PublicPreview,[switch]$WithoutModel)
$ErrorActionPreference='Stop'
$accountRoot=[IO.Path]::GetFullPath($PSScriptRoot)
$accountPython='C:\Users\gyk11\AppData\Local\Programs\Python\Python313\python.exe'
$accountPort=8796
$accountTunnel=$null
$accountServer=$null
$accountPreviousKey=$env:DEEPSEEK_API_KEY
Push-Location $accountRoot
try {
    if(Get-NetTCPConnection -State Listen -LocalPort $accountPort -ErrorAction SilentlyContinue){throw '8796 is occupied; no process was stopped.'}
    & $accountPython setup_accounts.py --check
    if($LASTEXITCODE -ne 0){
        & $accountPython setup_accounts.py
        if($LASTEXITCODE -ne 0){throw 'Account setup not completed.'}
    }
    if($WithoutModel){$env:DEEPSEEK_API_KEY=''}
    elseif(-not $env:DEEPSEEK_API_KEY){
        $accountSecure=Read-Host 'DeepSeek API key (hidden; process memory only)' -AsSecureString
        $accountPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($accountSecure)
        try{$env:DEEPSEEK_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($accountPointer)}
        finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($accountPointer);$accountSecure.Dispose()}
        if(-not $env:DEEPSEEK_API_KEY){throw 'No model key entered. Use -WithoutModel for a no-cost account test.'}
    }
    if(-not $PublicPreview){
        & $accountPython app_server.py --port $accountPort --accounts
        return
    }
    $accountCloud=Join-Path $accountRoot 'data/life/tools/cloudflared.exe'
    if(-not(Test-Path -LiteralPath $accountCloud)){throw 'Portable cloudflared is missing; nothing was installed.'}
    $accountStamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    $accountLog=Join-Path $accountRoot "data/life/account-tunnel-$accountStamp.log"
    # The tunnel does not need the model key in its inherited environment.
    $accountRuntimeKey=$env:DEEPSEEK_API_KEY
    $env:DEEPSEEK_API_KEY=''
    try{$accountTunnel=Start-Process -FilePath $accountCloud -ArgumentList @('tunnel','--url',"http://127.0.0.1:$accountPort",'--no-autoupdate','--loglevel','info','--logfile',('"'+$accountLog+'"')) -WorkingDirectory $accountRoot -WindowStyle Hidden -PassThru}
    finally{$env:DEEPSEEK_API_KEY=$accountRuntimeKey;$accountRuntimeKey=$null}
    $accountDeadline=(Get-Date).AddSeconds(60)
    $accountOrigin=''
    while((Get-Date) -lt $accountDeadline){
        if($accountTunnel.HasExited){throw 'Tunnel exited before URL generation.'}
        if(Test-Path -LiteralPath $accountLog){$accountOrigin=[regex]::Match([string](Get-Content -LiteralPath $accountLog -Raw),'https://[a-z0-9-]+\.trycloudflare\.com').Value;if($accountOrigin){break}}
        Start-Sleep -Milliseconds 500
    }
    if(-not $accountOrigin){throw 'No tunnel URL returned within 60 seconds.'}
    $accountOut=Join-Path $accountRoot "data/life/account-server-$accountStamp.out.log"
    $accountErr=Join-Path $accountRoot "data/life/account-server-$accountStamp.err.log"
    $accountServer=Start-Process -FilePath $accountPython -ArgumentList @('app_server.py','--port',"$accountPort",'--accounts','--preview-origin',$accountOrigin) -WorkingDirectory $accountRoot -WindowStyle Hidden -RedirectStandardOutput $accountOut -RedirectStandardError $accountErr -PassThru
    $accountStarted=$accountServer.StartTime
    $env:DEEPSEEK_API_KEY=$accountPreviousKey
    $accountReady=$false
    $accountDeadline=(Get-Date).AddSeconds(300)
    $accountLastError=''
    Write-Host 'Waiting up to five minutes for the new public hostname. TLS certificate checks remain enabled.'
    while((Get-Date) -lt $accountDeadline){
        if($accountServer.HasExited -or $accountTunnel.HasExited){throw 'A new preview process exited; check private logs.'}
        $accountDiagnosticHint=''
        try{
            if(Get-Command curl.exe -ErrorAction SilentlyContinue){
                # Normal certificate verification; no insecure TLS fallback.
                $accountPage=& curl.exe --fail --silent --show-error --max-time 10 ($accountOrigin+'/explore/') 2>$null
                if($LASTEXITCODE -ne 0){$accountDiagnosticHint='curl exit '+$LASTEXITCODE;if($LASTEXITCODE -eq 6){$accountDiagnosticHint+=' (DNS not yet resolvable)'};throw 'Public page transport not ready'}
                $accountStateRaw=& curl.exe --fail --silent --show-error --max-time 10 ($accountOrigin+'/api/account/me') 2>$null
                if($LASTEXITCODE -ne 0){$accountDiagnosticHint='curl exit '+$LASTEXITCODE;throw 'Public account transport not ready'}
                $accountState=($accountStateRaw -join "`n") | ConvertFrom-Json
                $accountPageReady=($accountPage -join "`n").Contains('id="ask-form"')
            }else{
                $accountPage=Invoke-WebRequest ($accountOrigin+'/explore/') -UseBasicParsing -TimeoutSec 8
                $accountState=Invoke-RestMethod ($accountOrigin+'/api/account/me') -TimeoutSec 8
                $accountPageReady=$accountPage.StatusCode -eq 200 -and $accountPage.Content.Contains('id="ask-form"')
            }
            if($accountPageReady -and $accountState.enabled -and -not $accountState.user){$accountReady=$true;break}
        }catch{
            $accountDiagnostic=$_.Exception.GetType().Name
            if($accountDiagnosticHint){$accountDiagnostic=$accountDiagnosticHint}
            if($_.Exception.Response){$accountDiagnostic+=' HTTP '+[int]$_.Exception.Response.StatusCode}
            if($accountDiagnostic -ne $accountLastError){Write-Host ('Waiting for public verification: '+$accountDiagnostic);$accountLastError=$accountDiagnostic}
        }
        Start-Sleep -Milliseconds 500
    }
    if(-not $accountReady){throw 'Public HTTP not verified; no usable link claimed.'}
    Write-Host 'READY: account login enabled; personal chats are not public.' -ForegroundColor Green
    Write-Host ($accountOrigin+'/explore/?art=atelier')
    Write-Host ('Preview expiry (approximately): '+$accountStarted.AddHours(2).ToString('yyyy-MM-dd HH:mm'))
    Write-Host "New server PID: $($accountServer.Id); tunnel PID: $($accountTunnel.Id)"
    Write-Host 'Only page/account-status HTTP was checked. Test login and AI with your own account; keep the computer awake.'
    Write-Host 'This window owns the two new processes. Ctrl+C stops them; existing services are untouched.'
    $accountEnd=$accountStarted.AddHours(2)
    while((Get-Date) -lt $accountEnd -and -not $accountServer.HasExited -and -not $accountTunnel.HasExited){Start-Sleep -Seconds 2}
} finally {
    $env:DEEPSEEK_API_KEY=$accountPreviousKey
    $accountPreviousKey=$null
    foreach($accountOwned in @($accountServer,$accountTunnel)){if($null -ne $accountOwned -and -not $accountOwned.HasExited){$accountOwned.Kill()}}
    Pop-Location
}
