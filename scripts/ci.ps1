<#
.SYNOPSIS
    跑完整回归矩阵：每个 Python 子项目的 pytest + 前端 vitest/构建 + 语法检查 + 空白检查。

.DESCRIPTION
    项目位置不写死——从 git 索引里发现所有 tests/test_*.py，取它们所属的子项目。
    未跟踪的本地残留目录因此不会被误当作 CI 目标。

    依赖真实 TerminusDB 的用例默认跳过；加 -Integration 才会执行（需要本机
    TerminusDB 可达，且 wiki 相关变量已配置）。

.PARAMETER Integration
    设 SCIWEAVE_RUN_TERMINUSDB_INTEGRATION=1，执行真实库集成用例。

.PARAMETER SkipWeb
    跳过前端阶段（只跑 Python）。前端缺 node_modules 时本脚本会先 npm ci。

.PARAMETER Filter
    只跑路径匹配该正则的子项目，例如 -Filter 'centre-agents'。

.PARAMETER Fail Fast
    首个失败即停止。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ci.ps1 -Integration -Filter 'research-'
#>
param(
    [switch]$Integration,
    [switch]$SkipWeb,
    [switch]$FailFast,
    [string]$Filter = ''
)

$ErrorActionPreference = 'Continue'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# 字节码统一写到 var/ 下，不落在 src/ 的 __pycache__：既不让工作区被生成物污染，
# 也避免 compileall 因为「上一次留下的 pyc 还在」而空跑成假绿——干净机器上的首跑
# 必须同样能通过（缓存目录已被 .gitignore 覆盖）。
$pyCachePrefix = Join-Path $repoRoot 'var/pycache-ci'
Remove-Item -LiteralPath $pyCachePrefix -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $pyCachePrefix | Out-Null
$env:PYTHONPYCACHEPREFIX = $pyCachePrefix

$termVar = 'SCIWEAVE_RUN_TERMINUSDB_INTEGRATION'
if ($Integration) {
    [Environment]::SetEnvironmentVariable($termVar, '1')
} else {
    [Environment]::SetEnvironmentVariable($termVar, $null)
}

function Stage([string]$text) {
    Write-Host ''
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

function Invoke-Stage {
    param([string]$Name, [string]$WorkDir, [scriptblock]$Body)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $output = & $Body 2>&1 | Out-String
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    $watch.Stop()
    [pscustomobject]@{
        Name     = $Name
        Exit     = $code
        Output   = $output
        Seconds  = [math]::Round($watch.Elapsed.TotalSeconds, 1)
        Passed   = if ($output -match '(\d+) passed') { [int]$Matches[1] } else { 0 }
        Failed   = if ($output -match '(\d+) failed') { [int]$Matches[1] } else { 0 }
        Skipped  = if ($output -match '(\d+) skipped') { [int]$Matches[1] } else { 0 }
    }
}

# --- discover -------------------------------------------------------------
$tracked = & git ls-files '*tests/test_*.py'
if (-not $tracked) {
    Write-Host '没有发现任何 tests/test_*.py，检查是否在仓库根目录。' -ForegroundColor Red
    exit 2
}
$projects = $tracked |
    ForEach-Object { ($_ -split '/tests/')[0] } |
    Where-Object { $_ -and $_ -notmatch '\.venv' } |
    Sort-Object -Unique

if ($Filter) {
    $projects = $projects | Where-Object { $_ -match $Filter }
}

Stage "Python 矩阵（$($projects.Count) 个子项目）"
if (-not $Integration) {
    Write-Host "集成用例：跳过（设 -Integration 或 $termVar=1 执行）" -ForegroundColor DarkGray
}

$results = @()
foreach ($project in $projects) {
    $label = $project.Replace('sci-weave/', '')
    Write-Host ("  {0,-52}" -f $label) -NoNewline
    $result = Invoke-Stage -Name $label -Body {
        & uv run --directory $project --with pytest --with pytest-asyncio pytest tests -q -p no:cacheprovider
    }
    $results += $result
    if ($result.Exit -eq 0) {
        Write-Host ("PASS  {0,4} passed {1,3} skipped  {2,5}s" -f $result.Passed, $result.Skipped, $result.Seconds) -ForegroundColor Green
    } else {
        Write-Host ("FAIL  {0,4} passed {1,3} failed    {2,5}s" -f $result.Passed, $result.Failed, $result.Seconds) -ForegroundColor Red
        $tail = ($result.Output -split "`n" | Select-Object -Last 25) -join "`n"
        Write-Host $tail -ForegroundColor DarkRed
        if ($FailFast) { break }
    }
}

# --- syntax check ---------------------------------------------------------
Stage '语法检查（compileall）'
$srcDirs = $projects | ForEach-Object { Join-Path $_ 'src' } | Where-Object { Test-Path $_ }
$compile = Invoke-Stage -Name 'compileall' -Body {
    & uv run --with pytest python -m compileall -q @srcDirs
}
if ($compile.Exit -eq 0) {
    Write-Host ("  PASS  {0} 个 src 目录" -f $srcDirs.Count) -ForegroundColor Green
} else {
    Write-Host "  FAIL" -ForegroundColor Red
    Write-Host $compile.Output -ForegroundColor DarkRed
}
$results += $compile

# --- front end ------------------------------------------------------------
if (-not $SkipWeb) {
    Stage '前端（web-ui）'
    $webDir = 'sci-weave/centre-control/web-ui'
    if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
        Write-Host '  node_modules 缺失，先 npm ci ...' -ForegroundColor DarkGray
        Push-Location $webDir
        & npm ci 2>&1 | Out-Null
        Pop-Location
    }
    foreach ($task in 'test', 'build') {
        Write-Host ("  npm run {0,-10}" -f $task) -NoNewline
        $web = Invoke-Stage -Name "web-ui:$task" -Body {
            Push-Location $webDir
            try { & npm run $task } finally { Pop-Location }
        }
        if ($web.Exit -eq 0) {
            Write-Host ("PASS  {0,5}s" -f $web.Seconds) -ForegroundColor Green
        } else {
            Write-Host ("FAIL  {0,5}s" -f $web.Seconds) -ForegroundColor Red
            Write-Host (($web.Output -split "`n" | Select-Object -Last 25) -join "`n") -ForegroundColor DarkRed
        }
        $results += $web
    }
}

