"""
Configuration globale de l'app (pas par projet) : où vit le dossier `projects/`
(local ou clone d'un repo GitHub) et quel mode d'exécution utiliser pour les
modèles (branché par le reste de l'équipe, l'UI ne fait que stocker le choix).
"""

import json
import os
import subprocess
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "app_config.json"
ENV_PATH = CONFIG_PATH.parent.parent / ".env"

DEFAULT_CONFIG = {
    "storage_mode": "local",          # "local" | "github"
    "github_repo_path": "",           # chemin local du repo cloné (contient data/projects/), si github
    "execution_mode": "api",          # "local" | "api"
    "local_model_backend": "ollama",  # "ollama" | "colab"
    "api_model": "openai/whisper-large-v3",
    "clean_ai": "api",
    "clean_diarized": False,
    "clean_output": "",
    "clean_model": "",
    "transcription_enabled": False  # True = transcription activée, False = désactivée
}

API_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_API_KEY",
    "google": "GOOGLE_API_KEY",
    "whisper": "WHISPER_API_KEY",
    "whisperx": "WHISPERX_API_KEY",
    "gradium": "GRADIUM_API_KEY",
}


def _load_env_file():
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name or name.startswith("#"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(name, value)


_load_env_file()


def load_config():
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_api_key(provider):
    env_name = API_ENV_VARS.get(provider)
    if not env_name:
        return ""
    value = os.environ.get(env_name, "")
    if value or not ENV_PATH.exists():
        return value
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        name, sep, stored = line.partition("=")
        if sep and name.strip() == env_name:
            return stored.strip().strip('"').strip("'")
    return ""


def set_api_key(provider, value):
    env_name = API_ENV_VARS.get(provider)
    if not env_name:
        raise ValueError(f"Fournisseur inconnu : {provider}")
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    replacement = f'{env_name}="{escaped}"'
    found = False
    for index, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == env_name:
            lines[index] = replacement
            found = True
    if not found:
        lines.append(replacement)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[env_name] = value


def delete_api_key(provider):
    env_name = API_ENV_VARS.get(provider)
    if not env_name:
        return
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        ENV_PATH.write_text("\n".join(line for line in lines if line.split("=", 1)[0].strip() != env_name) + "\n", encoding="utf-8")
    os.environ.pop(env_name, None)


def push_to_github(cfg, message="update: projets"):
    repo_path = cfg.get("github_repo_path", "")
    if not repo_path:
        return False, "Aucun chemin de repo GitHub configuré."
    try:
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=repo_path, check=True, capture_output=True)
        return True, "Poussé sur GitHub avec succès."
    except subprocess.CalledProcessError as e:
        return False, f"Erreur git : {e.stderr.decode('utf-8', errors='ignore')}"
