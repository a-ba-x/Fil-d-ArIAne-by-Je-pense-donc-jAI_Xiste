"""
Le transcript est livré en HTML (pas en JSON structuré). Pour permettre la
recherche par speaker sans imposer un format au reste de l'équipe, on adopte
une convention par défaut, avec repli automatique si elle n'est pas respectée :

  Convention attendue : chaque tour de parole est un élément portant un
  attribut `data-speaker="Nom"`, ex. <p data-speaker="Arsene">...</p>

  Repli si absent : le HTML entier est traité comme un seul bloc de texte
  (tags retirés), cherchable en plein texte mais sans filtre par speaker.

Point à confirmer avec l'équipe : si le module de transcription produit un
autre format (ex. classe CSS plutôt que data-speaker), il suffit d'adapter
la regex SPEAKER_BLOCK_RE ci-dessous -- le reste de l'UI ne dépend que de la
fonction extract_segments().
"""

import re

SPEAKER_BLOCK_RE = re.compile(
    r'data-speaker="([^"]+)"[^>]*>(.*?)</\w+>',
    re.DOTALL | re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(html):
    return re.sub(TAG_RE, " ", html or "").strip()


def extract_segments(html):
    """
    Retourne une liste de {"speaker": str|None, "text": str}.
    Si aucun marquage data-speaker n'est trouvé, retourne un unique segment
    avec speaker=None et le texte complet (repli plein texte).
    """
    if not html:
        return []
    matches = SPEAKER_BLOCK_RE.findall(html)
    if not matches:
        text = strip_tags(html)
        return [{"speaker": None, "text": text}] if text else []
    return [{"speaker": speaker, "text": strip_tags(content)} for speaker, content in matches]
