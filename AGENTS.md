# AGENTS.md — Mockrot

> **Source unique de vérité** pour tout agent IA (Claude Code, Antigravity, Cursor, Codex…) et tout
> contributeur humain. La spécification produit complète se trouve dans
> [`cahierdecharge.md`](./cahierdecharge.md). Ce fichier définit **comment** on travaille ; le cahier
> des charges définit **quoi** construire.
>
> **Règle d'or :** en cas d'ambiguïté, de contradiction ou de décision structurante non couverte ici,
> **s'arrêter et demander** plutôt que supposer.

---

## 1. Contexte du projet

**Mockrot** (`pytest-mockrot`) est un plugin `pytest` qui détecte les **mocks obsolètes
(« Rotting Mocks »)** : des mocks dont les arguments d'appel ou les valeurs de retour ne
correspondent plus au contrat réel (signature + type de retour) du code de production.

- **Le problème :** `unittest.mock` (même avec `autospec=True`) ne valide jamais que `return_value`
  respecte l'annotation `-> ReturnType` de la vraie fonction. Les tests restent verts sur des données
  figées depuis des mois, la prod casse (`AttributeError`, `KeyError`, `ValidationError`).
- **La solution :** intercepter chaque mock, extraire le contrat de la cible réelle
  (`inspect.signature` + `typing.get_type_hints`), et valider **entrées ET sorties** à chaque appel
  via `pydantic.TypeAdapter`.
- **Promesse produit :** zéro configuration (`pytest --mockrot`), zéro faux positif bruyant,
  overhead négligeable, ne casse jamais la suite de l'utilisateur.
- **Cible :** projets Python 3.10+ typés (Pydantic, dataclass, TypedDict), et garde-fou pour le code
  généré/refactoré par des agents IA.

### Périmètre

| Version | Exigences | Contenu |
| :--- | :--- | :--- |
| **V1 (MVP)** | F1 → F8 | Interception, validation signature, validation retour, async, `side_effect`, champs zombies, modes `warn`/`strict`, exemptions |
| **V1.1** | F9 → F12 | Mode record (`.mockrot.lock`), mocks HTTP/OpenAPI, auto-fixer LibCST, export GitHub/JSON |

**Ne jamais implémenter une exigence V1.1 tant que la V1 n'est pas livrée et validée**, sauf demande
explicite.

### Plan de réalisation

1. **Semaine 1 :** bootstrap du dépôt, `interceptor`, `extractor`, `validator`, support async.
2. **Semaine 2 :** champs zombies, sous-mocks `MagicMock`, `reporter` Rich.
3. **Semaine 3 :** `recorder`, export GitHub, démo, publication PyPI v0.1.0.

---

## 2. Stack technique

| Rôle | Outil | Contrainte |
| :--- | :--- | :--- |
| Langage | Python | `>= 3.10` (CI : 3.10 → 3.13) |
| Projet & build | `uv` + `hatchling` | `pyproject.toml` PEP 621, `src-layout`, `uv.lock` versionné |
| Plugin | `pytest` | `>= 8.0`, entry-point `pytest11` |
| Validation | `pydantic` v2 | `TypeAdapter` uniquement, jamais d'API v1 |
| Rendu terminal | `rich` | Uniquement dans `reporter.py` |
| Auto-fixer | `libcst` | Extra optionnel `pytest-mockrot[fix]` (dépendance lourde) |
| Lint & format | `ruff` | Zéro warning |
| Typage | `pyright` mode **strict** | Zéro erreur |
| Tests | `pytest`, `pytester`, `pytest-cov`, `pytest-mock` | Couverture ≥ 90 % (lignes + branches) |

- Nom de distribution : `pytest-mockrot` — package importable : `mockrot`.
- **Aucune nouvelle dépendance runtime** sans justification écrite et validation explicite. Chaque
  dépendance runtime est un coût imposé à tous les utilisateurs.

---

## 3. Architecture

### Pipeline

```text
pytest ──▶ plugin.py ──▶ interceptor.py ──▶ extractor.py ──▶ validator.py ──▶ reporter.py
           (hooks)       (capture cible)    (contrat)        (violations)     (affichage)
```

### Responsabilités et règles de dépendance

