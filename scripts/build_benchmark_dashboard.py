import argparse
import csv
import json
from pathlib import Path


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Xeon vLLM Benchmark Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --accent: #22d3ee;
      --accent2: #f59e0b;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --ok: #34d399;
      --bad: #f87171;
    }
    body {
      font-family: "IBM Plex Sans", "Segoe UI", Arial, sans-serif;
      margin: 0;
      background: radial-gradient(circle at 20% 20%, #1f2937 0%, var(--bg) 60%);
      color: var(--text);
    }
    .wrap { max-width: 1200px; margin: 24px auto; padding: 12px; }
    .title { font-size: 28px; margin-bottom: 12px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
    .card { background: var(--card); border-radius: 14px; padding: 14px; border: 1px solid #1f2937; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid #1f2937; padding: 8px; text-align: left; }
    th { color: var(--muted); }
    .ok { color: var(--ok); font-weight: 600; }
    .bad { color: var(--bad); font-weight: 600; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">Xeon 6 vLLM Benchmark Dashboard</div>
    <div class="grid">
      <div class="card"><canvas id="throughputChart"></canvas></div>
      <div class="card"><canvas id="latencyChart"></canvas></div>
      <div class="card"><canvas id="successChart"></canvas></div>
    </div>
    <div class="card" style="margin-top:12px;">
      <h3>Scenario Details</h3>
      <table>
        <thead>
          <tr>
            <th>Scenario</th>
            <th>Concurrency</th>
            <th>Context</th>
            <th>P95 Latency (s)</th>
            <th>Req/s</th>
            <th>Out Tok/s</th>
            <th>Success</th>
          </tr>
        </thead>
        <tbody>
          __ROWS__
        </tbody>
      </table>
    </div>
  </div>
  <script>
    const labels = __LABELS__;
    const throughput = __THROUGHPUT__;
    const p95 = __P95__;
    const success = __SUCCESS__;

    new Chart(document.getElementById("throughputChart"), {{
      type: "bar",
      data: {{ labels, datasets: [{{ label: "Req/s", data: throughput, backgroundColor: "rgba(34,211,238,0.75)" }}] }},
      options: {{ responsive: true, plugins: {{ legend: {{ display: true }} }} }}
    }});

    new Chart(document.getElementById("latencyChart"), {{
      type: "line",
      data: {{ labels, datasets: [{{ label: "P95 latency (s)", data: p95, borderColor: "rgba(245,158,11,1)", backgroundColor: "rgba(245,158,11,0.15)" }}] }},
      options: {{ responsive: true }}
    }});

    new Chart(document.getElementById("successChart"), {{
      type: "line",
      data: {{ labels, datasets: [{{ label: "Success rate", data: success, borderColor: "rgba(52,211,153,1)", backgroundColor: "rgba(52,211,153,0.2)" }}] }},
      options: {{ responsive: true, scales: {{ y: {{ min: 0, max: 1 }} }} }}
    }});
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate benchmark dashboard HTML")
    parser.add_argument("--stats-csv", required=True, help="Path to scenario_stats.csv")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    rows = []
    labels = []
    throughput = []
    p95 = []
    success = []
    with Path(args.stats_csv).open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row["scenario"]
            succ = float(row["success_rate"])
            labels.append(scenario)
            throughput.append(float(row["throughput_req_per_s"]))
            p95.append(float(row["p95_latency_s"]))
            success.append(succ)
            cls = "ok" if succ >= 0.99 else "bad"
            rows.append(
                f"<tr><td>{scenario}</td><td>{row['concurrency']}</td><td>{row['context_len']}</td>"
                f"<td>{float(row['p95_latency_s']):.4f}</td><td>{float(row['throughput_req_per_s']):.2f}</td>"
                f"<td>{float(row['throughput_out_tok_per_s']):.2f}</td><td class='{cls}'>{succ:.4f}</td></tr>"
            )

    html = (
        HTML_TEMPLATE.replace("__ROWS__", "\n".join(rows))
        .replace("__LABELS__", json.dumps(labels))
        .replace("__THROUGHPUT__", json.dumps(throughput))
        .replace("__P95__", json.dumps(p95))
        .replace("__SUCCESS__", json.dumps(success))
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {out}")


if __name__ == "__main__":
    main()
