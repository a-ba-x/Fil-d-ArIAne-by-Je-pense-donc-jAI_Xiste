"""
Rise of Agents X -- UI Tkinter 

Lancement : python3 app.py


"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import threading

from ui import projects, tasks, search, calendar_export, storage, pipeline_hooks

STATUS_LABELS = {"running": "🔴 En cours", "paused": "⏸️ En pause", "stopped": "⏹️ Arrêté"}
TASK_ARGV_FIELDS = ["titre", "qui", "quand", "statut"]


class MeetingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rise of Agents X -- Agent de réunions")
        self.geometry("1150x700")
        self.minsize(900, 600)
        self.configure(background="#f4f6fa")

        # --- Configuration du style global et des onglets ---
        self.style = ttk.Style(self)
        available_themes = self.style.theme_names()
        if "clam" in available_themes:
            self.style.theme_use("clam")

        self.style.configure("TFrame", background="#f4f6fa")
        self.style.configure("Card.TFrame", background="#ffffff")
        self.style.configure("TLabel", background="#f4f6fa", foreground="#243247", font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"), foreground="#17263c")
        self.style.configure("TButton", padding=(10, 6), font=("Segoe UI", 9))
        self.style.configure("Accent.TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"))
        self.style.configure("TEntry", padding=5)
        self.style.configure("TCombobox", padding=4)
        self.style.configure("TNotebook", background="#f4f6fa", borderwidth=0, tabmargins=(0, 8, 0, 0))
        self.style.configure("TNotebook.Tab", padding=(16, 10), font=("Segoe UI", 10))
        self.style.map("TNotebook.Tab", background=[("selected", "#ffffff"), ("active", "#e8edf5")])
        self.style.configure("Treeview", rowheight=28, font=("Segoe UI", 9), background="#ffffff",
                             fieldbackground="#ffffff")
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=7)

        self.active_project = tk.StringVar()
        self._build_top_bar()

        # Séparateur visuel entre la barre du haut et les onglets
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(4, 16))

        self.tab_transcripts = TranscriptsTab(self.notebook, self)
        self.tab_session = SessionTab(self.notebook, self)
        self.tab_tasks = TasksTab(self.notebook, self)
        self.tab_planning = PlanningTab(self.notebook, self)
        self.tab_resumes = ResumesTab(self.notebook, self)
        self.tab_config = ConfigTab(self.notebook, self)

        for frame, label in [
            (self.tab_transcripts, "📝 Transcripts"), (self.tab_session, "🎙️ Session"),
            (self.tab_tasks, "✅ Tâches"), (self.tab_planning, "📅 Planning"),
            (self.tab_resumes, "📚 Résumés"), (self.tab_config, "⚙️ Configuration"),
        ]:
            self.notebook.add(frame, text=label)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.refresh_project_list()

    def _import_project_folder(self):
        pid = self.active_project.get()
        if not pid:
            messagebox.showwarning("Importer un dossier", "Aucun projet actif sélectionné.")
            return
        dest_dir = projects.project_dir(pid)
        src_dir = filedialog.askdirectory(title="Sélectionner le dossier à importer")
        if not src_dir:
            return
        import os, shutil
        copied_files = []
        for root, dirs, files in os.walk(src_dir):
            rel_root = os.path.relpath(root, src_dir)
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.normpath(os.path.join(rel_root, file)) if rel_root != '.' else file
                dest_path = os.path.join(dest_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)
                copied_files.append(rel_path)
        messagebox.showinfo("Import terminé", f"Dossier importé dans '{dest_dir}'.\n\nFichiers copiés :\n" + '\n'.join(copied_files))
        self.refresh_project_list()

    # --- Barre du haut : sélection / création de projet -----------------------
    def _build_top_bar(self):
        bar = ttk.Frame(self, style="Card.TFrame", padding=(20, 12))
        bar.pack(fill="x", padx=18, pady=(16, 8))

        ttk.Label(bar, text="Rise of Agents X", style="Title.TLabel").pack(side="left", padx=(0, 24))
        ttk.Label(bar, text="Projet").pack(side="left", padx=(0, 6))
        self.project_combo = ttk.Combobox(bar, textvariable=self.active_project, state="readonly", width=24)
        self.project_combo.pack(side="left", padx=(0, 12))
        self.project_combo.bind("<<ComboboxSelected>>", lambda e: self._on_project_changed())

        self.new_project_entry = ttk.Entry(bar, width=20)
        self.new_project_entry.pack(side="left")
        ttk.Button(bar, text="Créer", style="Accent.TButton", command=self._create_project).pack(side="left", padx=(6, 14))

        ttk.Button(bar, text="Importer…", command=self._import_project_folder).pack(side="left", padx=4)
        ttk.Button(bar, text="Fichiers du projet", command=self._show_project_files).pack(side="left", padx=4)

    def _show_project_files(self):
        import os
        pid = self.active_project.get()
        if not pid:
            messagebox.showwarning("Projet", "Aucun projet actif sélectionné.")
            return
        proj_dir = projects.project_dir(pid)
        if not os.path.isdir(proj_dir):
            messagebox.showinfo("Projet", f"Le dossier projet '{proj_dir}' n'existe pas.")
            return
        file_list = []
        for root, dirs, files in os.walk(proj_dir):
            rel_root = os.path.relpath(root, proj_dir)
            for file in files:
                rel_path = os.path.normpath(os.path.join(rel_root, file)) if rel_root != '.' else file
                file_list.append(rel_path)
        win = tk.Toplevel(self)
        win.title(f"Fichiers de {pid}")
        win.geometry("680x420")
        left = ttk.Frame(win)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right = ttk.Frame(win)
        right.pack(side="left", fill="both", expand=True, padx=(0,8), pady=8)
        lbl = ttk.Label(left, text="Fichiers trouvés :")
        lbl.pack()
        lb = tk.Listbox(left, width=40, height=22)
        lb.pack(fill="y", expand=True)
        for fp in sorted(file_list):
            lb.insert("end", fp)
        txt = tk.Text(right, height=22, width=60, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.config(state="disabled")
        def openfile(evt=None):
            if not lb.curselection():
                return
            fp = file_list[lb.curselection()[0]]
            fullpath = os.path.join(proj_dir, fp)
            try:
                with open(fullpath, encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"[Erreur lecture : {str(e)}]"
            txt.config(state="normal")
            txt.delete(1.0, "end")
            txt.insert("end", content)
            txt.config(state="disabled")
        lb.bind("<>", openfile)

    def _create_project(self):
        name = self.new_project_entry.get().strip()
        if not name:
            return
        pid = projects.create_project(name)
        self.new_project_entry.delete(0, "end")
        self.refresh_project_list()
        self.active_project.set(pid)
        self._on_project_changed()

    def refresh_project_list(self):
        ids = projects.list_projects()
        self.project_combo["values"] = ids
        if self.active_project.get() not in ids:
            self.active_project.set(ids[0] if ids else "")
        self._on_project_changed()

    def _on_project_changed(self):
        pid = self.active_project.get()
        if not pid:
            return
        self.refresh_project_views(pid)

    def refresh_project_views(self, project_id):
        if not project_id:
            return
        self.tab_session.refresh(project_id)
        self.tab_tasks.refresh(project_id)
        self.tab_transcripts.refresh(project_id)
        self.tab_resumes.refresh(project_id)

    def _on_tab_changed(self, event):
        self._on_project_changed()


# ------------------------------------------------------------------------------
class TranscriptsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.project_id = None
        self.meetings = []

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        sidebar = ttk.LabelFrame(body, text="Réunions du projet")
        sidebar.pack(side="left", fill="y", padx=(0, 8))
        self.meeting_list = tk.Listbox(sidebar, width=28, height=24, exportselection=False)
        self.meeting_list.pack(fill="y", expand=True, padx=4, pady=4)
        self.meeting_list.bind("<<ListboxSelect>>", self._on_meeting_selected)

        main = ttk.Frame(body)
        main.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(main)
        controls.pack(fill="x", pady=(0, 6))
        self.query_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.query_var).pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text="Rechercher", command=self._search).pack(side="left", padx=5)
        ttk.Button(controls, text="Actualiser", command=self._reload_selected).pack(side="left")
        self.match_label = ttk.Label(main, text="")
        self.match_label.pack(anchor="w", pady=(0, 4))

        self.transcript_text = tk.Text(main, wrap="word", state="disabled")
        self.transcript_text.pack(fill="both", expand=True)
        self.transcript_text.tag_configure("search_hit", background="#ffe680", foreground="#17263c")

    def refresh(self, project_id):
        previous_key = self._selected_key()
        self.project_id = project_id
        self.meetings = search.list_transcript_meetings(project_id)
        self.meeting_list.delete(0, "end")
        for meeting in self.meetings:
            self.meeting_list.insert("end", meeting["label"])

        selected_index = next(
            (i for i, meeting in enumerate(self.meetings) if meeting["key"] == previous_key),
            0 if self.meetings else None,
        )
        if selected_index is None:
            self._set_transcript("Aucune transcription disponible pour ce projet.")
            return
        self.meeting_list.selection_clear(0, "end")
        self.meeting_list.selection_set(selected_index)
        self.meeting_list.activate(selected_index)
        self._reload_selected()

    def _selected_key(self):
        selected = self.meeting_list.curselection() if hasattr(self, "meeting_list") else ()
        if not selected or selected[0] >= len(self.meetings):
            return None
        return self.meetings[selected[0]]["key"]

    def _on_meeting_selected(self, event=None):
        self._reload_selected()

    def _set_transcript(self, text):
        self.transcript_text.config(state="normal")
        self.transcript_text.delete("1.0", "end")
        self.transcript_text.insert("1.0", text)
        self.transcript_text.tag_remove("search_hit", "1.0", "end")
        self.transcript_text.config(state="disabled")
        self.match_label.config(text="")

    def _reload_selected(self):
        key = self._selected_key()
        if key is None or not self.project_id:
            return
        try:
            text, meeting = search.read_transcript_meeting(self.project_id, key)
        except OSError:
            text = "La transcription nettoyée n’est pas encore disponible pour cette réunion."
        self._set_transcript(text)

    def _search(self):
        self._reload_selected()
        query = self.query_var.get().strip()
        if not query:
            return
        self.transcript_text.config(state="normal")
        self.transcript_text.tag_remove("search_hit", "1.0", "end")
        start = "1.0"
        first_match = None
        matches = 0
        while True:
            match = self.transcript_text.search(
                query, start, stopindex="end-1c", nocase=True
            )
            if not match:
                break
            finish = f"{match}+{len(query)}c"
            self.transcript_text.tag_add("search_hit", match, finish)
            if first_match is None:
                first_match = match
            matches += 1
            start = f"{match}+1c"
        self.transcript_text.config(state="disabled")
        self.match_label.config(text=f"{matches} occurrence(s)")
        if first_match:
            self.transcript_text.see(first_match)

class SessionTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.project_id = None

        self.status_label = ttk.Label(self, text="", font=("", 14))
        self.status_label.pack(pady=20)

        btns = ttk.Frame(self)
        btns.pack()
        self.btn_start = ttk.Button(btns, text="▶️ Démarrer", command=self._start)
        self.btn_pause = ttk.Button(btns, text="⏸️ Pause", command=self._pause)
        self.btn_resume = ttk.Button(btns, text="▶️ Reprendre", command=self._resume)
        self.btn_stop = ttk.Button(btns, text="⏹️ Terminer", command=self._stop)
        self.btn_discard = ttk.Button(btns, text="Abandonner la réunion", command=self._discard)
        self.action_buttons = (
            self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop, self.btn_discard
        )
        for b in self.action_buttons:
            b.pack(side="left", padx=6)

    def refresh(self, project_id):
        self.project_id = project_id
        state = projects.load_session_state(project_id)
        status = state.get("status", "stopped")
        self.status_label.config(text=f"Statut : {STATUS_LABELS.get(status, status)}")
        pending = pipeline_hooks.has_unfinalized_meeting(project_id)
        if pending and status == "stopped":
            self.status_label.config(
                text="Finalisation en attente : utilisez Reessayer la finalisation "
                "ou Abandonner la reunion."
            )
        self.btn_start.config(state=("disabled" if status == "running" else "normal"))
        self.btn_pause.config(state=("normal" if status == "running" else "disabled"))
        self.btn_resume.config(state=("normal" if status == "paused" else "disabled"))
        self.btn_stop.config(
            text="Réessayer la finalisation" if status == "stopped" and pending else "Terminer",
            state=("normal" if status != "stopped" or pending else "disabled"),
        )
        self.btn_discard.config(state=("normal" if pending else "disabled"))

    def _run(self, func):
        project_id = self.project_id
        if not project_id:
            return
        for button in self.action_buttons:
            button.config(state="disabled")
        self.status_label.config(text="Action en cours…")

        def run_action():
            try:
                result = func(project_id)
            except Exception as exc:
                result = (False, f"Erreur pendant l'action : {exc}")
            try:
                self.app.after(0, lambda: self._finish_action(project_id, *result))
            except tk.TclError:
                pass

        threading.Thread(target=run_action, daemon=True).start()

    def _finish_action(self, project_id, ok, msg):
        if not self.winfo_exists():
            return
        if self.project_id == project_id:
            self.app.refresh_project_views(project_id)
            self.status_label.config(text=f"{self.status_label.cget('text')}\n{msg}", wraplength=850)
        else:
            for button in self.action_buttons:
                button.config(state="normal")

    def _start(self):
        self._run(pipeline_hooks.start_recording)

    def _pause(self):
        self._run(pipeline_hooks.pause_recording)

    def _resume(self):
        self._run(pipeline_hooks.resume_recording)

    def _stop(self):
        self._run(pipeline_hooks.stop_recording)

    def _discard(self):
        if not self.project_id or not pipeline_hooks.has_unfinalized_meeting(self.project_id):
            return
        confirmed = messagebox.askyesno(
            "Abandonner la réunion ?",
            "Cette action arrêtera la transcription et supprimera les fichiers de la "
            "réunion en cours ainsi que ses éventuelles archives partielles. "
            "Cette suppression ne peut pas être annulée.\n\nAbandonner cette réunion ?",
            icon="warning",
        )
        if confirmed:
            self._run(pipeline_hooks.discard_meeting)


# ------------------------------------------------------------------------------
class TasksTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.project_id = None
        self.view_mode = tk.StringVar(value="current")

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Radiobutton(top, text="Actuelle", variable=self.view_mode, value="current",
                        command=self._refresh_tree).pack(side="left")
        ttk.Radiobutton(top, text="Terminées / passées", variable=self.view_mode, value="archived",
                        command=self._refresh_tree).pack(side="left")
        self.show_events_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Afficher les évènements", variable=self.show_events_var, command=self._refresh_tree).pack(side="left", padx=(12, 4))
        ttk.Button(top, text="➕ Tâche", command=lambda: self._add_node("tache")).pack(side="left", padx=(20, 4))
        ttk.Button(top, text="➕ Évènement", command=lambda: self._add_node("evenement")).pack(side="left")
        ttk.Button(top, text="📝 Générer la liste des tâches", command=self._generate_tasks).pack(side="left", padx=20)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        columns = ("type", "qui", "quand", "statut", "termine")
        self.tree = ttk.Treeview(body, columns=columns, show="tree headings", height=20)
        self.tree.heading("#0", text="Titre")
        self.tree.heading("type", text="Type")
        self.tree.heading("qui", text="Qui")
        self.tree.heading("quand", text="Quand")
        self.tree.heading("statut", text="Statut")
        self.tree.heading("termine", text="Terminé")
        self.tree.column("#0", width=280)
        for c in columns:
            self.tree.column(c, width=100)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.detail = ttk.LabelFrame(body, text="Détail")
        self.detail.pack(side="left", fill="y", padx=(8, 0))
        self.detail_widgets = {}
        self._build_detail_placeholder()

    def _build_detail_placeholder(self):
        for w in self.detail.winfo_children():
            w.destroy()
        ttk.Label(self.detail, text="Sélectionne un élément\ndans l'arbre.", width=30).pack(padx=8, pady=8)

    def refresh(self, project_id):
        self.project_id = project_id
        self._refresh_tree()

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        if hasattr(self, "tree_events") and self.tree_events.winfo_exists():
            self.tree_events.destroy()
        if not self.project_id:
            return

        if self.view_mode.get() == "current":
            nodes = tasks.load_current(self.project_id)
        else:
            nodes = tasks.load_completed(self.project_id)

        visible_nodes = {
            name: node for name, node in nodes.items()
            if self.show_events_var.get() or node.get("type") != "evenement"
        }
        for name, node, depth in tasks.iter_tree(visible_nodes):
            argv = node.get("argv", {})
            parent = node.get("parent")
            parent_iid = parent if parent in visible_nodes else ""
            date_value = argv.get("quand") or argv.get("date") or ""
            self.tree.insert(
                parent_iid,
                "end",
                iid=name,
                text=tasks.get_title(node),
                values=(
                    node.get("type", tasks.DEFAULT_TYPE),
                    argv.get("qui", "") or "",
                    date_value,
                    argv.get("statut", "") or "",
                    "✓" if node.get("completed") else "",
                ),
            )
        self._build_detail_placeholder()
    def _on_select(self, event):
        if self.view_mode.get() != "current":
            return
        sel = self.tree.selection()
        if not sel:
            return
        name = sel[0]
        nodes = tasks.load_current(self.project_id)
        node = nodes.get(name)
        if node:
            self._build_detail_form(name, node)

    def _build_detail_form(self, name, node):
        for w in self.detail.winfo_children():
            w.destroy()

        argv = node.get("argv", {})
        node_type = node.get("type", tasks.DEFAULT_TYPE)
        row = 0

        ttk.Label(self.detail, text=f"Type : {node_type}").grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=2)
        row += 1

        node_type = node.get("type", tasks.DEFAULT_TYPE)
        initial_status = argv.get("statut", "a_faire")
        if initial_status == "fait":
            initial_status = "termine"
        completed_var = tk.BooleanVar(
            value=bool(node.get("completed")) or initial_status == "termine"
        )
        statut_var = tk.StringVar(value=initial_status)

        def _sync_status_from_checkbox():
            if node_type == "tache":
                if completed_var.get():
                    statut_var.set("termine")
                elif statut_var.get() == "termine":
                    statut_var.set("a_faire")

        def _sync_checkbox_from_status(event=None):
            if node_type == "tache":
                completed_var.set(statut_var.get() == "termine")

        ttk.Checkbutton(
            self.detail,
            text="Terminé",
            variable=completed_var,
            command=_sync_status_from_checkbox,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=2)
        row += 1
        entries = {}
        titre_var = tk.StringVar(value=argv.get("titre", ""))
        ttk.Label(self.detail, text="Titre").grid(row=row, column=0, sticky="w", padx=6)
        ttk.Entry(self.detail, textvariable=titre_var, width=25).grid(row=row, column=1, padx=6, pady=2)
        entries["titre"] = titre_var
        row += 1

        if node_type == "tache":
            for field, label in [("qui", "Qui"), ("quand", "Quand (AAAA-MM-JJ)"), ]:
                var = tk.StringVar(value=argv.get(field, "") or "")
                ttk.Label(self.detail, text=label).grid(row=row, column=0, sticky="w", padx=6)
                ttk.Entry(self.detail, textvariable=var, width=25).grid(row=row, column=1, padx=6, pady=2)
                entries[field] = var
                row += 1

            ttk.Label(self.detail, text="Statut").grid(row=row, column=0, sticky="w", padx=6)
            status_combo = ttk.Combobox(
                self.detail,
                textvariable=statut_var,
                values=["a_faire", "en_cours", "termine"],
                state="readonly",
                width=22,
            )
            status_combo.grid(row=row, column=1, padx=6, pady=2)
            status_combo.bind("<<ComboboxSelected>>", _sync_checkbox_from_status)
            entries["statut"] = statut_var
            row += 1
        else:
            for key, val in argv.items():
                if key == "titre":
                    continue
                var = tk.StringVar(value=str(val) if val is not None else "")
                ttk.Label(self.detail, text=key).grid(row=row, column=0, sticky="w", padx=6)
                ttk.Entry(self.detail, textvariable=var, width=25).grid(row=row, column=1, padx=6, pady=2)
                entries[key] = var
                row += 1

        warnings = tasks.missing_fields_warnings(node)
        if warnings:
            ttk.Label(self.detail, text="⚠️ " + " / ".join(warnings), foreground="darkorange",
                      wraplength=220).grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=4)
            row += 1

        def _save():
            new_argv = {k: (v.get() or None) for k, v in entries.items()}
            tasks.update_node(self.project_id, name, argv_updates=new_argv, completed=completed_var.get())
            self._refresh_tree()

        ttk.Button(self.detail, text="💾 Enregistrer", command=_save).grid(
            row=row, column=0, columnspan=2, pady=10)

    def _add_node(self, node_type):
        if not self.project_id:
            return
        default_titre = "Nouvelle tâche" if node_type == "tache" else "Nouvel évènement"
        tasks.create_node(self.project_id, node_type=node_type, argv={"titre": default_titre})
        self._refresh_tree()

    def _generate_tasks(self):
        if not self.project_id:
            return
        ok, msg = pipeline_hooks.generate_tasks(self.project_id)
        (messagebox.showinfo if ok else messagebox.showwarning)("Génération", msg)
        self._refresh_tree()


# ------------------------------------------------------------------------------
class PlanningTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ttk.Label(self, text="Génère un fichier .ics à partir des dates trouvées dans les "
                              "tâches/évènements du projet actif.").pack(padx=8, pady=12)
        ttk.Button(self, text="📅 Générer le planning", command=self._generate).pack()

    def _generate(self):
        project_id = self.app.active_project.get()
        if not project_id:
            return
        nodes = tasks.load_current(project_id)
        default_path = projects.project_dir(project_id) / "archive" / "calendar" / "latest.ical"
        calendar_export.save_ics(nodes, default_path, calendar_name=project_id)

        dest = filedialog.asksaveasfilename(
            title="Enregistrer le planning sous...", defaultextension=".ics",
            initialfile="planning.ics", filetypes=[("Calendrier iCal", "*.ics")],
        )
        if dest:
            calendar_export.save_ics(nodes, dest, calendar_name=project_id)
            messagebox.showinfo("Planning", f"Planning enregistré : {dest}")
        else:
            messagebox.showinfo("Planning", f"Planning généré dans le projet : {default_path}")


# ------------------------------------------------------------------------------
class ResumesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.project_id = None
        self.reports = []

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        sidebar = ttk.LabelFrame(body, text="Comptes rendus archivés")
        sidebar.pack(side="left", fill="y", padx=(0, 8))
        self.report_list = tk.Listbox(sidebar, width=30, height=24, exportselection=False)
        self.report_list.pack(fill="y", expand=True, padx=4, pady=4)
        self.report_list.bind("<<ListboxSelect>>", self._on_report_selected)

        main = ttk.Frame(body)
        main.pack(side="left", fill="both", expand=True)
        self.info_label = ttk.Label(main, text="Sélectionnez un compte rendu.")
        self.info_label.pack(anchor="w", pady=(4, 12))
        self.open_btn = ttk.Button(
            main,
            text="Ouvrir le compte rendu dans le navigateur",
            command=self._open_selected,
            state="disabled",
        )
        self.open_btn.pack(anchor="w")

    def refresh(self, project_id):
        previous_path = self._selected_path()
        self.project_id = project_id
        reports_dir = projects.meeting_reports_dir(project_id)
        self.reports = sorted(reports_dir.glob("*.html"), key=lambda path: path.name, reverse=True)
        self.report_list.delete(0, "end")
        for path in self.reports:
            self.report_list.insert("end", search.meeting_label(path.stem))

        selected_index = next(
            (i for i, path in enumerate(self.reports) if path == previous_path),
            0 if self.reports else None,
        )
        if selected_index is None:
            self.info_label.config(text="Aucun compte rendu archivé pour ce projet.")
            self.open_btn.config(state="disabled")
            return
        self.report_list.selection_clear(0, "end")
        self.report_list.selection_set(selected_index)
        self.report_list.activate(selected_index)
        self._show_selected()

    def _selected_path(self):
        selected = self.report_list.curselection() if hasattr(self, "report_list") else ()
        if not selected or selected[0] >= len(self.reports):
            return None
        return self.reports[selected[0]]

    def _on_report_selected(self, event=None):
        self._show_selected()

    def _show_selected(self):
        path = self._selected_path()
        if path is None:
            return
        self.info_label.config(text=f"Compte rendu : {path.name}")
        self.open_btn.config(state="normal")

    def _open_selected(self):
        path = self._selected_path()
        if path and path.is_file():
            webbrowser.open(path.resolve().as_uri())

class ConfigTab(ttk.Frame):
    API_PROVIDERS = ["openai", "anthropic", "azure", "google", "whisper", "whisperx", "gradium"]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        cfg = storage.load_config()

        self.canvas = tk.Canvas(self, background="#f4f6fa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = ttk.Frame(self.canvas, padding=(24, 18, 24, 28))
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.content_window, width=event.width))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        ttk.Label(self.content, text="Configuration", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))
        ttk.Label(self.content, text="Stockage", font=("", 11, "bold")).grid(row=1, column=0, sticky="w", padx=8, pady=(12, 2))
        self.storage_mode = tk.StringVar(value=cfg["storage_mode"])
        ttk.Radiobutton(self.content, text="Local", variable=self.storage_mode, value="local",
                        command=self._toggle_github_field).grid(row=2, column=0, sticky="w", padx=16)
        ttk.Radiobutton(self.content, text="GitHub", variable=self.storage_mode, value="github",
                        command=self._toggle_github_field).grid(row=2, column=1, sticky="w")

        ttk.Label(self.content, text="Chemin local du repo (doit contenir data/projects/)").grid(
            row=3, column=0, sticky="w", padx=16, pady=(6, 0))
        self.repo_path_var = tk.StringVar(value=cfg["github_repo_path"])
        self.repo_path_entry = ttk.Entry(self.content, textvariable=self.repo_path_var, width=50)
        self.repo_path_entry.grid(row=4, column=0, columnspan=2, sticky="w", padx=16)

        ttk.Label(self.content, text="Mode d'exécution", font=("", 11, "bold")).grid(
            row=5, column=0, sticky="w", padx=8, pady=(20, 2))
        self.execution_mode = tk.StringVar(value=cfg["execution_mode"])
        ttk.Radiobutton(self.content, text="Local (Ollama / Colab)", variable=self.execution_mode, value="local",
                        command=self._toggle_exec_fields).grid(row=6, column=0, sticky="w", padx=16)
        ttk.Radiobutton(self.content, text="API (OpenAI / Whisper)", variable=self.execution_mode, value="api",
                        command=self._toggle_exec_fields).grid(row=6, column=1, sticky="w")

        ttk.Label(self.content, text="Backend local").grid(row=7, column=0, sticky="w", padx=16, pady=(6, 0))
        self.local_backend_var = tk.StringVar(value=cfg["local_model_backend"])
        self.local_backend_combo = ttk.Combobox(
            self.content, textvariable=self.local_backend_var, values=["ollama", "colab"], state="readonly", width=20)
        self.local_backend_combo.grid(row=8, column=0, sticky="w", padx=16)

        ttk.Label(self.content, text="Modèle API").grid(row=7, column=1, sticky="w", pady=(6, 0))
        self.api_model_var = tk.StringVar(value=cfg["api_model"])
        self.api_model_entry = ttk.Entry(self.content, textvariable=self.api_model_var, width=30)
        self.api_model_entry.grid(row=8, column=1, sticky="w")

        ttk.Label(self.content, text="Nettoyage de transcription", font=("", 11, "bold")).grid(
            row=9, column=0, sticky="w", padx=8, pady=(12, 2))
        ttk.Label(self.content, text="Backend clean_txt").grid(row=10, column=0, sticky="w", padx=16)
        self.clean_ai_var = tk.StringVar(value=cfg["clean_ai"])
        ttk.Combobox(self.content, textvariable=self.clean_ai_var, values=["api", "local"],
                     state="readonly", width=18).grid(row=10, column=1, sticky="w")
        self.clean_diarized_var = tk.BooleanVar(value=cfg["clean_diarized"])
        ttk.Checkbutton(self.content, text="Transcription avec étiquettes de locuteurs (--diarized)",
                        variable=self.clean_diarized_var).grid(row=11, column=0, columnspan=2,
                                                               sticky="w", padx=16)
        ttk.Label(self.content, text="Fichier de sortie (vide = valeur par défaut)").grid(
            row=12, column=0, sticky="w", padx=16)
        self.clean_output_var = tk.StringVar(value=cfg["clean_output"])
        ttk.Entry(self.content, textvariable=self.clean_output_var, width=50).grid(
            row=12, column=1, sticky="w")
        ttk.Label(self.content, text="Modèle clean_txt (vide = valeur par défaut)").grid(
            row=13, column=0, sticky="w", padx=16)
        self.clean_model_var = tk.StringVar(value=cfg["clean_model"])
        ttk.Entry(self.content, textvariable=self.clean_model_var, width=30).grid(
            row=13, column=1, sticky="w")

        ttk.Button(self.content, text="💾 Enregistrer la configuration", command=self._save).grid(
            row=14, column=0, sticky="w", padx=16, pady=20)
        self.push_btn = ttk.Button(self.content, text="⬆️ Pousser sur GitHub maintenant", command=self._push)
        self.push_btn.grid(row=14, column=1, sticky="w")

        self._toggle_github_field()
        self._toggle_exec_fields()

        ##### --- GESTION DES CLÉS API FOURNISSEURS --- #####
        ttk.Label(self.content, text="Clés API (OpenAI, Anthropic...)", style="Section.TLabel").grid(
            row=16, column=0, sticky="w", padx=8, pady=(24, 8))
        api_row = 17
        self.api_provider_var = tk.StringVar(value=self.API_PROVIDERS[0])
        self.api_key_var = tk.StringVar(value="")
        self.api_combo = ttk.Combobox(
            self.content, textvariable=self.api_provider_var,
            values=self.API_PROVIDERS, state="readonly", width=18)
        self.api_combo.grid(row=api_row, column=0, sticky="w", padx=16)
        self.api_combo.bind("<<ComboboxSelected>>", self._on_api_provider_select)
        self.api_key_entry = ttk.Entry(self.content, textvariable=self.api_key_var, show="*", width=28)
        self.api_key_entry.grid(row=api_row, column=1, sticky="w")
        ttk.Button(self.content, text="Ajouter / Mettre à jour", command=self._add_update_api_key).grid(
            row=api_row, column=2, sticky="w", padx=8)

        self.api_keys_frame = ttk.Frame(self.content)
        self.api_keys_frame.grid(row=api_row+1, column=0, columnspan=3, sticky="w", padx=20, pady=(10, 6))
        self._api_add_lines = []
        self.api_add_btn = ttk.Button(self.content, text="Créer une clé", command=self._add_api_line)
        self.api_add_btn.grid(row=28, column=0, padx=20, pady=(2, 6), sticky="w")
        self._refresh_api_keys_list()

    def _on_mousewheel(self, event):
        if self.winfo_exists():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _toggle_github_field(self):
        state = "normal" if self.storage_mode.get() == "github" else "disabled"
        self.repo_path_entry.config(state=state)
        self.push_btn.config(state=state)

    def _toggle_exec_fields(self):
        local = self.execution_mode.get() == "local"
        self.local_backend_combo.config(state=("readonly" if local else "disabled"))
        self.api_model_entry.config(state=("normal" if not local else "disabled"))

    def _current_cfg(self):
        cfg = storage.load_config()
        base = {
            "storage_mode": self.storage_mode.get(),
            "github_repo_path": self.repo_path_var.get(),
            "execution_mode": self.execution_mode.get(),
            "local_model_backend": self.local_backend_var.get(),
            "api_model": self.api_model_var.get(),
            "clean_ai": self.clean_ai_var.get(),
            "clean_diarized": self.clean_diarized_var.get(),
            "clean_output": self.clean_output_var.get().strip(),
            "clean_model": self.clean_model_var.get().strip(),
        }
        return base

    def _save(self):
        storage.save_config(self._current_cfg())
        app = self.winfo_toplevel()
        if hasattr(app, "refresh_project_list"):
            app.refresh_project_list()
        messagebox.showinfo("Configuration", "Configuration enregistrée.")

    def _push(self):
        ok, msg = storage.push_to_github(self._current_cfg())
        (messagebox.showinfo if ok else messagebox.showerror)("GitHub", msg)

    def _on_api_provider_select(self, event=None):
        provider = self.api_provider_var.get()
        key = storage.get_api_key(provider)
        self.api_key_var.set(key if key else "")

    def _add_update_api_key(self):
        provider = self.api_provider_var.get()
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showwarning("Clé API", f"Aucune clé renseignée pour '{provider}'.")
            return
        storage.set_api_key(provider, key)
        messagebox.showinfo("Clé API", f"Clé enregistrée pour '{provider}'.")
        self._refresh_api_keys_list()

    def _delete_api_key(self, provider):
        if messagebox.askyesno("Suppression clé API", f"Supprimer la clé pour '{provider}' ?"):
            storage.delete_api_key(provider)
            self._refresh_api_keys_list()
            if self.api_provider_var.get() == provider:
                self.api_key_var.set("")

    def _add_api_line(self):
        used = {p for p in self.API_PROVIDERS if storage.get_api_key(p)}
        already_in_lines = set([w['provider_var'].get() for w in self._api_add_lines if 'provider_var' in w])
        candidates = [p for p in self.API_PROVIDERS if p not in used and p not in already_in_lines]
        if not candidates:
            messagebox.showinfo("Clé API", "Tous les fournisseurs gérés ont déjà une clé ou sont en cours d'ajout.")
            return
        provider_var = tk.StringVar(value=candidates[0])
        key_var = tk.StringVar(value="")
        row = len(self.api_keys_frame.winfo_children()) + len(self._api_add_lines)

        combo = ttk.Combobox(self.api_keys_frame, textvariable=provider_var, values=candidates, state="readonly", width=14)
        combo.grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(self.api_keys_frame, textvariable=key_var, show="*", width=18)
        entry.grid(row=row, column=1, sticky="w")
        def add():
            provider = provider_var.get()
            key = key_var.get().strip()
            if not key:
                messagebox.showwarning("Clé API", f"Aucune clé renseignée pour '{provider}'.")
                return
            storage.set_api_key(provider, key)
            self._clear_api_add_lines()
            self._refresh_api_keys_list()
            messagebox.showinfo("Clé API", f"Clé enregistrée pour '{provider}'.")
        add_btn = ttk.Button(self.api_keys_frame, text="Ajouter", width=12, command=add)
        add_btn.grid(row=row, column=2, padx=8, sticky="w")

        line = {'provider_var': provider_var, 'key_var': key_var, 'combo': combo, 'entry': entry, 'add_btn': add_btn}
        self._api_add_lines.append(line)

    def _clear_api_add_lines(self):
        for w in self._api_add_lines:
            for wid in ['combo', 'entry', 'add_btn']:
                widget = w.get(wid)
                if widget is not None:
                    widget.destroy()
        self._api_add_lines = []

    def _refresh_api_keys_list(self):
        for widget in self.api_keys_frame.winfo_children():
            widget.destroy()
        self._clear_api_add_lines()
        row = 0
        for provider in self.API_PROVIDERS:
            if storage.get_api_key(provider):
                ttk.Label(self.api_keys_frame, text=provider, width=14).grid(row=row, column=0, sticky="w")
                ttk.Label(self.api_keys_frame, text="***** (protégée)", width=18, foreground="grey").grid(row=row, column=1, sticky="w")
                btn = ttk.Button(self.api_keys_frame, text="Supprimer", width=12,
                                 command=lambda p=provider: self._delete_api_key(p))
                btn.grid(row=row, column=2, padx=8, sticky="w")
                row += 1


if __name__ == "__main__":
    app = MeetingApp()
    app.mainloop()
