"""Badge de la barre des menus : toute la zone du bouton prend la couleur de l'etat,
le micro de l'icone Reunion est dessine par-dessus.

Dessine en vectoriel, donc net sur tous les ecrans. Necessite AppKit (PyObjC).
"""
from __future__ import annotations

# etat -> (fond, trace) ; le jaune prend un trace sombre pour rester lisible
COULEURS = {
    "enregistrement": ("rouge", "blanc"),
    "attente": ("jaune", "sombre"),
    "prete": ("vert", "blanc"),
    "echec": ("gris", "blanc"),
}
LARGEUR, HAUTEUR = 20.0, 16.0
MARGE = 8.0  # de part et d'autre du contenu, dans la zone coloree
ECART = 6.0  # entre le micro, la duree et le carre stop
STOP = 8.0  # cote du carre stop
TAILLE_TEXTE = 12.0


def couleur(nom: str):
    import AppKit

    return {
        "rouge": AppKit.NSColor.systemRedColor(),
        "jaune": AppKit.NSColor.systemYellowColor(),
        "vert": AppKit.NSColor.systemGreenColor(),
        "gris": AppKit.NSColor.systemGrayColor(),
        "blanc": AppKit.NSColor.whiteColor(),
        "sombre": AppKit.NSColor.colorWithWhite_alpha_(0.12, 1.0),
    }[nom]


def attributs(trace: str) -> dict:
    import AppKit

    police = AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(TAILLE_TEXTE,
                                                                  AppKit.NSFontWeightSemibold)
    return {AppKit.NSFontAttributeName: police, AppKit.NSForegroundColorAttributeName: couleur(trace)}


def contenu(trace: str, duree: str = ""):
    """NSImage sans fond : le micro, puis, si une duree est donnee, la duree et un carre stop."""
    import AppKit

    texte = AppKit.NSAttributedString.alloc().initWithString_attributes_(duree, attributs(trace)) \
        if duree else None
    taille_texte = texte.size() if texte else None
    largeur = LARGEUR + (ECART + taille_texte.width + ECART + STOP if texte else 0)

    def dessiner(_rect):
        dessiner_micro(trace)
        if texte:
            x = LARGEUR + ECART
            texte.drawAtPoint_((x, (HAUTEUR - taille_texte.height) / 2))
            couleur(trace).setFill()
            AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((x + taille_texte.width + ECART, (HAUTEUR - STOP) / 2), (STOP, STOP)),
                1.5, 1.5).fill()
        return True

    image = AppKit.NSImage.imageWithSize_flipped_drawingHandler_((largeur, HAUTEUR), False, dessiner)
    image.setTemplate_(False)
    return image


def dessiner_micro(trace: str) -> None:
    """Le micro et le texte qui en sort, dans un carre de LARGEUR x HAUTEUR."""
    import AppKit

    couleur(trace).set()
    AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        ((3.6, 6.6), (4.6, 7.8)), 2.3, 2.3).fill()  # capsule
    etrier = AppKit.NSBezierPath.bezierPath()
    etrier.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        (5.9, 8.8), 4.3, 180, 360, False)
    etrier.moveToPoint_((5.9, 4.5))
    etrier.lineToPoint_((5.9, 2.6))  # pied
    etrier.moveToPoint_((3.4, 2.6))
    etrier.lineToPoint_((8.4, 2.6))  # socle
    etrier.setLineWidth_(1.3)
    etrier.setLineCapStyle_(AppKit.NSLineCapStyleRound)
    etrier.stroke()
    lignes = AppKit.NSBezierPath.bezierPath()
    for y, fin in ((12.4, 17.5), (10.2, 15.5), (8.0, 17.5)):
        lignes.moveToPoint_((8.8, y))
        lignes.lineToPoint_((fin, y))
    lignes.setLineWidth_(1.2)
    lignes.setLineCapStyle_(AppKit.NSLineCapStyleRound)
    lignes.stroke()


def poser(element, etat: str, duree: str = "") -> None:
    """Colore tout le bouton d'un NSStatusItem, en pilule, et y pose son contenu."""
    import AppKit

    fond, trace = COULEURS[etat]
    image = contenu(trace, duree)
    element.setLength_(image.size().width + 2 * MARGE)
    bouton = element.button()
    bouton.setTitle_("")
    bouton.setImage_(image)
    bouton.setImagePosition_(AppKit.NSImageOnly)
    bouton.setWantsLayer_(True)
    calque = bouton.layer()
    calque.setBackgroundColor_(couleur(fond).CGColor())
    hauteur = bouton.bounds().size.height or element.statusBar().thickness()
    calque.setCornerRadius_(hauteur / 2)  # pilule : demi-cercles aux extremites
