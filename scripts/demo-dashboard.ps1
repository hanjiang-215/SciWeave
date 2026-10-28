<#
.SYNOPSIS
  Bring up the SciWeave read-only dashboard against real data.

.DESCRIPTION
  Starts three processes and waits until each answers its health probe:

    1. research-map dashboard source  (/api/dashboard/source/mapping)
    2. dashboard-api                  (/api/dashboard/snapshot)
    3. web-ui Vite dev server         (the page itself)

  The browser then renders `mode: live` instead of the bundled fixture
  snapshot. Ports, hosts and the TerminusDB connection all come from the
  environment; the defaults below are only development conveniences.

  The seed step is idempotent: when SQLite already records a current formal
  revision, the existing domain is reused. Pass -ResetSeed to rebuild it.

  Every child PID is written to .demo-dashboard.json next to this script so
  that -Stop (or a later run) can clean up exactly what this script started.

.PARAMETER Stop
  Stop everything recorded in .demo-dashboard.json and exit.

.PARAMETER ResetSeed
  Drop the TerminusDB seed database and rebuild the demo route.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\demo-dashboard.ps1 -Stop
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$ResetSeed
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $PSScriptRoot '.demo-dashboard.json'

$mapDir = Join-Path $root 'sci-weave\centre-control\research-map'
$dashDir = Join-Path $root 'sci-weave\centre-control\dashboard-api'
$webDir = Join-Path $root 'sci-weave\centre-control\web-ui'

function Get-Setting {
    param([string]$Name, [string]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim()
}

function Wait-ForProbe {
    param([string]$Url, [int]$TimeoutSeconds = 30, [string]$Label)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return $true }
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    Write-Error "$Label did not become ready at $Url within ${TimeoutSeconds}s"
    return $false
}

function Stop-Recorded {
    if (-not (Test-Path $statePath)) {
        Write-Host '没有找到 .demo-dashboard.json，没有需要停止的进程。'
        return
    }
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
    $entries = @($state.processes)
    foreach ($entry in $entries) {
        if (-not $entry.pid) { continue }
        # uv 创建的 venv 里 python.exe 是启动器，真实解释器是它的子进程；
        # 单杀启动器会留下仍在监听的子进程，所以按进程树杀。
        & taskkill /T /F /PID $entry.pid 2>&1 | Out-Null
        if ($entry.url) {
            $port = ([uri]$entry.url).Port
            Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        }
        Write-Host "已停止 $($entry.name) (PID $($entry.pid))"
    }
    Remove-Item $statePath -Force
}

function Test-PortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$connection
}

if ($Stop) {
    Stop-Recorded
    exit 0
}

# --- settings -------------------------------------------------------------
$mappingHost = Get-Setting 'SCIWEAVE_MAPPING_DASHBOARD_HOST' '127.0.0.1'
$mappingPort = [int](Get-Setting 'SCIWEAVE_MAPPING_DASHBOARD_PORT' '8701')
$dashboardHost = Get-Setting 'SCIWEAVE_DASHBOARD_HOST' '127.0.0.1'
$dashboardPort = [int](Get-Setting 'SCIWEAVE_DASHBOARD_PORT' '8702')
$webHost = Get-Setting 'VITE_DEV_HOST' '127.0.0.1'
$webPort = [int](Get-Setting 'VITE_DEV_PORT' '5173')

$terminusUrl = Get-Setting 'SCIWEAVE_MAPPING_TERMINUSDB_URL' 'http://127.0.0.1:6363'
$terminusStore = Get-Setting 'SCIWEAVE_MAPPING_TERMINUSDB_STORE' 'admin'
$terminusDatabase = Get-Setting 'SCIWEAVE_MAPPING_TERMINUSDB_DATABASE' 'sciweave_dashboard_demo'
$terminusUser = Get-Setting 'SCIWEAVE_MAPPING_TERMINUSDB_USERNAME' 'admin'
$terminusPassword = Get-Setting 'SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD' 'root'
$domainId = Get-Setting 'SCIWEAVE_MAPPING_DOMAIN_ID' 'iris-demo'
$sqlitePath = Get-Setting 'SCIWEAVE_MAPPING_SQLITE_PATH' (Join-Path $mapDir 'data\dashboard.sqlite')

$webOrigin = "http://${webHost}:${webPort}"

# --- preconditions --------------------------------------------------------
$mapPython = Join-Path $mapDir '.venv\Scripts\python.exe'
$dashPython = Join-Path $dashDir '.venv\Scripts\python.exe'
$viteEntry = Join-Path $webDir 'node_modules\vite\bin\vite.js'
foreach ($required in @($mapPython, $dashPython, $viteEntry)) {
    if (-not (Test-Path $required)) {
        Write-Error "缺少依赖：$required。先在各子项目执行 uv sync / npm install。"
    }
}

$terminusHealthy = $false
try {
    Invoke-WebRequest -Uri "$terminusUrl/api/ok" -UseBasicParsing -TimeoutSec 3 | Out-Null
    $terminusHealthy = $true
} catch {
    try {
        Invoke-WebRequest -Uri "$terminusUrl" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $terminusHealthy = $true
    } catch { $terminusHealthy = $false }
}
if (-not $terminusHealthy) {
    Write-Error "TerminusDB 不可达：$terminusUrl。先执行 docker compose -f sci-weave/service/terminusdb/compose.yaml up -d"
}

# 清理上一轮遗留，避免端口冲突后误判为"已就绪"。
Stop-Recorded

