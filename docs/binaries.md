# {octicon}`desktop-download` Binaries

All standalone executables of the `click-extra` demo CLI published by this repository, one row per binary, newest release first. The version links to its GitHub release, the platform to the direct binary download, and the VirusTotal cell to the file's public analysis.

Compiled Python binaries are regularly flagged by heuristic antivirus engines, so every release is submitted to [VirusTotal](https://www.virustotal.com/): this seeds vendor databases with the new signatures and keeps false positives in check. The VirusTotal cell tracks those false positives: a green check marks binaries no engine flags, and flagged binaries show the share of engine verdicts flagging them, snapshotted minutes after publication and before false-positive reports get processed. The live analysis behind the link supersedes it.

## Development builds

Fresh binaries are compiled from every push to the default branch by the [release workflow](https://github.com/kdeldycke/click-extra/actions/workflows/release.yaml). To try the latest development build: open the most recent successful run and download the artifact matching your platform (a GitHub account is required, and the binary comes wrapped in a zip). The same builds are also attached to a rolling dev pre-release, a draft only visible to repository maintainers.

<!-- binaries-start -->

## VirusTotal detections

Share of antivirus engine verdicts flagging the binaries of each release, at scan time. Colors follow the catalog shields: green for zero detections, amber below 10%, red from there up.

```{raw} html
<div style="height: 320px;"><canvas id="vt-trend"></canvas></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.min.js"></script>
<script>
const VT_TREND = [{"date": "2026-04-16", "flagged": 26, "pct": 6.6, "tag": "v7.12.0", "total": 393}, {"date": "2026-04-16", "flagged": 27, "pct": 6.8, "tag": "v7.13.0", "total": 395}, {"date": "2026-04-24", "flagged": 30, "pct": 7.7, "tag": "v7.14.0", "total": 392}, {"date": "2026-04-26", "flagged": 29, "pct": 7.4, "tag": "v7.14.1", "total": 392}, {"date": "2026-05-03", "flagged": 27, "pct": 7.0, "tag": "v7.15.0", "total": 385}, {"date": "2026-05-14", "flagged": 32, "pct": 8.8, "tag": "v7.16.0", "total": 365}, {"date": "2026-05-15", "flagged": 26, "pct": 6.7, "tag": "v7.16.1", "total": 389}, {"date": "2026-05-25", "flagged": 7, "pct": 2.3, "tag": "v7.17.0", "total": 310}, {"date": "2026-05-25", "flagged": 7, "pct": 2.0, "tag": "v7.17.1", "total": 358}, {"date": "2026-05-26", "flagged": 7, "pct": 1.8, "tag": "v7.17.2", "total": 387}, {"date": "2026-05-29", "flagged": 12, "pct": 3.1, "tag": "v7.18.0", "total": 388}, {"date": "2026-06-12", "flagged": 26, "pct": 7.1, "tag": "v7.19.0", "total": 367}, {"date": "2026-06-17", "flagged": 22, "pct": 5.9, "tag": "v7.20.0", "total": 376}, {"date": "2026-06-18", "flagged": 25, "pct": 6.6, "tag": "v7.20.1", "total": 380}, {"date": "2026-06-22", "flagged": 16, "pct": 4.5, "tag": "v8.0.1", "total": 359}, {"date": "2026-06-24", "flagged": 19, "pct": 5.0, "tag": "v8.1.0", "total": 378}, {"date": "2026-06-24", "flagged": 17, "pct": 5.3, "tag": "v8.1.1", "total": 318}, {"date": "2026-06-27", "flagged": 12, "pct": 3.1, "tag": "v8.1.2", "total": 385}, {"date": "2026-06-27", "flagged": 12, "pct": 3.1, "tag": "v8.1.3", "total": 382}, {"date": "2026-06-27", "flagged": 11, "pct": 2.9, "tag": "v8.1.4", "total": 382}, {"date": "2026-07-01", "flagged": 22, "pct": 5.8, "tag": "v8.2.0", "total": 380}, {"date": "2026-07-08", "flagged": 22, "pct": 5.7, "tag": "v8.3.0", "total": 383}];
const VT_DANGER_PCT = 10;
const vtCss = getComputedStyle(document.documentElement);
const vtColor = (name, fallback) =>
    vtCss.getPropertyValue(name).trim() || fallback;
const vtTint = (p) => {
    if (p.pct === 0) { return vtColor("--sd-color-success", "#28a745"); }
    return p.pct >= VT_DANGER_PCT
        ? vtColor("--sd-color-danger", "#dc3545")
        : vtColor("--sd-color-warning", "#f0b37e");
};
new Chart(document.getElementById("vt-trend"), {
    type: "line",
    data: {
        datasets: [{
            data: VT_TREND.map((p) => ({x: Date.parse(p.date), y: p.pct})),
            borderColor: "#88888866",
            pointBackgroundColor: VT_TREND.map(vtTint),
            pointBorderColor: VT_TREND.map(vtTint),
            pointRadius: 4,
            tension: 0.2,
        }],
    },
    options: {
        maintainAspectRatio: false,
        plugins: {
            legend: {display: false},
            tooltip: {callbacks: {
                title: (items) => VT_TREND[items[0].dataIndex].tag,
                label: (item) => {
                    const p = VT_TREND[item.dataIndex];
                    return p.flagged + " / " + p.total
                        + " verdicts flagged (" + p.pct + "%)";
                },
            }},
        },
        scales: {
            x: {
                type: "linear",
                ticks: {
                    maxTicksLimit: 8,
                    callback: (value) =>
                        new Date(value).toISOString().slice(0, 10),
                },
            },
            y: {
                beginAtZero: true,
                title: {display: true, text: "Flagged verdicts (%)"},
            },
        },
    },
});
</script>
```

<!-- binaries-end -->

## Catalog

The table is searchable and sortable on the documentation site; the raw data lives in [`binaries.csv`](assets/binaries.csv).

```{csv-table}
:file: assets/binaries.csv
:header-rows: 1
:class: sphinx-datatable
```
