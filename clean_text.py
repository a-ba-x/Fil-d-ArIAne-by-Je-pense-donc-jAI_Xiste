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


DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")


# ---------------------------------------------------------------------------
# File extraction
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


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

SYSTEM_PROMPT = """
Tu reçois un chunk de transcription d'une réunion. Utilise tout le chunk comme contexte et produis une représentation fidèle et compacte des informations utiles, destinée à être analysée ensuite par un autre modèle pour créer un résumé, des tâches et des décisions.

Conserve les idées, propositions, problèmes, contraintes, questions, décisions, désaccords, intentions, actions, responsables, dates/chiffres, arguments et exemples utiles à la compréhension du projet ou de la discussion.

Supprime les fillers, réactions sans contenu (« oui », « ouais », « d'accord », etc.), hésitations, répétitions, transitions sans contenu et détails anecdotiques inutiles.

Découpe en unités de pensée : une unité = une idée utile. Regroupe les phrases et détails qui développent la même idée, mais sépare les idées réellement distinctes. Conserve l'ordre chronologique.

Reformule pour supprimer le bruit oral et rendre le contenu clair, sans ajouter d'information ni d'interprétation. Ne transforme pas une proposition en décision, une intention en action réalisée, une question en affirmation ou une possibilité en fait établi.

Ne crée pas de catégories ou d'étiquettes comme « Problème », « Proposition », « Contrainte », « Besoin », etc.

Conserve exactement les labels de locuteurs présents dans le chunk. Les labels sont locaux au chunk : ne suppose pas qu'un même label dans un autre chunk désigne la même personne.

En cas de doute, conserve l'information si elle pourrait être utile au modèle suivant.

Retourne uniquement le JSON demandé par le programme.
""".strip()

'''
Tu reçois une transcription continue d'une réunion.

Le format est : 
<Speaker_name_or_label>\n
Text they say
\n\n
<Speaker_name_or_label>\n
Text they say
\n\n

Utilise l'ensemble du texte comme contexte, mais ne restitue que les
informations, idées et éléments de discussion pertinents.

Le résultat doit être une extraction structurée des idées importantes,
pas une retranscription nettoyée.

-Conserve exactement les locuteurs et associe chaque item au locuteur qui l'a exprimé.

Garde :
- les idées et propositions nouvelles ;
- les problèmes et contraintes identifiés ;
- les questions importantes ;
- les décisions et points de désaccord ;
- les besoins / exigences du produit ;
- les observations utiles ;
- les exemples lorsqu'ils apportent une information utile ;
- les idées évoquées même si elles sont ensuite abandonnées, en conservant
  le fait qu'elles ont été abandonnées si cela ressort du contexte.
- les noms, chiffres, dates, acronymes et termes techniques.

Supprime :
- les hésitations et fillers ;
- « oui », « ouais », « d'accord », « hum » seuls ;
- les phrases de transition sans contenu ;
- les commentaires sur le fait de prendre des notes ou d'organiser la discussion ;
- les répétitions d'une même idée ;
- les formulations différentes qui expriment exactement le même point ;
- les détails anecdotiques qui n'apportent rien à la compréhension du sujet.

Une unité doit contenir une seule idée utile.
Plusieurs idées distinctes dans une même intervention doivent être séparées.
Regroupe les détails qui servent à illustrer une même idée.

Ne cherche pas à produire un résumé. Cherche à produire une représentation fidèle et compacte des informations utiles de la réunion, destinée à être analysée ultérieurement par un autre modèle.

Utilise le contexte de toute la conversation pour comprendre les références,
mais n'ajoute aucune information absente du texte.

N'ajoute pas de catégories ou d'interprétation qui ne sont pas demandées.

Ne résume pas toute la réunion en quelques points : conserve une granularité
suffisamment fine pour ne pas perdre les idées distinctes.

Ne produis pas de commentaires sur ton travail.
Retourne uniquement la structure demandée: 
<Speaker_name_or_label>\n
<item>
<item>
…
<item>
\n\n
<Speaker_name_or_label>\n
<item>
<item>
…
<item>
\n\n
…
<Speaker_name_or_label>\n
<item>
<item>
…
<item>
\n\n

Tu es un éditeur de transcription de réunions en français.

Tu reçois UNE SEULE TRANSCRIPTION CONTINUE. Elle peut contenir plusieurs
locuteurs et plusieurs idées. Utilise tout le contexte disponible pour
comprendre les références, les pronoms, les ellipses et les liens entre les
phrases.

Ta tâche est de transformer la transcription brute en unités de pensée lisibles.

RÈGLES:
- Ne fais PAS un résumé global.
- Ne supprime AUCUNE idée exprimée.
- N'INVENTE aucune information.
- Nettoie les hésitations, répétitions purement orales et artefacts évidents
  de transcription.
- Conserve fidèlement le sens.
- Une unité = une idée cohérente qui peut être lue indépendamment.
- Une unité peut contenir plusieurs phrases si elles portent sur la même idée.
- Sépare les idées distinctes en items distincts.
- Utilise le contexte des phrases voisines pour comprendre le sens.
- Ne change pas une question en affirmation.
- Ne change pas une proposition en décision.
- Ne change pas une intention en fait accompli.
- Conserve les noms, chiffres, dates, acronymes et termes techniques.
- Conserve exactement les locuteurs et associe chaque item au locuteur qui
  l'a exprimé.
- Ne fusionne pas deux locuteurs.
- Ne crée pas de locuteur qui n'existe pas dans le texte.
- Garde le français.

IMPORTANT:
- Le résultat doit couvrir l'ensemble des idées exprimées dans la
  transcription.
- Ne produis pas de commentaires sur ton travail.
- Retourne uniquement la structure demandée.
'''


