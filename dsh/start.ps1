# 本地一键启动 centre-control 全部 12 个角色（不走 Docker 打镜像）。
#
# 设计来源：sci-weave/centre-stack 的 Dockerfile + supervisord.conf + compose.yaml
# 里定义了“同一份环境 + 12 个角色各自的工作目录/入口/端口”。本脚本把那份容器内
# 编排翻译成本机进程：每个角色用各自子项目的 .venv 启动，环境变量从 dsh/.env 读，
# 数据落 dsh/data/，TerminusDB / Redpanda 仍用 Docker 起（它们是第三方依赖，不是本
# 项目产物）。
#
# 用法（在仓库根目录或任意位置执行均可）：
#   pwsh -File dsh/start.ps1              # 全量启动（含第三方服务 + bootstrap）
#   pwsh -File dsh/start.ps1 -SkipDocker  # 已有 TerminusDB/Redpanda 时跳过它们
#   pwsh -File dsh/start.ps1 -SkipWeb     # 不启动前端
#   pwsh -File dsh/start.ps1 -NoBuild     # 前端直接 dev，不预构建（默认就是 dev）
#
# 停止：pwsh -File dsh/stop.ps1

[CmdletBinding()]
param(
    [switch]$SkipDocker,
    [switch]$SkipBootstrap,
    [switch]$SkipWeb
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- 路径
$scriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot    = Split-Path -Parent $scriptDir
$controlDir  = Join-Path $repoRoot 'sci-weave/centre-control'
$serviceDir  = Join-Path $repoRoot 'sci-weave/service'
$dataDir     = Join-Path $scriptDir 'data'
$logDir      = Join-Path $scriptDir 'logs'
$pidsDir     = Join-Path $scriptDir 'pids'
$envFile     = Join-Path $scriptDir '.env'
$envExample  = Join-Path $scriptDir '.env.example'

foreach ($d in @($dataDir, $logDir, $pidsDir)) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
# 数据子目录（归属各角色的 SQLite 与会话文件）。
foreach ($sub in @('mapping', 'wiki', 'audit', 'registry', 'email', 'coordinator', 'centre-agents', 'centre-agents/worker-home')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $dataDir $sub) | Out-Null
}

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Info($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }
function Write-Warn2($msg) { Write-Host "    ! $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. 准备 .env
Write-Step '准备 dsh/.env'

function New-RandomToken { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ }) }

if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) { throw "缺少 $envExample" }
    Copy-Item $envExample $envFile
    Write-Info '首次运行：已从 .env.example 生成 .env'
}

# 把仍是 change-me-* 的令牌换成随机值。
$lines = Get-Content -LiteralPath $envFile
$replacements = @{}
$changed = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^(CENTRE_TOKEN_[A-Z_]+)=change-me-.*$') {
        $name = $Matches[1]
        if (-not $replacements.ContainsKey($name)) { $replacements[$name] = New-RandomToken }
        $lines[$i] = "$name=$($replacements[$name])"
        $changed = $true
    }
}
if ($changed) {
    Set-Content -LiteralPath $envFile -Value $lines -Encoding UTF8
    Write-Info '已为所有 change-me-* 令牌生成随机值'
} else {
    Write-Info '令牌已就绪，未改动'
}

# 解析 .env 成哈希表（支持 # 注释与 KEY=VALUE）。
function Import-DotEnv($path) {
    $map = @{}
    foreach ($line in Get-Content -LiteralPath $path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $idx = $t.IndexOf('=')
        if ($idx -lt 1) { continue }
        $k = $t.Substring(0, $idx).Trim()
        $v = $t.Substring($idx + 1).Trim()
        $map[$k] = $v
    }
    return $map
}
$envMap = Import-DotEnv $envFile

function Get-Env($name, $default = '') {
    if ($envMap.ContainsKey($name) -and $envMap[$name] -ne '') { return $envMap[$name] }
    return $default
}

