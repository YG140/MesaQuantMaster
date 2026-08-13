[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipDatabaseCheck,
    [switch]$DedicatedWindow,
    [ValidateRange(5, 600)]
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$script:StartedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
$script:KnownProcessIds = [System.Collections.Generic.HashSet[int]]::new()

function Get-StartupPaths {
    param([string]$Root = $PSScriptRoot)

    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    [pscustomobject]@{
        Root = [System.IO.Path]::GetFullPath($Root)
        Backend = Join-Path $Root "backend"
        Frontend = Join-Path $Root "frontend_web"
        Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
        EnvFile = Join-Path $Root "backend\.env"
        Npm = if ($npm) { $npm.Source } else { $null }
        Node = if ($node) { $node.Source } else { $null }
        Vite = Join-Path $Root "frontend_web\node_modules\vite\bin\vite.js"
    }
}

function Assert-StartupEnvironment {
    param($Paths)

    if (-not (Test-Path -LiteralPath $Paths.Backend -PathType Container)) {
        throw "Diretorio do backend nao encontrado."
    }
    if (-not (Test-Path -LiteralPath $Paths.Frontend -PathType Container)) {
        throw "Diretorio do frontend nao encontrado."
    }
    if (-not (Test-Path -LiteralPath $Paths.Python -PathType Leaf)) {
        throw "Ambiente Python ausente em backend\.venv."
    }
    if (-not $Paths.Npm -or -not (Test-Path -LiteralPath $Paths.Npm -PathType Leaf)) {
        throw "npm.cmd nao encontrado. Instale o Node.js antes de iniciar."
    }
    if (-not $Paths.Node -or -not (Test-Path -LiteralPath $Paths.Node -PathType Leaf)) {
        throw "node.exe nao encontrado. Instale o Node.js antes de iniciar."
    }
    if (-not (Test-Path -LiteralPath $Paths.Vite -PathType Leaf)) {
        throw "Vite local nao encontrado. Instale previamente as dependencias do frontend."
    }
    if (-not (Test-Path -LiteralPath $Paths.EnvFile -PathType Leaf)) {
        throw "backend/.env ausente. Crie a configuracao local antes de iniciar."
    }
}

function Test-PortAvailable {
    param([int]$Port)

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
    )
    try {
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        $listener.Stop()
    }
}

function Assert-PortsAvailable {
    param([int[]]$Ports = @(8000, 5173))

    $occupied = @($Ports | Where-Object { -not (Test-PortAvailable $_) })
    if ($occupied.Count -gt 0) {
        throw "Porta(s) ocupada(s): $($occupied -join ', '). Nenhum processo foi encerrado."
    }
}

function Invoke-BackendPreflight {
    param($Paths)

    $oldDebug = [Environment]::GetEnvironmentVariable("DEBUG", "Process")
    try {
        [Environment]::SetEnvironmentVariable("DEBUG", "false", "Process")
        $output = & $Paths.Python -m app.cli.startup_check 2>$null
        $exitCode = $LASTEXITCODE
    }
    finally {
        [Environment]::SetEnvironmentVariable("DEBUG", $oldDebug, "Process")
    }
    if (-not $output) {
        throw "PostgreSQL indisponivel ou configuracao invalida."
    }
    try {
        $result = $output | ConvertFrom-Json
    }
    catch {
        throw "Nao foi possivel validar o PostgreSQL de forma segura."
    }
    if ($result.database -ne "available" -or $exitCode -eq 2) {
        throw "PostgreSQL indisponivel. Verifique o servico e backend/.env."
    }
    if (-not $result.migrations_match -or $exitCode -eq 3) {
        throw "Migration pendente: revision atual difere do head esperado. Nenhuma migration foi aplicada."
    }
    return $result
}

function Start-OwnedProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )

    $previous = @{}
    try {
        foreach ($name in $Environment.Keys) {
            $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
            [Environment]::SetEnvironmentVariable($name, $Environment[$name], "Process")
        }
        $process = Start-Process -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -NoNewWindow -PassThru
    }
    finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
        }
    }
    $script:StartedProcesses.Add($process)
    [void]$script:KnownProcessIds.Add($process.Id)
    return $process
}

function Get-OwnedDescendantIds {
    param([int[]]$RootIds)

    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $result = [System.Collections.Generic.HashSet[int]]::new()
    $pending = [System.Collections.Generic.Queue[int]]::new()
    foreach ($id in $RootIds) { $pending.Enqueue($id) }
    while ($pending.Count -gt 0) {
        $parent = $pending.Dequeue()
        foreach ($child in $all | Where-Object { $_.ParentProcessId -eq $parent }) {
            if ($result.Add([int]$child.ProcessId)) {
                $pending.Enqueue([int]$child.ProcessId)
            }
        }
    }
    return @($result)
}