| Module | Responsabilité | Peut importer |
| :--- | :--- | :--- |
| `plugin.py` | Hooks pytest, options CLI, config `[tool.mockrot]`, **seule frontière fail-safe** | tout |
| `interceptor.py` | Wrap de `unittest.mock._patch` et `MonkeyPatch.setattr`, proxy d'appel | `extractor`, `validator`, `models` |
| `extractor.py` | Signature, type hints, `ForwardRef`/`TYPE_CHECKING`, async, cache | `models` |
| `validator.py` | Validation des arguments et du retour, champs zombies | `extractor`, `models` |
| `reporter.py` | Rendu Rich, export JSON / SARIF / GitHub | `models` |
| `recorder.py` | Enregistrement d'empreintes `.mockrot.lock` (V1.1) | `models` |
| `fixer.py` | Réécriture LibCST (V1.1) | `models` |
| `models.py` | Types de domaine (`Contract`, `Violation`, `MockSite`…) en `dataclass(frozen=True, slots=True)` | stdlib uniquement |

Règles :

- **Seul `plugin.py` importe `pytest`.** Le cœur (`extractor`, `validator`) est testable sans pytest.
- **Seul `reporter.py` importe `rich`.** Seul `fixer.py` importe `libcst`.
- **Seul `interceptor.py` touche aux API privées** (`unittest.mock._patch`). Toute dépendance à une
  API privée est isolée, commentée, et testée sur toute la matrice Python.
- Les modules communiquent via les types de `models.py`, jamais via des `str` ou des `dict` ad hoc.
- Pas de dépendance circulaire. Pas d'état global mutable, sauf le registre de session explicitement
  créé et détruit par `plugin.py`.

### Structure cible du dépôt

```text
mockrot/
├── pyproject.toml
├── uv.lock
├── AGENTS.md / CLAUDE.md / README.md / CHANGELOG.md / LICENSE
├── .github/workflows/ci.yml
├── src/mockrot/
│   ├── __init__.py  plugin.py  interceptor.py  extractor.py
│   ├── validator.py  reporter.py  models.py  errors.py
│   ├── recorder.py  fixer.py          # V1.1
│   └── py.typed
└── tests/
    ├── unit/            # cœur pur, sans plugin pytest
    ├── integration/     # plugin de bout en bout via la fixture `pytester`
    └── fixtures/        # faux modules « production » (sync, async, pydantic, dataclass, TypedDict…)
```

Toute déviation par rapport à cette structure doit être justifiée et validée.

---

## 4. Invariants produit (non négociables)

1. **Ne jamais faire planter la suite de tests de l'utilisateur.** Toute erreur interne est capturée
   à une **unique frontière** dans `plugin.py`, convertie en avertissement « mode dégradé », et le test
   continue normalement.
2. **Transparence totale.** Le proxy ne modifie jamais la valeur retournée, l'exception levée, ni le
   comportement du mock. En mode `warn`, un test doit produire exactement le même résultat avec ou
   sans Mockrot.
3. **Zéro effet de bord quand désactivé.** Sans `--mockrot`, aucun patch n'est installé, aucun import
   coûteux n'est effectué. Tous les patchs sont restaurés en fin de session, de manière idempotente.
4. **Faux négatif > faux positif.** En cas de doute (type non résolu, signature indisponible, cible
   dynamique), on passe en mode dégradé silencieux. La confiance est le produit.
