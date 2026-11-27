# Final report

CAP 6411 final report, built on the official CVPR author kit
(https://github.com/cvpr-org/author-kit, commit 1fd5709). Due Mon 30 Nov 11:59 PM, 6 to 8 pages.

Build from this directory with [Tectonic](https://tectonic-typesetting.github.io/):

```bash
mkdir -p build && tectonic -X compile main.tex --outdir build   # writes build/main.pdf
```

`latexmk -pdf main.tex` also works with a TeX Live install. Build outputs are not committed.

- `sec/`: one file per section. Each file's first comment names its owner (4e plan:
  James and Shawn draft data, results and limitations; Austin and Alejandro the
  architecture and implementation).
- Orange "Notes for ..." boxes list facts the repository already supports; turn them into
  prose and delete the box. Red `\TODO{}` marks open items.
- `data/pilot-2026-11-18.csv`: per-clip results behind Table 1 (Mac mini functional check).
  Totals use the rows whose `windows_from` equals `clip`.
- `main.bib`: citations from arXiv's BibTeX export or official project pages only.