# 把单个角色需要的环境变量组装成一份字符串表，交给 Start-Process。
function New-RoleEnv([hashtable]$overrides) {
    $base = @{
        TZ                                = 'Asia/Shanghai'
        PYTHONUNBUFFERED                  = '1'
        SCIWEAVE_CENTRE_PUBLIC_ORIGIN     = Get-Env 'SCIWEAVE_CENTRE_PUBLIC_ORIGIN' 'http://127.0.0.1:5173'

        # TerminusDB（本机直连）
        SCIWEAVE_MAPPING_TERMINUSDB_URL        = Get-Env 'SCIWEAVE_MAPPING_TERMINUSDB_URL' 'http://127.0.0.1:6363'
        SCIWEAVE_MAPPING_TERMINUSDB_DATABASE   = Get-Env 'SCIWEAVE_MAPPING_TERMINUSDB_DATABASE' 'sciweave_mapping'
        SCIWEAVE_MAPPING_TERMINUSDB_STORE      = Get-Env 'SCIWEAVE_MAPPING_TERMINUSDB_STORE' 'admin'
        SCIWEAVE_MAPPING_TERMINUSDB_USERNAME   = Get-Env 'SCIWEAVE_MAPPING_TERMINUSDB_USERNAME' 'admin'
        SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD   = Get-Env 'SCIWEAVE_MAPPING_TERMINUSDB_PASSWORD' 'root'
        SCIWEAVE_WIKI_TERMINUSDB_URL           = Get-Env 'SCIWEAVE_WIKI_TERMINUSDB_URL' 'http://127.0.0.1:6363'
        SCIWEAVE_WIKI_TERMINUSDB_DATABASE      = Get-Env 'SCIWEAVE_WIKI_TERMINUSDB_DATABASE' 'sciweave_wiki'
        SCIWEAVE_WIKI_TERMINUSDB_STORE         = Get-Env 'SCIWEAVE_WIKI_TERMINUSDB_STORE' 'admin'
        SCIWEAVE_WIKI_TERMINUSDB_USERNAME      = Get-Env 'SCIWEAVE_WIKI_TERMINUSDB_USERNAME' 'admin'
        SCIWEAVE_WIKI_TERMINUSDB_PASSWORD      = Get-Env 'SCIWEAVE_WIKI_TERMINUSDB_PASSWORD' 'root'
        SCIWEAVE_BUFFER_TERMINUSDB_URL         = Get-Env 'SCIWEAVE_BUFFER_TERMINUSDB_URL' 'http://127.0.0.1:6363'
        SCIWEAVE_BUFFER_TERMINUSDB_DATABASE    = Get-Env 'SCIWEAVE_BUFFER_TERMINUSDB_DATABASE' 'sciweave_draft_domain'
        SCIWEAVE_BUFFER_TERMINUSDB_USERNAME    = Get-Env 'SCIWEAVE_BUFFER_TERMINUSDB_USERNAME' 'admin'
        SCIWEAVE_BUFFER_TERMINUSDB_PASSWORD    = Get-Env 'SCIWEAVE_BUFFER_TERMINUSDB_PASSWORD' 'root'

        # 共享 broker
        SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP   = Get-Env 'SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP' '127.0.0.1:19092'

        # 令牌
        CENTRE_TOKEN_MAP_AGENT            = Get-Env 'CENTRE_TOKEN_MAP_AGENT'
        CENTRE_TOKEN_MAP_OWNER            = Get-Env 'CENTRE_TOKEN_MAP_OWNER'
        CENTRE_TOKEN_WIKI_AGENT           = Get-Env 'CENTRE_TOKEN_WIKI_AGENT'
        CENTRE_TOKEN_WIKI_OWNER           = Get-Env 'CENTRE_TOKEN_WIKI_OWNER'
        CENTRE_TOKEN_CENTRE_AGENT         = Get-Env 'CENTRE_TOKEN_CENTRE_AGENT'
        CENTRE_TOKEN_BUFFER               = Get-Env 'CENTRE_TOKEN_BUFFER'
        CENTRE_TOKEN_REGISTRY_OWNER       = Get-Env 'CENTRE_TOKEN_REGISTRY_OWNER'
        CENTRE_TOKEN_REGISTRY_RESEARCHER  = Get-Env 'CENTRE_TOKEN_REGISTRY_RESEARCHER'
        CENTRE_TOKEN_REGISTRY_CENTRE      = Get-Env 'CENTRE_TOKEN_REGISTRY_CENTRE'
        CENTRE_TOKEN_REGISTRY_EMAIL       = Get-Env 'CENTRE_TOKEN_REGISTRY_EMAIL'
        CENTRE_TOKEN_EMAIL_WORKFLOW       = Get-Env 'CENTRE_TOKEN_EMAIL_WORKFLOW'
        CENTRE_TOKEN_EMAIL_OPS            = Get-Env 'CENTRE_TOKEN_EMAIL_OPS'
        CENTRE_TOKEN_COORDINATOR          = Get-Env 'CENTRE_TOKEN_COORDINATOR'
        CENTRE_TOKEN_GATEWAY              = Get-Env 'CENTRE_TOKEN_GATEWAY'
        CENTRE_TOKEN_DASHBOARD_SOURCE     = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'

        # 发件人 / Worker 模型
        SCIWEAVE_EMAIL_FROM_ADDRESS       = Get-Env 'SCIWEAVE_EMAIL_FROM_ADDRESS' 'no-reply@example.test'
        SCIWEAVE_EMAIL_SMTP_HOST          = Get-Env 'SCIWEAVE_EMAIL_SMTP_HOST'
        SCIWEAVE_EMAIL_SMTP_PORT          = Get-Env 'SCIWEAVE_EMAIL_SMTP_PORT'
        SCIWEAVE_EMAIL_SMTP_USERNAME      = Get-Env 'SCIWEAVE_EMAIL_SMTP_USERNAME'
        SCIWEAVE_EMAIL_SMTP_PASSWORD      = Get-Env 'SCIWEAVE_EMAIL_SMTP_PASSWORD'
        SCIWEAVE_EMAIL_SMTP_SECURITY      = Get-Env 'SCIWEAVE_EMAIL_SMTP_SECURITY'
        DEEPSEEK_API_KEY                  = Get-Env 'DEEPSEEK_API_KEY'
        DEEPSEEK_BASE_URL                 = Get-Env 'DEEPSEEK_BASE_URL' 'https://api.deepseek.com'
        SCIWEAVE_WORKER_MODEL             = Get-Env 'SCIWEAVE_WORKER_MODEL' 'deepseek-chat'
        SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME = Get-Env 'SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME' '0'
    }
    foreach ($k in $overrides.Keys) { $base[$k] = $overrides[$k] }
    return $base
}

