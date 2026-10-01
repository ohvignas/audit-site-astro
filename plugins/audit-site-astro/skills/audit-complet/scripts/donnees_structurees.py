#!/usr/bin/env python3
"""donnees_structurees.py — JSON-LD : propriétés requises par Google pour chaque type de résultat enrichi, et types qui n'ont
plus d'affichage enrichi dans Google Search (retraits de 2023 à 2026, journal des mises à jour de Google Search Central).
Module du diffuseur html_observateurs (T3) : Observateur (un passage par page) puis issues(pages, add, ctx).

Deux notions distinctes : l'éligibilité à un résultat enrichi Google (propriétés requises par Google, constat « moyenne ») et la
validité schema.org (un JSON-LD sans effet chez Google reste valide et utile aux assistants IA : constat « info » seulement).

Table REQUIS vérifiée sur developers.google.com le 2026-10-01 (pages « Required properties » de chaque type, mises à jour le
2026-09-08 sauf indication) ; retraits lus dans https://developers.google.com/search/updates le 2026-10-01.
Écarts avec le plan v2.1 (la page prime) : JobPosting exige aussi jobLocation (ou applicantLocationRequirements pour un poste 100 %
télétravail) ; FAQPage n'a plus de propriétés requises (documentation supprimée le 15/06/2026, résultat enrichi arrêté le
07/05/2026) ; la liste des types retirés s'étend à FAQPage (2026) et à la boîte de recherche de sitelinks (2024).

Contrôle de cohérence volontairement minimal : un prix de JSON-LD absent du texte visible (« basse ») ; rien d'autre n'est comparé.

Objets contrôlés : seulement ceux que Google évalue comme résultat enrichi, soit la racine, les éléments de @graph ou d'une liste
racine, mainEntity / mainEntityOfPage, l'item d'un ListItem, et les Review / AggregateRating lus sous review, reviews, aggregateRating.
Jamais les objets valeurs d'autres propriétés (itemOffered, itemReviewed, provider, author, publisher, location, brand,
hasOfferCatalog…) : Google n'exige rien d'eux. Les @id sont résolus sur toute la page (nœuds fusionnés ; un Offer qui désigne un
produit par itemOffered, un Review ou AggregateRating par itemReviewed, lui donnent offers, review, aggregateRating)."""
import json
import math
import re

import html_observateurs as ho

NOM = "donnees_structurees"
LOCAL = {"LocalBusiness", "Restaurant", "Store", "ProfessionalService", "MedicalClinic", "Dentist", "Hotel", "Bakery",
         "CafeOrCoffeeShop", "AutoRepair", "HealthAndBeautyBusiness", "LegalService", "RealEstateAgent",
         # sous-types schema.org de LocalBusiness (Google : « utiliser le sous-type le plus précis »)
         "FoodEstablishment", "BarOrPub", "FastFoodRestaurant", "IceCreamShop", "Winery", "Brewery", "LodgingBusiness", "Motel",
         "Hostel", "BedAndBreakfast", "Resort", "Electrician", "Plumber", "Locksmith", "RoofingContractor", "GeneralContractor",
         "HVACBusiness", "MovingCompany", "HousePainter", "HairSalon", "BeautySalon", "DaySpa", "NailSalon", "HealthClub",
         "GymOrFitnessCenter", "Physician", "Pharmacy", "AutoDealer", "AutoWash", "GasStation", "AccountingService", "Attorney",
         "Notary", "TravelAgency", "InsuranceAgency", "FinancialService", "BankOrCreditUnion", "Library", "BookStore",
         "ClothingStore", "Florist", "FurnitureStore", "HardwareStore", "GroceryStore", "PetStore", "EntertainmentBusiness"}
EVENEMENTS = {"BusinessEvent", "ChildrensEvent", "ComedyEvent", "DanceEvent", "EducationEvent", "ExhibitionEvent", "Festival",
              "FoodEvent", "Hackathon", "LiteraryEvent", "MusicEvent", "ScreeningEvent", "SocialEvent", "SportsEvent", "TheaterEvent",
              "VisualArtsEvent"}  # sous-types d'Event ; ni CourseInstance (Course info, retiré), ni EventSeries, ni BroadcastEvent
