$scriptPath = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "start.ps1"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. $scriptPath

function New-FakePaths {
    param([string]$Root)
    [pscustomobject]@{
        Root = $Root
        Backend = Join-Path $Root "backend"
        Frontend = Join-Path $Root "frontend_web"
        Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
        EnvFile = Join-Path $Root "backend\.env"
        Npm = Join-Path $Root "tools\npm.cmd"
        Node = Join-Path $Root "tools\node.exe"
        Vite = Join-Path $Root "frontend_web\node_modules\vite\bin\vite.js"
    }
}

Describe "Inicializador unificado" {
    BeforeEach {
        $script:StartedProcesses = [System.Collections.Generic.List[System.Diagnostics.Process]]::new()
        $script:KnownProcessIds = [System.Collections.Generic.HashSet[int]]::new()
    }

    It "resolve caminhos a partir da raiz informada" {
        $paths = Get-StartupPaths -Root "C:\projeto com espacos"
        $paths.Python | Should Be "C:\projeto com espacos\backend\.venv\Scripts\python.exe"
        $paths.Frontend | Should Be "C:\projeto com espacos\frontend_web"
        $paths.Vite | Should Be "C:\projeto com espacos\frontend_web\node_modules\vite\bin\vite.js"
    }

    It "falha quando Python nao existe" {
        $root = Join-Path $TestDrive "missing-python"
        New-Item "$root\backend", "$root\frontend_web\node_modules\vite\bin", "$root\tools" -ItemType Directory -Force | Out-Null
        New-Item "$root\backend\.env", "$root\tools\npm.cmd", "$root\tools\node.exe", "$root\frontend_web\node_modules\vite\bin\vite.js" -ItemType File -Force | Out-Null
        { Assert-StartupEnvironment (New-FakePaths $root) } | Should Throw
    }

    It "falha quando npm nao existe" {
        $root = Join-Path $TestDrive "missing-npm"
        New-Item "$root\backend\.venv\Scripts", "$root\frontend_web\node_modules\vite\bin", "$root\tools" -ItemType Directory -Force | Out-Null
        New-Item "$root\backend\.env", "$root\backend\.venv\Scripts\python.exe", "$root\tools\node.exe", "$root\frontend_web\node_modules\vite\bin\vite.js" -ItemType File -Force | Out-Null
        { Assert-StartupEnvironment (New-FakePaths $root) } | Should Throw
    }

    It "falha quando backend env nao existe" {
        $root = Join-Path $TestDrive "missing-env"
        New-Item "$root\backend\.venv\Scripts", "$root\frontend_web\node_modules\vite\bin", "$root\tools" -ItemType Directory -Force | Out-Null
        New-Item "$root\backend\.venv\Scripts\python.exe", "$root\tools\npm.cmd", "$root\tools\node.exe", "$root\frontend_web\node_modules\vite\bin\vite.js" -ItemType File -Force | Out-Null
        { Assert-StartupEnvironment (New-FakePaths $root) } | Should Throw
    }

    It "bloqueia quando porta 8000 esta ocupada" {
        Mock Test-PortAvailable { param($Port) return $Port -ne 8000 }
        { Assert-PortsAvailable } | Should Throw
    }

    It "bloqueia quando porta 5173 esta ocupada" {
        Mock Test-PortAvailable { param($Port) return $Port -ne 5173 }
        { Assert-PortsAvailable } | Should Throw
    }

    It "nao inicia filhos quando preflight do banco falha" {
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}
        Mock Assert-PortsAvailable {}
        Mock Invoke-BackendPreflight { throw "PostgreSQL indisponivel" }
        Mock Start-OwnedProcess {}
        Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -NoBrowser -StartupTimeoutSeconds 5 } | Should Throw
        Assert-MockCalled Start-OwnedProcess 0 -Scope It
    }

    It "bloqueia migration divergente antes de iniciar filhos" {
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}
        Mock Assert-PortsAvailable {}
        Mock Invoke-BackendPreflight { throw "Migration pendente" }
        Mock Start-OwnedProcess {}
        Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -NoBrowser -StartupTimeoutSeconds 5 } | Should Throw
        Assert-MockCalled Start-OwnedProcess 0 -Scope It
    }

    It "encerra frontend se backend falha no readiness" {
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}; Mock Assert-PortsAvailable {}; Mock Invoke-BackendPreflight { @{} }
        Mock Start-OwnedProcess { [pscustomobject]@{ Id = 101; HasExited = $false } }
        Mock Wait-ServiceReady { param($Name) if ($Name -eq "Backend") { throw "Backend falhou" } }
        Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -NoBrowser -StartupTimeoutSeconds 5 } | Should Throw
        Assert-MockCalled Stop-OwnedProcesses 1 -Scope It
    }

    It "encerra backend se frontend falha no readiness" {
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}; Mock Assert-PortsAvailable {}; Mock Invoke-BackendPreflight { @{} }
        Mock Start-OwnedProcess { [pscustomobject]@{ Id = 102; HasExited = $false } }
        Mock Wait-ServiceReady { param($Name) if ($Name -eq "Frontend") { throw "Frontend falhou" } }
        Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -NoBrowser -StartupTimeoutSeconds 5 } | Should Throw
        Assert-MockCalled Stop-OwnedProcesses 1 -Scope It
    }

    It "timeout de readiness gera erro objetivo" {
        $source = Get-Content $scriptPath -Raw
        $source | Should Match "nao ficou pronto em.*segundos"
        $source | Should Match "AddSeconds\(\`$TimeoutSeconds\)"
    }

    It "cleanup e executado quando o monitoramento e interrompido" {
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}; Mock Assert-PortsAvailable {}; Mock Invoke-BackendPreflight { @{} }
        Mock Start-OwnedProcess { [pscustomobject]@{ Id = 103; HasExited = $true } }
        Mock Wait-ServiceReady {}
        Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -NoBrowser -StartupTimeoutSeconds 5 } | Should Throw
        Assert-MockCalled Stop-OwnedProcesses 1 -Scope It
    }

    It "cleanup limita encerramento aos PIDs conhecidos e descendentes" {
        $rows = @(
            [pscustomobject]@{ ProcessId = 201; ParentProcessId = 200 },
            [pscustomobject]@{ ProcessId = 202; ParentProcessId = 201 },
            [pscustomobject]@{ ProcessId = 999; ParentProcessId = 50 }
        )
        Mock Get-CimInstance { $rows }
        $owned = @(Get-OwnedDescendantIds -RootIds @(200))
        ($owned -contains 201) | Should Be $true
        ($owned -contains 202) | Should Be $true
        ($owned -contains 999) | Should Be $false
    }

    It "abre navegador somente depois dos dois readiness" {
        $script:order = @()
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}; Mock Assert-PortsAvailable {}; Mock Invoke-BackendPreflight { @{} }
        Mock Start-OwnedProcess { [pscustomobject]@{ Id = 104; HasExited = $true } }
        Mock Wait-ServiceReady { param($Name) $script:order += $Name }
        Mock Open-MesaQuantMasterBrowser { $script:order += "Browser"; return $true }
        Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -StartupTimeoutSeconds 5 } | Should Throw
        $script:order[0] | Should Be "Backend"
        $script:order[1] | Should Be "Frontend"
        $script:order[2] | Should Be "Browser"
        Assert-MockCalled Open-MesaQuantMasterBrowser 1 -Scope It
    }

    It "NoBrowser nao abre navegador" {
        Mock Get-StartupPaths { New-FakePaths $repoRoot }
        Mock Assert-StartupEnvironment {}; Mock Assert-PortsAvailable {}; Mock Invoke-BackendPreflight { @{} }
        Mock Start-OwnedProcess { [pscustomobject]@{ Id = 105; HasExited = $true } }
        Mock Wait-ServiceReady {}; Mock Open-MesaQuantMasterBrowser {}; Mock Stop-OwnedProcesses {}
        { Invoke-MesaQuantMaster -NoBrowser -StartupTimeoutSeconds 5 } | Should Throw
        Assert-MockCalled Open-MesaQuantMasterBrowser 0 -Scope It
    }

    It "SkipDatabaseCheck nao remove validacao de portas" {
        $source = Get-Content $scriptPath -Raw
        $portsIndex = $source.IndexOf("Assert-PortsAvailable")
        $skipIndex = $source.IndexOf('if ($SkipDatabaseCheck)')
        $portsIndex | Should BeLessThan $skipIndex
    }

    It "BAT lanca nova janela desacoplada e encaminha argumentos" {
        $batPath = Join-Path $repoRoot "Iniciar MesaQuantMaster.bat"
        $bat = Get-Content $batPath -Raw
        $lines = @(Get-Content $batPath | Where-Object { $_.Trim() })
        $bat | Should Match "%~dp0"
        $bat | Should Match 'start "Mesa Quant Master" powershell\.exe'
        $bat | Should Match '-NoProfile -NoExit -ExecutionPolicy Bypass'
        $bat | Should Match '-File "%MQM_ROOT%start\.ps1" -DedicatedWindow %\*'
        $lines[-2] | Should Match '^start "Mesa Quant Master" powershell\.exe'
        $lines[-1] | Should Be "exit /b 0"
        $bat | Should Not Match "-NoBrowser"
        $bat | Should Not Match "pause|set /p|choice"
    }

    It "fontes do inicializador nao contem nomes de segredos em saida" {
        $source = Get-Content $scriptPath -Raw
        $source | Should Not Match "Write-(Host|Output).*DATABASE_URL"
        $source | Should Not Match "Write-(Host|Output).*(SECRET_KEY|BRAPI_API_KEY|SMTP_PASSWORD)"
    }

    It "nao usa taskkill nem encerramento por nome ou porta" {
        $source = Get-Content $scriptPath -Raw
        $source | Should Not Match "taskkill"
        $source | Should Not Match "Get-NetTCPConnection.*Stop-Process"
        $source | Should Not Match "Stop-Process.*-Name"
    }

    It "inicia o Vite local diretamente com node sem cadeia batch" {
        $source = Get-Content $scriptPath -Raw
        $source | Should Match 'Start-OwnedProcess -FilePath \$paths.Node'
        $source | Should Match '\$paths.Vite'
        $source | Should Not Match 'Start-OwnedProcess -FilePath \$paths.Npm'
        $source | Should Not Match 'Start-OwnedProcess -FilePath .*cmd\.exe'
        $source | Should Match '"--strictPort"'
    }

    It "preserva npm como validacao sem executa-lo" {
        $source = Get-Content $scriptPath -Raw
        $source | Should Match 'Get-Command npm\.cmd'
        $source | Should Match 'npm\.cmd nao encontrado'
        $source | Should Not Match '-FilePath \$paths.Npm'
    }

    It "BAT nao implementa nem inicia npm ou Vite" {
        $bat = Get-Content (Join-Path $repoRoot "Iniciar MesaQuantMaster.bat") -Raw
        $bat | Should Not Match "npm"
        $bat | Should Not Match "vite"
        $bat | Should Match '(?m)^start "Mesa Quant Master" powershell\.exe .* -File "%MQM_ROOT%start\.ps1" -DedicatedWindow %\*'
    }

    It "BAT nao aguarda powershell diretamente" {
        $lines = Get-Content (Join-Path $repoRoot "Iniciar MesaQuantMaster.bat")
        @($lines | Where-Object { $_ -match '^powershell\.exe' }).Count | Should Be 0
        @($lines | Where-Object { $_ -match '^start "Mesa Quant Master" powershell\.exe' }).Count | Should Be 1
    }

    It "caminho do script permanece cotado para raiz com espacos" {
        $bat = Get-Content (Join-Path $repoRoot "Iniciar MesaQuantMaster.bat") -Raw
        $bat | Should Match '-File "%MQM_ROOT%start\.ps1"'
        $bat | Should Match 'set "MQM_ROOT=%~dp0"'
    }

    It "janela dedicada retorna ao prompt em vez de executar exit" {
        $source = Get-Content $scriptPath -Raw
        $source | Should Match '\[switch\]\$DedicatedWindow'
        $source | Should Match 'if \(\$DedicatedWindow\)'
        $source | Should Match 'Aplicacao encerrada\. Voce pode fechar esta janela\.'
        $source | Should Match 'return\s*\}\s*exit \$exitCode'
    }

}

