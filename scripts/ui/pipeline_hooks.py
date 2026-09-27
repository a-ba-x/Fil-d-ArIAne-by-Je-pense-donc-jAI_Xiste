"""Connect UI actions to transcription and extraction entry points."""

import json
from datetime import date
import subprocess
import sys
import threading
from pathlib import Path

from ui import calendar_export, projects, storage

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
APP_ROOT = SCRIPTS_DIR.parent
TRANSCRIPTION_SCRIPT = SCRIPTS_DIR / "loop.py"
EXTRACTION_DIR = SCRIPTS_DIR / "extraction"
_TRANSCRIPTION_PROCESSES = {}
_TRANSCRIPTION_LOGS = {}


def _control_file(project_id):
    return projects.project_dir(project_id) / "transcription_control.json"


def _set_going(project_id, going):
    path = _control_file(project_id)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps({"going": going}, indent=2), encoding="utf-8")
    temporary_path.replace(path)
    return path


def _launch_transcription(project_id, control_file):
    if not TRANSCRIPTION_SCRIPT.exists():
        return None, f"Script de transcription introuvable : {TRANSCRIPTION_SCRIPT}"

    log_path = APP_ROOT / "data" / "logs" / f"transcription_{project_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        log_file = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            [
                sys.executable,
                str(TRANSCRIPTION_SCRIPT),
                "--project-dir",
                str(projects.project_dir(project_id)),
                "--control-file",
                str(control_file),
            ],
            cwd=SCRIPTS_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        return None, f"Impossible de démarrer la transcription : {exc}"
    finally:
        if "log_file" in locals():
            log_file.close()

    _TRANSCRIPTION_PROCESSES[project_id] = process
    _TRANSCRIPTION_LOGS[project_id] = log_path
    return process, ""


def start_recording(project_id):
    """Finalize any previous meeting, then start a fresh recording session."""
    if projects.load_session_state(project_id).get("status") == "running":
        return False, "Une transcription est déjà en cours pour ce projet."

    meeting_state = projects.load_meeting_state(project_id)
    has_workspace_data = _meeting_workspace_has_data(project_id)
    recovery_message = ""
    if meeting_state is None or meeting_state.get("meeting_id") is None:
        if has_workspace_data:
            _stop_transcription_process(project_id)
            projects.start_meeting(project_id)
            ok, message = finalize_meeting(project_id)
            if not ok:
                return False, (
                    "Les fichiers de l'ancienne réunion ont été conservés, "
                    "mais sa finalisation a échoué :\n"
                    f"{message}\nCorrigez le problème puis cliquez de nouveau sur Démarrer pour réessayer."
                )
            recovery_message = "Ancienne réunion récupérée et archivée. "
    elif not meeting_state.get("finalized", False):
        _stop_transcription_process(project_id)
        ok, message = finalize_meeting(project_id)
        if not ok:
            return False, f"La réunion précédente n'a pas pu être finalisée :\n{message}"
    elif has_workspace_data:
        try:
            _clear_meeting_workspace(project_id)
        except OSError as exc:
            return False, f"Impossible de nettoyer les fichiers précédents : {exc}"

    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    control_file = _set_going(project_id, True)
    if process is not None and process.poll() is None:
        _set_going(project_id, False)
        return False, "Un ancien processus est encore actif ; utilisez Reprendre ou Terminer."
    process, error = _launch_transcription(project_id, control_file)
    if process is None:
        _set_going(project_id, False)
        return False, error
    projects.start_meeting(project_id)
    projects.set_session_status(project_id, "running")
    _watch_in_background(project_id, process)
    return True, f"{recovery_message}Nouvelle réunion démarrée. Utilisez Pause pour la suspendre."


def pause_recording(project_id):
    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    if process is None or process.poll() is not None:
        return False, "Aucun processus de transcription actif à mettre en pause."
    _set_going(project_id, False)
    projects.set_session_status(project_id, "paused")
    return True, "Transcription en pause. Reprendre relancera la capture."


def resume_recording(project_id):
    meeting_state = projects.load_meeting_state(project_id)
    if (
        meeting_state is None
        or meeting_state.get("meeting_id") is None
        or meeting_state.get("finalized", False)
    ):
        return False, "Aucune réunion en pause à reprendre. Utilisez Démarrer pour en créer une."
    if projects.load_session_state(project_id).get("status") != "paused":
        return False, "Le projet n'est pas en pause."

    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    control_file = _set_going(project_id, True)
    if process is None or process.poll() is not None:
        process, error = _launch_transcription(project_id, control_file)
        if process is None:
            _set_going(project_id, False)
            return False, error
    projects.set_session_status(project_id, "running")
    _watch_in_background(project_id, process)
    return True, "Transcription reprise."