APPLICATIONS = {"MobileApplication", "WebApplication"}  # cités par la page Google « Software app »
REQUIS = {  # type : groupes ; chaque groupe exige au moins une des propriétés (lu sur les pages Google le 2026-10-01)
    "Event": (("name",), ("startDate",), ("location",)),
    "Product": (("name",), ("offers", "review", "aggregateRating")),
    "JobPosting": (("datePosted",), ("description",), ("hiringOrganization",), ("jobLocation", "applicantLocationRequirements"),
                   ("title",)),
    "Recipe": (("name",), ("image",)),
    "VideoObject": (("name",), ("thumbnailUrl",), ("uploadDate",)),
    "BreadcrumbList": (("itemListElement",),),
    "Course": (("name",), ("description",)),  # liste de cours (au moins trois cours) ; « Course info » est retiré
    "SoftwareApplication": (("name",), ("offers",), ("aggregateRating", "review")),
    "Review": (("author",), ("reviewRating",)),
    "AggregateRating": (("ratingValue",), ("ratingCount", "reviewCount")),
    "LocalBusiness": (("name",), ("address",)),
}
RETIRES = {  # type : message. Une fonctionnalité retirée de Google reste du schema.org valide (info, jamais une erreur)
    "ClaimReview": "ClaimReview : affichage en cours de retrait (bannière Google du 12/06/2025)",
    "SpecialAnnouncement": "SpecialAnnouncement : documentation supprimée le 09/09/2025",
    "Occupation": "Estimated salary (Occupation) : documentation supprimée le 09/09/2025",
    "Quiz": "Practice problem (Quiz) : déprécié le 05/11/2025, documentation supprimée le 06/01/2026",
    "HowTo": "HowTo : résultats enrichis retirés en 2023",
    "FAQPage": "FAQPage : résultat enrichi FAQ arrêté le 07/05/2026 (restreint aux sites gouvernementaux et de santé depuis 2023)",
}
PROFONDEUR_MAX = 40
TYPES_PRIX = {"Offer", "AggregateOffer", "PriceSpecification", "UnitPriceSpecification"}
MIN_TEXTE_VISIBLE = 100  # caractères : en dessous, la page n'a rien à comparer
MAX_CHIFFRES = 15        # un prix ou un nombre du texte plus long n'est pas un prix
PREFIXE_TYPE = re.compile(r"^(?:https?://schema\.org/|schema:)")
# Le texte visible est normalisé par split() avant la recherche : espaces ordinaires, insécables (U+00A0, U+202F) et fines y deviennent
# un espace simple, donc « 1 490 », « 1&nbsp;490 » et « 1&#8239;490 » se lisent pareil.
GROUPES_MILLIERS = re.compile(r"\d{1,3}(?:[ .,]\d{3})+(?:[.,]\d+)?")
NOMBRES_SIMPLES = re.compile(r"\d+(?:[.,]\d+)?")


def _types(o):
    t = o.get("@type")
    return [PREFIXE_TYPE.sub("", x) for x in (t if isinstance(t, list) else [t]) if isinstance(x, str) and x]


def _famille(t):
    if t in LOCAL:
        return "LocalBusiness"
    if t in EVENEMENTS:
        return "Event"
    return "SoftwareApplication" if t in APPLICATIONS else t


def _objets(racine):
    """(objet, rôle) pour tout objet typé (ou à @id) du JSON-LD. rôle = « plein » (Google l'évalue : racine, @graph, liste racine, mainEntity,
    item d'un ListItem), « avis » (Review / AggregateRating lus sous review, reviews, aggregateRating) ou None (valeur d'une autre
    propriété : itemOffered, provider, location… ; jamais contrôlé, mais lu pour les types retirés, les prix et les @id)."""
    pile = [(racine, "plein", 0)]
    while pile:
        o, role, prof = pile.pop()
        if prof > PROFONDEUR_MAX:
            continue
        if isinstance(o, dict):
            types = _types(o)
            if types or "@id" in o:  # un nœud sans @type mais avec @id sert à fusionner les propriétés d'un même @id
                yield o, role
            for k, v in o.items():
                if k == "@graph":
                    r = role
                elif k in ("mainEntity", "mainEntityOfPage") or (k == "item" and "ListItem" in types):
                    r = "plein"
                elif k in ("review", "reviews", "aggregateRating"):
                    r = "avis"
                else:
                    r = None
                pile.append((v, r, prof + 1))
        elif isinstance(o, list):
            pile.extend((v, role, prof + 1) for v in o)


def _rempli(v):
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _identifiants(objets):
    """{@id: propriétés fusionnées} de tous les nœuds de la page ; un Offer (itemOffered) ou un Review / AggregateRating (itemReviewed)
    qui désigne un nœud par @id lui apporte offers, review ou aggregateRating."""
    fus = {}
    for o, _ in objets:
        i = o.get("@id")
        if isinstance(i, str) and set(o) != {"@id"}:  # un simple renvoi n'apporte rien
            for k, v in o.items():
                if _rempli(v):
                    fus.setdefault(i, {}).setdefault(k, v)
    for o, _ in objets:
        types = _types(o)
        for cle, propriete in (("itemOffered", "offers"), ("itemReviewed", "review" if "Review" in types else "aggregateRating"
                                                           if "AggregateRating" in types else None)):
            cibles = o.get(cle)
            for c in cibles if isinstance(cibles, list) else [cibles]:
                if propriete and isinstance(c, dict) and isinstance(c.get("@id"), str):
                    fus.setdefault(c["@id"], {}).setdefault(propriete, {"@id": o.get("@id", "#")})
    return fus