# 启动一个角色：用其子项目 venv 的 python，记录 pid。
function Test-PortInUse([int]$Port) {
    # ai4-18cl: a role that starts while its port is still held by a lingering
    # previous process exits on bind. Probe the port first and wait for it to free.
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $connected = $iar.AsyncWaitHandle.WaitOne(300)
        if ($connected) { $client.EndConnect($iar) }
        $client.Close()
        return $connected
    } catch {
        return $false
    }
}

function Wait-PortFree([int]$Port, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-PortInUse $Port)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return -not (Test-PortInUse $Port)
}

function Get-RolePort([hashtable]$EnvMap) {
    # The listen port is whichever *_PORT / HOST_PORT field the role is configured
    # with; pick the one the process binds (prefer *MCP_PORT* then any *PORT*).
    foreach ($k in @($EnvMap.Keys | Where-Object { $_ -match 'MCP_PORT$' })) {
        $v = 0; if ([int]::TryParse([string]$EnvMap[$k], [ref]$v)) { return $v }
    }
    foreach ($k in @($EnvMap.Keys | Where-Object { $_ -match 'PORT$' })) {
        $v = 0; if ([int]::TryParse([string]$EnvMap[$k], [ref]$v)) { return $v }
    }
    return 0
}

function Start-Role {
    param(
        [string]$Name,
        [string]$WorkDir,
        [string]$Python,           # venv python 或可执行文件完整路径
        [string[]]$ArgList,
        [hashtable]$EnvMap,
        [string]$EntryPath = 'src/main.py'
    )
    $port = Get-RolePort $EnvMap
    if ($port -gt 0) {
        if (Test-PortInUse $port) {
            Write-Warn2 ("{0} 的端口 {1} 被占用，等待释放（最多 30s）" -f $Name, $port)
            if (-not (Wait-PortFree $port 30)) {
                Write-Warn2 ("{0} 的端口 {1} 30s 内未释放，仍尝试启动（可能 bind 失败）" -f $Name, $port)
            }
        }
    }
    $outLog = Join-Path $logDir "$Name.out.log"
    $errLog = Join-Path $logDir "$Name.err.log"
    # 用 cmd 包装给每个子进程一份干净环境（Start-Process -Environment 需 PS7+，这里显式设置）。
    $prev = @{}
    foreach ($k in $EnvMap.Keys) {
        $prev[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$EnvMap[$k], 'Process')
    }
    try {
        $startArgs = @{
            FilePath         = $Python
            WorkingDirectory = $WorkDir
            RedirectStandardOutput = $outLog
            RedirectStandardError  = $errLog
            PassThru         = $true
            WindowStyle      = 'Hidden'
        }
        # 控制台脚本（如 gateway 的 .exe）没有参数：不能传空字符串给 ArgumentList。
        if ($ArgList -and $ArgList.Count -gt 0) {
            $startArgs['ArgumentList'] = @($ArgList)
        }
        $p = Start-Process @startArgs
    } finally {
        foreach ($k in $EnvMap.Keys) {
            [Environment]::SetEnvironmentVariable($k, $prev[$k], 'Process')
        }
    }
    Set-Content -LiteralPath (Join-Path $pidsDir "$Name.pid") -Value $p.Id
    Write-Info ("启动 {0,-22} pid={1}" -f $Name, $p.Id)
    return $p
}

function Get-VenvPython($projectDir) {
    $p = Join-Path $projectDir '.venv/Scripts/python.exe'
    if (-not (Test-Path $p)) { throw "缺少 venv：$p（先在 $projectDir 执行 uv sync）" }
    return $p
}

