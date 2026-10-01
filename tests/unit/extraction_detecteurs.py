"""Extraction, depuis le source des détecteurs, d'échantillons réalistes de ce qu'ils produisent (aide des tests de couverture).

- Python (`crawl_site.py`, `geo_check.py`, `astro_scan.py`) : analyse `ast` ; les f-strings sont instanciées avec des valeurs plausibles.
- Shell (`http_checks.sh`, `security_probe.sh`) : les lignes `echo` qui contiennent ❌ ou ⚠️ sont « développées » (substitutions
  de commandes, `${var:-défaut}`, variables `v` / `verdict` / variables de boucle `for`), une variante par branche marquée.
  Heuristique documentée : dans une substitution de commande sans écho marqué, la valeur par défaut `${x:-défaut}` est retenue
  (cas « absent »), sinon « x ». Les lignes sans ❌/⚠️ ne sont pas extraites (signaux.collecter les ignore aussi).
"""
import ast
import itertools
import re

MARQUES = ("❌", "⚠️")
_LIMITE = 60


def a_marque(s):
    return any(m in s for m in MARQUES)


# --------------------------------------------------------------------------- Python

def _defaut(expr):
    """Valeur plausible d'une expression inconnue d'un f-string."""
    if re.search(r"len\(|\[\s*['\"](load|only)['\"]\s*\]|\bq\b|_imgs?\b|svg_imports|\bv\[0\]|latest\[0\]", expr):
        return ["3"]
    if re.fullmatch(r"i", expr):
        return ["12"]
    return ["exemple"]


def valeurs(node, env=None):
    """Chaînes possibles pour un nœud `ast` de message (Constant, f-string, concaténation, conditionnelle). `env` associe le
    source d'une expression de f-string à une liste de valeurs."""
    env = env or {}
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        morceaux = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                morceaux.append([part.value])
            else:  # FormattedValue
                src = ast.unparse(part.value)
                morceaux.append(env.get(src) or _defaut(src))
        return ["".join(c) for c in itertools.islice(itertools.product(*morceaux), _LIMITE)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return ["".join(c) for c in itertools.islice(itertools.product(valeurs(node.left, env), valeurs(node.right, env)), _LIMITE)]
    if isinstance(node, ast.IfExp):
        return valeurs(node.body, env) + valeurs(node.orelse, env)
    src = ast.unparse(node)  # appel, variable, indice… : valeur du tableau `env` ou valeur plausible
    return env.get(src) or _defaut(src)


def appels(source, nom, indice_message, env=None):
    """Messages des appels `nom(...)` (fonction nue) du source : liste de listes de chaînes (une par appel)."""
    out = []
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nom and len(n.args) > indice_message:
            out.append(valeurs(n.args[indice_message], env))
    return out


def cles_crawl(source):
    """Clés d'issue de crawl_site.py : 1er argument de `add(...)`, 2ᵉ de `ajouter_groupes(add, ...)`, 1er de `issues.setdefault(...)` et `issues["clé"] = …`.
    Lève ValueError si un de ces arguments n'est pas un littéral (l'extraction ne serait plus fiable)."""
    cles = set()

    def lit(node, ou):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            raise ValueError(f"clé d'issue non littérale ({ou}) : {ast.unparse(node)}")
        cles.add(node.value)

    arbre = ast.parse(source)
    # le corps de l'aide `add(key, …)` elle-même utilise `issues.setdefault(key, …)` avec une variable : à ignorer
    interne = {id(x) for f in ast.walk(arbre) if isinstance(f, ast.FunctionDef) and f.name in ("add", "ajouter_groupes")
               for x in ast.walk(f)}
    for n in ast.walk(arbre):
        if id(n) in interne:
            continue
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "add" and n.args:
            lit(n.args[0], "add")  # add(…) nu seulement : jamais ensemble.add(x) (crawl_site.py en a 8, T14 aussi)
        elif (isinstance(n, ast.Call) and len(n.args) > 1
              and (getattr(n.func, "id", None) == "ajouter_groupes" or getattr(n.func, "attr", None) == "ajouter_groupes")):
            lit(n.args[1], "ajouter_groupes")  # (html_observateurs.)ajouter_groupes(add, "clé", …)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "setdefault"
              and ast.unparse(n.func.value) == "issues" and n.args):
            lit(n.args[0], "issues.setdefault")
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Subscript) and ast.unparse(t.value) == "issues":
                    lit(t.slice, "issues[…]")
    return cles


