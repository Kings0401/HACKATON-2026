<#
  El Booster K1 saluda con la mano (y opcionalmente dice algo).

  El firmware solo acepta gestos en modo WALK. Si el robot está de pie en PREP,
  -EntrarWalk lo pasa a WALK, saluda y lo devuelve a PREP. Antes de usarlo:
  espacio libre alrededor y alguien con el control remoto (LT + BACK = DAMP).

    .\booster_k1\saludar.ps1 -EntrarWalk
    .\booster_k1\saludar.ps1 -EntrarWalk -Texto "Hola, bienvenidos a N Club" -Segundos 5
#>
param(
  [string]$Texto,
  [double]$Segundos = 4,
  [switch]$EntrarWalk,
  [string]$Robot = "192.168.10.102",
  [string]$Usuario = "booster"
)
$ErrorActionPreference = "Stop"
$destino = "$Usuario@$Robot"
$ssh = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8")

& ssh @ssh $destino "mkdir -p ~/nclub_k1"
if ($LASTEXITCODE -ne 0) { throw "Sin SSH al K1. Ejecute primero: .\booster_k1\conectar.ps1" }
& scp -q @ssh (Join-Path $PSScriptRoot "robot\saludar_k1.py") "${destino}:nclub_k1/saludar_k1.py"

$args_ = @("--segundos", $Segundos.ToString([Globalization.CultureInfo]::InvariantCulture))
if ($EntrarWalk) { $args_ += "--entrar-walk" }
if ($Texto) { $args_ += "--texto-b64", [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Texto)) }
& ssh @ssh $destino "python3 nclub_k1/saludar_k1.py $($args_ -join ' ') 2>&1 | grep -v InitChannel"