def _stop_transcription_process(project_id):
    _set_going(project_id, False)
    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    if process is None or process.poll() is not None:
        projects.set_session_status(project_id, "stopped")
        return True, "Processus déjà arrêté."
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    projects.set_session_status(project_id, "stopped")
    return True, "Processus de transcription arrêté."


def stop_recording(project_id):
    """The Terminer action stops recording and finalizes the current meeting."""
    stopped, stop_message = _stop_transcription_process(project_id)
    if not stopped:
        return False, stop_message
    finalized, final_message = finalize_meeting(project_id)
    if not finalized:
        details = _transcription_log_tail(project_id)
        suffix = f"\nDernier journal :\n{details}" if details else ""
        return False, f"{stop_message}\nFinalisation échouée :\n{final_message}{suffix}"
    return True, f"{stop_message}\n{final_message}"


def _transcription_log_tail(project_id, max_chars=3000):
    path = _TRANSCRIPTION_LOGS.get(project_id)
    if path is None or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-max_chars:].strip()
    except OSError:
        return ""


def _watch_in_background(project_id, process):
    def watch():
        process.wait()
        if _TRANSCRIPTION_PROCESSES.get(project_id) is not process:
            return
        status = projects.load_session_state(project_id).get("status")
        if status in {"running", "paused"}:
            projects.set_session_status(project_id, "stopped")

    threading.Thread(target=watch, daemon=True).start()