# ---------------------------------------------------------------- 2. 第三方服务
if (-not $SkipDocker) {
    Write-Step '启动第三方服务（TerminusDB / Redpanda）'
    docker compose -f (Join-Path $serviceDir 'terminusdb/compose.yaml') up -d
    docker compose -f (Join-Path $serviceDir 'redpanda/compose.yaml') up -d
    Write-Info '等待 TerminusDB 可达（端口 6363）...'
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:6363/api/ok' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { $ok = $true; break }
        } catch {
            try {
                $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:6363/' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($resp.StatusCode -ge 200) { $ok = $true; break }
            } catch { Start-Sleep -Seconds 2 }
        }
    }
    if ($ok) { Write-Info 'TerminusDB 已就绪' } else { Write-Warn2 'TerminusDB 60s 内未就绪，继续（角色可能报错）' }
}

# ---------------------------------------------------------------- 3. bootstrap 领域库
function Invoke-Bootstrap {
    Write-Step 'bootstrap 三个领域库'
    # 复用 centre-stack 里现成的纯标准库脚本，按各服务读取的环境变量建库（幂等）。
    $bootScript = Join-Path $repoRoot 'sci-weave/centre-stack/scripts/bootstrap_terminusdb.py'
    if (-not (Test-Path $bootScript)) {
        Write-Warn2 "未找到 $bootScript，跳过 bootstrap"
        return
    }
    $bootEnv = New-RoleEnv @{}
    $prev = @{}
    foreach ($k in $bootEnv.Keys) {
        $prev[$k] = [Environment]::GetEnvironmentVariable($k, 'Process')
        [Environment]::SetEnvironmentVariable($k, [string]$bootEnv[$k], 'Process')
    }
    try {
        python $bootScript
        if ($LASTEXITCODE -ne 0) { Write-Warn2 'bootstrap 返回非零，继续启动（部分领域库可能不可用）' }
    } finally {
        foreach ($k in $bootEnv.Keys) { [Environment]::SetEnvironmentVariable($k, $prev[$k], 'Process') }
    }
}
if (-not $SkipBootstrap) { Invoke-Bootstrap }

# ---------------------------------------------------------------- 4. 12 个角色
Write-Step '启动 Python 角色'

# -- research-map：MCP 模式 + 看板模式（同一 main.py 两个进程）
$mapDir = Join-Path $controlDir 'research-map'
$mapPy  = Get-VenvPython $mapDir
Start-Role -Name 'mapping-mcp' -WorkDir $mapDir -Python $mapPy -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_MAPPING_DOMAIN_ID               = Get-Env 'SCIWEAVE_MAPPING_DOMAIN_ID' 'iris-demo'
    SCIWEAVE_MAPPING_SQLITE_PATH             = (Join-Path $dataDir 'mapping/mapping.sqlite')
    SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH       = (Join-Path $dataDir 'audit/mapping.sqlite3')
    SCIWEAVE_MAPPING_MCP_HOST                = '127.0.0.1'
    SCIWEAVE_MAPPING_MCP_PORT                = '8710'
    SCIWEAVE_MAPPING_PREREVIEW_RULES_DIR     = (Join-Path $controlDir 'centre-agents/rules')
    SCIWEAVE_MAPPING_DASHBOARD_MODE          = '0'
    SCIWEAVE_MAPPING_DASHBOARD_TOKEN         = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
    SCIWEAVE_MAPPING_MCP_TOKENS_JSON         = ('{"' + (Get-Env 'CENTRE_TOKEN_MAP_AGENT') + '":"map-agent","' + (Get-Env 'CENTRE_TOKEN_MAP_OWNER') + '":"map-owner","' + (Get-Env 'CENTRE_TOKEN_CENTRE_AGENT') + '":"centre-agent"}')
    SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON = '{"map-agent":["read","candidate_submit"],"map-owner":["read","candidate_review","formalize"],"centre-agent":["centre","prereview_log","merged_candidate"]}'
    SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP         = Get-Env 'SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP' '127.0.0.1:19092'
}) | Out-Null

Start-Role -Name 'mapping-dashboard' -WorkDir $mapDir -Python $mapPy -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_MAPPING_DOMAIN_ID               = Get-Env 'SCIWEAVE_MAPPING_DOMAIN_ID' 'iris-demo'
    SCIWEAVE_MAPPING_SQLITE_PATH             = (Join-Path $dataDir 'mapping/mapping.sqlite')
    SCIWEAVE_MAPPING_AUDIT_SQLITE_PATH       = (Join-Path $dataDir 'audit/mapping.sqlite3')
    SCIWEAVE_MAPPING_DASHBOARD_MODE          = '1'
    SCIWEAVE_MAPPING_DASHBOARD_HOST          = '127.0.0.1'
    SCIWEAVE_MAPPING_DASHBOARD_PORT          = '8711'
    SCIWEAVE_MAPPING_DASHBOARD_TOKEN         = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
}) | Out-Null

