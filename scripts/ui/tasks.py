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
from datetime import date, datetime, timezone
from pathlib import Path

from ui import projects

DEFAULT_TYPE = "tache"
TASK_ARGV_FIELDS = ["titre", "qui", "quand", "statut"]  # ordre d'affichage pour type=="tache"


def load_current(project_id):
    _ensure_archive_store(project_id)
    return _read_nodes(projects.open_tasks_and_upcoming_events_path(project_id))


def save_current(project_id, nodes):
    _ensure_archive_store(project_id)
    _write_nodes(projects.open_tasks_and_upcoming_events_path(project_id), nodes)


def load_completed(project_id):
    _ensure_archive_store(project_id)
    return _read_nodes(projects.completed_tasks_and_past_events_path(project_id))


def save_completed(project_id, nodes):
    _ensure_archive_store(project_id)
    _write_nodes(projects.completed_tasks_and_past_events_path(project_id), nodes)


def _read_nodes(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        nodes = json.load(f)
    return nodes if isinstance(nodes, dict) else {}


def _write_nodes(path, nodes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(nodes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _is_completed_or_past(node):
    argv = node.get("argv", {})
    if node.get("type", DEFAULT_TYPE) == "evenement":
        event_date = argv.get("date")
        try:
            return bool(event_date) and date.fromisoformat(event_date) < date.today()
        except (TypeError, ValueError):
            return False
    return bool(node.get("completed")) or argv.get("statut") in {"termine", "fait"}


def _normalize_task_completion(node, completed=None):
    if node.get("type", DEFAULT_TYPE) != "tache":
        return
    argv = node.setdefault("argv", {})
    status = argv.get("statut")
    if completed is not None:
        is_completed = bool(completed)
    else:
        is_completed = bool(node.get("completed")) or status in {"termine", "fait"}
    node["completed"] = is_completed
    if is_completed:
        argv["statut"] = "termine"
    elif status in {"termine", "fait"}:
        argv["statut"] = "a_faire"


def _ensure_archive_store(project_id):
    """One-time, non-destructive import from the older project task files."""
    marker = projects.project_dir(project_id) / "task_archive_migrated.json"
    open_path = projects.open_tasks_and_upcoming_events_path(project_id)
    completed_path = projects.completed_tasks_and_past_events_path(project_id)
    open_nodes = _read_nodes(open_path)
    completed_nodes = _read_nodes(completed_path)
    migrated_now = not marker.exists()
    if migrated_now:
        legacy_nodes = _read_nodes(projects.current_tasks_path(project_id))
        renamed = {name: f"legacy::{name}" for name in legacy_nodes}
        for name, old_node in legacy_nodes.items():
            node = json.loads(json.dumps(old_node, ensure_ascii=False))
            parent = node.get("parent")
            if parent in renamed:
                node["parent"] = renamed[parent]
            _normalize_task_completion(node)
            destination = completed_nodes if _is_completed_or_past(node) else open_nodes
            target_name = renamed[name]
            while target_name in open_nodes or target_name in completed_nodes:
                target_name = f"legacy::{target_name}"
            destination[target_name] = node

    changed = False
    for node in completed_nodes.values():
        if node.get("type", DEFAULT_TYPE) == "tache":
            was_completed = node.get("completed")
            old_status = node.get("argv", {}).get("statut")
            _normalize_task_completion(node, completed=True)
            if was_completed is not True or old_status != node.get("argv", {}).get("statut"):
                changed = True
    for name, node in list(open_nodes.items()):
        _normalize_task_completion(node)
        if _is_completed_or_past(node):
            completed_nodes[name] = node
            del open_nodes[name]
            changed = True
    if migrated_now or changed or not open_path.exists():
        _write_nodes(open_path, open_nodes)
    if migrated_now or changed or not completed_path.exists():
        _write_nodes(completed_path, completed_nodes)
    if migrated_now:
        marker.write_text(
            json.dumps({"completed_at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )


def load_archived(project_id):
    p = projects.archived_tasks_path(project_id)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save_node_pair(project_id, open_nodes, completed_nodes):
    _write_nodes(projects.open_tasks_and_upcoming_events_path(project_id), open_nodes)
    _write_nodes(projects.completed_tasks_and_past_events_path(project_id), completed_nodes)


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
    _normalize_task_completion(node, completed=completed)

    completed_nodes = load_completed(project_id)
    if _is_completed_or_past(node):
        nodes.pop(name, None)
        completed_nodes[name] = node
    else:
        completed_nodes.pop(name, None)
        nodes[name] = node
    _save_node_pair(project_id, nodes, completed_nodes)
    return nodes


def next_free_name(nodes, prefix="tache"):
    n = 1
    while f"{prefix}-{n}" in nodes:
        n += 1
    return f"{prefix}-{n}"


def create_node(project_id, node_type=DEFAULT_TYPE, parent=None, argv=None, reason="création manuelle"):
    nodes = load_current(project_id)
    archive_snapshot(project_id, nodes, reason=reason)
    completed_nodes = load_completed(project_id)
    name = next_free_name({**completed_nodes, **nodes}, prefix=node_type)
    node_argv = argv or {"titre": "Nouveau"}
    if node_type == "tache":
        node_argv.setdefault("statut", "a_faire")
    node = {
        "type": node_type,
        "parent": parent,
        "completed": False,
        "argv": node_argv,
    }
    _normalize_task_completion(node)
    if _is_completed_or_past(node):
        completed_nodes[name] = node
        save_completed(project_id, completed_nodes)
    else:
        nodes[name] = node
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