function Stop-OwnedProcesses {
    $roots = @($script:StartedProcesses | ForEach-Object { $_.Id })
    if ($roots.Count -eq 0) { return }
    $descendants = @(Get-OwnedDescendantIds -RootIds $roots)
    foreach ($id in $descendants) { [void]$script:KnownProcessIds.Add([int]$id) }
    foreach ($id in @($descendants + $roots) | Select-Object -Unique | Sort-Object -Descending) {
        if ($id -eq $PID) { continue }
        $process = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $id -ErrorAction SilentlyContinue
            try { Wait-Process -Id $id -Timeout 5 -ErrorAction SilentlyContinue } catch {}
            $process = Get-Process -Id $id -ErrorAction SilentlyContinue
            if ($process -and $script:KnownProcessIds.Contains([int]$id)) {
                Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

function Wait-ServiceReady {
    param(
        [string]$Name,
        [string]$Url,
        $Process,
        [int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "$Name encerrou antes de ficar pronto."
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        }
        catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "$Name nao ficou pronto em $TimeoutSeconds segundos."
}

function Open-MesaQuantMasterBrowser {
    param(
        [string]$Url = "http://127.0.0.1:5173/",
        [scriptblock]$PrimaryOpener = {
            param($TargetUrl)
            Start-Process -FilePath $TargetUrl -ErrorAction Stop
        },
        [scriptblock]$FallbackOpener = {
            param($TargetUrl)
            $explorer = Join-Path $env:WINDIR "explorer.exe"
            Start-Process -FilePath $explorer -ArgumentList @($TargetUrl) -ErrorAction Stop
        },
        [scriptblock]$MessageWriter = {
            param($Message)
            Write-Host $Message -ForegroundColor Yellow
        }
    )

    try {
        & $PrimaryOpener $Url
        return $true
    }
    catch {
        try {
            & $FallbackOpener $Url
            return $true
        }
        catch {
            & $MessageWriter "Nao foi possivel abrir o navegador automaticamente."
            & $MessageWriter "Abra manualmente: $Url"
            return $false
        }
    }
}

function Invoke-MesaQuantMaster {
    param(
        [switch]$NoBrowser,
        [switch]$SkipDatabaseCheck,
        [int]$StartupTimeoutSeconds
    )

    Write-Host "Mesa Quant Master"
    Write-Host "Verificando ambiente..."
    $paths = Get-StartupPaths
    Assert-StartupEnvironment $paths
    Assert-PortsAvailable

    Push-Location $paths.Backend
    try {
        if ($SkipDatabaseCheck) {
            Write-Host "PostgreSQL: verificacao ignorada por solicitacao explicita."
        }
        else {
            [void](Invoke-BackendPreflight $paths)
            Write-Host "PostgreSQL: disponivel"
            Write-Host "Migrations: atualizadas"
        }

        Write-Host "Iniciando backend..."
        $backend = Start-OwnedProcess -FilePath $paths.Python `
            -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
            -WorkingDirectory $paths.Backend -Environment @{ DEBUG = "false" }

        Write-Host "Iniciando frontend..."
        $frontend = Start-OwnedProcess -FilePath $paths.Node `
            -ArgumentList @("`"$($paths.Vite)`"", "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
            -WorkingDirectory $paths.Frontend `
            -Environment @{ VITE_API_BASE_URL = "http://127.0.0.1:8000" }

        Wait-ServiceReady -Name "Backend" -Url "http://127.0.0.1:8000/" `
            -Process $backend -TimeoutSeconds $StartupTimeoutSeconds
        Wait-ServiceReady -Name "Frontend" -Url "http://127.0.0.1:5173/" `
            -Process $frontend -TimeoutSeconds $StartupTimeoutSeconds

        Write-Host "Backend: http://127.0.0.1:8000"
        Write-Host "Frontend: http://127.0.0.1:5173"
        if (-not $NoBrowser) {
            [void](Open-MesaQuantMasterBrowser)
        }
        Write-Host "Pressione Ctrl+C para encerrar."

        while (-not $backend.HasExited -and -not $frontend.HasExited) {
            Start-Sleep -Milliseconds 500
        }
        if ($backend.HasExited) { throw "Backend encerrou inesperadamente." }
        throw "Frontend encerrou inesperadamente."
    }
    finally {
        Write-Host "Encerrando servicos iniciados..."
        Stop-OwnedProcesses
        Pop-Location
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    $exitCode = 0
    try {
        Invoke-MesaQuantMaster -NoBrowser:$NoBrowser `
            -SkipDatabaseCheck:$SkipDatabaseCheck `
            -StartupTimeoutSeconds $StartupTimeoutSeconds
    }
    catch {
        Write-Host "Erro: $($_.Exception.Message)" -ForegroundColor Red
        $exitCode = 1
    }
    if ($DedicatedWindow) {
        $global:LASTEXITCODE = $exitCode
        Write-Host "Aplicacao encerrada. Voce pode fechar esta janela."
        return
    }
    exit $exitCode
}