# -- research-wiki：MCP + 看板
$wikiDir = Join-Path $controlDir 'research-wiki'
$wikiPy  = Get-VenvPython $wikiDir
Start-Role -Name 'wiki-mcp' -WorkDir $wikiDir -Python $wikiPy -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_WIKI_DOMAIN_ID              = Get-Env 'SCIWEAVE_WIKI_DOMAIN_ID' 'sciweave-wiki'
    SCIWEAVE_WIKI_SQLITE_PATH            = (Join-Path $dataDir 'wiki/wiki.sqlite')
    SCIWEAVE_WIKI_AUDIT_SQLITE_PATH      = (Join-Path $dataDir 'audit/wiki.sqlite3')
    SCIWEAVE_WIKI_MCP_HOST               = '127.0.0.1'
    SCIWEAVE_WIKI_MCP_PORT               = '8720'
    SCIWEAVE_WIKI_PREREVIEW_RULES_DIR    = (Join-Path $controlDir 'centre-agents/rules')
    SCIWEAVE_WIKI_DASHBOARD_MODE         = '0'
    SCIWEAVE_WIKI_DASHBOARD_TOKEN        = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
    SCIWEAVE_WIKI_MCP_TOKENS_JSON        = ('{"' + (Get-Env 'CENTRE_TOKEN_WIKI_AGENT') + '":"wiki-agent","' + (Get-Env 'CENTRE_TOKEN_WIKI_OWNER') + '":"wiki-owner","' + (Get-Env 'CENTRE_TOKEN_CENTRE_AGENT') + '":"centre-agent"}')
    SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON = '{"wiki-agent":["read","candidate_submit"],"wiki-owner":["read","candidate_review","formalize"],"centre-agent":["centre","prereview_log","merged_candidate"]}'
    SCIWEAVE_WIKI_KAFKA_BOOTSTRAP        = Get-Env 'SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP' '127.0.0.1:19092'
}) | Out-Null

Start-Role -Name 'wiki-dashboard' -WorkDir $wikiDir -Python $wikiPy -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_WIKI_DOMAIN_ID              = Get-Env 'SCIWEAVE_WIKI_DOMAIN_ID' 'sciweave-wiki'
    SCIWEAVE_WIKI_SQLITE_PATH            = (Join-Path $dataDir 'wiki/wiki.sqlite')
    SCIWEAVE_WIKI_AUDIT_SQLITE_PATH      = (Join-Path $dataDir 'audit/wiki.sqlite3')
    SCIWEAVE_WIKI_DASHBOARD_MODE         = '1'
    SCIWEAVE_WIKI_DASHBOARD_HOST         = '127.0.0.1'
    SCIWEAVE_WIKI_DASHBOARD_PORT         = '8721'
    SCIWEAVE_WIKI_DASHBOARD_TOKEN        = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
}) | Out-Null

# -- buffer（草稿箱）
$bufDir = Join-Path $controlDir 'buffer'
Start-Role -Name 'draft-buffer' -WorkDir $bufDir -Python (Get-VenvPython $bufDir) -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_BUFFER_REQUEST_TIMEOUT_SECONDS = Get-Env 'SCIWEAVE_BUFFER_REQUEST_TIMEOUT_SECONDS' '10'
    SCIWEAVE_BUFFER_REVIEWERS_JSON          = '{"mapping":["person:mapping-reviewer"],"wiki":["person:wiki-reviewer"]}'
    SCIWEAVE_BUFFER_MCP_HOST                = '127.0.0.1'
    SCIWEAVE_BUFFER_MCP_PORT                = '8730'
    SCIWEAVE_BUFFER_MCP_TOKENS_JSON         = ('{"' + (Get-Env 'CENTRE_TOKEN_BUFFER') + '":"service:task-agent-1"}')
}) | Out-Null

# -- registry
$regDir = Join-Path $controlDir 'registry'
Start-Role -Name 'registry' -WorkDir $regDir -Python (Get-VenvPython $regDir) -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_REGISTRY_SQLITE_PATH     = (Join-Path $dataDir 'registry/registry.sqlite3')
    SCIWEAVE_AUDIT_SQLITE_PATH        = (Join-Path $dataDir 'audit/registry.sqlite3')
    SCIWEAVE_REGISTRY_HOST            = '127.0.0.1'
    SCIWEAVE_REGISTRY_PORT            = '8740'
    SCIWEAVE_REGISTRY_ISSUER_URL      = 'http://127.0.0.1:8740/issuer'
    SCIWEAVE_REGISTRY_RESOURCE_URL    = 'http://127.0.0.1:8740/registry'
    SCIWEAVE_REGISTRY_TOKENS_JSON     = ('{"' + (Get-Env 'CENTRE_TOKEN_REGISTRY_OWNER') + '":{"caller_id":"person:owner","caller_type":"project_owner"},"' + (Get-Env 'CENTRE_TOKEN_REGISTRY_RESEARCHER') + '":{"caller_id":"person:researcher","caller_type":"researcher","principal_id":"person:researcher"},"' + (Get-Env 'CENTRE_TOKEN_REGISTRY_CENTRE') + '":{"caller_id":"service:centre","caller_type":"service","service_role":"centre"},"' + (Get-Env 'CENTRE_TOKEN_REGISTRY_EMAIL') + '":{"caller_id":"service:email","caller_type":"service","service_role":"email"}}')
}) | Out-Null