5. **Zéro configuration.** Tout fonctionne sans `[tool.mockrot]`. La config ne fait qu'affiner.
6. **Budget de performance.** Contrats et `TypeAdapter` compilés **une seule fois par cible**.
   Objectif : overhead < 15 ms sur 500 tests (seuil d'alerte : 50 ms). Toute régression est mesurée.
7. **Chaque violation est actionnable.** Fichier + ligne du mock, cible, contrat réel, et diff précis.

---

## 5. Pièges techniques connus (à lire avant de coder)

Le code de la §6 du cahier des charges est **indicatif**, pas à copier tel quel. Points identifiés :

- **`_patch.start()` ne suffit pas.** `@patch` en décorateur et `with patch(...)` passent par
  `_patch.__enter__` (que `start()` appelle). Il faut intercepter `__enter__` pour couvrir les trois
  usages et `pytest-mock`.
- **Mode lax de Pydantic = faux négatifs.** `validate_python("5000", strict=False)` accepte `"5000"`
  pour un `int`. Le rapport attendu signale ce cas comme « Type mismatch » : la validation des valeurs
  mockées doit être **stricte** (`strict=True`), avec les adaptations nécessaires (ex. `dict` → modèle).
- **Champs zombies.** `TypeAdapter(BaseModel)` ignore les clés en trop par défaut. Ne **jamais**
  muter la config du modèle utilisateur : calculer les clés obsolètes séparément (`model_fields`,
  alias, `TypedDict.__annotations__` / `__required_keys__`).
- **Cache.** `lru_cache` sur `real_fn` échoue sur les callables non hashables, et un cache par
  `id()` est faux (réutilisation des `id` après GC). Utiliser un cache par identité robuste
  (`WeakKeyDictionary` avec repli) et garder `lru_cache` pour les cas hashables.
- **`self` / `cls`.** Utiliser `inspect.getattr_static` pour distinguer fonction, `staticmethod`,
  `classmethod`, méthode liée ; ajuster la signature avant `bind()`.
- **`side_effect` itérable.** Ne jamais consommer l'itérateur par anticipation : valider chaque
  valeur au moment où elle est produite. Exceptions (classes **et** instances) = toujours légitimes.
- **`AsyncMock`.** Valider la valeur **résolue après `await`**, jamais la coroutine.
- **Mocks déjà spécifiés.** `autospec=True` / `spec=` : ne pas dupliquer les erreurs de signature
  déjà levées par `unittest.mock`.
- **Cibles non fonctionnelles.** Patch d'une classe, d'une constante, d'une propriété, d'un module :
  définir le contrat explicitement (ex. classe → `__init__` + instance) ou ignorer proprement.
- **`monkeypatch.setattr` avec un vrai callable** (lambda, fonction factice) : même validation que
  pour un `Mock`, via un wrapper transparent.
- **`ForwardRef` / `TYPE_CHECKING`.** Résolution via le `globalns` du module, puis repli AST isolé
  et mis en cache. Échec → mode dégradé, jamais d'exception.
- **`pytest-xdist`.** Le rapport doit à terme agréger les résultats des workers : ne pas coder un
  registre qui suppose un processus unique sans l'isoler derrière une interface.

- **`inspect.stack()` vs `sys._getframe`.** `inspect.stack()` effectue des appels `os.stat`
  sur chaque fichier de la pile pour lire le code source, ce qui brise les suites asynchrones
  vérifiant les I/O bloquantes (ex. `blockbuster.BlockingError` dans Starlette) et introduit un
  surcoût majeur. Utiliser `sys._getframe()` pour une inspection purement mémoire sans I/O.
- **Plugins pytest internes utilisant `MonkeyPatch.setattr`.** `pytest-asyncio` monkeypatche
  `item.obj` pour synchroniser l'exécution des tests coroutines. Le hook `_patched_monkeypatch_setattr`
  doit ignorer les appels issus des plugins internes de test runner (`pytest_asyncio`, `_pytest`,
  `pluggy`) pour ne pas valider à tort les fonctions de test elles-mêmes comme des mocks.

Tout nouveau piège découvert est **ajouté à cette section** dans le même commit que son correctif.

---

## 6. Méthode de travail (niveau senior)

### Cycle pour chaque tâche

1. **Comprendre** — relire l'exigence (F-ID) dans le cahier des charges, lire le code existant
   concerné, identifier les cas limites. Reformuler l'objectif en une phrase.
2. **Planifier** — pour toute tâche touchant plus d'un module ou l'API publique : présenter un plan
   court (fichiers impactés, approche, tests prévus, risques) et **attendre validation**.
3. **Test rouge** — écrire d'abord le test qui échoue (détection attendue **et** absence de faux
   positif). Pour un bug : un test qui reproduit le bug avant tout correctif.
4. **Implémenter** — le minimum pour passer au vert. Pas de code spéculatif (YAGNI).
5. **Refactorer** — nommage, duplication, lisibilité, sans changer le comportement.
6. **Vérifier** — lancer la vérification complète (§10). Rien n'est « fini » sans preuve.
7. **Commiter** — commits atomiques et propres (§8).

### Principes

- **Petits incréments.** Une branche = un objectif. Une PR relisible en moins de 15 minutes
  (idéalement < 400 lignes de diff hors tests et fixtures).
- **Pas de changement hors périmètre.** Ne pas reformater, renommer ou « améliorer » du code non lié
  à la tâche. Les améliorations repérées sont notées et proposées séparément.
- **Lire avant d'écrire.** Réutiliser les abstractions existantes avant d'en créer de nouvelles.
- **Décisions tracées.** Toute décision d'architecture non triviale est consignée dans
  `docs/adr/NNNN-titre.md` (contexte, décision, alternatives, conséquences).
