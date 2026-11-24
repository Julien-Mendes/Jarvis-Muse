#Requires -Version 5.1
<#
.SYNOPSIS
    Lancement de session Jarvis-Muse (étape 6) : minuteurs, résumés Carson,
    HUD léger, boucle vocale — puis « Jarvis prêt ».
.DESCRIPTION
    Orchestre les scripts existants, sans logique dupliquée :
      1. Vérifie l'environnement (Python, venv, .env) — avertit sans planter.
      2. Démarre le surveillant de minuteurs dans une fenêtre à part
         (c'est lui qui annonce les minuteurs manqués au démarrage).
      3. Annonce les minuteurs et rappels du jour, en une phrase, à voix haute.
      4. Lit les résumés Carson du dossier a-dire/ (fichiers .txt), s'il y en a.
      5. Lance le HUD léger en arrière-plan.
      6. Range les fenêtres en quadrants si [quadrants] est configuré
         (config.local.toml — vide par défaut, à compléter avec Julien).
      7. Lance la boucle vocale au premier plan (F9 pour parler).
    La boucle tourne au premier plan : Ctrl+C pour quitter la session.
    Le surveillant et le HUD continuent de tourner dans leurs fenêtres —
    fermez-les pour tout arrêter.
    Pas de météo ni de briefing reconstruit (doublons Carson, bloc 6).
    Pas d'auto-start (bloc 25, décision ouverte) : ce script se lance
    à la main (double-clic, ou clic droit « Exécuter avec PowerShell »).
    Auto-start (bloc 25, validé le 21 nov.) : étape 1 = raccourci manuel
    dans le dossier Démarrage, créé par scripts\installer_demarrage.ps1
    (une semaine de test) ; étape 2 = Planificateur de tâches, documentée
    dans docs/etape-6-hud-session.md, à configurer après la semaine de test.
.PARAMETER SansHud
    Ne pas démarrer le HUD (utile pour tester).
.PARAMETER SansBoucle
    Ne pas démarrer la boucle vocale à la fin (utile pour tester) :
    la session s'arrête après « Jarvis prêt ».
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\lancer_session.ps1
#>
param(
    [switch]$SansHud,
    [switch]$SansBoucle
)

$ErrorActionPreference = "Continue"
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine

function Write-Etape {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message ==" -ForegroundColor Cyan
}

function Invoke-Voix {
    <#
    .SYNOPSIS
        Lit un texte (ou un fichier) à voix haute via lire_voix.py.
        Si la voix est indisponible, affiche le texte au lieu de planter.
    #>
    param([string]$Texte, [string]$Fichier)
    try {
        if ($Fichier) {
            & $script:Python scripts\lire_voix.py --fichier $Fichier --langue $script:Langue 2>$null
        } else {
            & $script:Python scripts\lire_voix.py --texte $Texte --langue $script:Langue 2>$null
        }
        if ($LASTEXITCODE -ne 0) { throw "lire_voix.py a échoué (code $LASTEXITCODE)." }
    } catch {
        if ($Fichier) {
            Write-Host "(Voix indisponible — contenu de $Fichier :)"
            Get-Content $Fichier -Raw | Write-Host
        } else {
            Write-Host "(Voix indisponible) $Texte"
        }
    }
}

function Get-ConfigJarvis {
    <#
    .SYNOPSIS
        Lit [session], [quadrants] et la langue avec config_jarvis.py (config
        publique < config.toml < config.local.toml), en JSON.
        Renvoie les valeurs par défaut si la lecture échoue.
    #>
    $defaut = [PSCustomObject]@{
        session   = [PSCustomObject]@{
            lire_a_dire = $true; annoncer_minuteurs_du_jour = $true; demarrer_hud = $true
        }
        quadrants = [PSCustomObject]@{ actif = $false; apps = @() }
        langue    = "en"
    }
    $code = @'
import json, sys
sys.path.insert(0, "scripts")
import config_jarvis
donnees = config_jarvis.charger_donnees()
session = dict(config_jarvis.section(donnees, "session"))
quadrants = config_jarvis.section(donnees, "quadrants")
langue = config_jarvis.langue(donnees)
print(json.dumps({"session": session, "quadrants": quadrants,
                  "langue": langue}))
'@
    try {
        $json = & $script:Python -c $code 2>$null | Out-String
        if (-not $json) { return $defaut }
        $lu = $json | ConvertFrom-Json
        $session = $lu.session
        if ($null -eq $session) { $session = $defaut.session }
        $quadrants = $lu.quadrants
        if ($null -eq $quadrants) { $quadrants = $defaut.quadrants }
        $langue = if ($lu.langue -in @("fr", "en")) { $lu.langue } else { "en" }
        return [PSCustomObject]@{ session = $session; quadrants = $quadrants; langue = $langue }
    } catch {
        return $defaut
    }
}

function Format-Delai {
    param([datetime]$Echeance, [datetime]$Maintenant)
    $reste = $Echeance - $Maintenant
    $en = ($script:Langue -eq "en")
    if ($reste.TotalSeconds -le 0) { return $(if ($en) { "now" } else { "maintenant" }) }
    if ($reste.TotalMinutes -lt 60) {
        $minutes = [int][math]::Round($reste.TotalMinutes)
        if ($minutes -le 1) { return $(if ($en) { "in 1 minute" } else { "dans 1 minute" }) }
        return $(if ($en) { "in $minutes minutes" } else { "dans $minutes minutes" })
    }
    if ($en) { return "at $($Echeance.ToString('HH:mm'))" }
    return "à $($Echeance.ToString('HH \h mm'))"
}

function Invoke-Quadrants {
    param($Quadrants)
    $apps = @($Quadrants.apps)
    if (-not $Quadrants.actif -or $apps.Count -eq 0) {
        Write-Host "Quadrants : non configurés (config.local.toml [quadrants] vide) — rien à ranger."
        return
    }
    Add-Type -AssemblyName System.Windows.Forms
    $zone = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $rects = @{
        "haut-gauche" = @{ X = $zone.Left; Y = $zone.Top; L = [int]($zone.Width / 2); H = [int]($zone.Height / 2) }
        "haut-droite" = @{ X = $zone.Left + [int]($zone.Width / 2); Y = $zone.Top; L = [int]($zone.Width / 2); H = [int]($zone.Height / 2) }
        "bas-gauche"  = @{ X = $zone.Left; Y = $zone.Top + [int]($zone.Height / 2); L = [int]($zone.Width / 2); H = [int]($zone.Height / 2) }
        "bas-droite"  = @{ X = $zone.Left + [int]($zone.Width / 2); Y = $zone.Top + [int]($zone.Height / 2); L = [int]($zone.Width / 2); H = [int]($zone.Height / 2) }
    }
    $codeWin32 = @'
using System;
using System.Runtime.InteropServices;
public static class Win32Jarvis {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
'@
    try {
        Add-Type -TypeDefinition $codeWin32 -ErrorAction Stop
    } catch {
        Write-Host "Quadrants : impossible de charger les fonctions Windows ($_) — étape ignorée."
        return
    }
    foreach ($app in $apps) {
        $quadrant = $app.quadrant
        if (-not $rects.ContainsKey($quadrant)) {
            Write-Host "Quadrants : quadrant inconnu « $quadrant » pour $($app.nom) — ignoré."
            continue
        }
        $processus = Get-Process -Name $app.processus -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        if (-not $processus) {
            $cible = $app.chemin
            if (-not $cible) { $cible = $app.processus }
            try {
                Start-Process $cible -ErrorAction Stop | Out-Null
                Write-Host "Quadrants : lancement de $($app.nom)…"
            } catch {
                Write-Host "Quadrants : impossible de lancer $($app.nom) ($cible) — ignoré."
                continue
            }
            for ($essai = 0; $essai -lt 5 -and -not $processus; $essai++) {
                Start-Sleep -Seconds 2
                $processus = Get-Process -Name $app.processus -ErrorAction SilentlyContinue |
                    Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
            }
        }
        if (-not $processus) {
            Write-Host "Quadrants : aucune fenêtre trouvée pour $($app.nom) — ignoré."
            continue
        }
        $handle = $processus.MainWindowHandle
        if ([Win32Jarvis]::IsIconic($handle)) {
            [Win32Jarvis]::ShowWindow($handle, 9) | Out-Null
        }
        $rect = $rects[$quadrant]
        [Win32Jarvis]::SetWindowPos($handle, [IntPtr]::Zero, $rect.X, $rect.Y, $rect.L, $rect.H, 0x0040) | Out-Null
        Write-Host "Quadrants : $($app.nom) rangé en $quadrant."
    }
}

# ---------------------------------------------------------------------------
# 1. Vérifications
# ---------------------------------------------------------------------------
Write-Etape "Vérification de l'environnement"
$PythonVenv = Join-Path $Racine ".venv\Scripts\python.exe"
if (Test-Path $PythonVenv) {
    $script:Python = (Resolve-Path $PythonVenv).Path
} else {
    $script:Python = "python"
}
try {
    $versionPython = & $script:Python --version 2>&1
    Write-Host "Python : $versionPython"
} catch {
    Write-Host "Erreur : Python est introuvable. Installez Python 3.10+ puis relancez ce script." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $Racine ".venv"))) {
    Write-Host "Avertissement : pas d'environnement virtuel (.venv) — on utilise le Python système."
}
if (-not (Test-Path (Join-Path $Racine ".env")) -and -not (Test-Path (Join-Path $Racine "config\.env"))) {
    Write-Host "Avertissement : pas de fichier .env — la boucle aura besoin d'une clé Groq (voir docs/etape-4-declenchement.md)."
}
New-Item -ItemType Directory -Force -Path (Join-Path $Racine "data") | Out-Null