# -- email-service
$emDir = Join-Path $controlDir 'email-service'
Start-Role -Name 'email-service' -WorkDir $emDir -Python (Get-VenvPython $emDir) -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_EMAIL_SQLITE_PATH             = (Join-Path $dataDir 'email/email-delivery.sqlite3')
    SCIWEAVE_AUDIT_SQLITE_PATH             = (Join-Path $dataDir 'audit/email.sqlite3')
    SCIWEAVE_EMAIL_HOST                    = '127.0.0.1'
    SCIWEAVE_EMAIL_PORT                    = '8750'
    SCIWEAVE_EMAIL_ISSUER_URL              = 'http://127.0.0.1:8750/issuer'
    SCIWEAVE_EMAIL_RESOURCE_URL            = 'http://127.0.0.1:8750/email-service'
    SCIWEAVE_EMAIL_API_VERSION             = '1'
    SCIWEAVE_EMAIL_FROM_ADDRESS            = Get-Env 'SCIWEAVE_EMAIL_FROM_ADDRESS' 'no-reply@example.test'
    SCIWEAVE_EMAIL_TOKENS_JSON             = ('{"' + (Get-Env 'CENTRE_TOKEN_EMAIL_WORKFLOW') + '":{"caller_id":"service:centre-workflow","caller_type":"service"},"' + (Get-Env 'CENTRE_TOKEN_EMAIL_OPS') + '":{"caller_id":"human:oncall","caller_type":"operator"}}')
    SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS   = '1'
    SCIWEAVE_EMAIL_RETRY_MULTIPLIER        = '2'
    SCIWEAVE_EMAIL_RETRY_MAX_SECONDS       = '60'
    SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS   = '0.2'
    SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS = '30'
    SCIWEAVE_EMAIL_MAX_ATTEMPTS            = '3'
    SCIWEAVE_EMAIL_REGISTRY_URL            = 'http://127.0.0.1:8740/mcp'
    SCIWEAVE_EMAIL_REGISTRY_TOKEN          = Get-Env 'CENTRE_TOKEN_REGISTRY_EMAIL'
    SCIWEAVE_EMAIL_REGISTRY_TIMEOUT_SECONDS = '5'
}) | Out-Null

# -- coordinator
$coDir = Join-Path $controlDir 'coordinator'
Start-Role -Name 'coordinator' -WorkDir $coDir -Python (Get-VenvPython $coDir) -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_COORDINATOR_SQLITE_PATH          = (Join-Path $dataDir 'coordinator/coordinator.sqlite3')
    SCIWEAVE_COORDINATOR_KAFKA_BOOTSTRAP      = Get-Env 'SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP' '127.0.0.1:19092'
    SCIWEAVE_COORDINATOR_KAFKA_GROUP_ID       = 'coordinator'
    SCIWEAVE_MAPPING_MCP_ENDPOINT             = 'http://127.0.0.1:8710/mcp'
    SCIWEAVE_MAPPING_MCP_TOKEN                = Get-Env 'CENTRE_TOKEN_CENTRE_AGENT'
    SCIWEAVE_REGISTRY_MCP_ENDPOINT            = 'http://127.0.0.1:8740/mcp'
    SCIWEAVE_REGISTRY_MCP_TOKEN               = Get-Env 'CENTRE_TOKEN_REGISTRY_CENTRE'
    SCIWEAVE_EMAIL_MCP_ENDPOINT               = 'http://127.0.0.1:8750/mcp'
    SCIWEAVE_EMAIL_MCP_TOKEN                  = Get-Env 'CENTRE_TOKEN_EMAIL_WORKFLOW'
    SCIWEAVE_COORDINATOR_RETRY_INITIAL_SECONDS = '1'
    SCIWEAVE_COORDINATOR_RETRY_MULTIPLIER     = '2'
    SCIWEAVE_COORDINATOR_RETRY_MAX_SECONDS    = '60'
    SCIWEAVE_COORDINATOR_DISPATCH_POLL_SECONDS = '1'
    SCIWEAVE_COORDINATOR_MAX_ATTEMPTS         = '5'
    SCIWEAVE_COORDINATOR_MCP_HOST             = '127.0.0.1'
    SCIWEAVE_COORDINATOR_MCP_PORT             = '8762'
    SCIWEAVE_COORDINATOR_MCP_TOKEN            = Get-Env 'CENTRE_TOKEN_COORDINATOR'
}) | Out-Null

