#!/usr/bin/env python3
"""
Clean a French meeting transcription into thought units.

Modes:
  --mode api   -> OpenAI API
  --mode local -> local Ollama model

Input:
  1 txt file:
      Read from the beginning until the first line starting with '#'.

  2 txt files:
      Read from the first '#' marker of file 1 (included, '#' removed)
      through the end of file 1, then from the beginning of file 2 until
      its first '#' marker (excluded).

The extracted block is sent to the model AS A WHOLE, preserving conversational
context across speakers.

Expected input format:
    <Speaker_name_or_label>
    Text they say

    <Speaker_name_or_label>
    Text they say

    ...
    #<Last_Speaker_name_or_label>
    Text they say

Output:
    <Speaker_name_or_label>
    <item>
    <item>

    <Speaker_name_or_label>
    <item>
    <item>

Authentication:
  API mode reads OPENAI_API_KEY from .env / environment variables.
  The API key is never stored in this script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
REPO_ROOT = Path(__file__).resolve().parents[2]
INPUT_FOLDER = REPO_ROOT / "files" / "raw_text_chunks"
CLEAN_TEXT_OUTPUT = REPO_ROOT / "files" / "extracted_data" / "whole_clean_text.txt"
RAW_TEXT_OUTPUT = REPO_ROOT / "files" / "backup" /"whole_raw_text.txt"


DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

# ---------------------------------------------------------------------------
# Append text to raw text file
# ---------------------------------------------------------------------------
def append_raw_text(path: Path, raw_text_output: Path) -> None:
    raw_text_output.parent.mkdir(parents=True, exist_ok=True)

    text = path.read_text(encoding="utf-8-sig")

    if not text.strip():
        return

    with raw_text_output.open("a", encoding="utf-8") as f:
        if raw_text_output.stat().st_size > 0:
            f.write("\n\n")
        f.write(text.rstrip())
        f.write("\n")

# ---------------------------------------------------------------------------
# File extraction
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")



# ---------------------------------------------------------------------------
# File extraction for 
# ---------------------------------------------------------------------------


def find_marker_line(text: str) -> int:
    """Return the character index of the first line whose stripped text starts with '#'."""
    match = re.search(r"(?m)^[ \t]*#.*$", text)
    return match.start() if match else -1


def normalize_marker_speaker_block(text: str) -> str:
    """Remove '#' from a leading #Speaker marker."""
    lines = text.splitlines()

    if lines and lines[0].lstrip().startswith("#"):
        leading = len(lines[0]) - len(lines[0].lstrip())
        stripped = lines[0].lstrip()
        lines[0] = lines[0][:leading] + stripped[1:].lstrip()

    return "\n".join(lines).strip()

def get_last_speaker_turns(text: str, n: int = 2) -> str:
    """
    Return the last n complete speaker turns from a transcript.
    Speaker turns are separated by blank lines.
    """
    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n+", text.strip())
        if block.strip()
    ]

    return "\n\n".join(blocks[-n:])


def extract_segment(paths: List[Path]) -> Tuple[str, str]:
    """
    Return:
        previous_context, current_chunk

    1 file:
        current_chunk = beginning -> first '#'
        previous_context = ""

    2 files:
        previous_context = last 2 speaker turns before '#' in file 1
        current_chunk = from '#' in file 1 -> before '#' in file 2
    """
    if len(paths) not in (1, 2):
        raise ValueError("Use exactly 1 or 2 input files.")

    first = read_text(paths[0])

    # ---------------------------------------------------------------
    # One file
    # ---------------------------------------------------------------
    if len(paths) == 1:
        marker = find_marker_line(first)

        if marker == -1:
            return "", first.strip()

        current_chunk = first[:marker].strip()
        return "", current_chunk

    # ---------------------------------------------------------------
    # Two files
    # ---------------------------------------------------------------
    second = read_text(paths[1])

    marker1 = find_marker_line(first)
    marker2 = find_marker_line(second)

    if marker1 == -1:
        raise ValueError(f"No '#' marker found in first file: {paths[0]}")
    if marker2 == -1:
        raise ValueError(f"No '#' marker found in second file: {paths[1]}")

    # Everything before # in file 1 belongs to the previous chunk.
    previous_chunk = first[:marker1].strip()

    # Current chunk starts at # in file 1.
    part1 = normalize_marker_speaker_block(first[marker1:])

    # Continue through the beginning of file 2.
    part2 = second[:marker2].strip()

    if part1 and part2:
        current_chunk = part1 + "\n\n" + part2
    else:
        current_chunk = part1 or part2

    previous_context = get_last_speaker_turns(previous_chunk, n=2)

    return previous_context, current_chunk


