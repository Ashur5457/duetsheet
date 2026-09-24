# Duetsheet tutorial

This tutorial walks through one full review cycle: open a report, bring in raw data, trace a figure back to it, comment on a figure, let an AI agent revise the report, and check what it changed. It uses the demo project in [`examples/demo-project`](../examples/demo-project) (synthetic data, not experimental results).

You need a desktop computer. There are two ways to open a report:

- **From Claude Code (fastest)**: install once (section 0), then see section 0b. Claude starts Duetsheet for your data folder and the report opens by itself.
- **By hand**: open `duetsheet.html` in Chrome or Edge and choose the folder (steps 1 and 2 below). No install is needed.

A third path, Claude Artifacts on claude.ai, is at the end.

## 0. Install

Every way of using Duetsheet on your computer needs **Python 3.8 or later** (nothing else: no packages to install). Check with `python --version`.

### With Claude Code in a terminal, VS Code or JetBrains

In Claude Code (with a subscription or an API key), type these two lines once:

```
/plugin marketplace add Ashur5457/duetsheet
/plugin install duetsheet@duetsheet
```

Start a new session and type `/`: **duetsheet** is in the list.

- **Update**: `/plugin marketplace update duetsheet`, then start a new session.
- **Remove**: `/plugin uninstall duetsheet@duetsheet`.

### With the Claude desktop app, or without the plugin system