# -- centre-agents：gateway-mcp + gateway-subscriber（uv workspace，控制台脚本）
$caDir = Join-Path $controlDir 'centre-agents'
$caScripts = Join-Path $caDir '.venv/Scripts'
$workerHome = Join-Path $dataDir 'centre-agents/worker-home'
New-Item -ItemType Directory -Force -Path (Join-Path $workerHome 'sessions') | Out-Null

$gatewayEnv = New-RoleEnv @{
    SCIWEAVE_GATEWAY_TOKEN               = Get-Env 'CENTRE_TOKEN_GATEWAY'
    SCIWEAVE_GATEWAY_CALLER_ID           = 'person:owner'
    SCIWEAVE_GATEWAY_DB                  = (Join-Path $dataDir 'centre-agents/centre.sqlite3')
    SCIWEAVE_GATEWAY_HOST                = '127.0.0.1'
    SCIWEAVE_GATEWAY_PORT                = '8760'
    SCIWEAVE_AGENT_ID                    = 'task-agent-1'
    SCIWEAVE_SUBSCRIBER_TOPICS           = 'sciweave.task-handoff.task-agent-1'
    SCIWEAVE_QUEUE_BOOTSTRAP_SERVERS     = Get-Env 'SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP' '127.0.0.1:19092'
    SCIWEAVE_QUEUE_GROUP_ID              = 'sciweave.task-workflow.task-agent-1'
    SCIWEAVE_SUBSCRIBER_DASHBOARD_HOST   = '127.0.0.1'
    SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT   = '8761'
    SCIWEAVE_SUBSCRIBER_DASHBOARD_TOKEN  = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
    SCIWEAVE_DRAFT_BUFFER_ENDPOINT       = 'http://127.0.0.1:8730/mcp'
    SCIWEAVE_DRAFT_BUFFER_TOKEN          = Get-Env 'CENTRE_TOKEN_BUFFER'
    SCIWEAVE_DRAFT_BUFFER_NAMESPACE      = 'mapping'
    SCIWEAVE_DRAFT_BUFFER_SUBMITTER_ID   = 'service:task-agent-1'
    SCIWEAVE_WORKER_HOME                 = $workerHome
    SCIWEAVE_WORKER_SESSION_DIR          = 'sessions'
    SCIWEAVE_WORKER_CONNECTION_SCOPE     = 'centre-agent'
    SCIWEAVE_WORKER_MODEL                = Get-Env 'SCIWEAVE_WORKER_MODEL' 'deepseek-chat'
    CENTRE_DEFINITIONS_PATH              = (Join-Path $caDir 'definitions')
    CENTRE_MCP_LIBS_PATH                 = (Join-Path $caDir 'libs/mcp-libs')
    CENTRE_RULES_DIR                     = (Join-Path $caDir 'rules')
    RESEARCH_MAPPING_MCP_URL             = 'http://127.0.0.1:8710/mcp'
    LLM_WIKI_MCP_URL                     = 'http://127.0.0.1:8720/mcp'
    EMAIL_MCP_URL                        = 'http://127.0.0.1:8750/mcp'
    RESEARCH_MAPPING_MCP_TOKEN           = Get-Env 'CENTRE_TOKEN_CENTRE_AGENT'
    LLM_WIKI_MCP_TOKEN                   = Get-Env 'CENTRE_TOKEN_CENTRE_AGENT'
    EMAIL_MCP_TOKEN                      = Get-Env 'CENTRE_TOKEN_EMAIL_WORKFLOW'
}
Start-Role -Name 'centre-gateway-mcp' -WorkDir $caDir -Python (Join-Path $caScripts 'sciweave-task-agent-gateway-mcp.exe') -ArgList @() -EnvMap $gatewayEnv | Out-Null
Start-Role -Name 'centre-gateway-subscriber' -WorkDir $caDir -Python (Join-Path $caScripts 'sciweave-task-agent-gateway-subscriber.exe') -ArgList @() -EnvMap $gatewayEnv | Out-Null

