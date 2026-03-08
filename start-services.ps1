# AIWeb - Windows one-click startup script
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\start-services.ps1 start
#   .\start-services.ps1 stop
#   .\start-services.ps1 status

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "logs", "clean", "help")]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$ServiceName
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ScriptDir "backend"
$FrontendDir = Join-Path $ScriptDir "frontend"
$InfraComposeFile = Join-Path $ScriptDir "infra\docker-compose.yml"
$BackendEnvFile = Join-Path $BackendDir ".env"
$BackendEnvExample = Join-Path $BackendDir ".env.example"
$RuntimeDir = Join-Path $ScriptDir ".aiweb-runtime"
$ProcessFile = Join-Path $RuntimeDir "processes.json"

$InfraServices = @(
    "minio",
    "redis",
    "postgres",
    "milvus-etcd",
    "milvus-minio",
    "milvus",
    "rabbitmq",
    "redisinsight",
    "pgadmin",
    "elasticsearch",
    "kibana"
)

function Write-Info($Message) {
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success($Message) {
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-WarningMessage($Message) {
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-ErrorMessage($Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Ensure-RuntimeDir {
    if (-not (Test-Path $RuntimeDir)) {
        New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
    }
}

function Test-CommandExists([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-Prerequisites {
    Write-Info "Checking prerequisites..."

    if (-not (Test-CommandExists "docker")) {
        throw "docker was not found. Please install Docker Desktop first."
    }
    if (-not (Test-CommandExists "npm")) {
        throw "npm was not found. Please install Node.js first."
    }
    if (-not (Test-CommandExists "python")) {
        throw "python was not found. Please install Python 3 first."
    }

    docker info *> $null
    Write-Success "Docker is available"
    Write-Success "Node.js / npm is available"
    Write-Success "Python is available"
}

function Get-PythonExe {
    $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Invoke-InDirectory {
    param(
        [string]$Path,
        [scriptblock]$ScriptBlock
    )

    Push-Location $Path
    try {
        & $ScriptBlock
    }
    finally {
        Pop-Location
    }
}

function Set-Or-AppendEnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $content = ""
    if (Test-Path $Path) {
        $content = Get-Content -Path $Path -Raw -Encoding UTF8
    }

    $escapedKey = [regex]::Escape($Key)
    $pattern = "(?m)^\s*#?\s*$escapedKey=.*$"
    $replacement = "$Key=$Value"

    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, $replacement, 1)
    }
    else {
        if ($content.Length -gt 0 -and -not $content.EndsWith("`r`n")) {
            $content += "`r`n"
        }
        $content += "$replacement`r`n"
    }

    Set-Content -Path $Path -Value $content -Encoding UTF8
}

function Read-EnvValue {
    param(
        [string]$Path,
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    $match = Select-String -Path $Path -Pattern "^\s*$([regex]::Escape($Key))=(.*)$" -Encoding UTF8 | Select-Object -First 1
    if ($null -eq $match) {
        return $null
    }

    return $match.Matches[0].Groups[1].Value.Trim()
}

function Prompt-ApiKey {
    param(
        [string]$DisplayName,
        [string]$EnvKey,
        [string]$Hint = ""
    )

    $existingValue = Read-EnvValue -Path $BackendEnvFile -Key $EnvKey
    if ($existingValue) {
        Write-Info "$EnvKey already exists. Reusing the current value."
        return $existingValue
    }

    $prompt = "Enter $DisplayName (optional, press Enter to skip)"
    if (-not [string]::IsNullOrWhiteSpace($Hint)) {
        Write-Host "  $Hint" -ForegroundColor DarkGray
    }
    $value = Read-Host $prompt
    return $value.Trim()
}

function Prompt-And-StoreApiKey {
    param(
        [string]$EnvKey,
        [string]$Hint = ""
    )

    $value = Prompt-ApiKey -DisplayName $EnvKey -EnvKey $EnvKey -Hint $Hint
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        Set-Or-AppendEnvValue -Path $BackendEnvFile -Key $EnvKey -Value $value
    }
    return $value
}

function Ensure-BackendEnv {
    Write-Info "Preparing backend/.env ..."

    if (-not (Test-Path $BackendEnvFile)) {
        Copy-Item $BackendEnvExample $BackendEnvFile
        Write-Success "Created backend/.env from .env.example"
    }

    Write-Host ""
    Write-Host "The script will now ask for API keys and related tokens used by AIWeb." -ForegroundColor White
    Write-Host "All of them are optional here. You can press Enter to skip any item." -ForegroundColor White
    Write-Host "If a value already exists in backend/.env, the script will reuse it automatically." -ForegroundColor Gray
    Write-Host ""

    Write-Host "=== Model providers ===" -ForegroundColor Cyan
    Prompt-And-StoreApiKey -EnvKey "OPENAI_API_KEY" -Hint "Used for OpenAI models and some audio parsing fallback paths."
    Prompt-And-StoreApiKey -EnvKey "ANTHROPIC_API_KEY" -Hint "Used for Claude models."
    Prompt-And-StoreApiKey -EnvKey "DEEPSEEK_API_KEY" -Hint "Used by DeepResearch, memory scoring, outline/report generation."
    Prompt-And-StoreApiKey -EnvKey "QWEN_API_KEY" -Hint "Used by embeddings, RAG image understanding, some multimodal features."
    Prompt-And-StoreApiKey -EnvKey "DASHSCOPE_API_KEY" -Hint "Used for DashScope / Qwen ASR style integrations."
    Prompt-And-StoreApiKey -EnvKey "MOONSHOT_API_KEY" -Hint "Used for Moonshot / Kimi models."
    Prompt-And-StoreApiKey -EnvKey "ZHIPU_API_KEY" -Hint "Used for GLM / Zhipu models."
    Prompt-And-StoreApiKey -EnvKey "GEMINI_API_KEY" -Hint "Used for Gemini models."
    Prompt-And-StoreApiKey -EnvKey "DEFAULT_MODEL_API_KEY" -Hint "Optional dedicated key for the manually configured default model."

    Write-Host "" 
    Write-Host "=== Agentic and search ===" -ForegroundColor Cyan
    Prompt-And-StoreApiKey -EnvKey "SERPER_API_KEY" -Hint "Used by the web_search tool via Serper."
    Prompt-And-StoreApiKey -EnvKey "BOCHA_API_KEY" -Hint "Used by the web_search tool via Bocha."

    Write-Host ""
    Write-Host "=== RAG and parsing ===" -ForegroundColor Cyan
    Prompt-And-StoreApiKey -EnvKey "JINA_API_KEY" -Hint "Optional. Enables Jina reranker for RAG search quality."
    Prompt-And-StoreApiKey -EnvKey "MINERU_API_TOKEN" -Hint "Optional. Enables MinerU cloud PDF parsing before local fallback."

    $jwtSecret = Read-EnvValue -Path $BackendEnvFile -Key "JWT_SECRET"
    if (-not $jwtSecret) {
        $jwtSecret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
    }

    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "JWT_SECRET" -Value $jwtSecret

    # Align with the values used by infra/docker-compose.yml
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MINIO_ENDPOINT" -Value "localhost:9000"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MINIO_ACCESS_KEY" -Value "Eddiex"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MINIO_SECRET_KEY" -Value "12345678"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MINIO_BUCKET" -Value "aiweb"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MINIO_SECURE" -Value "false"

    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "POSTGRES_HOST" -Value "localhost"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "POSTGRES_PORT" -Value "5432"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "POSTGRES_USER" -Value "aiweb"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "POSTGRES_PASSWORD" -Value "aiweb"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "POSTGRES_DB" -Value "aiweb"

    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "REDIS_HOST" -Value "localhost"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "REDIS_PORT" -Value "6379"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MILVUS_HOST" -Value "localhost"
    Set-Or-AppendEnvValue -Path $BackendEnvFile -Key "MILVUS_PORT" -Value "19530"

    Write-Success "backend/.env is ready"
}

function Ensure-BackendDependencies {
    $pythonExe = Get-PythonExe

    if ($pythonExe -eq "python" -and -not (Test-Path (Join-Path $BackendDir ".venv"))) {
        $createVenv = Read-Host "backend/.venv was not found. Create venv and install backend dependencies now? (Y/n)"
        if ($createVenv -notmatch "^(n|no)$") {
            Write-Info "Creating backend/.venv ..."
            Invoke-InDirectory -Path $BackendDir -ScriptBlock {
                python -m venv .venv
            }
            $pythonExe = Get-PythonExe
        }
    }

    $needInstall = $false
    if (Test-Path (Join-Path $BackendDir ".venv")) {
        $needInstall = -not (Test-Path (Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"))
    }
    else {
        $needInstall = $true
    }

    if ($needInstall) {
        Write-Info "Installing backend dependencies. This may take a while on first run..."
        Invoke-InDirectory -Path $BackendDir -ScriptBlock {
            & $pythonExe -m pip install --upgrade pip
            & $pythonExe -m pip install -r requirements.txt
        }
        Write-Success "Backend dependencies installed"
    }
    else {
        Write-Info "Backend dependencies already exist. Skipping install."
    }
}

function Ensure-FrontendDependencies {
    $nodeModulesDir = Join-Path $FrontendDir "node_modules"
    if (-not (Test-Path $nodeModulesDir)) {
        Write-Info "Installing frontend dependencies..."
        Invoke-InDirectory -Path $FrontendDir -ScriptBlock {
            npm install
        }
        Write-Success "Frontend dependencies installed"
    }
    else {
        Write-Info "Frontend dependencies already exist. Skipping npm install."
    }
}

function Get-ManagedProcesses {
    if (-not (Test-Path $ProcessFile)) {
        return $null
    }

    try {
        return Get-Content $ProcessFile -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Save-ManagedProcesses($BackendPid, $FrontendPid) {
    Ensure-RuntimeDir
    $payload = @{
        backend_pid  = $BackendPid
        frontend_pid = $FrontendPid
        updated_at   = (Get-Date).ToString("s")
    }
    $payload | ConvertTo-Json | Set-Content -Path $ProcessFile -Encoding UTF8
}

function Test-ProcessAlive($PidValue) {
    if (-not $PidValue) {
        return $false
    }
    try {
        $null = Get-Process -Id $PidValue -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Start-Infrastructure {
    Write-Info "Starting infra services (Attu is skipped by default to avoid port 8000 conflict)..."
    & docker compose -f $InfraComposeFile up -d @InfraServices
    Start-Sleep -Seconds 8
    Write-Success "Infra startup command completed"
}

function Run-DatabaseSchema {
    $pythonExe = Get-PythonExe
    Write-Info "Running database schema setup..."
    Invoke-InDirectory -Path $BackendDir -ScriptBlock {
        & $pythonExe -m db.run_schema
    }
    Write-Success "Database schema setup completed"
}

function Start-AppWindows {
    $existing = Get-ManagedProcesses
    if ($existing -and ((Test-ProcessAlive $existing.backend_pid) -or (Test-ProcessAlive $existing.frontend_pid))) {
        Write-WarningMessage "Backend or frontend is already running from a previous script launch. Skipping duplicate start."
        return
    }

    $pythonExe = Get-PythonExe
    $backendCommand = "Set-Location '$BackendDir'; & '$pythonExe' -m uvicorn main:app --host 0.0.0.0 --port 8000"
    $frontendCommand = "Set-Location '$FrontendDir'; npm run dev"

    Write-Info "Opening backend window..."
    $backendProc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand
    ) -PassThru

    Start-Sleep -Seconds 2

    Write-Info "Opening frontend window..."
    $frontendProc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand
    ) -PassThru

    Save-ManagedProcesses -BackendPid $backendProc.Id -FrontendPid $frontendProc.Id
    Write-Success "Backend and frontend windows have been started"
}

function Stop-AppWindows {
    $managed = Get-ManagedProcesses
    if (-not $managed) {
        Write-Info "No managed backend/frontend process record was found."
        return
    }

    foreach ($item in @(
        @{ Name = "backend";  Pid = $managed.backend_pid  },
        @{ Name = "frontend"; Pid = $managed.frontend_pid }
    )) {
        if (Test-ProcessAlive $item.Pid) {
            Write-Info "Stopping $($item.Name) process (PID=$($item.Pid)) ..."
            Stop-Process -Id $item.Pid -Force
            Write-Success "$($item.Name) stopped"
        }
    }

    if (Test-Path $ProcessFile) {
        Remove-Item $ProcessFile -Force
    }
}

function Stop-Infrastructure {
    Write-Info "Stopping Docker infra..."
    & docker compose -f $InfraComposeFile down
    Write-Success "Docker infra stopped"
}

function Show-HealthStatus {
    Write-Info "Docker service status:"
    & docker compose -f $InfraComposeFile ps
    Write-Host ""

    try {
        & docker exec aiweb-postgres pg_isready -U aiweb *> $null
        Write-Success "PostgreSQL: running"
    }
    catch {
        Write-WarningMessage "PostgreSQL: not ready"
    }

    try {
        $redisReply = & docker exec aiweb-redis redis-cli ping 2>$null
        if ($redisReply -match "PONG") {
            Write-Success "Redis: running"
        }
        else {
            Write-WarningMessage "Redis: not ready"
        }
    }
    catch {
        Write-WarningMessage "Redis: not ready"
    }

    try {
        $null = Invoke-WebRequest -Uri "http://localhost:9091/healthz" -UseBasicParsing -TimeoutSec 3
        Write-Success "Milvus: running"
    }
    catch {
        Write-WarningMessage "Milvus: not ready"
    }

    $managed = Get-ManagedProcesses
    if ($managed) {
        Write-Host ""
        Write-Info "App process status:"
        if (Test-ProcessAlive $managed.backend_pid) {
            Write-Success "Backend: running (PID=$($managed.backend_pid))"
        }
        else {
            Write-WarningMessage "Backend: not running"
        }
        if (Test-ProcessAlive $managed.frontend_pid) {
            Write-Success "Frontend: running (PID=$($managed.frontend_pid))"
        }
        else {
            Write-WarningMessage "Frontend: not running"
        }
    }

    Write-Host ""
    Write-Host "Common URLs:" -ForegroundColor White
    Write-Host "  Frontend:     http://localhost:5173" -ForegroundColor Gray
    Write-Host "  Swagger:      http://localhost:8000/docs" -ForegroundColor Gray
    Write-Host "  MinIO:       http://localhost:9001" -ForegroundColor Gray
    Write-Host "  pgAdmin:     http://localhost:5050" -ForegroundColor Gray
    Write-Host "  RedisInsight:http://localhost:5540" -ForegroundColor Gray
}

function Show-Logs {
    if ([string]::IsNullOrWhiteSpace($ServiceName)) {
        Write-Info "Showing Docker infra logs."
        Write-Host "Tip: backend and frontend logs are visible in the two PowerShell windows opened by the script." -ForegroundColor Gray
        & docker compose -f $InfraComposeFile logs -f --tail=100
        return
    }

    & docker compose -f $InfraComposeFile logs -f --tail=100 $ServiceName
}

function Clear-AllData {
    Write-WarningMessage "This will delete Docker volume data including database, cache and vector data."
    $confirm = Read-Host "Type YES to continue"
    if ($confirm -ne "YES") {
        Write-Info "Clean action cancelled."
        return
    }

    Stop-AppWindows
    & docker compose -f $InfraComposeFile down -v
    Write-Success "All infra data has been removed"
}

function Show-Help {
    Write-Host "AIWeb - Windows one-click startup script" -ForegroundColor White
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor White
    Write-Host "  .\start-services.ps1 start" -ForegroundColor Gray
    Write-Host "  .\start-services.ps1 stop" -ForegroundColor Gray
    Write-Host "  .\start-services.ps1 restart" -ForegroundColor Gray
    Write-Host "  .\start-services.ps1 status" -ForegroundColor Gray
    Write-Host "  .\start-services.ps1 logs [service-name]" -ForegroundColor Gray
    Write-Host "  .\start-services.ps1 clean" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor White
    Write-Host "  start    Ask for API keys, prepare .env, start infra, run schema, open backend and frontend" -ForegroundColor Gray
    Write-Host "  stop     Stop managed backend/frontend processes and shut down Docker infra" -ForegroundColor Gray
    Write-Host "  restart  Run stop first, then start again" -ForegroundColor Gray
    Write-Host "  status   Show infra and app status" -ForegroundColor Gray
    Write-Host "  logs     Show Docker infra logs, optionally for one service" -ForegroundColor Gray
    Write-Host "  clean    Remove Docker volume data (dangerous)" -ForegroundColor Gray
    Write-Host "  help     Show this help" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Notes:" -ForegroundColor White
    Write-Host "  - Attu is skipped by default to avoid using port 8000" -ForegroundColor Gray
    Write-Host "  - On first start, the script asks for API keys and writes them into backend/.env" -ForegroundColor Gray
    Write-Host "  - Backend and frontend are opened in separate PowerShell windows for easy log viewing" -ForegroundColor Gray
}

try {
    switch ($Command) {
        "start" {
            Assert-Prerequisites
            Ensure-BackendEnv
            Ensure-BackendDependencies
            Ensure-FrontendDependencies
            Start-Infrastructure
            Run-DatabaseSchema
            Start-AppWindows
            Show-HealthStatus
        }
        "stop" {
            Stop-AppWindows
            Stop-Infrastructure
        }
        "restart" {
            Stop-AppWindows
            Stop-Infrastructure
            Assert-Prerequisites
            Ensure-BackendEnv
            Ensure-BackendDependencies
            Ensure-FrontendDependencies
            Start-Infrastructure
            Run-DatabaseSchema
            Start-AppWindows
            Show-HealthStatus
        }
        "status" {
            Show-HealthStatus
        }
        "logs" {
            Show-Logs
        }
        "clean" {
            Clear-AllData
        }
        default {
            Show-Help
        }
    }
}
catch {
    Write-ErrorMessage $_.Exception.Message
    exit 1
}