# --- seed ---------------------------------------------------------------
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sqlitePath) | Out-Null
$env:SCIWEAVE_MAPPING_TERMINUSDB_URL = $terminusUrl
$env:SCIWEAVE_MAPPING_TERMINUSDB_STORE = $terminusStore
$env:SCIWEAVE_MAPPING_TERMINUSDB_DATABASE = $terminusDatabase
$env:SCIWEAVE_MAPPING_TERMINUSDB_USERNAME = $terminusUser
$env:SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD = $terminusPassword
$env:SCIWEAVE_MAPPING_DOMAIN_ID = $domainId
$env:SCIWEAVE_MAPPING_SQLITE_PATH = $sqlitePath

$seedArgs = @((Join-Path $PSScriptRoot 'seed_dashboard_demo.py'))
if ($ResetSeed) { $seedArgs += '--reset' }
Write-Host '--- 播种演示域 ---'
& $mapPython @seedArgs
if ($LASTEXITCODE -ne 0) { Write-Error '种子脚本失败，看板不会显示真实数据。' }

# --- start processes -----------------------------------------------------
$processes = @()

$env:SCIWEAVE_MAPPING_DASHBOARD_MODE = '1'
$env:SCIWEAVE_MAPPING_DASHBOARD_HOST = $mappingHost
$env:SCIWEAVE_MAPPING_DASHBOARD_PORT = "$mappingPort"
$env:SCIWEAVE_MAPPING_DASHBOARD_TOKEN = Get-Setting 'SCIWEAVE_MAPPING_DASHBOARD_TOKEN' ''
$env:PYTHONPATH = Join-Path $mapDir 'src'
$mappingProcess = Start-Process -FilePath $mapPython -ArgumentList 'src\main.py' `
    -WorkingDirectory $mapDir -PassThru -WindowStyle Hidden
$processes += [pscustomobject]@{ name = 'mapping-dashboard-source'; pid = $mappingProcess.Id; url = "http://${mappingHost}:${mappingPort}" }

Wait-ForProbe -Url "http://${mappingHost}:${mappingPort}/health" -Label 'mapping dashboard source' | Out-Null

$env:SCIWEAVE_DASHBOARD_HOST = $dashboardHost
$env:SCIWEAVE_DASHBOARD_PORT = "$dashboardPort"
$env:SCIWEAVE_DASHBOARD_CORS_ORIGIN = $webOrigin
$env:SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL = "http://${mappingHost}:${mappingPort}/api/dashboard/source/mapping"
if (Get-Setting 'SCIWEAVE_MAPPING_DASHBOARD_TOKEN' '') {
    $env:SCIWEAVE_DASHBOARD_SOURCE_MAPPING_TOKEN = Get-Setting 'SCIWEAVE_MAPPING_DASHBOARD_TOKEN' ''
}
$env:PYTHONPATH = Join-Path $dashDir 'src'
$dashboardProcess = Start-Process -FilePath $dashPython -ArgumentList 'src\main.py' `
    -WorkingDirectory $dashDir -PassThru -WindowStyle Hidden
$processes += [pscustomobject]@{ name = 'dashboard-api'; pid = $dashboardProcess.Id; url = "http://${dashboardHost}:${dashboardPort}" }

Wait-ForProbe -Url "http://${dashboardHost}:${dashboardPort}/health" -Label 'dashboard-api' | Out-Null

$env:VITE_DASHBOARD_API_URL = "http://${dashboardHost}:${dashboardPort}/"
$env:VITE_DEV_HOST = $webHost
$env:VITE_DEV_PORT = "$webPort"
$webProcess = Start-Process -FilePath 'node' -ArgumentList @($viteEntry, '--host', $webHost, '--port', "$webPort", '--strictPort') `
    -WorkingDirectory $webDir -PassThru -WindowStyle Hidden
$processes += [pscustomobject]@{ name = 'web-ui'; pid = $webProcess.Id; url = $webOrigin }

# --- persist and report --------------------------------------------------
[pscustomobject]@{ processes = $processes } | ConvertTo-Json -Depth 4 |
    Set-Content -Path $statePath -Encoding utf8

try {
    Wait-ForProbe -Url "$webOrigin/" -Label 'web-ui' -TimeoutSeconds 40 | Out-Null
    $snapshot = Invoke-WebRequest -Uri "http://${dashboardHost}:${dashboardPort}/api/dashboard/snapshot" -UseBasicParsing -TimeoutSec 8
    $payload = $snapshot.Content | ConvertFrom-Json
    $mappingSource = $payload.sources | Where-Object { $_.id -eq 'mapping' }
    Write-Host ''
    Write-Host "模式      : $($payload.mode)"
    Write-Host "mapping   : $($mappingSource.status)"
    Write-Host "项目/任务 : $($payload.projects.Count) / $($payload.tasks.Count)"
    Write-Host "部分来源  : $($payload.partial)"
    Write-Host ''
    Write-Host "看板地址  : $webOrigin"
    Write-Host "快照接口  : http://${dashboardHost}:${dashboardPort}/api/dashboard/snapshot"
    Write-Host ''
    # 只装 Windows PowerShell 的机器上没有 pwsh，提示必须给出本机真能执行的命令。
    $hostExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { 'pwsh' } else { 'powershell' }
    Write-Host "停止      : $hostExe scripts/demo-dashboard.ps1 -Stop"
} catch {
    Write-Warning "看板已启动但自检失败：$($_.Exception.Message)"
    Write-Host "看板地址  : $webOrigin"
}
