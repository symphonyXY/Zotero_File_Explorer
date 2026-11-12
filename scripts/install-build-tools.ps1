$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$toolDirectory = Join-Path $projectRoot 'build\tools'
New-Item -ItemType Directory -Force -Path $toolDirectory | Out-Null
$downloadPath = Join-Path $toolDirectory 'innosetup-6.7.4.exe'
if (-not (Test-Path -LiteralPath $downloadPath) -or (Get-Item -LiteralPath $downloadPath).Length -eq 0) {
    Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe' -OutFile $downloadPath -TimeoutSec 120
}
$signature = Get-AuthenticodeSignature -LiteralPath $downloadPath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Pyrsys B.V.*') {
    throw 'Inno Setup signature verification failed.'
}
$installDirectory = Join-Path $toolDirectory 'inno'
$arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="' + $installDirectory + '"'))
$process = Start-Process -FilePath $downloadPath -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
if (-not (Test-Path -LiteralPath (Join-Path $installDirectory 'ISCC.exe'))) { throw 'Inno Setup installation failed.' }