$config = Get-ConfigJarvis
$script:Langue = $config.langue

# ---------------------------------------------------------------------------
# 2. Surveillant de minuteurs (fenêtre à part — c'est lui qui fait sonner
#    les minuteurs ; sans lui, un minuteur échu n'est annoncé qu'au prochain
#    lancement). Il annonce aussi les minuteurs manqués au démarrage.
# ---------------------------------------------------------------------------
Write-Etape "Surveillant de minuteurs"
try {
    Start-Process -FilePath $script:Python -ArgumentList "scripts\minuteur.py", "surveiller" | Out-Null
    Write-Host "Surveillant démarré dans une autre fenêtre."
} catch {
    Write-Host "Avertissement : impossible de démarrer le surveillant ($_) — les minuteurs ne sonneront pas."
}
# Laisser au surveillant le temps d'annoncer les minuteurs manqués avant
# que la session parle (éviter deux voix en même temps).
Start-Sleep -Seconds 4

# ---------------------------------------------------------------------------
# 3. Minuteurs et rappels du jour, en une phrase
# ---------------------------------------------------------------------------
if ($config.session.annoncer_minuteurs_du_jour -ne $false) {
    Write-Etape "Minuteurs du jour"
    $fichierMinuteurs = Join-Path $Racine "data\timers.json"
    $aujourdhui = @()
    if (Test-Path $fichierMinuteurs) {
        try {
            $etat = Get-Content $fichierMinuteurs -Raw | ConvertFrom-Json
            $maintenant = Get-Date
            $aujourdhui = @($etat.timers) | Where-Object {
                $due = [datetime]$_.due
                $due -ge $maintenant -and $due.Date -eq $maintenant.Date
            } | Sort-Object due
        } catch {
            Write-Host "Avertissement : minuteurs illisibles ($_) — étape ignorée."
        }
    }
    if ($aujourdhui.Count -gt 0) {
        $maintenant = Get-Date
        $morceaux = foreach ($minuteur in $aujourdhui) {
            $genre = if ($script:Langue -eq "fr") {
                if ($minuteur.kind -eq "timer") { "minuteur" } else { "rappel" }
            } else { $minuteur.kind }
            $quoi = if ($minuteur.label) { "$genre « $($minuteur.label) »" } else { $genre }
            "$quoi $(Format-Delai -Echeance ([datetime]$minuteur.due) -Maintenant $maintenant)"
        }
        $debut = if ($script:Langue -eq "fr") { "Aujourd'hui : " } else { "Today: " }
        $phrase = $debut + ($morceaux -join ", ") + "."
        Write-Host $phrase
        Invoke-Voix -Texte $phrase
    } else {
        Write-Host "Aucun minuteur ni rappel aujourd'hui."
    }
}