def _vue(o, fus):
    """Propriétés renseignées de l'objet, complétées par celles des autres nœuds de même @id."""
    i = o.get("@id")
    vue = dict(fus.get(i, {})) if isinstance(i, str) else {}
    vue.update({k: v for k, v in o.items() if _rempli(v)})
    return vue


def _renvoi_inconnu(o, fus):
    """Objet qui n'est qu'un renvoi @id vers un nœud absent de la page : impossible à juger."""
    return set(o) <= {"@id"} and o.get("@id") not in fus


def _elements(v):
    return [x for x in (v if isinstance(v, list) else [v]) if x not in (None, "")]


def _lieu_manque(location, fus):
    """location.name / location.address absents d'un lieu physique ; [] pour un lieu en ligne, un texte ou un renvoi non résolu."""
    manque = []
    for el in _elements(location):
        if not isinstance(el, dict) or _renvoi_inconnu(el, fus) or "VirtualLocation" in _types(el):
            return []
        vue = _vue(el, fus)
        m = ["location." + p for p in ("name", "address") if p not in vue]
        if not m:
            return []
        manque = manque or m
    return manque


def _offre_manque(offers, fus):
    """offers.price absent (Google : « offers.price » requis pour une application ; 0 = gratuit est une valeur)."""
    for el in _elements(offers):
        if not isinstance(el, dict) or _renvoi_inconnu(el, fus) or "price" in _vue(el, fus):
            return []
    return ["offers.price"]


DETAILS = {("Event", "location"): _lieu_manque, ("SoftwareApplication", "offers"): _offre_manque}


def _absentes(famille, o, fus):
    vue, absentes = _vue(o, fus), []
    for g in REQUIS[famille]:
        if not any(p in vue for p in g):
            absentes.append("|".join(g))
        elif (famille, g[0]) in DETAILS and len(g) == 1:
            absentes.extend(DETAILS[(famille, g[0])](vue[g[0]], fus))
    return absentes


def _retires(o, types):
    """Messages « type sans affichage enrichi » de l'objet (sans doublon : un objet à deux types compte une fois)."""
    msgs = [RETIRES[t] for t in types if t in RETIRES]
    if "Course" in types and "hasCourseInstance" in o:
        msgs.append("Course Info (hasCourseInstance) : documentation supprimée le 09/09/2025")
    if ("Car" in types or "Vehicle" in types) and _rempli(o.get("offers")):
        msgs.append("Vehicle listing : documentation supprimée le 09/09/2025")
    if "VideoObject" in types and any(_rempli(o.get(p)) for p in ("learningResourceType", "educationalLevel", "educationalAlignment")):
        msgs.append("Learning video : documentation supprimée le 09/09/2025")
    if "WebSite" in types:
        actions = o.get("potentialAction")
        for a in actions if isinstance(actions, list) else [actions]:
            if isinstance(a, dict) and "SearchAction" in _types(a):
                msgs.append("Sitelinks search box (WebSite + SearchAction) : documentation supprimée le 29/11/2024")
                break
    return list(dict.fromkeys(msgs))


def _prix(o):
    """Prix numérique d'une offre, ou None (« sur devis », 0 = gratuit, valeur trop longue ou non finie : rien à comparer)."""
    v = o.get("price")
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, int) and len(str(abs(v))) > MAX_CHIFFRES:
            return None
        x = float(v)
    else:
        s = "".join(str(v).split())
        s = s.replace(",", ".") if "," in s and "." not in s else s
        if len(s) > MAX_CHIFFRES + 3 or not re.fullmatch(r"\d+(?:\.\d+)?", s):
            return None
        x = float(s)
    return x if math.isfinite(x) and 0 < x < 10 ** MAX_CHIFFRES else None