# --------------------------------------------------------------------------- Shell

def _lire_mot(s, i):
    """Lit un mot shell à partir de s[i] (guillemets simples/doubles concaténés). Retourne (mot sans guillemets externes, fin)."""
    out, n = [], len(s)
    while i < n and s[i] not in " \t|&;)\n":
        c = s[i]
        if c == "'":
            j = s.index("'", i + 1)
            out.append(s[i + 1:j])
            i = j + 1
        elif c == '"':
            j = _fin_guillemets(s, i + 1)
            out.append(s[i + 1:j])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out), i


def _fin_guillemets(s, i):
    """Index du guillemet double fermant, en sautant `\\x`, `$( … )` et `${ … }`."""
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
        elif s.startswith("$(", i):
            i = _fermant(s, i + 2, "(", ")") + 1
        elif s.startswith("${", i):
            i = _fermant(s, i + 2, "{", "}") + 1
        elif c == '"':
            return i
        else:
            i += 1
    raise ValueError(f"guillemet non fermé : {s!r}")


def _fermant(s, i, ouvre, ferme):
    """Index de la parenthèse/accolade fermante correspondante (profondeur 1 au départ), sensible aux guillemets."""
    depth, n = 1, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            i = s.index("'", i + 1) + 1
            continue
        if c == '"':
            i = _fin_guillemets(s, i + 1) + 1
            continue
        if c == ouvre:
            depth += 1
        elif c == ferme:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"délimiteur non fermé : {s!r}")


def _echos(ligne):
    """Arguments (mot brut avec guillemets, tel qu'écrit) des `echo` de niveau 0 de la ligne (hors `$( … )` et guillemets)."""
    out, i, n = [], 0, len(ligne)
    while i < n:
        c = ligne[i]
        if c == "'":
            i = ligne.index("'", i + 1) + 1
        elif c == '"':
            i = _fin_guillemets(ligne, i + 1) + 1
        elif ligne.startswith("$(", i):
            i = _fermant(ligne, i + 2, "(", ")") + 1
        elif ligne.startswith("echo", i) and (i == 0 or ligne[i - 1] in " \t;&|(") and ligne[i + 4:i + 5] in (" ", "\t"):
            j = i + 4
            while j < n and ligne[j] in " \t":
                j += 1
            k = j
            while k < n and ligne[k] not in " \t|&;\n":
                if ligne[k] == "'":
                    k = ligne.index("'", k + 1) + 1
                elif ligne[k] == '"':
                    k = _fin_guillemets(ligne, k + 1) + 1
                elif ligne.startswith("$(", k):
                    k = _fermant(ligne, k + 2, "(", ")") + 1
                else:
                    k += 1
            out.append(ligne[j:k])
            i = k
        else:
            i += 1
    return out


def _produit(listes):
    return ["".join(c) for c in itertools.islice(itertools.product(*listes), _LIMITE)]


def developper(s, env, dq=False):
    """Développe une chaîne shell en variantes. `env` : nom de variable -> liste de valeurs. `dq` : le contenu vient d'un
    « … » (les apostrophes y sont littérales)."""
    morceaux, i, n = [], 0, len(s)
    tampon = []

    def vider():
        if tampon:
            morceaux.append(["".join(tampon)])
            tampon.clear()

    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            tampon.append(s[i + 1])
            i += 2
        elif c == "'" and not dq:  # apostrophes de citation dans un mot brut
            j = s.index("'", i + 1)
            tampon.append(s[i + 1:j])
            i = j + 1
        elif c == '"' and not dq:
            j = _fin_guillemets(s, i + 1)
            vider()
            morceaux.append(developper(s[i + 1:j], env, dq=True))
            i = j + 1
        elif s.startswith("$((", i):
            j = _fermant(s, i + 3, "(", ")")
            tampon.append("42")
            i = j + 2
        elif s.startswith("$(", i):
            j = _fermant(s, i + 2, "(", ")")
            vider()
            morceaux.append(_commande(s[i + 2:j], env))
            i = j + 1
        elif s.startswith("${", i):
            j = _fermant(s, i + 2, "{", "}")
            vider()
            morceaux.append(_parametre(s[i + 2:j], env))
            i = j + 1
        elif c == "$" and i + 1 < n and (s[i + 1].isalpha() or s[i + 1] == "_"):
            m = re.match(r"\w+", s[i + 1:])
            vider()
            morceaux.append(env.get(m.group(0)) or ["x"])
            i += 1 + m.end()
        else:
            tampon.append(c)
            i += 1
    vider()
    return _produit(morceaux) if morceaux else [""]


