---
name: duetsheet
description: Start Duetsheet, the interactive report that the user reviews in the browser (comments, lasso on charts, change history) while you write and revise it as report.json. Use when the user asks to start or open Duetsheet, to write a report from a data folder for review, or to read and handle their Duetsheet annotations.
---

# Duetsheet

Duetsheet is installed in `${CLAUDE_PLUGIN_ROOT}`:
- `duetsheet.py`: the launcher (Python 3.8+, standard library only)
- `AGENTS.md`: the data model and the rules for writing `report.json`. Read it fully before you write anything.

Reply in the user's language. Tell the user what you are about to do before each step that writes files or starts a program.

## Start

1. **Choose the folder.** Use the folder the user names; otherwise the current working folder. It is normally the folder with the raw data. Say which folder you will use.
2. **Find the report.** If the folder has `report.json`, that folder is the project folder (raw data in `data/`). Otherwise the report is `<folder>/duetsheet/report.json` and the raw data is the folder itself. Never modify raw data files.
3. **Read** `${CLAUDE_PLUGIN_ROOT}/AGENTS.md`.
4. **If there is no report yet**: list the data files, propose the report in a few lines (topic, figures, tables) and wait for the user to agree. Then write `report.json` as AGENTS.md describes ("Write a new report"). Record each dataset's source (path relative to the folder of report.json, and SHA-256). Lay it out for reading: a one-page summary first, then an `outline` block (a clickable table of contents), and each figure's discussion next to the figure (`breakBefore: "beside"`, see "Layout" in AGENTS.md).
5. **Check** before starting:
   `python "${CLAUDE_PLUGIN_ROOT}/duetsheet.py" check "<folder>"`
   Fix every ERROR and run it again until it prints OK.
6. **Start** it as a background process (it keeps running):
   `python "${CLAUDE_PLUGIN_ROOT}/duetsheet.py" "<folder>"`
   It opens the report in the browser, already connected to the folder. Tell the user it is open, and that they can review in Edit mode and click "Finish this round" when done.

## While it runs

- The launcher prints every problem the page reports as `[duetsheet] ERROR ...` or `[duetsheet] WARNING ...`, and appends it to `errors.log` next to `report.json`. Check the launcher output after each of your writes and whenever the user says something went wrong. Fix what you caused, then run `check` again.
- When the user asks you to handle their comments ("read the annotations", "revise"), follow "Revise the report from the user's annotations" in AGENTS.md. Read `report.json` fresh right before you change it, change only the documents you mean to change, and write the whole file in one step.
- Write strict JSON: no NaN or Infinity (write null; in Python use `json.dump(..., allow_nan=False)`), UTF-8 without a byte order mark. Run `check` after every write.
- The page reloads `report.json` within about two seconds of your write. Do not edit while the user is still reviewing a round; wait until they tell you they are done.
- To stop Duetsheet, stop the background process. To open it again later, start it again the same way.

## Other requests

- **A desktop shortcut** so the user can open the report without you: `python "${CLAUDE_PLUGIN_ROOT}/duetsheet.py" shortcut "<folder>"`.
- **A read-only copy** to send to someone: tell the user to click **Export read-only copy** in the page; it is saved in `exports/`.
- **Other AI tools** (Copilot, Cursor, Codex) working in the same folder: `python "${CLAUDE_PLUGIN_ROOT}/duetsheet.py" init-agent "<folder>"` adds a short `AGENTS.md` there that points them to the rules.
