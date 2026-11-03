# Lance tous les tests avec le Python indique (defaut : celui du PATH).
#   .\outils\lancer_tests.ps1
#   .\outils\lancer_tests.ps1 -Python C:\Python314\python.exe
param([string]$Python = "python")

Set-Location (Split-Path -Parent $PSScriptRoot)
& $Python --version
# -W error::DeprecationWarning : toute fonction obsolete utilisee fait echouer les tests
& $Python -X utf8 -W error::DeprecationWarning -m unittest discover -s tests -t . -v
exit $LASTEXITCODE
