// Reunion.app : l'icone du Dock de transcription-locale.
//
// Compilee sur chaque Mac par `transcription-locale raccourci` (swiftc des outils de
// developpement d'Apple), jamais livree toute faite. Deux roles, et rien d'autre :
//
//   - un clic sur l'icone (lancement sans fichier, ou nouveau clic pendant qu'elle tourne)
//     lance `transcription-locale reunion`, qui demarre ou arrete l'enregistrement ;
//   - l'ouverture d'un fichier .notification (par `open -g -a Reunion.app fichier`) affiche
//     son texte en notification, avec l'icone de l'application, puis efface le fichier.
//
// L'application se ferme des qu'elle n'a plus rien a faire. Elle ne lit aucun autre fichier,
// n'ouvre aucune connexion et ne garde rien.
//
// macOS rattache l'autorisation d'enregistrer l'ecran a cette application : l'enregistreur
// qu'elle lance en herite. C'est pourquoi `raccourci` ne la reconstruit jamais une fois en place.

import AppKit
import UserNotifications

let titre = "Réunion"
let extensionMessage = "notification"
let tailleMaxMessage = 4096

final class Lanceur: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    private var lanceeAvecFichiers = false
    private var basculeEnCours = false
    private var taches = 0

    // --- cycle de vie ------------------------------------------------------------------------

    func application(_ application: NSApplication, open urls: [URL]) {
        lanceeAvecFichiers = true
        notifier(urls)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
        if !lanceeAvecFichiers { basculer() }
        terminerSiInactive()
    }

    // nouveau clic sur l'icone du Dock pendant que l'application tourne encore
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        basculer()
        return false
    }

    private func commencer() { taches += 1 }

    private func finir() {
        taches -= 1
        terminerSiInactive()
    }

    private func terminerSiInactive() {
        // petit delai : laisse arriver un fichier ou un clic qui suivrait de pres
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            if self.taches == 0 { NSApp.terminate(nil) }
        }
    }

    // --- clic sur l'icone ----------------------------------------------------------------------

    private func basculer() {
        if basculeEnCours { return }  // un double clic : le premier suffit
        basculeEnCours = true
        commencer()
        let python = Bundle.main.object(forInfoDictionaryKey: "RN20Python") as? String ?? ""
        DispatchQueue.global().async {
            let (code, erreur) = self.lancerReunion(python: python)
            DispatchQueue.main.async {
                self.basculeEnCours = false
                if code != 0 { self.alerte(erreur) }
                self.finir()
            }
        }
    }

    /// La commande du PATH passe en premier : l'application n'est jamais refaite, elle ne doit
    /// pas dependre d'un interpreteur fige. Le Python de l'installation ne sert que de secours.
    private func lancerReunion(python: String) -> (Int32, String) {
        let script = """
            export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
            if command -v transcription-locale >/dev/null 2>&1; then
                exec transcription-locale reunion
            fi
            exec "$1" -m transcription_locale reunion
            """
        let processus = Process()
        processus.executableURL = URL(fileURLWithPath: "/bin/sh")
        processus.arguments = ["-c", script, "sh", python]  // le chemin passe en argument, jamais dans le script
        let sortieErreur = Pipe()
        processus.standardError = sortieErreur
        processus.standardOutput = FileHandle.nullDevice
        do {
            try processus.run()
        } catch {
            return (1, "Lancement impossible : \(error.localizedDescription)")
        }
        let donnees = sortieErreur.fileHandleForReading.readDataToEndOfFile()
        processus.waitUntilExit()
        let texte = String(data: donnees, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return (processus.terminationStatus, texte.isEmpty ? "La commande a échoué." : texte)
    }

    private func alerte(_ texte: String) {
        NSApp.activate(ignoringOtherApps: true)
        let fenetre = NSAlert()
        fenetre.alertStyle = .critical
        fenetre.messageText = titre
        fenetre.informativeText = texte
        fenetre.runModal()
    }

    // --- notifications ---------------------------------------------------------------------------

    private func lireMessage(_ url: URL) -> String? {
        defer { try? FileManager.default.removeItem(at: url) }
        guard url.pathExtension == extensionMessage,
              let donnees = try? Data(contentsOf: url), donnees.count <= tailleMaxMessage,
              let texte = String(data: donnees, encoding: .utf8) else { return nil }
        let propre = texte.trimmingCharacters(in: .whitespacesAndNewlines)
        return propre.isEmpty ? nil : propre
    }

    private func notifier(_ urls: [URL]) {
        let messages = urls.compactMap(lireMessage)
        if messages.isEmpty { return }
        commencer()
        let centre = UNUserNotificationCenter.current()
        centre.requestAuthorization(options: [.alert, .sound]) { accordee, _ in
            let groupe = DispatchGroup()
            for message in messages {
                groupe.enter()
                if accordee {
                    let contenu = UNMutableNotificationContent()
                    contenu.title = titre
                    contenu.body = message
                    let demande = UNNotificationRequest(identifier: UUID().uuidString,
                                                        content: contenu, trigger: nil)
                    centre.add(demande) { erreur in
                        if erreur != nil { self.notifierParScript(message) }
                        groupe.leave()
                    }
                } else {
                    // notifications refusees pour Reunion : celles du systeme, icone de script
                    self.notifierParScript(message)
                    groupe.leave()
                }
            }
            groupe.notify(queue: .main) { self.finir() }
        }
    }

    private func notifierParScript(_ message: String) {
        let processus = Process()
        processus.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        processus.arguments = ["-e", "on run argv",
                               "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                               "-e", "end run", message, titre]
        try? processus.run()
        processus.waitUntilExit()
    }

    // la notification s'affiche aussi quand l'application est au premier plan
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
}

let application = NSApplication.shared
let lanceur = Lanceur()
application.delegate = lanceur
application.setActivationPolicy(.accessory)
application.run()