def _nombres(texte):
    """Valeurs numériques lisibles dans un texte normalisé (« 1 200 € », « 1.200,00 », « 49,90 ») ; large exprès : plus il y a de lectures
    possibles, moins on signale à tort. Les suites de plus de MAX_CHIFFRES caractères ne sont pas des prix."""
    vus = set()
    for m in GROUPES_MILLIERS.finditer(texte):
        brut = m.group(0).replace(" ", "")
        if len(brut) > MAX_CHIFFRES + 3:
            continue
        vus.add(round(float(re.sub(r"[.,]", "", brut)), 2))
        i = max(brut.rfind(","), brut.rfind("."))
        if i >= 0:
            vus.add(round(float(re.sub(r"[.,]", "", brut[:i]) + "." + brut[i + 1:]), 2))
    for m in NOMBRES_SIMPLES.finditer(texte):
        brut = m.group(0)
        if len(brut) > MAX_CHIFFRES + 3:
            continue
        vus.add(round(float(brut.replace(",", ".")), 2))
        vus.add(round(float(re.sub(r"[.,]", "", brut)), 2))
    return vus


class Observateur(ho.Observateur):
    def __init__(self, entetes, url):
        super().__init__(entetes, url)
        self._bloc, self.blocs, self._visible = None, [], []

    def debut(self, noeud, pile):
        if noeud["tag"] == "script" and "ld+json" in noeud["a"].get("type", "").lower():
            self._bloc = []

    def texte(self, donnees, pile):
        if self._bloc is not None:
            self._bloc.append(donnees)
        elif ho.visible(pile):
            self._visible.append(donnees)

    def fin(self, noeud, pile):
        if noeud["tag"] == "script" and self._bloc is not None:
            self.blocs.append("".join(self._bloc))
            self._bloc = None

    def resultat(self):
        manquantes, retires, incoherentes, cours_isoles = {}, {}, {}, {}
        visible = " ".join(" ".join(self._visible).split())
        nombres = _nombres(visible) if len(visible) >= MIN_TEXTE_VISIBLE else None
        objets = []
        for brut in self.blocs:
            try:
                donnees = json.loads(brut)
            except (ValueError, RecursionError):
                continue  # JSON invalide : jsonld_invalid (crawl_site)
            objets.extend(_objets(donnees))
        fus = _identifiants(objets)
        liste_de_cours = sum(1 for o, role in objets if role and "Course" in _types(o)) >= 3
        for o, role in objets:
            types = _types(o)
            vus = set()
            for t in types if role else ():
                famille = _famille(t)
                if famille in vus or famille not in REQUIS or (role == "avis" and famille not in ("Review", "AggregateRating")):
                    continue
                vus.add(famille)
                absentes = _absentes(famille, o, fus)
                if absentes:
                    sig = "{0} : {1}".format(t, ", ".join(absentes))
                    # Course : Google n'affiche « liste de cours » que pour au moins trois cours : constat à part s'il n'y a pas de liste
                    cible = cours_isoles if famille == "Course" and not liste_de_cours else manquantes
                    cible[sig] = cible.get(sig, 0) + 1
            for r in _retires(o, types):
                retires[r] = retires.get(r, 0) + 1
            if nombres is not None and TYPES_PRIX.intersection(types):
                prix = _prix(o)
                if prix is not None and round(prix, 2) not in nombres:
                    sig = "Offer : prix {0} absent du texte visible".format(("%.2f" % prix).rstrip("0").rstrip("."))
                    incoherentes[sig] = incoherentes.get(sig, 0) + 1
        conv = lambda d: [{"signature": k, "n": v} for k, v in sorted(d.items())]  # noqa: E731
        res = {"manquantes": conv(manquantes), "retires": conv(retires)}
        for cle, d in (("incoherentes", incoherentes), ("cours_isoles", cours_isoles)):
            if d:  # clés présentes seulement si elles servent : le format de base reste {manquantes, retires}
                res[cle] = conv(d)
        return res


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "jsonld_proprietes_requises", "JSON-LD : propriétés requises par Google absentes (pas de résultat enrichi)",
                       "moyenne", ho.collecter_groupes(pages, NOM, "manquantes"), "SEO technique")
    ho.ajouter_groupes(add, "jsonld_cours_incomplet", "JSON-LD : Course sans name ou description (Google ne montre un résultat « liste de "
                       "cours » que pour au moins trois cours sur une page ou dans une liste ; sans liste, rien ne se perd)",
                       "basse", ho.collecter_groupes(pages, NOM, "cours_isoles"), "SEO technique")
    ho.ajouter_groupes(add, "jsonld_type_sans_effet", "JSON-LD : type sans affichage enrichi Google (retiré ou restreint), balisage "
                       "toujours valide schema.org", "info", ho.collecter_groupes(pages, NOM, "retires"), "SEO technique")
    ho.ajouter_groupes(add, "jsonld_prix_absent_du_texte", "JSON-LD : prix absent du texte visible de la page (à vérifier : le balisage "
                       "doit refléter le contenu visible)", "basse", ho.collecter_groupes(pages, NOM, "incoherentes"), "SEO technique")
