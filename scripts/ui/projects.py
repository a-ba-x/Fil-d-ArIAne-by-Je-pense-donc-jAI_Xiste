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
import uuid
from pathlib import Path
from datetime import datetime, timezone

APP_ROOT = Path(__file__).resolve().parents[2]
LOCAL_PROJECTS_ROOT = APP_ROOT / "projects"


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
    """Create a project and return its id (slug)."""
    project_id = slugify(name)
    d = projects_root() / project_id

    # Do not reset an existing project's data if its name is reused.
    if d.exists():
        raise FileExistsError(f"Le projet existe déjà : {project_id}")

    d.mkdir(parents=True)

    leaf_dirs = [
        "files/audio",
        "files/backup",
        "files/extracted_data",
        "files/raw_text_chunks",
        "files/reference",
        "files/tests",
        "archive/calendar",
        "archive/meeting_reports",
        "archive/tasks_and_events",
    ]
    for relative_dir in leaf_dirs:
        folder = d / relative_dir
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".gitkeep").touch()

    (d / "current_tasks.json").write_text("{}", encoding="utf-8")
    (d / "archived_tasks.json").write_text("[]", encoding="utf-8")
    (d / "archive/tasks_and_events/completed_tasks_and_past_events.json").write_text(
        "{}", encoding="utf-8"
    )
    (d / "archive/tasks_and_events/open_tasks_and_upcoming_events.json").write_text(
        "{}", encoding="utf-8"
    )
    (d / "archive/calendar/latest.ical").write_text(
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//RiseOfAgentsX//MeetingAgent//FR\r\n"
        "END:VCALENDAR\r\n",
        encoding="utf-8",
    )

    save_session_state(
        project_id,
        {"status": "stopped", "updated_at": _now()},
    )
    save_meeting_state(
        project_id,
        {
            "meeting_id": None,
            "started_at": None,
            "finalized": True,
            "finalized_at": None,
        },
    )
    (d / "transcription_control.json").write_text(
        '{"going": false}\n',
        encoding="utf-8",
    )

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


def meeting_state_path(project_id):
    """Path to the state record for the project's current meeting."""
    return project_dir(project_id) / "current_meeting.json"


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


def load_meeting_state(project_id):
    """Load current-meeting state; return None for projects without a record."""
    path = meeting_state_path(project_id)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_meeting_state(project_id, state):
    """Persist current-meeting state without changing meeting files."""
    with meeting_state_path(project_id).open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def start_meeting(project_id):
    """Create and persist a fresh meeting record, returning its state."""
    state = {
        "meeting_id": uuid.uuid4().hex,
        "started_at": _now(),
        "finalized": False,
        "finalized_at": None,
    }
    save_meeting_state(project_id, state)
    return state


def mark_meeting_finalized(project_id):
    """Mark the current meeting finalized; return None if no meeting exists."""
    state = load_meeting_state(project_id)
    if state is None or state.get("meeting_id") is None:
        return None
    if not state.get("finalized"):
        state["finalized"] = True
        state["finalized_at"] = _now()
        save_meeting_state(project_id, state)
    return state
