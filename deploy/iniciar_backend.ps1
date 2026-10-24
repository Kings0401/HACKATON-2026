<#
  Inicia el backend FastAPI en este PC, accesible para el robot por el cable.

    .\deploy\iniciar_backend.ps1            # Supabase real (backend\.env)
    .\deploy\iniciar_backend.ps1 -Memoria   # datos ficticios, todo marcado como simulación
#>
param([int]$Puerto = 8000, [switch]$Memoria)
$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  Write-Host "Creando entorno de Python del backend (una sola vez)..." -ForegroundColor Cyan
  python -m venv (Join-Path $backend ".venv")
  Push-Location $backend
  try { & $python -m pip install -q -r requirements.txt } finally { Pop-Location }
}
if (-not (Test-Path (Join-Path $backend ".env")) -and -not $Memoria) {
  throw "Falta backend\.env (copie backend\.env.example y complete las claves)"
}

# El robot entra por el cable: abrir el puerto en el firewall de Windows (una vez, pide permiso).
$regla = "N Club backend $Puerto"
if (-not (Get-NetFirewallRule -DisplayName $regla -ErrorAction SilentlyContinue)) {
  Write-Host "Abriendo el puerto $Puerto en el firewall (acepte el aviso de Windows)..." -ForegroundColor Cyan
  $cmd = "New-NetFirewallRule -DisplayName '$regla' -Direction Inbound -Protocol TCP -LocalPort $Puerto -Action Allow -Profile Any"
  try { Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $cmd }
  catch { Write-Warning "No se abrió el puerto; si el robot no conecta, permita Python en el firewall." }
}

$env:PUBLIC_API_URL = "http://127.0.0.1:$Puerto"
$env:CORS_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"
if ($Memoria) { $env:NCLUB_BACKEND_MODE = "memory" }
Write-Host "Backend en http://0.0.0.0:$Puerto (robot: http://10.0.1.2:$Puerto). Ctrl+C para detener." -ForegroundColor Green
Push-Location $backend
try { & $python -m uvicorn app.main:app --host 0.0.0.0 --port $Puerto } finally { Pop-Location }
