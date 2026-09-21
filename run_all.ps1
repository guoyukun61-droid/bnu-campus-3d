$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$blenderExe = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'

python (Join-Path $projectDir 'prepare_assets.py')
& $blenderExe --background --python (Join-Path $projectDir 'build_blender_scene.py')

Write-Host "完成：$projectDir\output"