- **Honnêteté.** Ne jamais affirmer qu'un test passe sans l'avoir exécuté. Signaler explicitement
  ce qui n'a pas été vérifié, les compromis faits, et les limites connues.
- **Dogfooding.** Dès que F1–F3 sont livrés, la suite de tests de Mockrot tourne elle-même avec
  `--mockrot=strict` en CI.

---

## 7. Standards de code

### Langue

- **Anglais** pour tout ce qui est versionné et public : code, identifiants, docstrings,
  commentaires, messages d'erreur, commits, branches, PR, README, CHANGELOG.
- **Français** pour les échanges avec l'utilisateur et la documentation interne (`AGENTS.md`,
  `CLAUDE.md`, cahier des charges).

### Python

- `from __future__ import annotations` en tête de chaque module.
- **Typage complet**, `pyright --strict` à zéro erreur. `Any` uniquement aux frontières (valeurs
  mockées arbitraires) et jamais propagé. `# type: ignore[code]` / `# pyright: ignore[rule]`
  interdit sans commentaire justificatif sur la même ligne.
- Types de domaine : `@dataclass(frozen=True, slots=True)`. Énumérations : `enum.Enum`/`StrEnum`
  (avec repli 3.10).
- Fonctions courtes, pures dès que possible, une seule responsabilité. Pas d'effets de bord à
  l'import.
- **Exceptions :** hiérarchie dédiée dans `errors.py` (`MockrotError` → …). Jamais de `except:` nu
  ni de `except Exception` hors de la frontière fail-safe de `plugin.py` (et du repli documenté de
  `extractor.py`). Toujours chaîner (`raise ... from exc`).
- Pas de `print()`. Sortie utilisateur via `reporter.py` ; diagnostic interne via `logging`
  (logger `mockrot`) ou `warnings`.
- Docstrings style Google sur toute l'API publique et les fonctions non triviales. Les commentaires
  expliquent le **pourquoi**, pas le quoi.
- Pas de code mort, pas de code commenté, pas de `TODO` sans référence (`TODO(F9): ...`).
- Ruff (base) : `E, W, F, I, B, UP, SIM, RUF, PT, N, C4, TC, ARG, BLE, ERA, PL`. Format : `ruff format`.

---

## 8. Workflow Git

### Branches

- **`main`** : protégée, toujours verte, toujours publiable. **Aucun commit direct.** Historique
  **linéaire** (pas de merge commits).
- Branches courtes (durée de vie ≤ 2–3 jours), créées depuis `main` à jour :

```text
<type>/<scope-ou-fid>-<description-kebab-case>

feat/f2-signature-validation
feat/f4-async-mock-support
fix/extractor-forward-ref-name-error
refactor/validator-split-zombie-detection
test/integration-side-effect-iterables
ci/python-matrix
docs/readme-quickstart
chore/bootstrap-uv-project
```

- Une branche = un sujet. Rebaser régulièrement : `git fetch origin && git rebase origin/main`.
- Supprimer la branche après merge.

### Commits — Conventional Commits 1.0

```text
<type>(<scope>): <résumé impératif, minuscules, sans point, ≤ 72 caractères>

<corps optionnel : POURQUOI ce changement, contexte, alternatives écartées.
Lignes ≤ 72 caractères.>

<footer optionnel : Refs: F2 | Closes #12 | BREAKING CHANGE: ...>
```

- **Types :** `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`, `style`,
  `revert`.
- **Scopes :** `plugin`, `interceptor`, `extractor`, `validator`, `reporter`, `recorder`, `fixer`,
  `models`, `config`, `deps`, `ci`, `release`.

Exemples :

```text
feat(interceptor): wrap _patch.__enter__ to capture original target
fix(validator): validate scalar return values in strict mode
test(validator): cover zombie keys on nested TypedDict
refactor(extractor): extract self/cls stripping into dedicated helper
perf(extractor): cache TypeAdapter per target with weak references
build(deps): add pydantic>=2.7 as runtime dependency
```

Règles :

- **Atomique :** un commit = un changement logique cohérent. Chaque commit passe la vérification
  complète (historique *bisectable*).
- Ne jamais mélanger refactor, formatage et changement de comportement dans le même commit.
- Le code et ses tests vont **dans le même commit**.
- Interdits : `wip`, `fix`, `update`, `misc`, `changes`, messages vagues ou en français.
- Avant d'ouvrir une PR : nettoyer l'historique de **sa propre branche** (`git rebase -i`,
  `git commit --fixup` + `--autosquash`).

