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

def all_transcript_paths(project_id):
    dir = projects.project_dir(project_id)
    if not dir or not os.path.isdir(dir):
        return []
    files = []
    for fn in os.listdir(dir):
        if fn.lower().startswith("transcript") and (fn.endswith(".txt") or fn.endswith(".html")):
            files.append(Path(dir)/fn)
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