OUTPUT_SCHEMA = {
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


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def clean_with_openai(text: str, previous_context: str, model: str) -> List[dict]:
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
    instructions=SYSTEM_PROMPT,
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
            "schema": OUTPUT_SCHEMA,
        }
    },
)
    '''
    response = client.responses.create(
        model=model,
        reasoning={"effort": "none"},
        instructions=SYSTEM_PROMPT,
        input=f"TRANSCRIPTION À TRAITER:\n\n{text}",
        text={
            "format": {
                "type": "json_schema",
                "name": "meeting_thought_units",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
    )
    '''
    try:
        data = json.loads(response.output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "OpenAI returned invalid JSON:\n" + response.output_text
        ) from exc

    return validate_blocks(data)
    

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def clean_with_ollama(text: str, model: str) -> List[dict]:
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
    parser = argparse.ArgumentParser(
        description="Clean a French transcript into thought units."
    )

    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="1 or 2 .txt input files",
    )

    parser.add_argument(
        "--mode",
        choices=["api", "local"],
        default="api",
        help="Use OpenAI API or local Ollama (default: api)",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("clean_text.txt"),
        help="Output file (default: clean_text.txt)",
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Override the model for the selected mode.",
    )

    args = parser.parse_args()

    if len(args.files) not in (1, 2):
        parser.error("Provide exactly 1 or 2 input files.")

    for path in args.files:
        if not path.exists():
            print(f"Erreur: fichier introuvable: {path}", file=sys.stderr)
            return 1

    try:
        previous_context, segment = extract_segment(args.files)
    except (OSError, ValueError) as exc:
        print(f"Erreur d'extraction: {exc}", file=sys.stderr)
        return 1

    word_count = len(segment.split())
    print(f"Bloc extrait: ~{word_count} mots")
    print(f"Mode: {args.mode}")

    try:
        if args.mode == "api":
            model = args.model or DEFAULT_OPENAI_MODEL
            print(f"Modèle: {model}")
            blocks = clean_with_openai(segment, previous_context, model)
        else:
            model = args.model or DEFAULT_OLLAMA_MODEL
            print(f"Modèle: {model}")
            blocks = clean_with_ollama(segment, model)

    except Exception as exc:
        print(f"\nErreur pendant le traitement: {exc}", file=sys.stderr)
        return 1

    result = format_output(blocks)

    try:
        args.output.write_text(result, encoding="utf-8")
    except OSError as exc:
        print(f"Erreur d'écriture: {exc}", file=sys.stderr)
        return 1

    print(f"\nFichier écrit: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