'''
def extract_segment(paths: List[Path]) -> str:
    if len(paths) not in (1, 2):
        raise ValueError("Use exactly 1 or 2 input files.")

    first = read_text(paths[0])

    # One file: beginning -> first # marker.
    if len(paths) == 1:
        marker = find_marker_line(first)
        return first[:marker].strip() if marker != -1 else first.strip()

    second = read_text(paths[1])

    marker1 = find_marker_line(first)
    marker2 = find_marker_line(second)

    if marker1 == -1:
        raise ValueError(f"No '#' marker found in first file: {paths[0]}")
    if marker2 == -1:
        raise ValueError(f"No '#' marker found in second file: {paths[1]}")

    # File 1: from # marker through the end, including the speaker marker.
    part1 = normalize_marker_speaker_block(first[marker1:])

    # File 2: from beginning until its # marker, excluded.
    part2 = second[:marker2].strip()

    if not part1:
        return part2
    if not part2:
        return part1

    return part1 + "\n\n" + part2
'''

# ---------------------------------------------------------------------------
# Model prompt + output schema
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_RAW = """
Tu reçois un chunk de transcription d'une réunion. Utilise tout le chunk comme contexte et produis une représentation fidèle et compacte des informations utiles, destinée à être analysée ensuite par un autre modèle pour créer un résumé, des tâches et des décisions.

Conserve les idées, propositions, problèmes, contraintes, questions, décisions, désaccords, intentions, actions, responsables, dates/chiffres, arguments et exemples utiles à la compréhension du projet ou de la discussion.

Supprime les fillers, réactions sans contenu (« oui », « ouais », « d'accord », etc.), hésitations, répétitions, transitions sans contenu et détails anecdotiques inutiles.

Découpe en unités de pensée : une unité = une idée utile. Regroupe les phrases et détails qui développent la même idée, mais sépare les idées réellement distinctes. Conserve l'ordre chronologique.

Reformule pour supprimer le bruit oral et rendre le contenu clair, sans ajouter d'information ni d'interprétation. Ne transforme pas une proposition en décision, une intention en action réalisée, une question en affirmation ou une possibilité en fait établi.

Ne crée pas de catégories ou d'étiquettes comme « Problème », « Proposition », « Contrainte », « Besoin », etc.

Conserve exactement les labels de locuteurs présents dans le chunk.

En cas de doute, conserve l'information si elle pourrait être utile au modèle suivant.

Retourne uniquement le JSON demandé par le programme.
""".strip()

SYSTEM_PROMPT_DIARIZED = """
Tu reçois un chunk de transcription brute d'une réunion, sans labels fiables de locuteurs.

Utilise tout le chunk comme contexte et produis une représentation fidèle, compacte et exploitable de ce qui a réellement été dit. Le résultat sera ensuite utilisé par un autre modèle pour produire un résumé, des tâches, des décisions et des points à suivre.

Conserve les idées, propositions, problèmes, contraintes, questions, décisions, désaccords, intentions, actions, échéances, chiffres, arguments et exemples utiles à la compréhension de la réunion ou du projet.

Supprime les fillers, hésitations, réactions sans contenu (« oui », « ouais », « d'accord », etc.), répétitions, transitions sans contenu et détails anecdotiques inutiles.

Découpe en unités de pensée : une unité correspond à une idée utile. Regroupe plusieurs phrases lorsqu'elles développent la même idée, mais sépare les idées distinctes. Conserve l'ordre chronologique.

Reformule pour supprimer le bruit oral et rendre le contenu clair, sans ajouter d'information ni d'interprétation. Ne transforme pas une proposition en décision, une intention en action réalisée, une question en affirmation ou une possibilité en fait établi.

N'invente jamais de locuteur.

Le contexte précédent sert uniquement à comprendre la continuité et les références. Ne le reproduis pas dans la sortie. La sortie doit représenter uniquement le chunk à traiter.

En cas de doute, conserve l'information si elle pourrait être utile au modèle suivant.

Retourne uniquement le JSON demandé.
""".strip()


