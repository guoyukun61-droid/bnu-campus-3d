param([switch]$WithoutModel)
$ErrorActionPreference = 'Stop'
$appPython = 'C:\Users\gyk11\AppData\Local\Programs\Python\Python313\python.exe'
if (!(Test-Path -LiteralPath $appPython)) { throw 'Project Python was not found. Use the existing project Python environment.' }
if (Get-NetTCPConnection -LocalPort 8793 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host 'Port 8793 is already listening. Existing app: http://127.0.0.1:8793/'
    return
}
$previousKey = $env:DEEPSEEK_API_KEY
try {
    if ($WithoutModel) { $env:DEEPSEEK_API_KEY = '' }
    elseif (!$env:DEEPSEEK_API_KEY) {
        $secureKey = Read-Host 'DeepSeek API key (hidden, process memory only)' -AsSecureString
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        try { $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer); $secureKey.Dispose() }
    }
    Push-Location $PSScriptRoot
    try { & $appPython app_server.py --port 8793 }
    finally { Pop-Location }
} finally {
    $env:DEEPSEEK_API_KEY = $previousKey
    $previousKey = $null
}
