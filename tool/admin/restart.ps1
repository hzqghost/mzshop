param(
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$adminDir = Join-Path $projectRoot "admin"
$pythonExe = Join-Path $adminDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Project virtual environment not found: $pythonExe"
}

$normalizedAdmin = $adminDir.Replace("\", "/")
$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match "^python(\.exe)?$" -and
    $_.CommandLine -match "uvicorn\s+app\.main:app" -and
    ($_.CommandLine -match [regex]::Escape($adminDir) -or
     $_.CommandLine -match [regex]::Escape($normalizedAdmin) -or
     $_.ExecutablePath -eq $pythonExe)
}

if ($processes) {
    $ids = @($processes | Select-Object -ExpandProperty ProcessId)
    Write-Host ("Stopping mzShop admin. PID: " + ($ids -join ", "))
    Stop-Process -Id $ids -Force
    Start-Sleep -Milliseconds 600
} else {
    Write-Host "No running mzShop admin process found. Starting a new process."
}

$arguments = @("-m", "uvicorn", "app.main:app", "--app-dir", $adminDir, "--host", "127.0.0.1", "--port", "$Port")
$started = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $adminDir -WindowStyle Hidden -PassThru
Write-Host "Started mzShop admin. PID: $($started.Id)"

$healthUrl = "http://127.0.0.1:$Port/login"
for ($attempt = 1; $attempt -le 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -Method Get -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Write-Host "Restart succeeded: $healthUrl" -ForegroundColor Green
            exit 0
        }
    } catch {
        # Connection failures are expected while the server is starting.
    }
}

throw "The process started but health check failed within 10 seconds: $healthUrl"
