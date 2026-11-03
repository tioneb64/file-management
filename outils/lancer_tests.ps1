# Lance tous les tests avec le Python indique (defaut : celui du PATH) et ecrit un rapport
# dans rapports\tests_<machine>_<date>.txt, a renvoyer au developpement.
#   .\outils\lancer_tests.ps1
#   .\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
param([string]$Python = "python")

$racine = Split-Path -Parent $PSScriptRoot
Set-Location $racine
New-Item -ItemType Directory -Force (Join-Path $racine "rapports") | Out-Null
$rapport = Join-Path $racine ("rapports\tests_{0}_{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format "yyyyMMdd_HHmmss"))

$entete = "Machine : $env:COMPUTERNAME | Compte : $env:USERDOMAIN\$env:USERNAME | " +
          "Systeme : $([Environment]::OSVersion.VersionString) | PowerShell $($PSVersionTable.PSVersion)"
$entete | Tee-Object -FilePath $rapport
& $Python --version 2>&1 | Tee-Object -FilePath $rapport -Append
# -W error::DeprecationWarning : toute fonction obsolete utilisee fait echouer les tests
& $Python -X utf8 -W error::DeprecationWarning -m unittest discover -s tests -t . -v 2>&1 |
    Tee-Object -FilePath $rapport -Append
$code = $LASTEXITCODE
"Code retour : $code" | Tee-Object -FilePath $rapport -Append
"Rapport : $rapport"
exit $code
