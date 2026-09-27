"""
Un "projet" = une réunion ou un ensemble de réunions suivies dans le temps.

Structure sur disque (locale ou clone d'un repo GitHub -- le dossier racine
`projects/` est le même dans les deux cas, seul son emplacement change via
la config de storage) :

data/projects/<project_id>/
    current_tasks.json    # état actif des tâches/évènements (schéma plat, voir tasks.py)
    archived_tasks.json   # historique (append-only)
    transcript.html        # transcript HTML généré par le module transcription
    resume.html            # résumé thématique HTML généré par le module clean/extraction
    session_state.json     # statut de l'enregistrement en cours (running/paused/stopped)
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

APP_ROOT = Path(__file__).resolve().parents[2]
LOCAL_PROJECTS_ROOT = APP_ROOT / "files" / "projects"


def projects_root():
    """Resolve the project directory from the UI storage configuration."""
    from ui import storage

    config = storage.load_config()
    if config.get("storage_mode") == "github":
        repo_path = config.get("github_repo_path", "").strip()
        if repo_path:
            return Path(repo_path).expanduser() / "data" / "projects"
    return LOCAL_PROJECTS_ROOT

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def slugify(name):
    return _SLUG_RE.sub("-", name.strip()).strip("-").lower() or "projet"


def list_projects():
    """Liste les ids de projets existants (= noms de sous-dossiers)."""
    root = projects_root()
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def project_dir(project_id):
    d = projects_root() / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_project(name):
    """Crée un nouveau projet et retourne son id (slug)."""
    project_id = slugify(name)
    d = project_dir(project_id)
    # squelettes vides pour que le reste du code n'ait jamais à tester l'existence
    current_tasks_path(project_id).write_text("{}", encoding="utf-8")
    archived_tasks_path(project_id).write_text("[]", encoding="utf-8")
    save_session_state(project_id, {"status": "stopped", "updated_at": _now()})
    return project_id


def current_tasks_path(project_id):
    return project_dir(project_id) / "current_tasks.json"


def archived_tasks_path(project_id):
    return project_dir(project_id) / "archived_tasks.json"


def transcript_html_path(project_id):
    return project_dir(project_id) / "transcript.html"


def resume_html_path(project_id):
    return project_dir(project_id) / "resume.html"


def session_state_path(project_id):
    return project_dir(project_id) / "session_state.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_session_state(project_id):
    p = session_state_path(project_id)
    if not p.exists():
        return {"status": "stopped", "updated_at": None}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_session_state(project_id, state):
    with open(session_state_path(project_id), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def set_session_status(project_id, status):
    """status attendu : 'running' | 'paused' | 'stopped'."""
    state = {"status": status, "updated_at": _now()}
    save_session_state(project_id, state)
    return state
