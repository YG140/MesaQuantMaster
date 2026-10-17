$scriptPath = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "start.ps1"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. $scriptPath

Describe "Modo sincronizado PC e APK" {
    It "aceita somente endereco HTTPS publico do site" {
        $uri = Assert-PublicCloudWebUri -Url "https://mesa-quant-master-web.onrender.com/"
        $uri.AbsoluteUri | Should Be "https://mesa-quant-master-web.onrender.com/"
    }

    It "recusa HTTP, localhost, login embutido e fragmento" {
        @(
            "http://mesa-quant-master-web.onrender.com/",
            "https://localhost:5173/",
            "https://127.0.0.1:5173/",
            "https://usuario:senha@mesa-quant-master-web.onrender.com/",
            "https://mesa-quant-master-web.onrender.com/#token"
        ) | ForEach-Object {
            { Assert-PublicCloudWebUri -Url $_ } | Should Throw
        }
    }

    It "abre o site com HTTPS sem iniciar servidores ou verificar banco local" {
        Mock Open-MesaQuantMasterBrowser { return $true }
        Mock Invoke-MesaQuantMaster { throw "Nao pode iniciar backend local" }
        Mock Invoke-BackendPreflight { throw "Nao pode consultar banco local" }
        Mock Start-OwnedProcess { throw "Nao pode iniciar subprocessos" }

        Invoke-MesaQuantMasterCloud -CloudWebUrl "https://mesa-quant-master-web.onrender.com/"

        Assert-MockCalled Open-MesaQuantMasterBrowser 1 -Scope It -ParameterFilter {
            $Url -eq "https://mesa-quant-master-web.onrender.com/"
        }
        Assert-MockCalled Invoke-MesaQuantMaster 0 -Scope It
        Assert-MockCalled Invoke-BackendPreflight 0 -Scope It
        Assert-MockCalled Start-OwnedProcess 0 -Scope It
    }

    It "NoBrowser nao abre o site" {
        Mock Open-MesaQuantMasterBrowser { throw "Nao deveria abrir navegador" }
        Invoke-MesaQuantMasterCloud -CloudWebUrl "https://mesa-quant-master-web.onrender.com/" -NoBrowser
        Assert-MockCalled Open-MesaQuantMasterBrowser 0 -Scope It
    }

    It "mantem o atalho local inalterado e o atalho remoto separado" {
        $local = Get-Content (Join-Path $repoRoot "Iniciar MesaQuantMaster.bat") -Raw
        $cloud = Get-Content (Join-Path $repoRoot "Abrir MesaQuantMaster Sincronizado.bat") -Raw
        $local | Should Not Match " -Cloud"
        $cloud | Should Match 'start\.ps1" -Cloud -DedicatedWindow'
    }

    It "nunca conecta o APK diretamente a banco local" {
        $doc = Get-Content (Join-Path $repoRoot "SINCRONIZACAO_PC_APK.md") -Raw
        $doc | Should Match "mesma API HTTPS"
        $doc | Should Match "backup offline"
    }
}
