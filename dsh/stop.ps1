# 停止 dsh/start.ps1 拉起的全部 Python 角色与前端进程。
#
# 只按 dsh/pids/*.pid 里记录的 pid 精确停止，不误杀其他进程。
# 第三方服务（TerminusDB / Redpanda）默认保留；加 -StopDocker 一起停。
#
# 用法：pwsh -File dsh/stop.ps1 [-StopDocker]

[CmdletBinding()]
param([switch]$StopDocker)

$ErrorActionPreference = 'Stop'
$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot   = Split-Path -Parent $scriptDir
$pidsDir    = Join-Path $scriptDir 'pids'
$serviceDir = Join-Path $repoRoot 'sci-weave/service'

if (Test-Path $pidsDir) {
    $pidFiles = Get-ChildItem -Path $pidsDir -Filter '*.pid' -ErrorAction SilentlyContinue
    foreach ($f in $pidFiles) {
        $name = $f.BaseName
        $procId = (Get-Content -LiteralPath $f.FullName -Raw).Trim()
        if ($procId -match '^\d+$') {
            try {
                $p = Get-Process -Id ([int]$procId) -ErrorAction Stop
                Stop-Process -Id $p.Id -Force -ErrorAction Stop
                Write-Host ("停止 {0,-24} pid={1}" -f $name, $procId) -ForegroundColor Yellow
            } catch {
                Write-Host ("跳过 {0,-24} (pid={1} 已不存在)" -f $name, $procId) -ForegroundColor DarkGray
            }
        }
        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host '没有找到 pids 目录，可能未通过 start.ps1 启动。' -ForegroundColor DarkGray
}

# 兜底：按本栈固定端口清理仍监听的回环进程（pid 记录可能因 exe 包装而失准）。
# 不清理 Docker 的 wslrelay / com.docker.backend，它们属第三方服务端口转发。
$ports = 5173, 8702, 8710, 8711, 8720, 8721, 8730, 8740, 8750, 8760, 8761, 8762
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        try {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction Stop
            if ($proc.ProcessName -in @('wslrelay', 'com.docker.backend', 'vpnkit', 'Docker Desktop')) { continue }
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Write-Host ("清理端口 {0,-5} pid={1} ({2})" -f $port, $proc.Id, $proc.ProcessName) -ForegroundColor Yellow
        } catch { }
    }
}

if ($StopDocker) {
    Write-Host '停止第三方服务（TerminusDB / Redpanda）...' -ForegroundColor Cyan
    docker compose -f (Join-Path $serviceDir 'terminusdb/compose.yaml') down
    docker compose -f (Join-Path $serviceDir 'redpanda/compose.yaml') down
}

Write-Host '完成。' -ForegroundColor Green
