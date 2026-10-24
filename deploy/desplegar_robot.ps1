<#
  Sube el agente N Club al AGIBOT X2 y lo inicia, conectado al backend de este PC.

  Uso (PowerShell, desde la carpeta del proyecto):
    .\deploy\desplegar_robot.ps1                 # sube, instala (primera vez) e inicia
    .\deploy\desplegar_robot.ps1 -Gestos         # además saluda con el brazo
    .\deploy\desplegar_robot.ps1 -Reinstalar     # fuerza reinstalar dependencias
    .\deploy\desplegar_robot.ps1 -SoloReiniciar  # no sube nada; reinicia el agente

  Requisitos: cable al puerto SDK, este PC con IP 10.0.1.2, acceso SSH por llave
  (ver deploy\README.md) y el backend corriendo (.\deploy\iniciar_backend.ps1).
#>
param(
  [string]$Robot = "10.0.1.41",
  [string]$Usuario = "agi",
  [string]$PcIp = "10.0.1.2",
  [int]$Puerto = 8000,
  [string]$RobotId = "robot1",
  [switch]$Gestos,
  [switch]$SinVoz,
  [switch]$Reinstalar,
  [switch]$SoloReiniciar
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$destino = "$Usuario@$Robot"
$ssh = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=10")

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Remoto($comando) {
  & ssh @ssh $destino $comando
  if ($LASTEXITCODE -ne 0) { throw "Falló en el robot: $comando" }
}

Paso "1. Conexión con el robot ($destino)"
& ssh @ssh $destino "echo conectado" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Sin acceso SSH sin contraseña. Revise el cable, la IP $PcIp y la llave (deploy\README.md)." }
Write-Host "OK"

Paso "2. Backend en este PC (http://${PcIp}:$Puerto)"
try {
  $health = Invoke-RestMethod "http://127.0.0.1:$Puerto/health" -TimeoutSec 5
  Write-Host "OK · base de datos: $($health.database)"
} catch {
  Write-Warning "El backend no responde. Inícielo en otra ventana: .\deploy\iniciar_backend.ps1"
}

if (-not $SoloReiniciar) {
  Paso "3. Empaquetando el agente"
  $envFile = Join-Path $root "backend\.env"
  $clave = (Get-Content $envFile | Where-Object { $_ -match '^ROBOT_API_KEY=' }) -replace '^ROBOT_API_KEY=', ''
  if (-not $clave) { throw "No hay ROBOT_API_KEY en backend\.env" }
  $stage = Join-Path $env:TEMP "nclub_deploy"
  if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
  New-Item -ItemType Directory -Force "$stage\robot_agent", "$stage\vision\models" | Out-Null
  Copy-Item "$root\robot_agent\nclub_agent", "$root\robot_agent\config", "$root\robot_agent\launch", "$root\robot_agent\package.xml", "$root\robot_agent\setup.py", "$root\robot_agent\setup.cfg" "$stage\robot_agent" -Recurse
  Copy-Item "$root\vision\nclub_vision", "$root\vision\pyproject.toml", "$root\vision\requirements.txt" "$stage\vision" -Recurse
  Copy-Item "$root\vision\models\*.onnx" "$stage\vision\models"
  Copy-Item "$root\deploy\robot\*" $stage
  Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
  $robotEnv = @(
    "NCLUB_ROBOT_KEY=$clave",
    "NCLUB_API_URL=http://${PcIp}:$Puerto",
    "NCLUB_ROBOT_ID=$RobotId",
    "NCLUB_GESTURES=$(if ($Gestos) { 'true' } else { 'false' })",
    "NCLUB_ASR=$(if ($SinVoz) { 'none' } else { 'faster-whisper' })",
    "NCLUB_ASR_MODEL=small"
  ) -join "`n"
  [IO.File]::WriteAllText("$stage\robot.env", "$robotEnv`n")  # LF y sin BOM
  $tgz = Join-Path $env:TEMP "nclub_deploy.tgz"
  if (Test-Path $tgz) { Remove-Item $tgz -Force }
  tar -czf $tgz -C $stage .
  Write-Host ("OK · {0:N1} MB" -f ((Get-Item $tgz).Length / 1MB))

  Paso "4. Subiendo al robot"
  & scp -q @ssh $tgz "${destino}:/tmp/nclub_deploy.tgz"
  if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar el paquete" }
  Remoto "mkdir -p ~/nclub && tar -xzf /tmp/nclub_deploy.tgz -C ~/nclub && cd ~/nclub && sed -i 's/\r$//' *.sh robot.env && chmod 600 robot.env && chmod +x *.sh && rm /tmp/nclub_deploy.tgz"
  Write-Host "OK · ~/nclub"

  Paso "5. Instalando dependencias en el robot (la primera vez tarda varios minutos)"
  $instalado = (& ssh @ssh $destino "test -f ~/nclub/.instalado && echo si") -eq "si"
  if ($Reinstalar -or -not $instalado) {
    Remoto "cd ~/nclub && set -a && . ./robot.env && set +a && bash install.sh 2>&1 | tail -n 15 && touch ~/nclub/.instalado"
  } else {
    Write-Host "Ya instalado (use -Reinstalar para repetir)"
  }
}

Paso "6. Iniciando el agente de recepción"
Remoto "bash ~/nclub/start.sh"

Paso "Listo"
Write-Host "Abra la app web: Admin -> Robots (sesión ADMIN). El robot debe aparecer en línea."
Write-Host "Estado:   ssh $destino 'bash ~/nclub/status.sh'"
Write-Host "Detener:  ssh $destino 'bash ~/nclub/stop.sh'"
