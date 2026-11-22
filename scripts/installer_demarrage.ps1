#Requires -Version 5.1
<#
.SYNOPSIS
    Installe (ou retire) le lancement automatique de Jarvis-Muse au login Windows.
.DESCRIPTION
    Étape 1 de l'auto-start (bloc 25, validé le 21 nov. 2026) : un raccourci
    dans le dossier Démarrage de Windows, créé par ce script — pas de
    Planificateur de tâches pour l'instant (étape 2, après une semaine de
    test, voir docs/etape-6-hud-session.md).

    Le raccourci lance scripts\lancer_session.ps1 dans une fenêtre PowerShell
    visible : la session démarre au login (minuteurs, résumés, HUD, boucle
    vocale, « Jarvis prêt »). Ctrl+C dans cette fenêtre quitte la session ;
    le surveillant de minuteurs et le HUD continuent de tourner.

    Pendant la semaine de test, noter ce qui gêne (fenêtre au premier plan
    au login, voix au démarrage…) : c'est ce qui décidera du passage au
    Planificateur (lancement en arrière-plan, avec délai).
.PARAMETER Desinstaller
    Retire le raccourci du dossier Démarrage (la session ne démarre plus
    au login). Ne supprime rien d'autre.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\installer_demarrage.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\installer_demarrage.ps1 -Desinstaller
#>
param(
    [switch]$Desinstaller
)

$Racine = Split-Path -Parent $PSScriptRoot
$Nom = "Jarvis-Muse"
$DossierDemarrage = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$CheminRaccourci = Join-Path $DossierDemarrage "$Nom.lnk"

if ($Desinstaller) {
    if (Test-Path $CheminRaccourci) {
        Remove-Item $CheminRaccourci -Force
        Write-Host "Raccourci retiré : Jarvis-Muse ne démarrera plus au login."
    } else {
        Write-Host "Aucun raccourci « $Nom » dans le dossier Démarrage — rien à retirer."
    }
    Write-Host "Dossier Démarrage : $DossierDemarrage"
    exit 0
}

$ScriptSession = Join-Path $Racine "scripts\lancer_session.ps1"
if (-not (Test-Path $ScriptSession)) {
    Write-Host "Erreur : $ScriptSession introuvable — lancez ce script depuis le dépôt Jarvis-Muse." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $DossierDemarrage)) {
    New-Item -ItemType Directory -Force -Path $DossierDemarrage | Out-Null
}

try {
    $shell = New-Object -ComObject WScript.Shell
    $raccourci = $shell.CreateShortcut($CheminRaccourci)
    $raccourci.TargetPath = "powershell.exe"
    $raccourci.Arguments = '-ExecutionPolicy Bypass -File "' + $ScriptSession + '"'
    $raccourci.WorkingDirectory = $Racine
    $raccourci.Description = "Jarvis-Muse — lancement de session au login (étape 6, bloc 25)"
    $raccourci.WindowStyle = 1  # fenêtre normale (visible) : la session se voit et se ferme avec Ctrl+C
    $raccourci.Save()
} catch {
    Write-Host "Erreur : impossible de créer le raccourci ($_) — créez-le à la main (voir docs/etape-6-hud-session.md)." -ForegroundColor Red
    exit 1
}

Write-Host "Raccourci installé : $CheminRaccourci"
Write-Host "  Cible : powershell.exe -ExecutionPolicy Bypass -File `"$ScriptSession`""
Write-Host ""
Write-Host "Test : déconnectez puis reconnectez votre session Windows (ou redémarrez)."
Write-Host "La session Jarvis démarre toute seule (minuteurs, résumés, HUD, boucle vocale)."
Write-Host ""
Write-Host "Semaine de test : si la fenêtre au login vous gêne, notez-le — c'est ce qui"
Write-Host "décidera du passage au Planificateur de tâches (étape 2, après la semaine de test)."
Write-Host ""
Write-Host "Pour retirer : powershell -ExecutionPolicy Bypass -File scripts\installer_demarrage.ps1 -Desinstaller"
