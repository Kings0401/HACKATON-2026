<#
  Levanta todo N Club con un solo comando: red del robot, backend, app web,
  agente del robot y el panel Admin -> Robots en el navegador.

    .\deploy\iniciar_todo.ps1                     # cámara de la frente
    .\deploy\iniciar_todo.ps1 -Camara rgbd -Gestos
    .\deploy\iniciar_todo.ps1 -SoloReiniciar      # robot ya cargado: solo lo reinicia

  Si PowerShell bloquea scripts:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#>
param(
  [string]$Camara = "frente",
  [switch]$Gestos,
  [switch]$SoloReiniciar,
  [string]$Robot = "10.0.1.41",
  [string]$PcIp = "10.0.1.2",
  [int]$Puerto = 8000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
function Paso($texto) { Write-Host "`n### $texto" -ForegroundColor Yellow }

Paso "1/5 Cable al robot"
$adaptador = Get-NetAdapter -Physical -ErrorAction SilentlyContinue |
  Where-Object { $_.Status -eq "Up" -and $_.InterfaceDescription -notmatch "Wi-?Fi|Wireless|Bluetooth" } |
  Select-Object -First 1
if (-not $adaptador) { throw "No hay un adaptador de cable conectado. Conecte el cable al puerto SDK trasero del robot y enciéndalo." }
$tieneIp = Get-NetIPAddress -InterfaceAlias $adaptador.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -eq $PcIp }
if (-not $tieneIp) {
  Write-Host "Asignando $PcIp/24 a '$($adaptador.Name)' (acepte el aviso de Windows)..."
  $cmd = "Set-NetIPInterface -InterfaceAlias '$($adaptador.Name)' -Dhcp Disabled; " +
         "Get-NetIPAddress -InterfaceAlias '$($adaptador.Name)' -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:`$false; " +
         "New-NetIPAddress -InterfaceAlias '$($adaptador.Name)' -IPAddress $PcIp -PrefixLength 24 | Out-Null"
  Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile", "-Command", $cmd
  Start-Sleep -Seconds 3
}
if (-not (Test-Connection $Robot -Count 2 -Quiet)) { throw "El robot ($Robot) no responde. ¿Está encendido y con el cable en el puerto SDK?" }
Write-Host "OK · $($adaptador.Name) con $PcIp, robot responde"

Paso "2/5 Backend (ventana nueva)"
$ok = $false
try { Invoke-RestMethod "http://127.0.0.1:$Puerto/health" -TimeoutSec 3 | Out-Null; $ok = $true } catch {}
if (-not $ok) {
  Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "iniciar_backend.ps1"), "-Puerto", $Puerto
  for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
    Start-Sleep -Seconds 2
    try { Invoke-RestMethod "http://127.0.0.1:$Puerto/health" -TimeoutSec 2 | Out-Null; $ok = $true } catch {}
  }
  if (-not $ok) { throw "El backend no arrancó: revise la ventana del backend." }
}
Write-Host "OK · http://127.0.0.1:$Puerto"

Paso "3/5 App web (ventana nueva)"
$web = $false
try { Invoke-WebRequest "http://localhost:5173" -UseBasicParsing -TimeoutSec 3 | Out-Null; $web = $true } catch {}
if (-not $web) {
  $npm = "Set-Location '$root'; if (-not (Test-Path node_modules)) { npm install }; npm run dev"
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $npm
  Start-Sleep -Seconds 6
}
Write-Host "OK · http://localhost:5173"

Paso "4/5 Robot"
$opciones = @{ Camara = $Camara; Robot = $Robot; PcIp = $PcIp; Puerto = $Puerto }
if ($Gestos) { $opciones.Gestos = $true }
if ($SoloReiniciar) { $opciones.SoloReiniciar = $true }
& (Join-Path $PSScriptRoot "desplegar_robot.ps1") @opciones

Paso "5/5 Panel"
Start-Process "http://localhost:5173/#/admin/robots"
Write-Host "Entre con su cuenta ADMIN (Mi membresía, no Explorar demo)." -ForegroundColor Green
