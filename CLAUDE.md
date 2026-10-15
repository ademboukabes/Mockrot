# CLAUDE.md — Mockrot

@AGENTS.md

> Toutes les règles du projet (contexte, architecture, invariants, standards, Git) sont dans
> [`AGENTS.md`](./AGENTS.md), importé ci-dessus. **Ne pas les dupliquer ici.** Ce fichier ne contient
> que les consignes propres à **Claude Code**.

---

## Au démarrage de chaque tâche

1. `git status`, `git branch --show-current`, `git log --oneline -10` : connaître l'état du dépôt.
2. Si on est sur `main` → créer une branche selon la convention (`AGENTS.md` §8) **avant** toute
   modification.
3. Relire l'exigence concernée (F-ID) dans `cahierdecharge.md` et les sections pertinentes de
   `AGENTS.md` (§4 invariants, §5 pièges).
4. Lire le code existant impacté avant de proposer quoi que ce soit.

## Planification

- **Plan mode obligatoire** si la tâche touche plus d'un module, l'API publique, `pyproject.toml`,
  la CI, ou ajoute une dépendance. Présenter : objectif, fichiers impactés, approche, tests prévus,
  risques. **Attendre la validation** avant d'écrire du code.
- Suivre l'avancement avec la todo list ; une étape = un résultat vérifiable.
- Pour une exploration large du code ou de la doc d'une lib (`unittest.mock`, `pydantic`,
  `pytest`), déléguer à un sous-agent pour préserver le contexte principal.

## Boucle d'implémentation

- Test rouge → implémentation minimale → refactor (`AGENTS.md` §6).
- Après chaque modification : lancer **les tests ciblés** (`uv run pytest tests/unit/test_x.py -q`).
- Avant chaque commit : lancer la **vérification complète** (`AGENTS.md` §10) et lire la sortie.
- Si une vérification échoue : corriger la cause, jamais contourner (pas de `skip`, pas de
  `type: ignore`, pas d'assouplissement de config sans accord).
- Après deux tentatives infructueuses sur le même problème : s'arrêter, exposer l'analyse et les
  options à l'utilisateur.

## Git — ce que Claude peut faire seul

| Autorisé sans demander | Nécessite un accord explicite |
| :--- | :--- |
| Créer une branche depuis `main` à jour | `git push` (toute branche) |
| `git add <chemins explicites>` | Ouvrir / merger une PR |
| Commit atomique Conventional Commit | `rebase -i` d'une branche déjà poussée |
| `git commit --fixup` sur sa branche locale | `--force-with-lease` |
| `git fetch`, `git rebase origin/main` (local) | `reset --hard`, `clean`, `branch -D`, tag de release |

Avant chaque commit : montrer `git diff --staged --stat`, vérifier qu'aucun fichier hors périmètre
n'est inclus, puis commiter avec un message conforme (anglais, impératif, ≤ 72 caractères, corps
expliquant le *pourquoi*).

## Fichiers protégés

Ne pas modifier sans demande explicite : `cahierdecharge.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`,
`.github/workflows/*`, la configuration `[tool.ruff]` / `[tool.pyright]` de `pyproject.toml`.
Exception : ajouter un nouveau piège découvert dans `AGENTS.md` §5 (en le signalant).

## Communication avec l'utilisateur

- Répondre en **français**, de manière concise et technique.
- En fin de tâche, toujours fournir :
  - **Fait :** ce qui a changé (fichiers, commits).
  - **Pourquoi :** décisions et compromis.
  - **Vérifié :** commandes exécutées et résultats réels.
  - **Reste à faire / risques :** limites connues, points non vérifiés, questions ouvertes.
- Ne jamais affirmer qu'un test passe sans l'avoir exécuté dans la session.
- Signaler proactivement toute incohérence repérée dans le cahier des charges plutôt que de la
  « corriger » silencieusement.

## Hygiène du contexte

- Une session = une tâche cohérente. `/clear` entre deux tâches sans rapport.
- Ne pas relire inutilement de gros fichiers déjà en contexte ; cibler les plages de lignes.