def _run_command(args):
    return subprocess.run(
        args,
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _project_files_dir(project_id):
    return projects.project_dir(project_id) / "files"


def _meeting_workspace_has_data(project_id):
    files_dir = _project_files_dir(project_id)
    return files_dir.exists() and any(
        path.is_file() and path.name != ".gitkeep" for path in files_dir.rglob("*")
    )


def _clear_meeting_workspace(project_id):
    files_dir = _project_files_dir(project_id)
    if not files_dir.exists():
        return
    for path in files_dir.rglob("*"):
        if path.is_file() and path.name != ".gitkeep":
            path.unlink()


def _atomic_write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _load_archive_json(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"Le fichier d'archive doit contenir un objet JSON : {path}")
    return value


def _meeting_item_is_completed_or_past(node, today):
    if node.get("type") == "evenement":
        event_date = node.get("argv", {}).get("date")
        try:
            return bool(event_date) and date.fromisoformat(event_date) < today
        except (TypeError, ValueError):
            return False
    return bool(node.get("completed")) or node.get("argv", {}).get("statut") == "termine"


def _archive_meeting_outputs(project_id, meeting_state, report_path, data_path):
    meeting_id = meeting_state["meeting_id"]
    project_path = projects.project_dir(project_id)
    archive_root = project_path / "archive"
    task_event_dir = archive_root / "tasks_and_events"
    completed_path = task_event_dir / "completed_tasks_and_past_events.json"
    open_path = task_event_dir / "open_tasks_and_upcoming_events.json"
    report_archive_path = archive_root / "meeting_reports" / f"{meeting_id}.html"
    calendar_path = archive_root / "calendar" / "latest.ical"

    report = report_path.read_text(encoding="utf-8")
    if not report.strip():
        raise ValueError("meeting_report.html est vide.")
    with data_path.open(encoding="utf-8") as f:
        meeting_items = json.load(f)
    if not isinstance(meeting_items, dict):
        raise ValueError("meeting_data.json doit contenir un objet JSON.")

    completed = _load_archive_json(completed_path)
    upcoming = _load_archive_json(open_path)
    prefix = f"{meeting_id}::"
    completed = {key: value for key, value in completed.items() if not key.startswith(prefix)}
    upcoming = {key: value for key, value in upcoming.items() if not key.startswith(prefix)}
    meeting_keys = {key: f"{prefix}{key}" for key in meeting_items}
    today = date.today()

    for key, node in meeting_items.items():
        if not isinstance(key, str) or not isinstance(node, dict):
            raise ValueError("Chaque élément de meeting_data.json doit être un objet nommé.")
        archived_node = json.loads(json.dumps(node, ensure_ascii=False))
        if archived_node.get("type") == "tache":
            argv = archived_node.setdefault("argv", {})
            is_completed = bool(archived_node.get("completed")) or argv.get("statut") == "termine"
            archived_node["completed"] = is_completed
            if is_completed:
                argv["statut"] = "termine"
        parent = archived_node.get("parent")
        if parent in meeting_keys:
            archived_node["parent"] = meeting_keys[parent]
        destination = completed if _meeting_item_is_completed_or_past(archived_node, today) else upcoming
        destination[meeting_keys[key]] = archived_node

    _atomic_write_text(report_archive_path, report)
    _atomic_write_text(completed_path, json.dumps(completed, ensure_ascii=False, indent=2) + "\n")
    _atomic_write_text(open_path, json.dumps(upcoming, ensure_ascii=False, indent=2) + "\n")
    _atomic_write_text(
        calendar_path,
        calendar_export.build_ics(upcoming, calendar_name=project_id) + "\r\n",
    )


def finalize_meeting(project_id):
    """Generate and archive outputs before clearing the current meeting files."""
    if projects.load_session_state(project_id).get("status") == "running":
        return False, "Arrêtez la transcription avant de finaliser la réunion."
    meeting_state = projects.load_meeting_state(project_id)
    if meeting_state is None or meeting_state.get("meeting_id") is None:
        if _meeting_workspace_has_data(project_id):
            return False, (
                "Des fichiers existent mais aucun état de réunion ne permet de les "
                "attribuer. Ils ont été conservés."
            )
        return True, "Aucune donnée de réunion à finaliser."

    if meeting_state.get("finalized", False):
        try:
            _clear_meeting_workspace(project_id)
        except OSError as exc:
            return False, f"La réunion est archivée, mais le nettoyage a échoué : {exc}"
        return True, "Cette réunion était déjà finalisée ; fichiers de travail nettoyés."

    ok, message = generate_resume(project_id, storage.load_config(), reuse_existing=True)
    if not ok:
        return False, message

    extracted_dir = _project_files_dir(project_id) / "extracted_data"
    report_path = extracted_dir / "meeting_report.html"
    data_path = extracted_dir / "meeting_data.json"
    try:
        _archive_meeting_outputs(project_id, meeting_state, report_path, data_path)
        projects.mark_meeting_finalized(project_id)
        _clear_meeting_workspace(project_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, f"Échec de l'archivage ; les fichiers de travail sont conservés : {exc}"

    return True, "Rapport, tâches, évènements et calendrier archivés ; fichiers de réunion nettoyés."


def generate_resume(project_id, config=None, reuse_existing=False):
    """Run project-scoped cleaning and summary; retain resume.html for the current UI."""
    config = config or {}
    clean_script = EXTRACTION_DIR / "clean_text.py"
    summary_script = EXTRACTION_DIR / "summary.py"
    if not clean_script.exists() or not summary_script.exists():
        return False, "Script clean_text.py ou summary.py introuvable dans extraction/."

    ai_mode = config.get("clean_ai", "api")
    diarized = bool(config.get("clean_diarized", False))
    project_path = projects.project_dir(project_id)
    extracted_dir = project_path / "files" / "extracted_data"
    generated_report = extracted_dir / "meeting_report.html"
    generated_data = extracted_dir / "meeting_data.json"

    if reuse_existing and generated_report.is_file() and generated_data.is_file():
        try:
            with generated_data.open(encoding="utf-8") as f:
                data = json.load(f)
            report_html = generated_report.read_text(encoding="utf-8")
            if isinstance(data, dict) and report_html.strip():
                projects.resume_html_path(project_id).write_text(report_html, encoding="utf-8")
                return True, "Rapport déjà généré ; réutilisation des résultats existants."
        except (OSError, json.JSONDecodeError):
            pass

    clean_args = [
        sys.executable,
        str(clean_script),
        "--ai",
        ai_mode,
        "--project-dir",
        str(project_path),
    ]
    if diarized:
        clean_args.append("--diarized")
    if config.get("clean_model"):
        clean_args.extend(["--model", config["clean_model"]])

    clean_result = _run_command(clean_args)
    if clean_result.returncode:
        detail = clean_result.stderr.strip() or clean_result.stdout.strip()
        return False, f"Échec de clean_text.py (code {clean_result.returncode}).\n{detail}"

    summary_args = [
        sys.executable,
        str(summary_script),
        "--ai",
        ai_mode,
        "--project-dir",
        str(project_path),
    ]
    if diarized:
        summary_args.append("--diarized")
    summary_result = _run_command(summary_args)
    if summary_result.returncode:
        detail = summary_result.stderr.strip() or summary_result.stdout.strip()
        return False, f"Échec de summary.py (code {summary_result.returncode}).\n{detail}"

    if not generated_report.exists():
        return False, f"Commande terminée, mais rapport introuvable : {generated_report}"

    project_report = projects.resume_html_path(project_id)
    project_report.write_text(generated_report.read_text(encoding="utf-8"), encoding="utf-8")
    return True, f"Résumé généré et enregistré dans le projet : {project_report}"


def generate_tasks(project_id):
    """No task extraction command or backend entry point is present yet."""
    return False, (
        "Aucun script d'extraction des tâches ni fonction backend.generate_tasks "
        "n'est présent dans cette version."
    )
