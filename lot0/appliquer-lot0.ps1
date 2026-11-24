# appliquer-lot0.ps1 : applique le Lot 0 (6 patchs) dans l'ordre, un commit par
# patch, sur une branche dédiée « lot0 ». Rien n'est poussé nulle part.
#
# Avant : arrêtez la boucle vocale Jarvis ET « minuteur.py surveiller »
# (un processus déjà lancé garde l'ancien code). Dépôt sans modification
# non validée.
#
# Usage, depuis la RACINE du dépôt (là où se trouvent scripts\ et config\) :
#     powershell -ExecutionPolicy Bypass -File C:\chemin\vers\appliquer-lot0.ps1
#
# Retour en arrière complet :  git switch main ; git branch -D lot0
# (adaptez « main » au nom de votre branche d'origine.)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    & git.exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($args -join ' ') a échoué (code $LASTEXITCODE)"
    }
}

$patchs = @(
    "lot0-1-brain-upgrade",
    "lot0-2-english-parity",
    "lot0-3-no-page-title",
    "lot0-4-securite-historique",
    "lot0-5-minuteur-langue",
    "lot0-6-tests-et-mesure"
)
$dossier = $PSScriptRoot

if (-not (Test-Path "scripts\boucle_voix.py")) {
    throw "Lancez ce script depuis la racine du dépôt (scripts\boucle_voix.py introuvable)."
}
if (& git.exe status --porcelain) {
    throw "Le dépôt a des modifications non validées : validez-les ou mettez-les de côté (git stash) d'abord."
}
foreach ($nom in $patchs) {
    if (-not (Test-Path (Join-Path $dossier "$nom.patch"))) {
        throw "Patch introuvable : $(Join-Path $dossier "$nom.patch")"
    }
}

Invoke-Git switch -c lot0

$n = 0
foreach ($nom in $patchs) {
    $n++
    $fichier = Join-Path $dossier "$nom.patch"
    & git.exe apply --check $fichier 2>$null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Git apply $fichier
    }
    else {
        # Fichiers en fins de ligne Windows (CRLF) : on ignore les espaces de fin de ligne.
        Write-Host "  (fins de ligne Windows : application avec --ignore-whitespace)"
        Invoke-Git apply --check --ignore-whitespace $fichier
        Invoke-Git apply --ignore-whitespace $fichier
    }
    Invoke-Git add -A
    Invoke-Git commit -q -m "Lot 0 ($n/$($patchs.Count)) : $nom"
    Write-Host "OK  $nom"
}

Write-Host ""
Write-Host "Tests (sans réseau, sans micro, sans voix) :"
& python scripts\test_parite_langue.py
if ($LASTEXITCODE -ne 0) {
    throw "Les tests échouent : ne gardez pas la branche lot0 telle quelle (retour en arrière ci-dessus)."
}
Write-Host ""
Write-Host "Lot 0 appliqué sur la branche lot0 ; tests OK. Relancez la boucle et « minuteur.py surveiller »."
