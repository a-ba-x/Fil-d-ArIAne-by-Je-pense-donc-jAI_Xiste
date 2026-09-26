"""
Génération .ics à partir des nœuds du projet actif -- fonctionne pour tout
type de nœud ayant une date exploitable (argv['quand'] ou argv['date'], voir
tasks.extract_date), pas seulement les tâches : un évènement daté est
exporté pareil qu'une tâche avec deadline.
"""

from datetime import datetime, timezone
import uuid

from ui import tasks


def _format_date(date_str):
    if not date_str:
        return None
    return date_str.replace("-", "")


def build_ics(nodes, calendar_name="Planning"):
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//RiseOfAgentsX//MeetingAgent//FR",
        f"X-WR-CALNAME:{calendar_name}",
    ]

    for name, node, depth in tasks.iter_tree(nodes):
        date_ics = _format_date(tasks.extract_date(node))
        if not date_ics:
            continue
        titre = tasks.get_title(node)
        qui = node.get("argv", {}).get("qui") or "Non assigné"
        uid = f"{name}-{uuid.uuid4()}@riseofagentsx"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE=DATE:{date_ics}",
            f"DTEND;VALUE=DATE:{date_ics}",
            f"SUMMARY:{titre} ({qui})",
            f"DESCRIPTION:Type : {node.get('type')} | Terminé : {node.get('completed')}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\n".join(lines)


def save_ics(nodes, path, calendar_name="Planning"):
    content = build_ics(nodes, calendar_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