OUTPUT_SCHEMA_DIARIZED = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["speaker", "items"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["blocks"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA_RAW = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def clean_with_openai(text: str, previous_context: str, model: str, system_prompt: st, output_schema: dict,diarized: bool) -> List[dict]:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Put it in .env or set it as an "
            "environment variable."
        )

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
    model=model,
    reasoning={"effort": "none"},
    instructions=system_prompt,
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "CONTEXTE DU CHUNK PRÉCÉDENT\n"
                        "Utilise uniquement ce contexte pour comprendre "
                        "les références et la continuité de la conversation. "
                        "Ne le reproduis pas dans la sortie.\n\n"
                        f"{previous_context}"
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "CHUNK À TRAITER\n"
                        "Seul ce texte doit être représenté dans la sortie.\n\n"
                        f"{text}"
                    ),
                }
            ],
        },
    ],
    text={
        "format": {
            "type": "json_schema",
            "name": "meeting_thought_units",
            "strict": True,
            "schema": output_schema,
        }
    },
)

    try:
        data = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "OpenAI returned invalid JSON:\n" + response.output_text
        ) from exc

    if diarized:
        return validate_blocks(data)
    else:
        return validate_raw(data)
    

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def clean_with_ollama(text: str, model: str, system_prompt: str) -> List[dict]:
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\n\nRetourne exactement un objet JSON avec cette forme:"
                + '\n{"blocks":[{"speaker":"...","items":["...","..."]}]}',
            },
            {
                "role": "user",
                "content": f"TRANSCRIPTION À TRAITER:\n\n{text}",
            },
        ],
        "options": {
            "temperature": 0.1,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Impossible de contacter Ollama à {OLLAMA_URL}. "
            "Vérifie qu'Ollama est lancé."
        ) from exc

    content = result.get("message", {}).get("content", "")

    if not content:
        raise RuntimeError(f"Réponse Ollama inattendue: {result}")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Ollama returned invalid JSON:\n" + content
        ) from exc

    return validate_blocks(data)


# ---------------------------------------------------------------------------
# Validation + formatting
# ---------------------------------------------------------------------------

def validate_blocks(data: dict) -> List[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("blocks"), list):
        raise RuntimeError(f"Invalid model response: {data}")

    blocks = []

    for block in data["blocks"]:
        if not isinstance(block, dict):
            continue

        speaker = block.get("speaker")
        items = block.get("items")

        if not isinstance(speaker, str):
            continue
        if not isinstance(items, list):
            continue

        clean_items = []

        for item in items:
            if isinstance(item, str):
                item = re.sub(r"\s+", " ", item).strip()
                if item:
                    clean_items.append(item)

        if speaker.strip() and clean_items:
            blocks.append(
                {
                    "speaker": speaker.strip(),
                    "items": clean_items,
                }
            )

    if not blocks:
        raise RuntimeError("The model returned no usable speaker blocks.")

    return blocks

