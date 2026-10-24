<#
  Sube el agente N Club al Booster K1 y lo inicia, conectado al backend de este PC.
  Es el equivalente de deploy\desplegar_robot.ps1 (AGIBOT X2), que no se modifica.

  Uso (PowerShell, desde la carpeta del proyecto, con el backend en marcha):
    .\booster_k1\desplegar_k1.ps1                 # sube, instala (1.ª vez) e inicia
    .\booster_k1\desplegar_k1.ps1 -Gestos         # además saluda con la mano (solo si el K1 ya está en WALK)
    .\booster_k1\desplegar_k1.ps1 -Reinstalar     # repite la instalación de dependencias
    .\booster_k1\desplegar_k1.ps1 -SoloReiniciar  # no sube nada; reinicia el agente
    .\booster_k1\desplegar_k1.ps1 -Detener
#>
param(
  [string]$Robot = "192.168.10.102",
  [string]$Usuario = "booster",
  [string]$PcIp = "192.168.10.10",
  [int]$Puerto = 8000,
  [string]$RobotId = "robot1",
  [string]$AsrModel = "small",
  [string]$Voz = "es_MX-claude-high",
  [switch]$Gestos,
  [switch]$SinVoz,
  [switch]$Reinstalar,
  [switch]$SoloReiniciar,
  [switch]$Detener
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$destino = "$Usuario@$Robot"
$ssh = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15")
$tar = Join-Path $env:SystemRoot "System32\tar.exe"  # el tar de Windows (no el de Git)

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
# En PowerShell 5.1 con la salida redirigida, cualquier línea de stderr de ssh/scp
# se vuelve un error que corta el script; se juzga solo por el código de salida.
function EnK1 { $ErrorActionPreference = "Continue"; & ssh.exe @ssh $destino @args 2>&1 | ForEach-Object { "$_" } }
function Remoto($comando) {
  EnK1 $comando
  if ($LASTEXITCODE -ne 0) { throw "Falló en el K1: $comando" }
}

Paso "1. Conexión con el K1 ($destino)"
EnK1 "echo conectado" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Sin SSH al K1. Ejecute .\booster_k1\conectar.ps1 (red y llave)." }
Write-Host "OK"
if ($Detener) { Remoto "bash ~/nclub/stop_k1.sh"; return }

Paso "2. Backend en este PC (http://${PcIp}:$Puerto)"
$salud = EnK1 "curl -s -m 5 http://${PcIp}:$Puerto/health"
if ($salud -notmatch '"ok"') {
  Write-Warning "El K1 no alcanza el backend. Inícielo con .\deploy\iniciar_backend.ps1 y revise el firewall."
} else { Write-Host "OK · $salud" }

if (-not $SoloReiniciar) {
  Paso "3. Empaquetando el agente"
  $envFile = Join-Path $root "backend\.env"
  $clave = (Get-Content $envFile | Where-Object { $_ -match '^ROBOT_API_KEY=' }) -replace '^ROBOT_API_KEY=', ''
  if (-not $clave) { throw "No hay ROBOT_API_KEY en backend\.env" }
  $stage = Join-Path $env:TEMP "nclub_k1_deploy"
  if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
  New-Item -ItemType Directory -Force "$stage\robot_agent", "$stage\vision\models" | Out-Null
  Copy-Item "$root\robot_agent\nclub_agent" "$stage\robot_agent" -Recurse
  Copy-Item "$root\vision\nclub_vision", "$root\vision\pyproject.toml" "$stage\vision" -Recurse
  Copy-Item "$root\vision\models\*.onnx" "$stage\vision\models"
  Copy-Item "$PSScriptRoot\robot\*.sh", "$PSScriptRoot\robot\*.py" $stage
  Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
  $k1Env = @(
    "NCLUB_ROBOT_KEY=$clave",
    "NCLUB_API_URL=http://${PcIp}:$Puerto",
    "NCLUB_ROBOT_ID=$RobotId",
    "NCLUB_ROBOT_NAME='Booster K1'",
    "NCLUB_GESTOS=$(if ($Gestos) { '1' } else { '0' })",
    "NCLUB_ASR=$(if ($SinVoz) { 'none' } else { 'faster-whisper' })",
    "NCLUB_ASR_MODEL=$AsrModel",
    "NCLUB_PIPER_VOICE=$Voz",
    "NCLUB_TTS=auto"
  ) -join "`n"
  [IO.File]::WriteAllText("$stage\k1.env", "$k1Env`n")  # LF y sin BOM
  $tgz = Join-Path $env:TEMP "nclub_k1_deploy.tgz"
  if (Test-Path $tgz) { Remove-Item $tgz -Force }
  & $tar -czf $tgz -C $stage .
  if ($LASTEXITCODE -ne 0) { throw "No se pudo empaquetar" }
  Write-Host ("OK · {0:N1} MB" -f ((Get-Item $tgz).Length / 1MB))

  Paso "4. Subiendo al K1"
  $ErrorActionPreference = "Continue"; & scp.exe -q @ssh $tgz "${destino}:/tmp/nclub_k1_deploy.tgz" 2>&1 | Out-Null; $ErrorActionPreference = "Stop"
  if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar el paquete" }
  Remoto "mkdir -p ~/nclub && tar -xzf /tmp/nclub_k1_deploy.tgz -C ~/nclub && cd ~/nclub && sed -i 's/\r$//' *.sh k1.env && chmod 600 k1.env && chmod +x *.sh && rm /tmp/nclub_k1_deploy.tgz"
  Write-Host "OK · ~/nclub"

  Paso "5. Dependencias en el K1 (la primera vez tarda varios minutos)"
  $instalado = (EnK1 "test -f ~/nclub/.instalado_k1 && echo si") -eq "si"
  if ($Reinstalar -or -not $instalado) {
    # Corre en segundo plano en el robot: si se corta el SSH, la instalación sigue.
    Remoto "cd ~/nclub && rm -f logs/install.done && mkdir -p logs && (set -a; . ./k1.env; set +a; setsid nohup bash -c 'bash install_k1.sh > logs/install.log 2>&1; echo `$? > logs/install.done' < /dev/null > /dev/null 2>&1 &)"
    $fin = (Get-Date).AddMinutes(30)
    do {
      Start-Sleep -Seconds 15
      $estado = EnK1 "cat ~/nclub/logs/install.done 2>/dev/null; tail -1 ~/nclub/logs/install.log 2>/dev/null"
      Write-Host "  $(($estado | Select-Object -Last 1))"
    } until (($estado | Select-Object -First 1) -match '^\d+$' -or (Get-Date) -gt $fin)
    if (($estado | Select-Object -First 1) -ne "0") {
      EnK1 "tail -20 ~/nclub/logs/install.log"
      throw "La instalación en el K1 falló (log arriba)."
    }
    Remoto "touch ~/nclub/.instalado_k1"
  } else {
    Write-Host "Ya instalado (use -Reinstalar para repetir)"
  }
}

Paso "6. Iniciando el agente en el K1"
Remoto "bash ~/nclub/start_k1.sh"

Paso "Listo"
Write-Host "Abra la app web: Admin -> Robots. El K1 aparece como 'Booster K1' ($RobotId)."
Write-Host "Estado:   ssh $destino 'bash ~/nclub/status_k1.sh'"
Write-Host "Detener:  .\booster_k1\desplegar_k1.ps1 -Detener"