The desktop app cannot add plugin marketplaces with `/plugin`. Install the skill from a copy of the repository instead (you need [git](https://git-scm.com/)). In a terminal, in the folder where you want to keep Duetsheet:

```bash
git clone https://github.com/Ashur5457/duetsheet.git && python duetsheet/duetsheet.py install-skill
```

This installs the `/duetsheet` skill into `~/.claude/skills/`, where the desktop app, the terminal and the editor extensions all find it. Start a new session and type `/`: **duetsheet** is in the list.

- **Update**: run `git pull` in the `duetsheet` folder, then `python duetsheet.py install-skill` again.
- **Moved the folder?** Run `python duetsheet.py install-skill` again from its new place.
- **Remove**: delete the folder `~/.claude/skills/duetsheet`.
- No git? [Download the ZIP](https://github.com/Ashur5457/duetsheet/archive/refs/heads/main.zip), unzip it, and run `python duetsheet.py install-skill` in the unzipped folder.

### With other AI agents (Copilot, Cursor, Codex, Gemini CLI, Cline and others)

These agents do not use Claude Code skills, but most of them read an `AGENTS.md` file in the folder they work in. Get Duetsheet (clone or [download the ZIP](https://github.com/Ashur5457/duetsheet/archive/refs/heads/main.zip)), then, once per data folder:

```bash
python path/to/duetsheet.py init-agent "path/to/data-folder"
```

It adds a short section to `AGENTS.md` and `CLAUDE.md` in the data folder (or creates the files) that tells any agent where the full rules are and how to check, start and listen to the report. Claude Code reads `CLAUDE.md` when you open it in that folder, so it knows the rules from the first message. Existing content in those files is kept: only the part between `<!-- duetsheet:start -->` and `<!-- duetsheet:end -->` belongs to Duetsheet, and running the command again only refreshes that part.

Duetsheet itself never calls an AI model or needs an API key: your agent reads and writes `report.json`.

### Opening a report later without an agent

- `python path/to/duetsheet.py shortcut "path/to/data-folder"` puts a shortcut on your desktop. Double-click it to open the report; keep the window that opens while you use it.
- To show the report to someone who has nothing installed, click **Export read-only copy** at the top of the page and send them the HTML file from `exports/`. It opens in any browser.

## 0b. Start from Claude Code

Open Claude Code in the folder that holds your raw data and type `/duetsheet`. Claude reads `AGENTS.md`, proposes a report, writes it after you agree, checks it with `duetsheet.py check`, and starts the launcher. Your browser opens the report, already connected to the folder: skip to step 3.

Without Claude Code you can start the launcher yourself: `python path/to/duetsheet.py "path/to/data-folder"`.

Duetsheet keeps everything it writes in a `duetsheet/` subfolder of your data folder (`report.json`, uploaded images, exports, your figure habits). The raw data files stay where they are and are never modified.

**One rule to know before you start: where files go.** Your raw data must be *inside* the folder you open, but *outside* `duetsheet/`; any subfolders are fine. What is computed from it goes *inside* `duetsheet/`: tables in `derived_data/`, the scripts that compute them in `scripts/`.

```
my-experiment/                the folder you open
  Data_R1/run001.xlsx         raw data: stays where it is, only read
  notes/instrument.csv
  duetsheet/                  made by Duetsheet
    report.json
    derived_data/cells.csv    tables computed from the raw data
    scripts/make_cells.py     the scripts that compute them
```

If some of your data is somewhere else (another drive, your Downloads folder), move or copy it into the folder first; Claude will ask you rather than do it. Only files inside the folder can be traced from a figure back to the raw data (section 3b).

## 1. Open Duetsheet

Download [`duetsheet.html`](../duetsheet.html) (or clone the repository) and open it in Chrome or Edge. The first time, a short welcome card explains the four steps. You can bring it back at any time with the **?** button.

![Welcome card](welcome.png)

The interface follows your browser language (English, Traditional Chinese, Simplified Chinese, Japanese, Korean or Spanish). Change it from the menu at the top right, or add your own language there ([how](translating.md)).

## 2. Open the project folder

Until you open a folder, the yellow bar reminds you that nothing is saved. Click **Open project folder** and choose `examples/demo-project`. For your own work, choose the folder that holds your raw data: Duetsheet creates `duetsheet/report.json` in it.

![The page before a folder is opened](open-folder.png)

The bar turns green: every change is now saved to `report.json` automatically. **View** shows the report as 16:9 pages; turn pages with the arrow keys or the buttons below.

![View mode with a project folder open](view-mode.png)

A project folder looks like this:

```
demo-project/
  report.json      the report
  data/            raw data (CSV, TSV, JSON)
  derived_data/    tables computed from the raw data
  scripts/         the scripts that compute them
  habits/          your own example figures and .mplstyle files
  assets/          images uploaded in the page (created when needed)
  exports/         files the page exports (created when needed)
```

The demo uses this project layout, with `report.json` at the top and the raw data in `data/`. When you open your own data folder, the same files go into its `duetsheet/` subfolder instead, and every data file in the folder (subfolders included) is listed in the Folder tab.

## 3. Bring in raw data

Open the **Folder** tab in the panel. Files in `data/` are listed with their status. Click **Import** next to `cycle4-runs.csv`.

![The Folder tab after importing a data file](folder-tab.png)

The file becomes a dataset. Duetsheet records where it came from: the path and a SHA-256 fingerprint of the file. If the file changes later, the Folder tab says "changed since import", charts that use it show a warning in Edit mode, and **Update** imports the new version (the change log keeps both).

**Many files at once.** Tick files (Shift-click ticks a range; the box on a folder ticks the whole folder). A bar appears at the bottom: **Add to a chart…** or **Replace the data of a chart…** asks which chart, lets you add a note (for example *one series per round*), and creates a comment with the exact file list for your agent; **Ask the agent to revise** sends it. **Datasets in the report** lists every dataset with the charts that use it; tick several and **Delete selected datasets** (the files are never touched).

Files are grouped by folder: **Import all** imports every file of one folder at once. **Show in folder** opens the file's folder in File Explorer or Finder (with the launcher; otherwise it copies the path).

To plot the new data, switch to **Edit**, click **Add chart**, open **Chart settings** and pick the dataset.

## 3b. Trace a figure back to its raw data

Most report data is not a raw file: a script combines or summarises raw files into a table first. Duetsheet keeps that chain. Every time your agent runs a script, it records a **step** (`python duetsheet.py step`): the script, the command, the parameters, and every input and output file with its fingerprint.

Under each chart and table, a small line shows where its data comes from, for example *Source: cycles1-3.csv ← combine_cycles.py ← 3 raw files*. Its dot shows the state of the whole chain:

- **green**: every file is exactly as recorded;
- **red**: something changed or is missing (a raw file, a script, a derived table), so the figure needs recomputing;
- **grey**: not checked (for example in a read-only copy, where the files are not at hand).

Click the line to see the whole chain: the dataset, the derived file, the step that made it, and its inputs, down to the raw files (grouped by folder).

The **Folder** tab has the **Data chain** overview: every derived file with the script and inputs it comes from and how many charts use it, then the raw data grouped by folder, then the scripts. It works backwards too: open a raw data folder and click **What depends on these files?**, or click a single file, to see which derived files, datasets and charts would change if it did.

**New data.** A step remembers the patterns its inputs were found with, for example `Data_TOSCAT/*/raw data_ch*.xlsx`. To add a new round or replace files, just put them into the folder with File Explorer or Finder; there is no path to type. The Folder tab then lists them as *new, not used yet*, and the steps that should use them turn red. Ask your agent to recompute (or click **Ask the agent to revise**).

Raw data can be large. Duetsheet compares size and modification date first and only reads a file again when they differ; the launcher keeps the fingerprints it computed in `duetsheet/cache/`. `python duetsheet.py check <folder>` reports the same states as warnings, and `check --deep` reads every file.

## 4. Review: edit and comment

Switch to **Edit**. You can:

- change titles, text and captions directly (every change is recorded);
- change chart settings (type, dataset, columns, axis labels, range, log scale), and under **Data series** add more series from other datasets, each with its own colour and legend name;
- drag blocks to reorder them and click the dividers to control page breaks;
- write a comment under any block, with preset tags such as **Use log scale** or **Highlight key points**.

On a chart you can point at the exact data: click **Lasso on figure** (or **Box on figure**) and draw around points, or simply click one point. The comment then stores the data range and the ids of the points inside it, which is what the agent reads.

![A lasso and a single data point marked on a chart, with the comments in the panel](edit-annotate.png)

When you have finished a batch of feedback, click **Finish this round** at the top of the page (it appears as soon as you change something), or in the **Changes** tab.

## 5. Let your agent revise the report

**With one button.** If Claude Code started the report (`/duetsheet`), it keeps listening in the background. Click **Ask the agent to revise** at the top: it finishes your round and hands your comments to the agent. Next to the button you see *Request sent*, then *The agent is revising the report…*, then *The agent handled N comments*; the report reloads by itself. Waiting costs the agent nothing; only the revision itself uses it.

If no agent is listening (for example, you opened the report with a desktop shortcut), the button shows a prompt to copy and paste into your agent. Your request is kept, and the agent picks it up and then keeps listening for the next one.

**By asking.** You can also open your AI agent (Claude Code, Codex, Gemini CLI, Cursor, ...) in the same folder and ask:

> Read AGENTS.md from the Duetsheet repository, then read the open annotations in report.json and revise the report.

[`AGENTS.md`](../AGENTS.md) tells the agent how to make the smallest change for each comment, record every change as its own, reply under each comment, and close its round. Keep Duetsheet open: within a few seconds the page reloads `report.json` and shows the agent's work.

![The agent's replies under each comment, and Figure 1 now on a log axis](agent-reply.png)

Comments the agent handled are marked **Done** with its reply. A comment it could not settle stays **Open**, with a question for you. To answer the agent, write under its reply and click **Reply**: the comment opens again, and the next **Ask the agent to revise** sends your answer. The agent bar above the report shows whether an agent is listening and what it is doing.

## 6. Check what changed

The **Changes** tab shows the current round; **Show full history** shows every round. Text changes are shown as inline differences; setting changes read as "before → after". Each change can be reverted on its own.

The timeline has one row per block and one column per round. Filled markers are edits (blue: you, purple: the agent), circles are comments. Click a column to see only that round.

![The change history and the timeline](change-log.png)

## 7. Teach it your figure style and your writing

The **Folder** tab has two parts: **Data** (the data chain and your data files) and **Habits**.

Put figures you like in `habits/figures/`: SVG exports from Origin, matplotlib, R or other tools, and `.mplstyle` files. In Folder > Habits, click **Learn my habits**.

Duetsheet measures the SVG files exactly (font, sizes, line width, colours, figure width), reads the `.mplstyle` files, and lists what it found. Each suggestion shows which files it is based on; suggestions that most files agree on are ticked. Nothing changes until you click **Apply selected**.

![Style suggestions learned from the habits folder](style-panel.png)

- **Save current style as my habits** writes `habits/profile.json`. Copy it into the `habits/` folder of your next project to start from the same style.
- PNG and JPG figures cannot be measured by the page. Ask your agent to look at them: it writes its suggestions to `style/proposal`, and they appear in the Style tab for you to confirm in the same way.
- **Export** in the Style tab saves the style as a matplotlib `.mplstyle` file (`exports/duetsheet-style.mplstyle`), so your plotting scripts can use it too.

**Your writing.** Put articles or reports you wrote in `habits/writing/` (.md, .txt, .docx, .pdf). **Measure my texts** shows plain numbers (sentence and paragraph length, lists, bold). For the rest, ask your agent: *Learn my writing style from habits/writing/.* Its suggestions (for example *Give the conclusion first, then the numbers*) appear in Folder > Habits with the files each one comes from; tick the ones to keep and click **Apply selected**. You can also add or remove rules yourself. Agents follow these rules whenever they write or revise text.

**Personal habits.** With the launcher, **Save as my personal habits** keeps your figure style and writing rules in `~/.duetsheet/habits/`, and **Load my personal habits** brings them into any new project.

## 8. Other languages

The interface language never changes the report content or the stored data, so people working in different languages can review the same report.

![The same report with the Japanese interface](language-ja.png)

## When something goes wrong

Errors and warnings do not just flash by: a **⚠** button appears at the top right with the number of problems. Click it to see each one, with details (for a broken `report.json`, the line and column), and **Copy all** to paste them to your agent. When Duetsheet was started by the launcher, the same problems are printed in the launcher's output and saved in `duetsheet/errors.log`, so Claude Code sees them without you copying anything.

Two common cases are handled for you: `NaN` and `Infinity` written by Python are read as empty values (with a warning), and a save that fails because another program holds the file for a moment (OneDrive, for example) is retried until it succeeds.

## Without a folder, and in Claude

**Firefox, Safari, or no folder**: use **Save report file** to download the report (`*.report.json`) and **Open report file** to continue later. An agent can edit that file the same way as `report.json`.

**In Claude (claude.ai)**: upload `duetsheet.html` to a conversation and ask Claude to "publish this file as an Artifact with the `db`, `assets`, `sample` and `downloads` capabilities". The report is then stored in the Artifact. After reviewing, go back to Claude, paste the Artifact link and say "Read the Duetsheet annotations and revise the report." In an Artifact, the Style tab can also ask Claude to estimate your style from PNG examples.
