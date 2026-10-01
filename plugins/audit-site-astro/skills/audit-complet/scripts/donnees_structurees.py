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
Un objet imbriqué qui ne porte que des champs de renvoi (name, url, image…) n'est pas contrôlé : c'est une référence, pas la page."""
import json
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
RENVOI = {"@type", "@id", "name", "url", "sameAs", "image", "logo", "description"}  # objet imbriqué qui n'a que ces champs : renvoi
PROFONDEUR_MAX = 40
TYPES_PRIX = {"Offer", "AggregateOffer", "PriceSpecification", "UnitPriceSpecification"}
MIN_TEXTE_VISIBLE = 100  # caractères : en dessous, la page n'a rien à comparer
GROUPES_MILLIERS = re.compile(r"\d{1,3}(?:[   .,]\d{3})+(?:[.,]\d+)?")
NOMBRES_SIMPLES = re.compile(r"\d+(?:[.,]\d+)?")


def _types(o):
    t = o.get("@type")
    return [x for x in (t if isinstance(t, list) else [t]) if isinstance(x, str) and x]


def _objets(racine):
    """(objet typé, de premier niveau ?) : premier niveau = racine, élément d'une liste racine ou de @graph ; un objet typé
    qui contient d'autres objets (offers, location, mainEntity…) les rend imbriqués."""
    pile = [(racine, True, 0)]
    while pile:
        o, premier, prof = pile.pop()
        if prof > PROFONDEUR_MAX:
            continue
        if isinstance(o, dict):
            if _types(o):
                yield o, premier
            for k, v in o.items():
                pile.append((v, premier and (k == "@graph" or "@type" not in o), prof + 1))
        elif isinstance(o, list):
            pile.extend((v, premier, prof + 1) for v in o)


def _rempli(v):
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


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
    """Prix numérique d'une offre, ou None (« sur devis », 0 = gratuit : rien à comparer)."""
    v = o.get("price")
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = re.sub(r"[\s  ]", "", str(v))
        s = s.replace(",", ".") if "," in s and "." not in s else s
        if not re.fullmatch(r"\d+(?:\.\d+)?", s):
            return None
        x = float(s)
    return x if x > 0 else None


def _nombres(texte):
    """Valeurs numériques lisibles dans un texte (« 1 200 € », « 1.200,00 », « 49,90 ») ; large exprès : plus il y a de lectures
    possibles, moins on signale à tort."""
    vus = set()
    for m in GROUPES_MILLIERS.finditer(texte):
        brut = re.sub(r"[   ]", "", m.group(0))
        vus.add(round(float(re.sub(r"[.,]", "", brut)), 2))
        i = max(brut.rfind(","), brut.rfind("."))
        if i >= 0:
            vus.add(round(float(re.sub(r"[.,]", "", brut[:i]) + "." + brut[i + 1:]), 2))
    for m in NOMBRES_SIMPLES.finditer(texte):
        brut = m.group(0)
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
        manquantes, retires, incoherentes = {}, {}, {}
        visible = " ".join(" ".join(self._visible).split())
        nombres = _nombres(visible) if len(visible) >= MIN_TEXTE_VISIBLE else None
        for brut in self.blocs:
            try:
                donnees = json.loads(brut)
            except (ValueError, RecursionError):
                continue  # JSON invalide : jsonld_invalid (crawl_site)
            for o, premier in _objets(donnees):
                types = _types(o)
                if premier or not set(o) <= RENVOI:  # un renvoi imbriqué (Course citée par nom et url) n'est pas une page candidate
                    vus = set()
                    for t in types:
                        famille = "LocalBusiness" if t in LOCAL else t
                        regles = REQUIS.get(famille)
                        if not regles or famille in vus:
                            continue
                        vus.add(famille)
                        absentes = ["|".join(g) for g in regles if not any(_rempli(o.get(p)) for p in g)]
                        if absentes:
                            sig = "{0} : {1}".format(t, ", ".join(absentes))
                            manquantes[sig] = manquantes.get(sig, 0) + 1
                for r in _retires(o, types):
                    retires[r] = retires.get(r, 0) + 1
                if nombres is not None and TYPES_PRIX.intersection(types):
                    prix = _prix(o)
                    if prix is not None and round(prix, 2) not in nombres:
                        sig = "Offer : prix {0} absent du texte visible".format(("%.2f" % prix).rstrip("0").rstrip("."))
                        incoherentes[sig] = incoherentes.get(sig, 0) + 1
        conv = lambda d: [{"signature": k, "n": v} for k, v in sorted(d.items())]  # noqa: E731
        res = {"manquantes": conv(manquantes), "retires": conv(retires)}
        if incoherentes:  # clé présente seulement si elle sert : le format de base reste {manquantes, retires}
            res["incoherentes"] = conv(incoherentes)
        return res


def issues(pages, add, ctx):
    ho.ajouter_groupes(add, "jsonld_proprietes_requises", "JSON-LD : propriétés requises par Google absentes (pas de résultat enrichi)",
                       "moyenne", ho.collecter_groupes(pages, NOM, "manquantes"), "SEO technique")
    ho.ajouter_groupes(add, "jsonld_type_sans_effet", "JSON-LD : type sans affichage enrichi Google (retiré ou restreint), balisage "
                       "toujours valide schema.org", "info", ho.collecter_groupes(pages, NOM, "retires"), "SEO technique")
    ho.ajouter_groupes(add, "jsonld_prix_absent_du_texte", "JSON-LD : prix absent du texte visible de la page (à vérifier : le balisage "
                       "doit refléter le contenu visible)", "basse", ho.collecter_groupes(pages, NOM, "incoherentes"), "SEO technique")
