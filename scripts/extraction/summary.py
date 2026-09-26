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
REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents
     if (parent / "files").is_dir() and ((parent / "app.py").is_file() or (parent / "scripts").is_dir())),
    Path(__file__).resolve().parents[1],
)
INPUT_FOLDER = REPO_ROOT / "files" / "raw_text_chunks"
CLEAN_TEXT_OUTPUT = REPO_ROOT / "files" / "extracted_data" / "whole_clean_text.txt"
RAW_TEXT_OUTPUT = REPO_ROOT / "files" / "backup" /"whole_raw_text.txt"

DEFAULT_SUMMARY_MODEL = "gpt-5.6-sol"
DEFAULT_LOCAL_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

SUMMARY_PROMPT_DIARIZED = """..."""
SUMMARY_PROMPT_RAW = """Tu reçois le texte nettoyé d'une réunion, sans identification fiable des locuteurs.

À partir de ce texte uniquement, produis un rapport de réunion clair, structuré et directement exploitable.

OBJECTIF

Créer un document HTML complet que l'utilisateur pourra copier-coller tel quel dans un fichier `.html` vide et ouvrir directement dans un navigateur.

Le rapport doit permettre de comprendre rapidement :

* pourquoi la réunion a eu lieu ;
* les principaux sujets discutés ;
* ce qui a été décidé ;
* ce qui reste à résoudre ;
* les actions à réaliser ;
* les prochaines étapes ;
* les contraintes, risques ou points de vigilance explicitement mentionnés.

FIDÉLITÉ

* Base-toi uniquement sur le texte fourni.
* N'invente aucune information.
* Ne déduis pas l'identité des participants, leurs responsabilités ou leurs intentions.
* Ne transforme pas une proposition en décision.
* Ne transforme pas une possibilité en fait.
* Ne transforme pas une discussion en consensus si celui-ci n'est pas explicitement établi.
* Ne crée pas de responsable ou d'échéance lorsqu'ils ne sont pas précisés.
* Lorsqu'une information est inconnue ou non précisée, indique « Non précisé » ou omets-la.
* Distingue clairement ce qui a été décidé de ce qui a seulement été discuté ou proposé.

STRUCTURE DU RAPPORT

Le HTML doit contenir au minimum :

1. Un en-tête avec :

   * titre du rapport ;
   * date, uniquement si elle apparaît dans le texte ;
   * durée, uniquement si elle apparaît dans le texte.

2. Une section « Synthèse » :

   * quelques points courts présentant l'essentiel de la réunion ;
   * pas de répétition du reste du rapport.

3. Une section « Décisions » :
   sous forme de tableau avec, lorsque disponible :

   * Décision
   * Contexte / justification
   * Statut

   N'inclus dans cette section que les décisions réellement établies.

4. Une section « Actions » :
   sous forme de tableau :

   * Action
   * Responsable
   * Échéance
   * Statut

   N'invente jamais de responsable ou d'échéance.

5. Une section « Questions et points à résoudre » :
   sous forme de tableau :

   * Question / problème
   * Prochaine étape éventuelle
   * Responsable éventuel

6. Une section « Discussion par thème » :
   regroupe les éléments de la réunion par grands thèmes plutôt que de suivre simplement l'ordre chronologique.
   Pour chaque thème :

   * titre ;
   * synthèse concise ;
   * éléments importants discutés.

7. Une section « Points de vigilance » :
   uniquement pour les contraintes, dépendances, risques ou incertitudes explicitement mentionnés.

8. Une section « Prochaines étapes » :
   uniquement pour les suites explicitement établies ou clairement prévues dans la réunion.

STYLE

* Rédige en français.
* Sois concis mais suffisamment précis pour préserver les informations importantes.
* Utilise des titres, sous-titres, tableaux et listes pour faciliter la lecture.
* Évite les longs blocs de texte.
* N'utilise pas de jargon qui n'apparaît pas dans le contenu ou qui n'est pas nécessaire.
* Ne mentionne jamais que le texte source était une transcription.
* Puisqu'il n'y a pas de diarisation fiable, ne fais aucune attribution de propos à des personnes.

HTML

Retourne UNIQUEMENT le document HTML complet.

Le résultat doit commencer par `<!DOCTYPE html>` et contenir :

* `<html>`
* `<head>`
* `<meta charset="UTF-8">`
* un `<title>`
* du CSS intégré dans `<style>`
* `<body>`

Le CSS doit produire un rapport professionnel, lisible sur ordinateur et mobile :

* largeur de lecture raisonnable ;
* titres hiérarchisés ;
* tableaux lisibles et adaptatifs ;
* espacement clair entre les sections ;
* contraste suffisant ;
* style sobre.

N'utilise aucun Markdown.

N'ajoute aucun texte avant `<!DOCTYPE html>` ni après `</html>`.

IMPORTANT

Le rapport doit privilégier la précision factuelle plutôt que la complétude artificielle. Il vaut mieux laisser une cellule « Non précisé » que d'inventer une information.
"""


def generate_summary_openai(
    text: str,
    model: str, prompt:str
) -> str:

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model,
        reasoning={"effort": "medium"},
        instructions=prompt,
        input=text,
    )

    return response.output_text

def generate_summary_ollama(
    text: str,
    model: str, prompt:str
) -> str:

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama: {exc}"
        ) from exc

    return data["message"]["content"]












def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a structured meeting report from cleaned text."
    )

    parser.add_argument(
        "--ai",
        choices=["api", "local"],
        default="api",
        help="AI backend: OpenAI API or local Ollama (default: api)",
    )

    parser.add_argument(
    "--diarized",
    action="store_true",
    help="Input transcript contains speaker labels.",
    )

    parser.add_argument(
        "--model",
        default=None,
        help="Override the default model for the selected AI backend.",
    )

    args = parser.parse_args()

    # -----------------------------------------------------------
    # Input
    # -----------------------------------------------------------

    input_file = (
        REPO_ROOT
        / "files"
        / "extracted_data"
        / "whole_clean_text.txt"
    )

    if not input_file.exists():
        print(
            f"Fichier introuvable: {input_file}",
            file=sys.stderr,
        )
        return 1

    try:
        text = input_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Erreur de lecture: {exc}", file=sys.stderr)
        return 1

    if not text.strip():
        print("Le fichier de transcription est vide.", file=sys.stderr)
        return 1

    print(f"Transcription chargée: ~{len(text.split())} mots")
    print(f"AI: {args.ai}")

    if args.diarized:
        summary_prompt = SUMMARY_PROMPT_DIARIZED
    else:
        summary_prompt = SUMMARY_PROMPT_RAW

    # -----------------------------------------------------------
    # Choose model
    # -----------------------------------------------------------

    if args.ai == "api":
        model = args.model or DEFAULT_SUMMARY_MODEL
        print(f"Modèle: {model}")

        result = generate_summary_openai(
            text=text,
            model=model, prompt=summary_prompt ,  
        )

    else:
        model = args.model or DEFAULT_LOCAL_MODEL
        print(f"Modèle: {model}")

        result = generate_summary_ollama(
            text=text,
            model=model, prompt=summary_prompt,
        )


    # -----------------------------------------------------------
    # Write report
    # -----------------------------------------------------------

    output_file = (
        REPO_ROOT
        / "files"
        / "extracted_data"
        / "meeting_report.html"
    )

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(result, encoding="utf-8")
    except OSError as exc:
        print(f"Erreur d'écriture: {exc}", file=sys.stderr)
        return 1

    print(f"\nRapport écrit: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