# -- dashboard-api
$daDir = Join-Path $controlDir 'dashboard-api'
Start-Role -Name 'dashboard-api' -WorkDir $daDir -Python (Get-VenvPython $daDir) -ArgList @('src/main.py') -EnvMap (New-RoleEnv @{
    SCIWEAVE_DASHBOARD_HOST                       = '127.0.0.1'
    SCIWEAVE_DASHBOARD_PORT                       = '8702'
    SCIWEAVE_DASHBOARD_CORS_ORIGIN                = Get-Env 'SCIWEAVE_CENTRE_PUBLIC_ORIGIN' 'http://127.0.0.1:5173'
    SCIWEAVE_DASHBOARD_SOURCE_TIMEOUT_SECONDS     = '5'
    SCIWEAVE_DASHBOARD_SOURCE_MAX_BYTES           = '1048576'
    SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL         = 'http://127.0.0.1:8711/api/dashboard/source/mapping'
    SCIWEAVE_DASHBOARD_SOURCE_MAPPING_TOKEN       = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
    SCIWEAVE_DASHBOARD_SOURCE_WIKI_URL            = 'http://127.0.0.1:8721/api/dashboard/source/wiki'
    SCIWEAVE_DASHBOARD_SOURCE_WIKI_TOKEN          = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
    SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_URL         = 'http://127.0.0.1:8760/sources'
    SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_TOKEN       = Get-Env 'CENTRE_TOKEN_GATEWAY'
    SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL           = 'http://127.0.0.1:8761/api/dashboard/source/queue'
    SCIWEAVE_DASHBOARD_SOURCE_QUEUE_TOKEN         = Get-Env 'CENTRE_TOKEN_DASHBOARD_SOURCE'
}) | Out-Null

# ---------------------------------------------------------------- 5. 前端
if (-not $SkipWeb) {
    Write-Step '启动 Web 前端（vite dev :5173）'
    $webDir = Join-Path $controlDir 'web-ui'
    $node = (Get-Command node -ErrorAction Stop).Source
    # pnpm 通过 corepack 提供；用 node 起 vite 更稳（避免 pnpm.ps1 执行策略问题）。
    $vite = Join-Path $webDir 'node_modules/.bin/vite.cmd'
    $prevVite = [Environment]::GetEnvironmentVariable('VITE_DASHBOARD_API_URL', 'Process')
    [Environment]::SetEnvironmentVariable('VITE_DASHBOARD_API_URL', (Get-Env 'VITE_DASHBOARD_API_URL' 'http://127.0.0.1:8702/'), 'Process')
    try {
        $outLog = Join-Path $logDir 'web-ui.out.log'
        $errLog = Join-Path $logDir 'web-ui.err.log'
        $p = Start-Process -FilePath $vite -ArgumentList @('--host','127.0.0.1','--port','5173') -WorkingDirectory $webDir -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru -WindowStyle Hidden
        Set-Content -LiteralPath (Join-Path $pidsDir 'web-ui.pid') -Value $p.Id
        Write-Info ("启动 {0,-22} pid={1}" -f 'web-ui', $p.Id)
    } finally {
        [Environment]::SetEnvironmentVariable('VITE_DASHBOARD_API_URL', $prevVite, 'Process')
    }
}

# ---------------------------------------------------------------- 6. 汇总
Write-Step '启动完成，等待就绪探测'
Start-Sleep -Seconds 8

$checks = @(
    @{ Name = 'dashboard-api'; Url = 'http://127.0.0.1:8702/health' },
    @{ Name = 'mapping-mcp';   Url = 'http://127.0.0.1:8710/health' },
    @{ Name = 'wiki-mcp';      Url = 'http://127.0.0.1:8720/health' },
    @{ Name = 'draft-buffer';  Url = 'http://127.0.0.1:8730/health' },
    @{ Name = 'registry';      Url = 'http://127.0.0.1:8740/health' },
    @{ Name = 'gateway';       Url = 'http://127.0.0.1:8760/health' },
    @{ Name = 'coordinator';   Url = 'http://127.0.0.1:8762/health' }
)
foreach ($c in $checks) {
    try {
        $r = Invoke-WebRequest -Uri $c.Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        Write-Host ("    {0,-16} {1}  {2}" -f $c.Name, $r.StatusCode, $c.Url) -ForegroundColor Green
    } catch {
        $code = try { $_.Exception.Response.StatusCode.value__ } catch { 'ERR' }
        Write-Host ("    {0,-16} {1}  {2}" -f $c.Name, $code, $c.Url) -ForegroundColor Yellow
    }
}

Write-Host @"

------------------------------------------------------------
本地栈已拉起。常用地址：
  看板前端      http://127.0.0.1:5173/
  看板 API      http://127.0.0.1:8702/health
  Mapping MCP   http://127.0.0.1:8710/mcp   (Bearer)
  Wiki MCP      http://127.0.0.1:8720/mcp   (Bearer)
  Gateway MCP   http://127.0.0.1:8760/mcp   (Bearer)

日志目录：$logDir
停止：pwsh -File dsh/stop.ps1
------------------------------------------------------------
"@ -ForegroundColor Cyan
