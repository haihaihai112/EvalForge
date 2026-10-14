#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port = 8791,
    [switch]$SkipInstall,
    [switch]$SetupOnly,
    [string]$EnvironmentPath = (Join-Path $PSScriptRoot '.venv')
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $EnvironmentPath 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskSystemPython = (Get-Command python -ErrorAction Stop).Source
    & $taskSystemPython -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
    if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.11 或更高版本。' }
    & $taskSystemPython -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw '创建 Python 虚拟环境失败。' }
}
if (-not $SkipInstall) {
    & $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络或 pip 镜像设置。' }
}
& $taskPython -c 'import fastapi,uvicorn,httpx,pydantic,pypdf; print("EvalForge dependencies ready")'
if ($LASTEXITCODE -ne 0) { throw '依赖未安装完整，请去掉 -SkipInstall 重试。' }
if ($SetupOnly) { return }
Write-Host "EvalForge 本地地址：http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host '首次启动将生成虚构 SOP、50 题演示集和一次双版本回归，约需数秒。Ctrl+C 停止。'
& $taskPython -m uvicorn evalforge.app:create_app --factory --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw "启动失败。若端口占用，请使用 -Port 指定其他端口。" }
