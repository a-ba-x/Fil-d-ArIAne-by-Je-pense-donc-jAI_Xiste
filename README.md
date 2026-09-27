# Fil d’ArIAne

Fil d’ArIAne is a desktop assistant for recording and organizing meetings. It can capture audio, transcribe and clean meeting conversations, generate structured summaries, and track follow-up tasks and events. It is built with Python and Tkinter.

## Features

- Create and switch between meeting projects.
- Start, pause, resume, and finalize a meeting recording.
- Transcribe recorded audio with Gradium.
- Search archived transcripts and preview generated HTML meeting reports.
- Review tasks and events extracted from meetings, edit them, and mark tasks complete.
- Export dated tasks and events as an iCalendar (`.ics`) file.
- Store project data locally or in a configured local Git clone.
- Choose API or local model options for supported extraction workflows.

## Requirements

- Python 3.10 or later.
- Tkinter (included with most Python installers; on some Linux distributions install the OS package, for example `python3-tk`).
- A microphone for recording meetings.
- API credentials for the online services you plan to use. Gradium is used for audio transcription; OpenAI credentials are needed for API-based cleaning and summaries. Local model workflows need Ollama installed and running.

## Setup

Create and activate a virtual environment from the repository root, then install dependencies:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate` instead.

### Configure API keys

Create a `.env` file in the repository root and add the keys for the services you use:

```dotenv
GRADIUM_API_KEY=your_gradium_key
OPENAI_API_KEY=your_openai_key
```

The application can also manage provider keys from **Settings**. Keep `.env` private; do not commit real credentials.

### Run the app

Run the UI from the `scripts` directory so its local Python modules resolve correctly:

```powershell
cd scripts
python app.py
```

On macOS or Linux, use the same commands after activating the virtual environment.

## Using the app

1. Create or select a project in the top bar.
2. Open **Session** and start recording. Pause and resume as needed, then finish the meeting to process and archive it.
3. Use **Search** to browse transcripts, **Tasks** to review extracted follow-ups, and **Summary** to open generated reports.
4. Use **Planning** to export dated tasks and events as an `.ics` file for import into a calendar application.

Calendar export creates a project copy under `projects/<project-id>/archive/calendar/latest.ical` and offers a Save As dialog for another copy. Import and ongoing synchronization are handled by the user's calendar application.

## Project layout

```text
scripts/
  app.py                 Tkinter desktop UI
  loop.py                Recording/transcription processing loop
  transcription/         Audio capture and Gradium transcription
  extraction/            Transcript cleaning and report generation
  ui/                    Project, task, search, storage, and export logic
  templates/             Meeting report HTML template
  data/app_config.json   Application settings
assets/                 App logo and window/application icon files
projects/                Local per-project data (ignored by Git)
data/logs/               Runtime logs
```

The Tkinter window and taskbar load `assets/fil-d-ariane-app-icon.png` and `assets/fil-d-ariane.ico`. The `.ico` also contains multiple sizes and is ready to pass as the icon when configuring a Windows executable build. This repository does not currently include an executable packaging configuration.

Project folders contain recordings, transcript archives, reports, session state, and task/event data. Local project data and `.env` credentials should be treated as private.

## Configuration notes

- The Settings page controls storage location, execution mode, cleaning options, and API keys.
- Local model workflows use Ollama by default. Configure the model name with `OLLAMA_MODEL` if needed; the default is `qwen2.5-coder:1.5b`.
- API model settings and provider choices are available in the app configuration.
- If `tkinterweb` is unavailable, reports can still be opened in the system browser; the app can install the embedded viewer from its Summary page.

## Troubleshooting

- **Tkinter cannot be imported:** install the Tk support package for your Python distribution (on Linux, commonly `python3-tk`).
- **Recording fails:** check that a microphone is connected and accessible to the operating system.
- **Transcription or summary fails:** check the relevant API key and network access. Processing logs are written under `data/logs/`.
- **Ollama mode fails:** start Ollama and confirm the configured model is available locally.
