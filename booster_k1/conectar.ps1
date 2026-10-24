<#
  Prueba la conexión con el Booster K1 por Ethernet y muestra qué tiene instalado.

  Uso (PowerShell normal, desde la carpeta del proyecto):
    .\booster_k1\conectar.ps1                  # ping, SSH y diagnóstico
    .\booster_k1\conectar.ps1 -InstalarLlave   # 1.ª vez: pide la contraseña del robot una sola vez
    .\booster_k1\conectar.ps1 -Buscar          # si el K1 no está en 192.168.10.102, lo busca en la red
#>
param(
  [string]$Robot = "192.168.10.102",
  [string]$Usuario = "booster",
  [string]$Adaptador = "Ethernet",
  [switch]$InstalarLlave,
  [switch]$Buscar
)
$ErrorActionPreference = "Stop"
$ssh = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new")
function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }

Paso "1. IP del PC en la red del K1"
$ips = (Get-NetIPAddress -InterfaceAlias $Adaptador -AddressFamily IPv4).IPAddress
Write-Host ("{0}: {1}" -f $Adaptador, ($ips -join ", "))
$red = ($Robot -split '\.')[0..2] -join '.'
if (-not ($ips | Where-Object { $_ -like "$red.*" })) {
  throw "El PC no tiene IP en $red.x. Ejecute como administrador: .\booster_k1\configurar_red.ps1"
}

if ($Buscar) {
  Paso "Buscando equipos en $red.0/24 (unos segundos)"
  $vivos = 1..254 | Where-Object { "$red.$_" -notin $ips } | ForEach-Object {
    $ip = "$red.$_"
    if ((ping -n 1 -w 150 $ip) -match "TTL=") { $ip }
  }
  if (-not $vivos) { throw "Nadie respondió en $red.x. Revise el cable y que el K1 esté encendido." }
  Write-Host "Responden: $($vivos -join ', ')"
  if ($vivos -notcontains $Robot) { $Robot = $vivos[0]; Write-Host "Uso $Robot" }
}

Paso "2. Ping a $Robot"
if (-not ((ping -n 2 -w 1000 $Robot) -match "TTL=")) {
  throw "El K1 no responde en $Robot. Pruebe con -Buscar, o revise el cable y el encendido."
}
Write-Host "OK"

$destino = "$Usuario@$Robot"
if ($InstalarLlave) {
  Paso "3. Instalando su llave SSH en el K1 (escriba la contraseña del robot cuando la pida)"
  $llave = Join-Path $env:USERPROFILE ".ssh\id_ed25519.pub"
  if (-not (Test-Path $llave)) { ssh-keygen -t ed25519 -N '""' -f (Join-Path $env:USERPROFILE ".ssh\id_ed25519") }
  Get-Content $llave | ssh -o StrictHostKeyChecking=accept-new $destino "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
}

Paso "3. SSH sin contraseña ($destino)"
& ssh @ssh $destino "echo conectado" | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "No entra sin contraseña. Ejecute una vez: .\booster_k1\conectar.ps1 -InstalarLlave"
}
Write-Host "OK"

Paso "4. Qué hay en el robot"
& ssh @ssh $destino @'
echo "equipo:   $(hostname) · $(uname -m) · $(. /etc/os-release 2>/dev/null; echo $PRETTY_NAME)"
echo "firmware: $(cat /opt/booster/version.txt 2>/dev/null || echo 'sin /opt/booster/version.txt')"
echo "python:   $(python3 --version 2>&1)"
echo "boosteros: $(python3 -m pip show boosteros 2>/dev/null | grep -i '^version' || echo 'no instalado')"
echo "audio:"; aplay -l 2>/dev/null | grep -i '^card' || echo "  (aplay no disponible)"
'@
Write-Host "`nListo. Para que hable: .\booster_k1\hablar.ps1 -Texto 'Hola, soy el robot K1 de N Club'"
