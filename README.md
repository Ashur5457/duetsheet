# Duetsheet

**The sheet humans and AI agents play from together, record every move on, and rerun.**

Duetsheet is an interactive HTML report that people and AI agents (such as Claude) review and revise together. Edit text and charts in place, circle what is wrong directly on a figure, and keep a full change history, so the agent reads your feedback precisely and revises the report round after round.

Why the name: in a duet, two performers play from **one sheet of music**. In Duetsheet, a human and an AI agent work from one shared page. Sheet music is also a set of steps that gets **played** again and again, which is where this project is heading: from recording and reviewing reports, to editable workflows you can rerun and branch.

It is a human-in-the-loop review tool for AI-generated reports: a single-file interactive report with visual annotation, per-block comments, change tracking with diffs, version rounds, and a change timeline.

> **Status: v0.2 prototype, Claude-first.** This version runs as a [Claude](https://claude.ai) Artifact and uses the Artifact database for cloud storage. See [Roadmap](#roadmap).

![Paginated view mode](docs/view-mode.png)

## Why

AI agents are good at producing reports that *look* right. The hard part is telling them precisely what is wrong.

Describing "the cluster of points in the upper left of the second figure looks off" in a chat box is vague, and after a few rounds of back-and-forth nobody knows which version is current. Duetsheet replaces the chat box with the report itself: you edit it directly, you draw on the figure, and the agent receives exact positions, data ranges, and before/after values instead of a paragraph of description.

## Features

- **View mode**: clean, paginated 16:9 pages with automatic page breaks. Mark any block as "force a new page" or "keep with the previous block". Figures shrink to fit when a page overflows.
- **Edit mode**: edit titles, text, and captions in place; change chart type, axes, ranges, and log scale; crop and resize images; drag blocks to reorder; add or delete blocks.
- **Per-block comments**: every block has a comment box with preset tags (for example "more concise", "add data", "change axis", "add trend line").
- **Visual annotation on figures**: box-select or free-hand lasso on charts and images, or click a single data point. On charts, the annotation stores the **data-space range and the enclosed data points**, not just pixels, so the agent knows exactly which measurements you mean.
- **Text quotes**: select a passage and attach it to a comment.
- **Change log**: every edit is recorded with before and after values. Text changes are shown as inline diffs; setting changes read as sentences ("Y axis: linear → log"). Each change can be reverted individually.
- **Rounds and timeline**: close a round of edits with one click. The history view shows a timeline (rows are report blocks, columns are rounds), with human and AI edits colour-coded, so you can see at a glance who changed what and where.
- **Human vs. AI attribution**: edits made by the agent are recorded separately from edits made by you.
- **Figures from any tool, with their source**: upload SVG (kept as vector) or PNG/JPEG/WebP/GIF from Origin, matplotlib, MATLAB, R, Igor Pro, Prism, Excel and others. Each image records which tool made it, the original file name, a note, the plotting script, and optionally the raw data file, so the agent knows how to regenerate it.
- **Style profile**: fonts, tick and axis-title sizes (in points, scaled to the figure width), marker size, line width, tick direction, frame, grid, colour palette, figure width presets (free, ACS single column, ACS double column), and defaults for new charts. Applied to every chart in the report and exportable as a matplotlib `.mplstyle` file or JSON.
- **Learn a style from your own figures**: upload example figures. SVG examples are parsed exactly (font, sizes, colours, line width, figure width); PNG/JPEG examples are estimated by Claude with a confidence per setting. You review the suggested changes and apply only the ones you tick.
- **Habit suggestions**: when you make the same chart change on three charts (for example switching to a log axis), Duetsheet offers to make it the default. Nothing changes until you confirm.

![Annotating a chart with a lasso and a data point](docs/edit-annotate.png)

![Change log with inline diff and timeline](docs/change-log.png)

![Style profile applied to a chart](docs/style-panel.png)

## Who it is for

Any workflow where **an AI drafts a data-heavy report and a domain expert must check it claim by claim**:

- Scientific data analysis and lab reports (the origin of this project: closed-loop materials experiments)
- Finance: equity research, financial analysis, audit working papers
- Engineering and manufacturing: failure analysis, quality investigations
- Consulting and market research reports
- Fact-checking and editorial review
- Incident post-mortems and design reviews

If your report is text only, a document editor's suggestion mode may be enough. Duetsheet is most useful when the report contains **charts backed by data** and every number needs to be traceable.

## How it works

A report is not a static HTML page. The page is a fixed viewer, and the content lives as structured data in a small database:

| Collection | Contents |
|---|---|
| `report/meta` | Title and block order |
| `blocks` | Report blocks: `text`, `chart`, `table`, `image` |
| `datasets` | Raw data tables; charts and tables reference them instead of copying values |
| `annotations` | Human feedback: target (block, point, box, or lasso), tags, text, status, agent reply |
| `changes` | One record per edited field: before, after, who (`user` or `claude`), when |
| `rounds` | Boundaries between rounds of edits |
| `style/profile` | The report's figure style |
| `examples` | Example figures the style can be learned from |

Images and data files are stored as Artifact assets; documents keep only their ids.

Because the content is data, an agent can change one caption or one chart setting without regenerating the whole report, and every change stays attributable and reversible.

The full data model and the protocol an agent should follow are in **[AGENTS.md](AGENTS.md)**. A complete example is in [`examples/nimo-demo.json`](examples/nimo-demo.json).

## Quick start (Claude)

Requirements: a [claude.ai](https://claude.ai) account where Claude can publish Artifacts with the database capability.

1. Download [`duetsheet.html`](duetsheet.html).
2. In a new Claude conversation, upload the file and ask:
   > Publish this file as an Artifact with the `db`, `assets`, `sample` and `downloads` capabilities.
3. Open the published link. On first open, the report loads a demo dataset (synthetic data, not experimental results).
4. To use your own content, give Claude your data and ask it to replace the demo blocks and datasets, following `AGENTS.md`.
5. Review the report: switch to **Edit**, change things directly, and leave comments or annotations on figures.
6. Go back to Claude, paste the Artifact link, and say:
   > Read the Duetsheet annotations and revise the report.

   Claude reads your annotations, edits the affected blocks, records its changes as `claude`, replies under each annotation, and closes the round. Everything it changed appears in the change log.

Opening `duetsheet.html` directly in a browser also works, but in that case data is kept in memory only and is lost on reload.

## Limitations

- Cloud storage currently works only inside a claude.ai Artifact. Artifacts are private to you unless shared within your organization.
- Designed for desktop browsers.
- Artifact database limits apply: roughly 256 kB per document and 5,000 documents per report. Uploaded images are compressed to about 230 kB.
- Only chart and image blocks support box and lasso annotation; text and tables support block-level comments and quotes.
- Learning a style from PNG/JPEG examples uses the viewer's own Claude usage and gives approximate values; SVG examples give exact values.
- The matplotlib export is saved as `duetsheet-style.mplstyle.txt` (the download allowlist has no `.mplstyle`); remove the `.txt` extension before use.
- Origin theme files (`.oth`) cannot be imported; export an SVG from Origin and use it as an example instead.

## Roadmap

Duetsheet is planned in four stages: **record and review** (today), **workflows**, **lab automation**, and **agent evaluation**.


- More interface languages (the code already supports a language switch; a Traditional Chinese translation exists)
- Local file storage and JSON import/export, so the report works without any AI platform
- A published JSON Schema, so any LLM (GPT, Gemini, local models) can generate and revise Duetsheet reports
- One-click "copy feedback for your LLM" prompt export
- **Workflow mode**: analysis steps as editable nodes; editing a step marks everything downstream as stale; re-run only what changed; fork a branch from any step to compare parameters side by side
- Agent decision trace per data point (which step, which model, what evidence)
- Axis calibration for imported images, so box and lasso annotations on an Origin or matplotlib image are stored in data coordinates
- Round-trip editing of source figures (for example Origin via its Python API): an annotation such as "use a log axis" is applied in the original tool and the figure is re-exported
- Connecting physical experiment steps in self-driving labs, behind explicit human approval
- Turning accumulated annotations and change logs into evaluation sets for measuring agent performance

## Contributing

Issues and pull requests are welcome, especially real-world report types, annotation needs from other fields, and translations.

## License

[MIT](LICENSE)

---

*Keywords: Duetsheet, human-in-the-loop AI, LLM report review, AI agent feedback, interactive HTML report, figure annotation, chart annotation, lasso selection, change tracking, diff, provenance, reproducible research, scientific workflow, Claude Artifacts.*
