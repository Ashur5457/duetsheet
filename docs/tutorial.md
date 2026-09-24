# Duetsheet tutorial

This tutorial walks through one full review cycle: open a report, bring in raw data, comment on a figure, let an AI agent revise the report, and check what it changed. It uses the demo project in [`examples/demo-project`](../examples/demo-project) (synthetic data, not experimental results).

You need a desktop computer. There are two ways to open a report:

- **From Claude Code (fastest)**: install once (section 0), then see section 0b. Claude starts Duetsheet for your data folder and the report opens by itself.
- **By hand**: open `duetsheet.html` in Chrome or Edge and choose the folder (steps 1 and 2 below). No install is needed.

A third path, Claude Artifacts on claude.ai, is at the end.

## 0. Install

Every way of using Duetsheet on your computer needs **Python 3.8 or later** (nothing else: no packages to install). Check with `python --version`.

### With Claude Code (recommended)

In Claude Code (terminal, VS Code extension, JetBrains plugin or desktop app, with a subscription or an API key), type these two lines once:

```
/plugin marketplace add Ashur5457/duetsheet
/plugin install duetsheet@duetsheet
```

Start a new session and type `/`: **duetsheet** is in the list. That's it.

- **Update**: `/plugin marketplace update duetsheet`, then start a new session.
- **Remove**: `/plugin uninstall duetsheet@duetsheet`.

### Without the plugin system