Describe "Abertura automatica do navegador" {
    It "abertura padrao solicita a URL publica exatamente uma vez" {
        $script:openedUrls = @()
        $opened = Open-MesaQuantMasterBrowser -PrimaryOpener {
            param($Url) $script:openedUrls += $Url
        }
        $opened | Should Be $true
        $script:openedUrls.Count | Should Be 1
        $script:openedUrls[0] | Should Be "http://127.0.0.1:5173/"
    }

    It "usa explorer como fallback controlado" {
        $script:fallbackUrls = @()
        $opened = Open-MesaQuantMasterBrowser `
            -PrimaryOpener { throw "associacao indisponivel" } `
            -FallbackOpener {
                param($Url) $script:fallbackUrls += $Url
        }
        $opened | Should Be $true
        $script:fallbackUrls.Count | Should Be 1
        $script:fallbackUrls[0] | Should Be "http://127.0.0.1:5173/"
    }

    It "falha de abertura e nao fatal e mostra somente URL publica" {
        $script:browserMessages = @()
        $opened = Open-MesaQuantMasterBrowser `
            -PrimaryOpener { throw "falha primaria" } `
            -FallbackOpener { throw "falha fallback" } `
            -MessageWriter { param($Message) $script:browserMessages += $Message }
        $output = $script:browserMessages -join "`n"
        $opened | Should Be $false
        $output | Should Match "Nao foi possivel abrir"
        $output | Should Match "http://127.0.0.1:5173/"
        $output | Should Not Match "DATABASE_URL|SECRET_KEY|TOKEN|PASSWORD"
    }

    It "falha ao abrir navegador nao chama cleanup" {
        Mock Stop-OwnedProcesses {}
        $opened = Open-MesaQuantMasterBrowser `
            -PrimaryOpener { throw "falha primaria" } `
            -FallbackOpener { throw "falha fallback" } `
            -MessageWriter {}
        $opened | Should Be $false
        Assert-MockCalled Stop-OwnedProcesses 0 -Scope It
    }

    It "nao reintroduz cadeia batch ou prompt de encerramento" {
        $source = Get-Content $scriptPath -Raw
        $bat = Get-Content (Join-Path $repoRoot "Iniciar MesaQuantMaster.bat") -Raw
        $source | Should Not Match 'Start-OwnedProcess -FilePath \$paths.Npm'
        $source | Should Not Match "cmd\.exe"
        $bat | Should Not Match "choice|set /p|Deseja finalizar"
    }
}
