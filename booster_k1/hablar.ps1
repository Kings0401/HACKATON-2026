<#
  Hace hablar al Booster K1: sube booster_k1\robot\hablar_k1.py y lo ejecuta en el robot.

  Uso (PowerShell, desde la carpeta del proyecto, después de .\booster_k1\conectar.ps1):
    .\booster_k1\hablar.ps1 -Texto "Hola, soy el robot K1 de N Club"
    .\booster_k1\hablar.ps1 -Voces                         # voces disponibles en el K1
    .\booster_k1\hablar.ps1 -Texto "Hola" -Voz <id> -Volumen 0.8
    .\booster_k1\hablar.ps1 -Texto "Hola" -Motor sistema   # voz del sistema (espeak), para probar el parlante
    .\booster_k1\hablar.ps1 -Wav .\saludo.wav              # reproduce un WAV PCM de 16 bits
    .\booster_k1\hablar.ps1 -Diagnostico
#>
param(
  [string]$Texto,
  [string]$Voz = "default",
  [double]$Velocidad = 1.0,
  [double]$Volumen = -1,
  [ValidateSet("auto", "boosteros", "sistema")][string]$Motor = "auto",
  [string]$Wav,
  [switch]$Voces,
  [switch]$Diagnostico,
  [string]$Robot = "192.168.10.102",
  [string]$Usuario = "booster"
)
$ErrorActionPreference = "Stop"
$destino = "$Usuario@$Robot"
$ssh = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8")
$script = Join-Path $PSScriptRoot "robot\hablar_k1.py"

& ssh @ssh $destino "mkdir -p ~/nclub_k1"
if ($LASTEXITCODE -ne 0) { throw "Sin SSH al K1. Ejecute primero: .\booster_k1\conectar.ps1" }
& scp -q @ssh $script "${destino}:nclub_k1/hablar_k1.py"
if ($LASTEXITCODE -ne 0) { throw "No se pudo subir hablar_k1.py" }

$args_ = @()
if ($Diagnostico) { $args_ += "--diagnostico" }
elseif ($Voces) { $args_ += "--voces" }
elseif ($Wav) {
  & scp -q @ssh $Wav "${destino}:nclub_k1/audio.wav"
  if ($LASTEXITCODE -ne 0) { throw "No se pudo subir $Wav" }
  $args_ += "--wav", "nclub_k1/audio.wav"
} elseif ($Texto) {
  # El texto viaja en base64 para que tildes, ñ y comillas lleguen intactas.
  $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Texto))
  $args_ += "--texto-b64", $b64, "--voz", $Voz, "--velocidad", $Velocidad.ToString([Globalization.CultureInfo]::InvariantCulture), "--motor", $Motor
} else {
  throw "Indique -Texto, -Wav, -Voces o -Diagnostico"
}
if ($Volumen -ge 0) { $args_ += "--volumen", $Volumen.ToString([Globalization.CultureInfo]::InvariantCulture) }

& ssh @ssh $destino "python3 nclub_k1/hablar_k1.py $($args_ -join ' ')"
if ($LASTEXITCODE -ne 0) { throw "El K1 no pudo hablar (vea el mensaje de arriba)." }