def validate_raw(data: dict) -> List[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RuntimeError(f"Invalid model response: {data}")

    clean_items = []

    for item in data["items"]:
        if isinstance(item, str):
            item = re.sub(r"\s+", " ", item).strip()
            if item:
                clean_items.append(item)

    if not clean_items:
        raise RuntimeError("The model returned no usable items.")

    # Normalize raw output to the same internal structure
    return [
        {
            "speaker": "",
            "items": clean_items,
        }
    ]

def format_output(blocks: List[dict]) -> str:
    output_blocks = []

    for block in blocks:
        lines = [block["speaker"]]
        lines.extend(block["items"])
        output_blocks.append("\n".join(lines))

    return "\n\n".join(output_blocks) + "\n\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:

    # ---------------------------------------------------------------------------
    # Command-line arguments
    # ---------------------------------------------------------------------------
    parser = argparse.ArgumentParser(
        description="Clean a transcript into thought units."
    )

    parser.add_argument(
        "--ai",
        choices=["api", "local"],
        default="api",
        help="AI backend: OpenAI API or local Ollama (default: api)",
    )

    parser.add_argument(
        "--diarized",
        action="store_true", #if i write nothing then that means false
        help="Input transcript contains speaker labels.",
    )

    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file")
    # Keep the --project-dir argument.

    parser.add_argument(
        "--model",
        default=None,
        help="Override the model for the selected mode.",
    )

    parser.add_argument(
    "--project-dir",
    type=Path,
    default=REPO_ROOT,
    help="Project directory containing files/.",
    )

    args = parser.parse_args()

    files_dir = args.project_dir / "files"
    input_folder = files_dir / "raw_text_chunks"
    raw_text_output = files_dir / "backup" / "whole_raw_text.txt"
    clean_text_output = args.output or (
    files_dir / "extracted_data" / "whole_clean_text.txt"
    )
    # ---------------------------------------------------------------------------
    # Select input files
    # ---------------------------------------------------------------------------
    files = sorted(
    (
        path
        for path in input_folder.glob("*.txt")
        if path.is_file()
    ),
    key=lambda path: path.stat().st_ctime,
    )[:2]

    if not files:
        print(
            f"Aucun fichier .txt trouvé dans {input_folder}",
            file=sys.stderr,
        )
        return 1

    print("Fichiers sélectionnés :")
    for path in files:
        print(f"  {path.name}")

    # ---------------------------------------------------------------------------
    # Update whole_raw_text.txt with the new chunk
    # ---------------------------------------------------------------------------
    append_raw_text(files[0], raw_text_output)
    print(f"Ajouté au fichier brut : {files[0].name}")

    # ---------------------------------------------------------------------------
    # According to diarized, extract the segment to process and choose the prompt
    # ---------------------------------------------------------------------------

    if args.diarized:
        # Speaker-labelled transcript: use # markers and speaker context
        try:
            previous_context, segment = extract_segment(files)
        except (OSError, ValueError) as exc:
            print(f"Erreur d'extraction: {exc}", file=sys.stderr)
            return 1

        system_prompt = SYSTEM_PROMPT_DIARIZED
        output_schema = OUTPUT_SCHEMA_DIARIZED

    else:
        # Raw transcript: oldest file is context, second-oldest is the segment.
        try:
            if len(files) == 1:
                previous_context = ""
                segment = files[0].read_text(
                    encoding="utf-8-sig"
                ).strip()
            else:
                previous_context = files[0].read_text(
                    encoding="utf-8-sig"
                ).strip()

                segment = files[1].read_text(
                    encoding="utf-8-sig"
                ).strip()

        except OSError as exc:
            print(f"Erreur de lecture: {exc}", file=sys.stderr)
            return 1

        system_prompt = SYSTEM_PROMPT_RAW
        output_schema = OUTPUT_SCHEMA_RAW

    word_count = len(segment.split())
    print(f"Bloc extrait: ~{word_count} mots")
    print(f"AI: {args.ai}")

    if not segment.strip():
        print("Bloc vide — aucun texte à nettoyer.")
        files[0].unlink()
        print(f"Fichier supprimé : {files[0].name}")
        return 0
    # ---------------------------------------------------------------------------
    # According to AI mode, call the appropriate model and clean the text
    # ---------------------------------------------------------------------------

    try:
        model = args.model or DEFAULT_OPENAI_MODEL
        print(f"Modèle: {model}")
        if args.ai == "api":

            blocks = clean_with_openai(
                segment,
                previous_context,
                model,
                system_prompt,output_schema, args.diarized
            )

        else:

            blocks = clean_with_ollama(
                segment,
                previous_context,
                model,
                system_prompt,
            )

    except Exception as exc:
        print(
            f"\nErreur pendant le traitement: {exc}",
            file=sys.stderr,
        )
        return 1

    result = format_output(blocks)

    try:
        clean_text_output.parent.mkdir(parents=True, exist_ok=True)

        with clean_text_output.open("a", encoding="utf-8") as f:
            if clean_text_output.stat().st_size > 0:
                f.write("\n\n")
            f.write(result.rstrip())
            f.write("\n")

        # Delete the oldest transcript only after successful cleaning
        if len(files) > 1:
            files[0].unlink()
            print(f"Fichier supprimé : {files[0].name}")
        else:
            print(f"Fichier conservé comme contexte : {files[0].name}")

    except OSError as exc:
        print(f"Erreur d'écriture: {exc}", file=sys.stderr)
        return 1

    

    print(f"\nFichier mis à jour: {clean_text_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
