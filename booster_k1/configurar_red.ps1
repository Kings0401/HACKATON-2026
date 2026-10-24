<#
  Agrega al adaptador Ethernet la IP de la red del Booster K1 (192.168.10.x)
  SIN quitar la 10.0.1.2 que usa el AGIBOT X2. No pone puerta de enlace, así
  internet sigue saliendo por el Wi-Fi.

  Uso: abrir PowerShell COMO ADMINISTRADOR, ir a la carpeta del proyecto y
    .\booster_k1\configurar_red.ps1
    .\booster_k1\configurar_red.ps1 -Quitar      # deshace el cambio (deja solo la del X2)
#>
param(
  [string]$Adaptador = "Ethernet",
  [string]$PcIp = "192.168.10.10",
  [switch]$Quitar
)
$ErrorActionPreference = "Stop"
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Abra PowerShell como administrador (clic derecho > Ejecutar como administrador)." }

$actual = Get-NetIPAddress -InterfaceAlias $Adaptador -IPAddress $PcIp -ErrorAction SilentlyContinue
if ($Quitar) {
  if ($actual) { Remove-NetIPAddress -InterfaceAlias $Adaptador -IPAddress $PcIp -Confirm:$false }
  Write-Host "Quitada $PcIp de $Adaptador."
} elseif ($actual) {
  Write-Host "$Adaptador ya tiene $PcIp."
} else {
  New-NetIPAddress -InterfaceAlias $Adaptador -IPAddress $PcIp -PrefixLength 24 | Out-Null
  Write-Host "Agregada $PcIp/24 a $Adaptador."
}
Get-NetIPAddress -InterfaceAlias $Adaptador -AddressFamily IPv4 | Format-Table IPAddress, PrefixLength -AutoSize