# ---------------------------------------------------------------------------
# 4. Résumés Carson dans a-dire/ (s'il y en a)
# ---------------------------------------------------------------------------
if ($config.session.lire_a_dire -ne $false) {
    Write-Etape "Résumés Carson (a-dire/)"
    $fichiers = Get-ChildItem (Join-Path $Racine "a-dire") -Filter *.txt -ErrorAction SilentlyContinue |
        Sort-Object Name
    if ($fichiers.Count -eq 0) {
        Write-Host "Aucun résumé à lire."
    } else {
        foreach ($fichier in $fichiers) {
            Write-Host "Lecture de $($fichier.Name)…"
            Invoke-Voix -Fichier $fichier.FullName
        }
    }
}

# ---------------------------------------------------------------------------
# 5. HUD léger (arrière-plan)
# ---------------------------------------------------------------------------
if ((-not $SansHud) -and ($config.session.demarrer_hud -ne $false)) {
    Write-Etape "HUD léger"
    $pythonw = Join-Path $Racine ".venv\Scripts\pythonw.exe"
    try {
        if (Test-Path $pythonw) {
            Start-Process -FilePath (Resolve-Path $pythonw).Path -ArgumentList "scripts\hud.py" -WindowStyle Hidden | Out-Null
        } else {
            Start-Process -FilePath $script:Python -ArgumentList "scripts\hud.py" -WindowStyle Minimized | Out-Null
        }
        Write-Host "HUD démarré en arrière-plan."
    } catch {
        Write-Host "Avertissement : impossible de démarrer le HUD ($_) — la session continue sans lui."
    }
} else {
    Write-Host "HUD : ignoré (option -SansHud ou demarrer_hud = false)."
}

# ---------------------------------------------------------------------------
# 6. Fenêtres en quadrants (si configuré dans config.local.toml)
# ---------------------------------------------------------------------------
Write-Etape "Quadrants"
Invoke-Quadrants -Quadrants $config.quadrants

# ---------------------------------------------------------------------------
# 7. Boucle vocale au premier plan
# ---------------------------------------------------------------------------
Write-Etape "Boucle vocale"
Invoke-Voix -Texte $(if ($script:Langue -eq "fr") { "Jarvis prêt." } else { "Jarvis ready." })
Write-Host "Jarvis prêt. Maintenez F9 pour parler (ou maintenez le clic sur l'anneau du HUD)."
if (-not $SansBoucle) {
    & $script:Python scripts\boucle_voix.py
}
Write-Host ""
Write-Host "Session terminée. Le surveillant de minuteurs et le HUD continuent"
Write-Host "de tourner dans leurs fenêtres — fermez-les pour tout arrêter."
