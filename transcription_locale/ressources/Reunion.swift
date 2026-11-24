// Reunion.app : l'icone du Dock de transcription-locale.
//
// Compilee sur chaque Mac par `transcription-locale raccourci` (xcrun swiftc, outils de
// developpement d'Apple), jamais livree toute faite. Deux roles, et rien d'autre :
//
//   - un clic sur l'icone (lancement simple, ou nouveau clic pendant qu'elle tourne)
//     lance `transcription-locale reunion`, qui demarre ou arrete l'enregistrement ;
//   - un fichier .notification de son dossier de messages, ouvert par
//     `open -g -a Reunion.app fichier`, s'affiche en notification avec l'icone de
//     l'application, puis est efface.
//
// L'application se ferme des qu'elle n'a plus rien a faire. Elle ne lit que son dossier de
// messages, n'ouvre aucune connexion et ne garde rien.
//
// macOS rattache l'autorisation d'enregistrer l'ecran a cette application : l'enregistreur
// qu'elle lance en herite. C'est pourquoi `raccourci` ne la reconstruit jamais une fois en place.

import AppKit
import UserNotifications

let titre = "Réunion"
let extensionMessage = "notification"
let tailleMaxMessage = 4096  // octets ; Python coupe les messages bien avant
let delaiScript: TimeInterval = 10  // repli osascript
let delaiBascule: TimeInterval = 60  // transcription-locale reunion attend au plus ~20 s
// meme dossier que reunion.dossier_messages() cote Python
let dossierMessages = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/transcription-locale/notifications",
                            isDirectory: true)
    .standardizedFileURL

/// Lance un processus et le termine s'il depasse le delai : l'application ne doit jamais rester
/// bloquee en arriere-plan, invisible, a avaler les clics suivants.
func executer(_ processus: Process, delai: TimeInterval) throws {
    try processus.run()
    let garde = DispatchWorkItem { if processus.isRunning { processus.terminate() } }
    DispatchQueue.global().asyncAfter(deadline: .now() + delai, execute: garde)
    processus.waitUntilExit()
    garde.cancel()
}

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
        // Lancement simple (clic sur l'icone) ou lancement pour ouvrir un fichier ? macOS le dit
        // dans la notification de lancement ; a defaut, on laisse un instant a l'evenement
        // d'ouverture, qui peut arriver apres celle-ci. Une notification ne doit jamais
        // demarrer ni arreter un enregistrement.
        let lancementSimple = notification.userInfo?["NSApplicationLaunchIsDefaultLaunchKey"] as? Bool
        commencer()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            if !self.lanceeAvecFichiers && lancementSimple != false { self.basculer() }
            self.finir()
        }
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
            if self.taches > 0 { return }
            // un message arrive pendant la fermeture ne se perd pas : il est lu avant de quitter
            let enAttente = self.messagesEnAttente()
            if enAttente.isEmpty { NSApp.terminate(nil) } else { self.notifier(enAttente) }
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
        let journal = FileManager.default.temporaryDirectory
            .appendingPathComponent("reunion-\(UUID().uuidString).err")
        FileManager.default.createFile(atPath: journal.path, contents: nil)
        defer { try? FileManager.default.removeItem(at: journal) }
        do {
            processus.standardError = try FileHandle(forWritingTo: journal)
            processus.standardOutput = FileHandle.nullDevice
            try executer(processus, delai: delaiBascule)
        } catch {
            return (1, "Lancement impossible : \(error.localizedDescription)")
        }
        let texte = (try? String(contentsOf: journal, encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if processus.terminationReason == .uncaughtSignal {
            return (1, "La commande transcription-locale reunion ne répond pas.")
        }
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

    private func dansLeDossierDesMessages(_ url: URL) -> Bool {
        url.isFileURL && url.pathExtension == extensionMessage
            && url.standardizedFileURL.deletingLastPathComponent().path == dossierMessages.path
    }

    private func messagesEnAttente() -> [URL] {
        let contenu = (try? FileManager.default.contentsOfDirectory(
            at: dossierMessages, includingPropertiesForKeys: nil)) ?? []
        return contenu.filter(dansLeDossierDesMessages)
    }

    /// Texte d'un message de notre dossier, efface ensuite ; tout autre fichier est ignore,
    /// sans etre lu ni efface.
    private func lireMessage(_ url: URL) -> String? {
        guard dansLeDossierDesMessages(url) else { return nil }
        defer { try? FileManager.default.removeItem(at: url) }
        guard let taille = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize,
              taille <= tailleMaxMessage,
              let donnees = try? Data(contentsOf: url),
              let texte = String(data: donnees, encoding: .utf8) else { return nil }
        let propre = texte.trimmingCharacters(in: .whitespacesAndNewlines)
        return propre.isEmpty ? nil : propre
    }

    private func notifier(_ urls: [URL]) {
        let messages = urls.compactMap(lireMessage)
        commencer()
        if messages.isEmpty {
            finir()
            return
        }
        let centre = UNUserNotificationCenter.current()
        centre.requestAuthorization(options: [.alert, .sound]) { accordee, erreur in
            if !accordee {
                // diagnostic : log show --predicate 'process == "Reunion"'
                NSLog("Réunion : notifications refusées (%@), repli sur osascript. "
                      + "Réglages > Notifications > Réunion pour les autoriser.",
                      erreur?.localizedDescription ?? "sans détail")
            }
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
                        if let erreur {
                            NSLog("Réunion : notification refusée (%@), repli sur osascript.",
                                  erreur.localizedDescription)
                            self.notifierParScript(message)
                        }
                        groupe.leave()
                    }
                } else {
                    self.notifierParScript(message)  // notification du systeme, icone de script
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
        try? executer(processus, delai: delaiScript)
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