### Pull Requests

- Titre = message Conventional Commit (il devient le commit sur `main`).
- Description : **Quoi / Pourquoi / Comment / Comment tester / Risques**, F-ID référencée.
- Merge uniquement si CI verte (lint, types, tests matrice, couverture). Stratégie : **squash merge**.

### Releases

- **SemVer** (`0.y.z` tant que l'API n'est pas stable). Tags annotés `vX.Y.Z` sur `main`.
- `CHANGELOG.md` au format *Keep a Changelog*, alimenté depuis les commits.

### Interdits absolus

- `git push` sur `main`, `git push --force` (seul `--force-with-lease` sur sa propre branche, après
  accord), `--no-verify`, réécriture d'un historique partagé.
- `git add -A` / `git add .` à l'aveugle : ajouter des chemins explicites et relire
  `git diff --staged` avant chaque commit.
- Commiter des secrets, `.env`, caches (`.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`),
  ou des fichiers sans rapport avec la tâche.
- Toute commande destructive (`reset --hard`, `clean -fd`, `branch -D`) sans accord explicite.

---

## 9. Stratégie de tests

- **Unitaires (`tests/unit/`)** : `extractor`, `validator`, `models` testés en isolation, sans
  charger le plugin.
- **Intégration (`tests/integration/`)** : plugin de bout en bout via la fixture officielle
  **`pytester`** (fichiers de test générés, assertions sur la sortie et le code de retour).
- **Chaque détection a son test négatif** : un test prouvant l'absence de faux positif sur un mock
  correct équivalent.
- Couvrir systématiquement : fonction, méthode d'instance, `classmethod`, `staticmethod`, `async def`,
  `BaseModel`, `dataclass`, `TypedDict`, `Union`/`Optional`, génériques, `side_effect` (itérable,
  callable, exception), `ForwardRef`, `TYPE_CHECKING`, builtins C sans signature.
- Noms explicites : `test_<comportement>_when_<condition>` (ex.
  `test_reports_zombie_key_when_dict_has_removed_field`).
- Tests déterministes, sans réseau, sans dépendance à l'ordre. Paramétrer (`pytest.mark.parametrize`)
  plutôt que dupliquer.
- Couverture ≥ 90 % lignes + branches sur `src/mockrot`. Pas de test écrit uniquement pour la
  couverture.
- Benchmark de l'overhead sur une suite synthétique de 500 tests avant chaque release.

---

## 10. Commandes

```bash
uv sync                                   # installer l'environnement
uv run ruff format .                      # formater
uv run ruff check .                       # linter (ajouter --fix si pertinent)
uv run pyright                            # typage strict
uv run pytest                             # tests
uv run pytest --cov=mockrot --cov-branch  # tests + couverture
```

**Vérification complète (obligatoire avant chaque commit) :**

```bash
uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest
```

---

## 11. Definition of Done

Une tâche est terminée **uniquement si** :

- [ ] L'exigence (F-ID) est satisfaite, cas limites inclus.
- [ ] Tests ajoutés : cas positif **et** test négatif (pas de faux positif).
- [ ] `ruff format`, `ruff check`, `pyright --strict`, `pytest` : tous au vert.
- [ ] Couverture ≥ 90 % maintenue.
- [ ] Les invariants de la §4 sont respectés (fail-safe, transparence, perf).
- [ ] Docstrings / README / CHANGELOG mis à jour si le comportement visible change.
- [ ] Nouveau piège technique documenté en §5 le cas échéant.
- [ ] Commits atomiques, Conventional Commits, branche propre et rebasée sur `main`.

---

## 12. Décisions tranchées et actées

- **CLI autonome** : module léger `cli.py` (point d'entrée console `mockrot = "mockrot.cli:main"` dans `pyproject.toml`) qui délègue à `pytest` avec `--mockrot` activé, garantissant le fonctionnement sans friction de `uvx mockrot`.
- **Budget de performance** : overhead du moteur de validation pur ciblé à **< 15 ms** sur 500 tests ; seuil d'alerte global de la suite de tests (incluant le rapport terminal Rich) fixé à **< 50 ms**.
- **Mode `accessed-only`** : planifié pour la V1.1 (`--mockrot-mode=accessed-only`) pour éliminer le bruit sur les vieilles bases de code sans compliquer le MVP V1.
- **LibCST** : confirmé en extra optionnel `pytest-mockrot[fix]` pour garder le package principal ultraléger.
- **Licence** : licence **MIT**.