If you prefer a copy of the repository on your computer (you need [git](https://git-scm.com/)):

```bash
git clone https://github.com/Ashur5457/duetsheet.git && python duetsheet/duetsheet.py install-skill
```

This installs the same `/duetsheet` skill into `~/.claude/skills/`, pointing to that copy. To update: `git pull` in that folder, then run `python duetsheet.py install-skill` again. If you move the folder, run `install-skill` again.

### With other AI agents (Copilot, Cursor, Codex, Gemini CLI, Cline and others)

These agents do not use Claude Code skills, but most of them read an `AGENTS.md` file in the folder they work in. Get Duetsheet (clone or [download the ZIP](https://github.com/Ashur5457/duetsheet/archive/refs/heads/main.zip)), then, once per data folder:

```bash
python path/to/duetsheet.py init-agent "path/to/data-folder"
```

It adds a short section to `AGENTS.md` in the data folder (or creates the file) that tells any agent where the full rules are and how to check and start the report. Existing content in that file is kept; running it again only refreshes the section.

Duetsheet itself never calls an AI model or needs an API key: your agent reads and writes `report.json`.

### Opening a report later without an agent

- `python path/to/duetsheet.py shortcut "path/to/data-folder"` puts a shortcut on your desktop. Double-click it to open the report; keep the window that opens while you use it.
- To show the report to someone who has nothing installed, click **Export read-only copy** at the top of the page and send them the HTML file from `exports/`. It opens in any browser.

## 0b. Start from Claude Code

Open Claude Code in the folder that holds your raw data and type `/duetsheet`. Claude reads `AGENTS.md`, proposes a report, writes it after you agree, checks it with `duetsheet.py check`, and starts the launcher. Your browser opens the report, already connected to the folder: skip to step 3.

Without Claude Code you can start the launcher yourself: `python path/to/duetsheet.py "path/to/data-folder"`.

Duetsheet keeps everything it writes in a `duetsheet/` subfolder of your data folder (`report.json`, uploaded images, exports, your figure habits). The raw data files stay where they are and are never modified.

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
  habits/          your own example figures and .mplstyle files
  assets/          images uploaded in the page (created when needed)
  exports/         files the page exports (created when needed)
```

The demo uses this project layout, with `report.json` at the top and the raw data in `data/`. When you open your own data folder, the same files go into its `duetsheet/` subfolder instead, and every data file in the folder (subfolders included) is listed in the Folder tab.

## 3. Bring in raw data

Open the **Folder** tab in the panel. Files in `data/` are listed with their status. Click **Import** next to `cycle4-runs.csv`.

![The Folder tab after importing a data file](folder-tab.png)

The file becomes a dataset. Duetsheet records where it came from: the path and a SHA-256 fingerprint of the file. If the file changes later, the Folder tab says "changed since import", charts that use it show a warning in Edit mode, and **Update** imports the new version (the change log keeps both).

To plot the new data, switch to **Edit**, click **Add chart**, open **Chart settings** and pick the dataset.

## 4. Review: edit and comment

Switch to **Edit**. You can:

- change titles, text and captions directly (every change is recorded);
- change chart settings (type, dataset, columns, axis labels, range, log scale);
- drag blocks to reorder them and click the dividers to control page breaks;
- write a comment under any block, with preset tags such as **Use log scale** or **Highlight key points**.

On a chart you can point at the exact data: click **Lasso on figure** (or **Box on figure**) and draw around points, or simply click one point. The comment then stores the data range and the ids of the points inside it, which is what the agent reads.

![A lasso and a single data point marked on a chart, with the comments in the panel](edit-annotate.png)

When you have finished a batch of feedback, open the **Changes** tab and click **Finish this round**.

## 5. Let your agent revise the report

Open your AI agent (Claude Code, Codex, Gemini CLI, Cursor, ...) in the same folder and ask:

> Read AGENTS.md from the Duetsheet repository, then read the open annotations in report.json and revise the report.

[`AGENTS.md`](../AGENTS.md) tells the agent how to make the smallest change for each comment, record every change as its own, reply under each comment, and close its round. Keep Duetsheet open: within a few seconds the page reloads `report.json` and shows the agent's work.

![The agent's replies under each comment, and Figure 1 now on a log axis](agent-reply.png)

Comments the agent handled are marked **Done** with its reply. A comment it could not settle stays **Open**, with a question for you.

## 6. Check what changed

The **Changes** tab shows the current round; **Show full history** shows every round. Text changes are shown as inline differences; setting changes read as "before → after". Each change can be reverted on its own.

The timeline has one row per block and one column per round. Filled markers are edits (blue: you, purple: the agent), circles are comments. Click a column to see only that round.

![The change history and the timeline](change-log.png)

## 7. Teach it your figure style

Put figures you like in `habits/`: SVG exports from Origin, matplotlib, R or other tools, and `.mplstyle` files. In the **Folder** tab, click **Learn my habits**.

Duetsheet measures the SVG files exactly (font, sizes, line width, colours, figure width), reads the `.mplstyle` files, and lists what it found. Each suggestion shows which files it is based on; suggestions that most files agree on are ticked. Nothing changes until you click **Apply selected**.

![Style suggestions learned from the habits folder](style-panel.png)

- **Save current style as my habits** writes `habits/profile.json`. Copy it into the `habits/` folder of your next project to start from the same style.
- PNG and JPG figures cannot be measured by the page. Ask your agent to look at them: it writes its suggestions to `style/proposal`, and they appear in the Style tab for you to confirm in the same way.
- **Export** in the Style tab saves the style as a matplotlib `.mplstyle` file (`exports/duetsheet-style.mplstyle`), so your plotting scripts can use it too.

## 8. Other languages

The interface language never changes the report content or the stored data, so people working in different languages can review the same report.

![The same report with the Japanese interface](language-ja.png)

## When something goes wrong

Errors and warnings do not just flash by: a **⚠** button appears at the top right with the number of problems. Click it to see each one, with details (for a broken `report.json`, the line and column), and **Copy all** to paste them to your agent. When Duetsheet was started by the launcher, the same problems are printed in the launcher's output and saved in `duetsheet/errors.log`, so Claude Code sees them without you copying anything.

Two common cases are handled for you: `NaN` and `Infinity` written by Python are read as empty values (with a warning), and a save that fails because another program holds the file for a moment (OneDrive, for example) is retried until it succeeds.

## Without a folder, and in Claude

**Firefox, Safari, or no folder**: use **Save report file** to download the report (`*.report.json`) and **Open report file** to continue later. An agent can edit that file the same way as `report.json`.

**In Claude (claude.ai)**: upload `duetsheet.html` to a conversation and ask Claude to "publish this file as an Artifact with the `db`, `assets`, `sample` and `downloads` capabilities". The report is then stored in the Artifact. After reviewing, go back to Claude, paste the Artifact link and say "Read the Duetsheet annotations and revise the report." In an Artifact, the Style tab can also ask Claude to estimate your style from PNG examples.
