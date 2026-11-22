#Requires -Version 5.1
<#
.SYNOPSIS
    Installe (ou retire) le raccourci « Jarvis » du menu Démarrer Windows.
.DESCRIPTION
    Étape 7.1 (décision 21 nov. 2026) : un raccourci « Jarvis » dans le
    menu Démarrer (épinglable à la barre des tâches par clic droit →
    « Épingler à la barre des tâches » — Windows ne laisse pas un
    programme s'épingler tout seul, comme dans le dépôt B).

    Le raccourci lance scripts\lancer_app.py avec pythonw (sans fenêtre
    console) : l'application s'ouvre, la boucle vocale et le surveillant
    de minuteurs tournent en arrière-plan. Fermer la fenêtre de
    l'application arrête toute la session (boucle + surveillant) —
    c'est le comportement voulu, comme dans le dépôt B où fermer le HUD
    quitte Jarvis. Si un processus reste coincé malgré tout : Gestionnaire
    des tâches → terminer les processus pythonw.exe du dossier Jarvis-Muse.

    Différence avec scripts\installer_demarrage.ps1 (étape 6) : celui-ci
    lançait la session complète au login, dans une fenêtre PowerShell
    visible (HUD + boucle au premier plan). Celui-ci ne lance rien au
    login : c'est un raccourci à cliquer quand Julien veut Jarvis.
.PARAMETER Desinstaller
    Retire le raccourci du menu Démarrer. Ne supprime rien d'autre.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\installer_raccourci.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\installer_raccourci.ps1 -Desinstaller
#>
param(
    [switch]$Desinstaller
)

$Racine = Split-Path -Parent $PSScriptRoot
$Nom = "Jarvis"
$DossierDemarrer = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$CheminRaccourci = Join-Path $DossierDemarrer "$Nom.lnk"

if ($Desinstaller) {
    if (Test-Path $CheminRaccourci) {
        Remove-Item $CheminRaccourci -Force
        Write-Host "Raccourci retiré : « $Nom » n'est plus dans le menu Démarrer."
    } else {
        Write-Host "Aucun raccourci « $Nom » dans le menu Démarrer — rien à retirer."
    }
    Write-Host "Dossier du menu Démarrer : $DossierDemarrer"
    exit 0
}

$ScriptLanceur = Join-Path $Racine "scripts\lancer_app.py"
if (-not (Test-Path $ScriptLanceur)) {
    Write-Host "Erreur : $ScriptLanceur introuvable — lancez ce script depuis le dépôt Jarvis-Muse." -ForegroundColor Red
    exit 1
}
$PythonwVenv = Join-Path $Racine ".venv\Scripts\pythonw.exe"
if (Test-Path $PythonwVenv) {
    $Pythonw = (Resolve-Path $PythonwVenv).Path
} else {
    $Pythonw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
}
if (-not $Pythonw) {
    Write-Host "Erreur : pythonw.exe introuvable (ni dans .venv, ni dans le PATH)." -ForegroundColor Red
    Write-Host "Vérifiez l'installation Python (venv du dépôt), puis relancez ce script."
    exit 1
}
if (-not (Test-Path $DossierDemarrer)) {
    New-Item -ItemType Directory -Force -Path $DossierDemarrer | Out-Null
}

try {
    $shell = New-Object -ComObject WScript.Shell
    $raccourci = $shell.CreateShortcut($CheminRaccourci)
    $raccourci.TargetPath = $Pythonw
    $raccourci.Arguments = "`"$ScriptLanceur`""
    $raccourci.WorkingDirectory = $Racine
    $raccourci.Description = "Jarvis-Muse — application + boucle vocale (étape 7.1)"
    $raccourci.IconLocation = $Pythonw
    $raccourci.WindowStyle = 1  # pythonw n'ouvre pas de console de toute façon
    $raccourci.Save()
} catch {
    Write-Host "Erreur : impossible de créer le raccourci ($_) — créez-le à la main (voir docs/etape-7.1-historique-chat-raccourci.md)." -ForegroundColor Red
    exit 1
}

Write-Host "Raccourci installé : $CheminRaccourci"
Write-Host "  Cible : $Pythonw `"$ScriptLanceur`""
Write-Host ""
Write-Host "Pour l'épingler à la barre des tâches : touche Windows, tapez « Jarvis »,"
Write-Host "clic droit sur « Jarvis » → « Épingler à la barre des tâches »."
Write-Host ""
Write-Host "Un clic lance l'application (sans fenêtre console) ; fermer la fenêtre"
Write-Host "arrête toute la session (boucle vocale + surveillant de minuteurs)."
Write-Host "Si un processus reste coincé : Gestionnaire des tâches → terminer"
Write-Host "les processus pythonw.exe du dossier Jarvis-Muse."
Write-Host ""
Write-Host "Pour retirer : powershell -ExecutionPolicy Bypass -File scripts\installer_raccourci.ps1 -Desinstaller"
