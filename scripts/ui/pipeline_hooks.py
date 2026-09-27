"""Connect UI actions to transcription and extraction entry points."""

import json
import subprocess
import sys
import threading
from pathlib import Path

from ui import projects

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
    """Start recording, or resume the process if it is waiting on the control flag."""
    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    control_file = _set_going(project_id, True)
    if process is None or process.poll() is not None:
        process, error = _launch_transcription(project_id, control_file)
        if process is None:
            _set_going(project_id, False)
            return False, error
    projects.set_session_status(project_id, "running")
    _watch_in_background(project_id, process)
    return True, "Transcription démarrée. Utilisez Pause pour la suspendre."


def pause_recording(project_id):
    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    if process is None or process.poll() is not None:
        return False, "Aucun processus de transcription actif à mettre en pause."
    _set_going(project_id, False)
    projects.set_session_status(project_id, "paused")
    return True, "Transcription en pause. Reprendre relancera la capture."


def resume_recording(project_id):
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


def stop_recording(project_id):
    _set_going(project_id, False)
    process = _TRANSCRIPTION_PROCESSES.get(project_id)
    if process is None or process.poll() is not None:
        projects.set_session_status(project_id, "stopped")
        details = _transcription_log_tail(project_id)
        message = "Aucun processus de transcription actif pour ce projet."
        return False, f"{message}\nDernier journal :\n{details}" if details else message
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    projects.set_session_status(project_id, "stopped")
    return True, "Processus de transcription arrêté."


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


def generate_resume(project_id, config=None):
    """Run clean_text.py followed by summary.py and attach the resulting HTML to the project."""
    config = config or {}
    clean_script = EXTRACTION_DIR / "clean_text.py"
    summary_script = EXTRACTION_DIR / "summary.py"
    if not clean_script.exists() or not summary_script.exists():
        return False, "Script clean_text.py ou summary.py introuvable dans extraction/."

    ai_mode = config.get("clean_ai", "api")
    diarized = bool(config.get("clean_diarized", False))
    clean_args = [sys.executable, str(clean_script), "--ai", ai_mode]
    if diarized:
        clean_args.append("--diarized")
    if config.get("clean_output"):
        clean_args.extend(["--output", config["clean_output"]])
    if config.get("clean_model"):
        clean_args.extend(["--model", config["clean_model"]])

    clean_result = _run_command(clean_args)
    if clean_result.returncode:
        detail = clean_result.stderr.strip() or clean_result.stdout.strip()
        return False, f"Échec de clean_text.py (code {clean_result.returncode}).\n{detail}"

    summary_args = [sys.executable, str(summary_script), "--ai", ai_mode]
    if diarized:
        summary_args.append("--diarized")
    summary_result = _run_command(summary_args)
    if summary_result.returncode:
        detail = summary_result.stderr.strip() or summary_result.stdout.strip()
        return False, f"Échec de summary.py (code {summary_result.returncode}).\n{detail}"

    generated_report = APP_ROOT / "files" / "extracted_data" / "meeting_report.html"
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
