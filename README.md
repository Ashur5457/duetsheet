# Duetsheet

**The sheet humans and AI agents play from together, record every move on, and rerun.**

Duetsheet is an open-source, single-file interactive HTML report that people and AI agents review and revise together. You edit text and charts in place, circle what is wrong directly on a figure, and every change is recorded with who made it, so the agent (Claude, ChatGPT, Gemini, or any LLM that can read files) receives precise feedback and revises the report round after round.

It is a human-in-the-loop review tool for AI-generated, data-heavy reports: visual annotation on charts, per-block comments, change tracking with diffs, review rounds on a timeline, raw-data provenance, and a figure style that follows your own habits. One HTML file, no install, no build, no server.

Why the name: in a duet, two performers play from **one sheet of music**. In Duetsheet, a human and an AI agent work from one shared page. Sheet music is also a set of steps that gets **played** again and again, which is where this project is heading: from recording and reviewing reports, to editable workflows you can rerun and branch.

> **Status: v0.4 prototype.** Works on your computer with a project folder (Chrome, Edge), as a [Claude](https://claude.ai) Artifact, or with a saved report file in any modern browser. See the [tutorial](docs/tutorial.md) and the [roadmap](#roadmap).

![Paginated view mode](docs/view-mode.png)

## Why

AI agents are good at producing reports that *look* right. The hard part is telling them precisely what is wrong.

Describing "the cluster of points in the upper left of the second figure looks off" in a chat box is vague, and after a few rounds of back-and-forth nobody knows which version is current. Duetsheet replaces the chat box with the report itself: you edit it directly, you draw on the figure, and the agent receives exact positions, data ranges, row ids and before/after values instead of a paragraph of description.

## Features

**Review**
- **View mode**: clean, paginated 16:9 pages with automatic page breaks. Mark any block as "force a new page" or "keep with the previous block". Figures shrink to fit when a page overflows.
- **Edit mode**: edit titles, text and captions in place; change chart type, dataset, axes, ranges and log scale; crop and resize images; drag blocks to reorder; add or delete blocks.
- **Visual annotation on figures**: box-select or free-hand lasso on charts and images, or click a single data point. On charts the annotation stores the **data-space range and the enclosed data points**, not pixels, so the agent knows exactly which measurements you mean.
- **Per-block comments** with preset tags ("more concise", "add data", "use log scale", "add trend line", ...) and quotes of selected text.

**History**
- **Change log**: every edit is recorded with before and after values. Text changes are shown as inline diffs; setting changes read as sentences ("Y axis: linear → log"). Each change can be reverted on its own.
- **Rounds and timeline**: close a round of edits with one click. The timeline shows rows as report blocks and columns as rounds, with human and AI edits colour-coded.
- **Human vs. AI attribution**: edits made by the agent are recorded separately from yours.

**Data and figures**
- **Project folder** (Chrome, Edge): the report is saved to `report.json` in a folder you choose, next to `data/` for raw data and `habits/` for your own example figures. Your agent can edit the same folder while the page is open; the page reloads and merges by document.
- **Raw data with provenance**: import CSV, TSV or JSON from `data/`. Each dataset records the file path and its SHA-256 fingerprint, and the page tells you when the source file changed after the import.
- **Figures from any tool, with their source**: upload SVG (kept as vector) or PNG/JPEG/WebP/GIF from Origin, matplotlib, MATLAB, R, Igor Pro, Prism, Excel and others. Each image records which tool made it, the original file name, the plotting script and the raw data, so the agent knows how to regenerate it.

**Your style**
- **Style profile**: fonts, tick and axis-title sizes in points, marker size, line width, tick direction, frame, grid, colour palette, figure width presets (free, ACS single column, ACS double column), and defaults for new charts. Exportable as a matplotlib `.mplstyle` file or JSON.
- **Learn your habits**: put your own figures and `.mplstyle` files in `habits/` and click **Learn my habits**. SVG files are measured exactly; each suggestion shows which files it comes from, and nothing changes until you tick it. Save the result as `habits/profile.json` and reuse it in your next project. Agents can add suggestions from PNG figures or plotting scripts, which you confirm the same way.
- **Habit suggestions**: when you make the same chart change on three charts (for example switching to a log axis), Duetsheet offers to make it the default.

**For everyone**
- **Six interface languages, plus your own**: English, Traditional Chinese, Simplified Chinese, Japanese, Korean and Spanish, picked from the browser language. Anyone can add a language or correct a translation from the language menu, with no code. See [docs/translating.md](docs/translating.md).
- **Open format**: the report is plain JSON with a published [JSON Schema](schema/report.schema.json), so any program or LLM can read, generate and validate it.

![Annotating a chart with a lasso and a data point](docs/edit-annotate.png)

![The Folder tab: raw data with provenance and figure habits](docs/folder-tab.png)

![Change log with inline diff and timeline](docs/change-log.png)

![Style suggestions learned from the habits folder](docs/style-panel.png)

## Quick start

### On your computer (no account needed)

1. Download [`duetsheet.html`](duetsheet.html), or clone this repository.
2. Open it in **Chrome** or **Edge**.
3. Click **Open project folder** and choose a folder. To try it, choose [`examples/demo-project`](examples/demo-project) from this repository; for your own work, choose an empty folder.
4. In the **Folder** tab, import the files in `data/` and click **Learn my habits**.
5. Switch to **Edit**, change things directly, and leave comments or draw on figures.
6. Ask your AI agent (Claude Code, Codex, Gemini CLI, Cursor, ...), working in the same folder:
   > Read AGENTS.md from the Duetsheet repository, then read the open annotations in report.json and revise the report.

   The page picks up the agent's changes within a few seconds. Everything it changed appears in the change log, marked as the agent's.

Firefox and Safari cannot open folders: use **Save report file** and **Open report file** instead.

### In Claude (claude.ai)

Requirements: a [claude.ai](https://claude.ai) account where Claude can publish Artifacts with the database capability.

1. In a new Claude conversation, upload [`duetsheet.html`](duetsheet.html) and ask:
   > Publish this file as an Artifact with the `db`, `assets`, `sample` and `downloads` capabilities.
2. Open the published link. On first open, the report loads a demo (synthetic data, not experimental results).
3. To use your own content, give Claude your data and ask it to replace the demo blocks and datasets, following `AGENTS.md`.
4. Review the report in **Edit** mode, then go back to Claude, paste the Artifact link, and say:
   > Read the Duetsheet annotations and revise the report.

The [tutorial](docs/tutorial.md) walks through both, step by step with screenshots.

## Use it with any AI agent

Duetsheet does not call any AI model by itself (except the optional "estimate style from PNG" in a Claude Artifact). Your agent reads and writes the report as JSON:

- [`AGENTS.md`](AGENTS.md): the data model, how to write `report.json` safely, and step-by-step tasks (revise from annotations, import data, learn figure habits, write a new report).
- [`schema/report.schema.json`](schema/report.schema.json): the formal JSON Schema.
- [`examples/demo-project/`](examples/demo-project/): a complete project folder.
- [`llms.txt`](llms.txt): a short index for LLMs.

Prompts that work well:

> Using AGENTS.md, write a Duetsheet report in report.json from the files in data/. Record where each dataset came from.

> Look at my figures in habits/ and suggest a style in style/proposal. Do not change style/profile.

> Read the open annotations in report.json. For each one, make the smallest change, record it in changes, reply under the annotation, and close your round.

## How it works

A report is not a static HTML page. The page is a fixed viewer and editor; the content lives as JSON documents:

| Collection | Contents |
|---|---|
| `report/meta` | Title and block order |
| `blocks` | Report blocks: `text`, `chart`, `table`, `image` |
| `datasets` | Data tables with their source file and SHA-256; charts and tables reference them instead of copying values |
| `annotations` | Human feedback: target (block, point, box, or lasso), tag ids, text, status, agent reply |
| `changes` | One record per edited field: before, after, who (`user` or `claude`), when |
| `rounds` | Boundaries between rounds of edits |
| `style/profile`, `style/proposal` | The figure style, and style changes suggested by an agent |
| `examples` | Example figures the style can be learned from |

The same documents can be stored in three ways: `report.json` in a project folder, the database of a Claude Artifact, or a report file you save and open. Because the content is data, an agent can change one caption or one chart setting without regenerating the whole report, and every change stays attributable and reversible.

## Who it is for

Any workflow where **an AI drafts a data-heavy report and a domain expert must check it claim by claim**:

- Scientific data analysis and lab reports (the origin of this project: closed-loop materials experiments)
- Finance: equity research, financial analysis, audit working papers
- Engineering and manufacturing: failure analysis, quality investigations
- Consulting and market research reports
- Fact-checking and editorial review
- Incident post-mortems and design reviews

If your report is text only, a document editor's suggestion mode may be enough. Duetsheet is most useful when the report contains **charts backed by data** and every number needs to be traceable.

## FAQ

**What is Duetsheet?**
A single HTML file that shows a report made of text, charts, tables and images, lets a person edit and annotate it, records every change with its author, and stores everything as JSON that an AI agent can read and revise.

**Do I need Claude or an account?**
No. On your computer, Chrome or Edge can save the report to a folder, and any agent that can edit files can work with it. Claude Artifacts are one supported way to host it, not a requirement.

**Which AI models or agents work with it?**
Any that can read and write JSON files: Claude Code, Codex, Gemini CLI, Cursor, local models with file access, or a script. They follow [`AGENTS.md`](AGENTS.md).

**Where is my data stored?**
In the folder you choose (`report.json`, `data/`, `assets/`), in your Claude Artifact, or in a file you save. Duetsheet has no server and sends nothing anywhere. It loads fonts from Google Fonts and one small library (SortableJS) from a CDN.

**How does the agent know which data point I mean?**
When you click a point, draw a box or a lasso on a chart, the annotation stores the data range in the chart's units and the ids of the rows inside it, not screen pixels.

**Can I use figures from Origin, matplotlib, MATLAB or R?**
Yes. Upload SVG or PNG and record the tool, the original file, the plotting script and the raw data. Box and lasso on images are stored relative to the image for now; mapping them to data coordinates is on the roadmap.

**Can it learn how I like my figures?**
Yes. Put your figures (SVG measured exactly) and `.mplstyle` files in `habits/`, click **Learn my habits**, and tick the suggestions you want. Agents can add suggestions from PNG figures and plotting scripts.

**How is it different from comments in Google Docs or Word, or from Jupyter and Quarto?**
Document comments point at text; Duetsheet comments can point at data points and regions of a chart, and the whole review history is structured data an agent can act on. Jupyter and Quarto produce reports from code; Duetsheet is where a person reviews and corrects a report together with an agent, whatever produced it.

**Is it free?**
Yes, MIT licensed.

## Limitations

- Opening a project folder needs Chrome or Edge (the File System Access API). Other browsers can save and open report files.
- Designed for desktop browsers.
- In a Claude Artifact, the database limits apply: roughly 256 kB per document and 5,000 documents per report. Without an asset store (report file mode), uploaded images are compressed to about 230 kB and stored inline.
- Only chart and image blocks support box and lasso annotation; text and tables support block-level comments and quotes.
- PNG/JPEG figures cannot be measured by the page: in a Claude Artifact, Claude estimates the style with a confidence per setting; elsewhere, ask your agent or use SVG.
- In a Claude Artifact the matplotlib export is saved as `duetsheet-style.mplstyle.txt` (the download allowlist has no `.mplstyle`); remove the `.txt` extension before use. In a project folder it is saved as `exports/duetsheet-style.mplstyle`.
- Excel and instrument files are not imported by the page; save them as CSV or ask your agent to convert them.
- Origin theme files (`.oth`) cannot be imported; export an SVG from Origin and put it in `habits/` instead.
- The interface language does not translate the report itself: titles, text and captions stay in the language they were written in.
- Right-to-left languages (for example Arabic or Hebrew) can be loaded as translations, but the layout stays left-to-right.

## Roadmap

Duetsheet is planned in four stages: **record and review** (today), **workflows**, **lab automation**, and **agent evaluation**.

- One-click "copy feedback for your LLM" prompt export
- Regenerate figures from their source: run the recorded Python script, or drive Origin through its Python API, so an annotation such as "use a log axis" is applied in the original tool
- Axis calibration for imported images, so box and lasso annotations on an Origin or matplotlib image are stored in data coordinates
- **Workflow mode**: analysis steps as editable nodes; editing a step marks everything downstream as stale; re-run only what changed; fork a branch from any step to compare parameters side by side
- Agent decision trace per data point (which step, which model, what evidence)
- Connecting physical experiment steps in self-driving labs, behind explicit human approval
- Turning accumulated annotations and change logs into evaluation sets for measuring agent performance

## Contributing

Issues and pull requests are welcome, especially real-world report types, annotation needs from other fields, and translations. The Simplified Chinese, Japanese, Korean and Spanish interface texts were drafted with AI help: corrections from native speakers are very welcome.

- `duetsheet.html` is the only source file. There is no build step: edit it and open it in a browser.
- New interface text goes through `tr('English text')` and needs an entry in the translation tables. [docs/translating.md](docs/translating.md) explains how.
- Before sending a pull request, run `python tools/check.py`. It checks that code and comments are English, that the translation tables are valid, and that no interface text is missing a translation entry.

## Citation

If you use Duetsheet in research, please cite it using [`CITATION.cff`](CITATION.cff) (GitHub shows a "Cite this repository" button).

## License

[MIT](LICENSE)

---

*Keywords: Duetsheet, human-in-the-loop AI, AI agent report review, LLM feedback, interactive HTML report, single-file HTML, figure annotation, chart annotation, lasso selection, data point annotation, change tracking, diff, review rounds, provenance, SHA-256, reproducible research, scientific workflow, matplotlib style, figure style, Claude Artifacts, Claude Code, AGENTS.md, JSON Schema.*
