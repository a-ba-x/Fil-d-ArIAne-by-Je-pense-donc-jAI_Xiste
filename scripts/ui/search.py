"""
Recherche à travers plusieurs projets à la fois -- l'utilisateur choisit
lesquels inclure (voir ui_components.render_project_multiselect), tout est
rechargé depuis le disque à chaque recherche (pas de cache : les fichiers
peuvent être modifiés par d'autres processus -- transcription en cours,
sync GitHub, etc.).
"""

from ui import projects, tasks
from ui.transcript_parser import extract_segments
import os
from pathlib import Path
from datetime import datetime


CURRENT_MEETING_KEY = "__current__"
_CLEAN_TRANSCRIPT_SUFFIX = "_whole_clean_text.txt"


def meeting_label(meeting_key):
    stamp = meeting_key.split("_", 1)[0]
    try:
        started = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        return started.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return meeting_key


def list_transcript_meetings(project_id):
    """Return the current meeting and archived meetings with cleaned text."""
    entries = []
    state = projects.load_meeting_state(project_id)
    current_path = projects.project_dir(project_id) / "files" / "extracted_data" / "whole_clean_text.txt"
    if state and state.get("meeting_id") and not state.get("finalized", False):
        entries.append({
            "key": CURRENT_MEETING_KEY,
            "label": f"En cours — {meeting_label(projects.meeting_archive_key(state))}",
            "path": current_path,
            "current": True,
        })
    elif current_path.is_file():
        entries.append({
            "key": CURRENT_MEETING_KEY,
            "label": "Réunion actuelle",
            "path": current_path,
            "current": True,
        })

    transcript_dir = projects.archived_cleaned_transcripts_dir(project_id)
    if transcript_dir.exists():
        archived = []
        for path in transcript_dir.glob(f"*{_CLEAN_TRANSCRIPT_SUFFIX}"):
            meeting_key = path.name[:-len(_CLEAN_TRANSCRIPT_SUFFIX)]
            archived.append({
                "key": meeting_key,
                "label": meeting_label(meeting_key),
                "path": path,
                "current": False,
            })
        entries.extend(sorted(archived, key=lambda item: item["key"], reverse=True))
    return entries


def read_transcript_meeting(project_id, meeting_key):
    """Read the selected current or archived cleaned transcript."""
    entries = {item["key"]: item for item in list_transcript_meetings(project_id)}
    entry = entries.get(meeting_key)
    if entry is None:
        raise FileNotFoundError(f"Meeting transcript not found: {meeting_key}")
    return entry["path"].read_text(encoding="utf-8"), entry

def all_transcript_paths(project_id):
    project_path = projects.project_dir(project_id)
    if not project_path or not os.path.isdir(project_path):
        return []
    files = []
    for fn in os.listdir(project_path):
        if fn.lower().startswith("transcript") and (fn.endswith(".txt") or fn.endswith(".html")):
            files.append(Path(project_path)/fn)
    current_cleaned = project_path / "files" / "extracted_data" / "whole_clean_text.txt"
    if current_cleaned.is_file():
        files.append(current_cleaned)
    archived_dir = projects.archived_cleaned_transcripts_dir(project_id)
    if archived_dir.is_dir():
        files.extend(archived_dir.glob(f"*{_CLEAN_TRANSCRIPT_SUFFIX}"))
    return sorted(files)


def search_transcript_in_project(project_id, query, speaker_filter=None):
    segments = []
    for fpath in all_transcript_paths(project_id):
        html = fpath.read_text(encoding="utf-8")
        segments.extend(extract_segments(html))
    query = (query or "").strip().lower()
    hits = []
    for seg in segments:
        if speaker_filter and seg.get("speaker") != speaker_filter:
            continue
        if query and query not in seg.get("text", "").lower():
            continue
        hits.append(seg)
    return hits


def search_tasks_in_project(project_id, query, speaker_filter=None):
    nodes = tasks.load_current(project_id)
    query = (query or "").strip().lower()
    hits = []
    for name, node, depth in tasks.iter_tree(nodes):
        argv = node.get("argv", {})
        if speaker_filter and argv.get("qui") != speaker_filter:
            continue
        haystack = f"{argv.get('titre', '')} {node.get('type', '')}".lower()
        if query and query not in haystack:
            continue
        hits.append((name, node, depth))
    return hits


def search_across_projects(project_ids, query, speaker_filter=None):
    """Retourne {project_id: {"transcript_hits": [...], "task_hits": [...]}}."""
    results = {}
    for pid in project_ids:
        results[pid] = {
            "transcript_hits": search_transcript_in_project(pid, query, speaker_filter),
            "task_hits": search_tasks_in_project(pid, query, speaker_filter),
        }
    return results


def list_known_speakers(project_ids):
    """Union des speakers vus dans tous les transcripts + argv['qui'] des tâches, sur les projets choisis."""
    speakers = set()
    for pid in project_ids:
        for fpath in all_transcript_paths(pid):
            try:
                content = fpath.read_text(encoding="utf-8")
                for seg in extract_segments(content):
                    if seg.get("speaker"):
                        speakers.add(seg["speaker"])
            except Exception:
                continue
        nodes = tasks.load_current(pid)
        for name, node, depth in tasks.iter_tree(nodes):
            qui = node.get("argv", {}).get("qui")
            if qui:
                speakers.add(qui)
    return sorted(speakers)
