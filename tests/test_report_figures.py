import csv
import json

from scripts import report_figures


def _write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_figures_from_synthetic_scores(tmp_path):
    scores = []
    for clip, windows, calls in (("control", 0, (3, 1)), ("thumbs_mov_1", 2, (40, 8))):
        for policy, n in zip(("fixed", "gated"), calls):
            named = min(windows, 1 if policy == "fixed" else 2)
            scores.append(
                {
                    "clip": clip,
                    "policy": policy,
                    "calls": n,
                    "windows": windows,
                    "windows_named": named,
                }
            )
    _write_csv(tmp_path / "scores.csv", scores)
    _write_csv(
        tmp_path / "annotations.csv",
        [
            {"video_id": "thumbs_mov_1", "onset_s": "30.0", "end_s": "34.0"},
            {"video_id": "thumbs_mov_1", "onset_s": "90.0", "end_s": "95.0"},
            {"video_id": "control", "onset_s": "1.0", "end_s": "2.0"},
        ],
    )
    runs = tmp_path / "runs"
    for policy, step in (("fixed", 4.0), ("gated", 10.0)):
        run = runs / f"thumbs_mov_1-{policy}"
        run.mkdir(parents=True)
        lines = [
            {
                "source_time_s": t * step,
                "status": "ok",
                "gesture": "thumbs_up" if 30 <= t * step < 34 else "none",
            }
            for t in range(12)
        ]
        lines.append({"source_time_s": None, "status": "failed"})
        (run / "requests.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    out = tmp_path / "figures"
    assert (
        report_figures.main(
            [
                "--scores",
                str(tmp_path / "scores.csv"),
                "--annotations",
                str(tmp_path / "annotations.csv"),
                "--timeline",
                str(tmp_path / "timeline.csv"),
                "--export-timeline",
                str(runs),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    timeline = list(csv.DictReader((tmp_path / "timeline.csv").open()))
    assert len(timeline) == 24 and {r["policy"] for r in timeline} == {"fixed", "gated"}
    for name in ("calls_per_clip", "named_per_clip", "timeline_thumbs_mov_1"):
        for ext in ("pdf", "png"):
            assert (out / f"{name}.{ext}").stat().st_size > 1000
