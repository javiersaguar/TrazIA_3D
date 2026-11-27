# Keep the existing local API, database and tunnel available without an interactive terminal.
param(
    [Parameter(Mandatory = $true)][string]$PublicOrigin,
    [string]$GroqEnvFile,
    [string]$TunnelUrl,
    [int]$ApiPort = 8020,
    [int]$DatabasePort = 55433
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$data = Join-Path $project 'generated\cuentas-datos'
$cluster = Join-Path $project 'generated\cuentas-postgres'
$python = Join-Path $project '.venv\Scripts\python.exe'
$logRoot = Join-Path $project 'generated\servicio-windows'
$keyPath = Join-Path $env:LOCALAPPDATA 'TrazIA-3D\catalogue-db-password.txt'
$pgCtl = (Get-Command pg_ctl.exe).Source
$ngrok = (Get-Command ngrok.exe).Source

foreach ($required in @($data, $cluster, $python, $keyPath)) {
    if (!(Test-Path -LiteralPath $required)) { throw "Falta el recurso local $required" }
}
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

$key = [Uri]::EscapeDataString([IO.File]::ReadAllText($keyPath).Trim())
$env:TRAZIA_DATABASE_URL = "postgresql+psycopg://trazia:${key}@127.0.0.1:${DatabasePort}/trazia"
$env:TRAZIA_DATA = $data
$env:TRAZIA_ROOT = $project
$env:PYTHONPATH = Join-Path $project 'src'
$env:TRAZIA_AUTH = '1'
$env:TRAZIA_AUTH_COOKIE_SECURE = '1'
$env:TRAZIA_EXTERNAL_PROVIDERS = 'synthetic_only'
$env:TRAZIA_CORS_ORIGINS = "$($PublicOrigin.TrimEnd('/')),http://127.0.0.1:3120,http://localhost:3120"
if ($GroqEnvFile -and (Test-Path -LiteralPath $GroqEnvFile -PathType Leaf)) {
    $settings = Get-Content -LiteralPath $GroqEnvFile
    foreach ($name in @('GROQ_API_KEY', 'TRAZIA_VOICE_GROQ_FREE', 'GROQ_VOICE_FREE_API_KEY')) {
        $prefix = "^\s*$name\s*="
        $line = $settings | Where-Object { $_ -match $prefix } | Select-Object -First 1
        if ($line) {
            [Environment]::SetEnvironmentVariable($name, ($line -replace $prefix, '').Trim().Trim('"').Trim("'"), 'Process')
        }
    }
}

function Write-ServiceLog([string]$Message) {
    Add-Content -LiteralPath (Join-Path $logRoot 'supervisor.log') -Value "$(Get-Date -Format o) $Message"
}

function Test-Listener([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Stop-OwnedApi([System.Diagnostics.Process]$Launcher) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$listener -or $listener.OwningProcess -eq $Launcher.Id) {
        Stop-Process -InputObject $Launcher
        return
    }
    # The Windows venv launcher can delegate the listening socket to its child.
    $worker = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($worker.ParentProcessId -eq $Launcher.Id) {
        Stop-Process -Id $worker.ProcessId
    } else {
        Write-ServiceLog 'El proceso que escucha no pertenece al supervisor; no se detuvo.'
    }
}

function Test-Api {
    try {
        $response = Invoke-WebRequest "http://127.0.0.1:$ApiPort/health" -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Start-LocalProcess([string]$File, [string[]]$CommandArguments, [string]$Name) {
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $process = Start-Process -FilePath $File -ArgumentList $CommandArguments -WorkingDirectory $project `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "$Name-$timestamp.out.log") `
        -RedirectStandardError (Join-Path $logRoot "$Name-$timestamp.err.log")
    Write-ServiceLog "$Name iniciado (PID $($process.Id))."
    return $process
}

$api = $null
$tunnel = $null
$databaseStart = $null
$failedChecks = 0
Write-ServiceLog 'Supervisor iniciado.'
while ($true) {
    try {
        if ($databaseStart -and $databaseStart.HasExited) {
            Write-ServiceLog "Arranque de PostgreSQL: codigo $($databaseStart.ExitCode)."
            $databaseStart = $null
        }
        if (!$databaseStart -and !(Test-Listener $DatabasePort)) {
            & $pgCtl -D $cluster status | Out-Null
            if ($LASTEXITCODE -ne 0) {
                # Postgres can inherit pg_ctl's stdout. A PowerShell pipeline may wait for EOF
                # after the launcher has exited. Redirect to files and keep supervising the ports.
                $databaseLog = Join-Path $logRoot 'postgres.log'
                $databaseStart = Start-LocalProcess $pgCtl @(
                    '-D', ('"{0}"' -f $cluster), '-l', ('"{0}"' -f $databaseLog),
                    '-o', ('"-h 127.0.0.1 -p {0}"' -f $DatabasePort), '-w', '-t', '15', 'start'
                ) 'pg-ctl'
            }
        }

        if ($api -and $api.HasExited) {
            Write-ServiceLog "API terminada (PID $($api.Id), codigo $($api.ExitCode))."
            $api = $null
        }
        if (!$api -and (Test-Listener $DatabasePort) -and !(Test-Listener $ApiPort)) {
            $api = Start-LocalProcess $python @('-m', 'uvicorn', 'trazia.api.app:create_app', '--factory', '--host', '127.0.0.1', '--port', $ApiPort) 'api'
            $started = Get-Date
            $failedChecks = 0
        } elseif ($api -and (Get-Date) -gt $started.AddSeconds(45)) {
            if (Test-Api) { $failedChecks = 0 } else { $failedChecks++ }
            if ($failedChecks -ge 4) {
                Write-ServiceLog "API sin respuesta en cuatro comprobaciones. Reiniciando PID $($api.Id)."
                Stop-OwnedApi $api
            }
        }

        if ($tunnel -and $tunnel.HasExited) {
            Write-ServiceLog "ngrok terminado (PID $($tunnel.Id), codigo $($tunnel.ExitCode))."
            $tunnel = $null
        }
        if (!$tunnel -and !(Test-Listener 4040) -and (Test-Api)) {
            $tunnelArguments = @('http', "http://127.0.0.1:$ApiPort", '--inspect=false', '--log', 'stdout')
            if ($TunnelUrl) { $tunnelArguments += @('--url', $TunnelUrl) }
            $tunnel = Start-LocalProcess $ngrok $tunnelArguments 'ngrok'
        }
    } catch {
        Write-ServiceLog "Error del supervisor: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 5
}