# --- whitespace -----------------------------------------------------------
Stage 'git diff --check（空白与冲突标记）'
# 捕获而不是直接透传：git 在 Windows 上会把「LF will be replaced by CRLF」写到
# stderr，透传会让 CI 日志充满可在任何门禁里被误读为失败的噪声。
$whitespaceOutput = & git diff --check 2>&1 | Out-String
$whitespace = [pscustomobject]@{
    Name = 'git diff --check'; Exit = $LASTEXITCODE; Output = $whitespaceOutput; Seconds = 0
    Passed = 0; Failed = 0; Skipped = 0
}
if ($whitespace.Exit -eq 0) {
    Write-Host '  PASS' -ForegroundColor Green
} else {
    Write-Host '  FAIL  存在行尾空白或冲突标记' -ForegroundColor Red
    Write-Host $whitespaceOutput -ForegroundColor DarkRed
}
$results += $whitespace

# --- summary --------------------------------------------------------------
Stage '汇总'
# 必须包成数组：Where-Object 只匹配到一个对象时返回的是标量，标量没有 Count，
# $failed.Count 会求值为 $null，于是「恰好一个阶段失败」被算成「全部通过」。
$failed = @($results | Where-Object { $_.Exit -ne 0 })
$totalPassed = ($results | Measure-Object -Property Passed -Sum).Sum
$totalSkipped = ($results | Measure-Object -Property Skipped -Sum).Sum
Write-Host ("  通过 {0} / 共 {1} 个阶段，pytest 用例 {2} 项通过" -f ($results.Count - $failed.Count), $results.Count, $totalPassed)
Write-Host ("  已跳过 {0} 项（默认为依赖真实 TerminusDB / Kafka 的集成用例）" -f $totalSkipped)
if ($failed) {
    Write-Host ''
    Write-Host '  失败阶段：' -ForegroundColor Red
    $failed | ForEach-Object { Write-Host ("    - {0}（exit {1}）" -f $_.Name, $_.Exit) -ForegroundColor Red }
    exit 1
}
Write-Host ''
Write-Host '  全部通过。' -ForegroundColor Green
exit 0
