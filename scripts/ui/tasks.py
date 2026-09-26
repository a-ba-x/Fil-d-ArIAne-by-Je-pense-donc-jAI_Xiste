"""
Nœuds génériques (tâches, évènements, tout sous-type futur) stockés à plat
dans current_tasks.json, par projet.

Schéma (accepté depuis le tableau de brainstorming) :

{
  "<nom>": {
      "type": "tache" | "evenement" | ...,   # champ commun
      "parent": "<nom_parent>" | null,        # champ commun -- reconstruit l'arbre
      "completed": true | false,              # champ commun
      "argv": { ... spécifique au type ... }  # ex. tache: titre/qui/quand/statut
  },
  ...
}

Hypothèse (à confirmer avec l'équipe) : "titre" n'étant pas listé comme champ
commun, il est rangé dans argv comme les autres champs spécifiques -- donc
CHAQUE type doit avoir un "titre" dans son argv pour être affichable dans
l'arborescence, sinon l'UI retombe sur le nom de la clé.

L'arbre est reconstruit à partir des pointeurs "parent" (pas de nesting en
dur) : un nœud est racine si parent est null OU si parent pointe vers un nom
qui n'existe pas dans le fichier (pointeur cassé -- traité comme racine avec
un avertissement plutôt que de faire planter le rendu).
"""

import json
import copy
from datetime import datetime, timezone

from ui import projects

DEFAULT_TYPE = "tache"
TASK_ARGV_FIELDS = ["titre", "qui", "quand", "statut"]  # ordre d'affichage pour type=="tache"


def load_current(project_id):
    p = projects.current_tasks_path(project_id)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_current(project_id, nodes):
    with open(projects.current_tasks_path(project_id), "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)


def load_archived(project_id):
    p = projects.archived_tasks_path(project_id)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def archive_snapshot(project_id, nodes, reason="modification"):
    archive = load_archived(project_id)
    archive.append({
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "snapshot": copy.deepcopy(nodes),
    })
    with open(projects.archived_tasks_path(project_id), "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def _children_map(nodes):
    children = {name: [] for name in nodes}
    roots = []
    for name, node in nodes.items():
        parent = node.get("parent")
        if parent is None or parent not in nodes:
            roots.append(name)
        else:
            children[parent].append(name)
    return children, roots


def iter_tree(nodes):
    """Parcourt les nœuds en profondeur depuis les racines. Yield (nom, node, depth)."""
    children, roots = _children_map(nodes)

    def _walk(names, depth):
        for name in sorted(names):
            yield name, nodes[name], depth
            yield from _walk(children.get(name, []), depth + 1)

    yield from _walk(roots, 0)


def get_title(node):
    return node.get("argv", {}).get("titre") or "(sans titre)"


def missing_fields_warnings(node):
    warnings = []
    argv = node.get("argv", {})
    if not argv.get("titre"):
        warnings.append("titre manquant")
    if node.get("type", DEFAULT_TYPE) == "tache":
        if not argv.get("qui"):
            warnings.append("qui : non assigné")
        if not argv.get("quand"):
            warnings.append("quand : pas de deadline")
    return warnings


def update_node(project_id, name, argv_updates=None, completed=None, node_type=None, reason=None):
    nodes = load_current(project_id)
    if name not in nodes:
        raise ValueError(f"Nœud introuvable : {name}")
    archive_snapshot(project_id, nodes, reason=reason or f"edit:{name}")

    node = nodes[name]
    if argv_updates:
        node.setdefault("argv", {}).update(argv_updates)
    if completed is not None:
        node["completed"] = completed
    if node_type is not None:
        node["type"] = node_type

    save_current(project_id, nodes)
    return nodes


def next_free_name(nodes, prefix="tache"):
    n = 1
    while f"{prefix}-{n}" in nodes:
        n += 1
    return f"{prefix}-{n}"


def create_node(project_id, node_type=DEFAULT_TYPE, parent=None, argv=None, reason="création manuelle"):
    nodes = load_current(project_id)
    archive_snapshot(project_id, nodes, reason=reason)
    name = next_free_name(nodes, prefix=node_type)
    nodes[name] = {
        "type": node_type,
        "parent": parent,
        "completed": False,
        "argv": argv or {"titre": "Nouveau"},
    }
    save_current(project_id, nodes)
    return name, nodes


def extract_date(node):
    """
    Cherche une date exploitable dans argv, quel que soit le type de nœud --
    accepte les clés 'quand' (tâches) ou 'date' (évènements et autres types).
    Retourne None si aucune des deux n'est présente.
    """
    argv = node.get("argv", {})
    return argv.get("quand") or argv.get("date")