def _parametre(inner, env):
    m = re.match(r"(\w+)(:-|:\+)(.*)$", inner, re.S)
    if not m:
        m2 = re.match(r"(\w+)", inner)
        return env.get(m2.group(1)) or ["x"] if m2 else ["x"]
    nom, op, reste = m.groups()
    if op == ":-":  # cas « variable absente » sauf si une valeur marquée est connue (v, verdict…)
        return env.get(nom) or developper(reste, env)
    return developper(reste, env)


def _commande(inner, env):
    """Substitution `$( … )` : variantes des `echo` marqués ; sinon, valeur par défaut du premier `${x:-défaut}` ; sinon « x »."""
    variantes = []
    for brut in _echos_profonds(inner):
        for v in developper(brut, env):
            if a_marque(v):
                variantes.append(v)
    if variantes:
        return variantes
    m = re.search(r"\$\{\w+:-([^}]*)\}", inner)
    return developper(m.group(1), env) if m else ["x"]


def _echos_profonds(inner):
    """Comme `_echos` mais sur le contenu d'une substitution (les echo y sont de niveau 0)."""
    return _echos(inner)


def _sections(lignes):
    """Index de section (`echo "## …"`) de chaque ligne."""
    out, cur = [], 0
    for l in lignes:
        if re.match(r'\s*echo "## ', l):
            cur += 1
        out.append(cur)
    return out


def echantillons_shell(source, exclure_valeurs=(), codes=("404",)):
    """Lignes `echo` marquées du script shell, développées. Retourne la liste triée des échantillons (chaînes) distincts.
    `exclure_valeurs` : {nom de variable de boucle: valeurs à ignorer} (branches surchargées plus loin dans le script)."""
    lignes = source.splitlines()
    sect = _sections(lignes)
    out = set()
    # variables « marquées » (v, verdict) par section, variables de boucle for, fonctions
    for idx, ligne in enumerate(lignes):
        if ligne.lstrip().startswith("#"):
            continue
        env = {"code": list(codes), "sev": ["@SEV@"], "path": ["@PATH@"], "size": ["1234"], "full": ["https://exemple.fr/_astro/app.js"],
               "mapref": ["sourceMappingURL=app.js.map"], "cors": ["access-control-allow-origin: *"], "nprio": ["2"], "i": ["1"]}
        # assignations marquées de v / verdict dans la même section
        alts = {}
        for j, l2 in enumerate(lignes):
            if sect[j] != sect[idx] or l2.lstrip().startswith("#"):
                continue
            for m in re.finditer(r"\b(v|verdict)=(?:\"((?:[^\"\\]|\\.)*)\"|'([^']*)')", l2):
                nom, val = m.group(1), (m.group(2) if m.group(2) is not None else m.group(3))
                if a_marque(val):
                    alts.setdefault(nom, []).append(val)
        for nom, vals in alts.items():
            env[nom] = sorted({x for val in vals for x in developper(val, dict(env, v=[""], verdict=[""]))})
        utilise = any(re.search(r"\$\{?" + nom + r"\b", ligne) for nom in alts)
        if not (a_marque(ligne) or utilise):
            continue
        # variable de boucle for la plus proche avant la ligne, dans la section
        for j in range(idx, -1, -1):
            if sect[j] != sect[idx]:
                break
            m = re.search(r"\bfor (\w+) in ([^;]+); do", lignes[j])
            if m:
                mots = [w for w in m.group(2).split() if not w.startswith("$")]
                mots = [w for w in mots if w not in exclure_valeurs.get(m.group(1), ())]
                env[m.group(1)] = mots or ["x"]
                break
        for brut in _echos(ligne):
            for v in developper(brut, env):
                if a_marque(v):
                    out.add(v.strip())
    return sorted(out)


def lignes_check(source):
    """Appels `check "chemin" "motif" "gravité"` de security_probe.sh -> [(chemin, motif, gravité)]."""
    return re.findall(r'^check "([^"]+)" "((?:[^"\\]|\\.)*)" "(\w+)"', source, re.M)
