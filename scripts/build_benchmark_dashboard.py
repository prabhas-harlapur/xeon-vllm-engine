import argparse
import csv
import json
from pathlib import Path

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Xeon 6 vLLM Performance Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #030712;
      --card: rgba(17, 24, 39, 0.7);
      --border: rgba(255, 255, 255, 0.1);
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.3);
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --success: #10b981;
      --warning: #f59e0b;
      --error: #ef4444;
    }
    body {
      font-family: 'Outfit', sans-serif;
      background: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.1) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(245, 158, 11, 0.05) 0px, transparent 50%);
      color: var(--text);
      margin: 0;
      min-height: 100vh;
    }
    .header {
      padding: 40px 20px;
      text-align: center;
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(10px);
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(3, 7, 18, 0.8);
    }
    .header h1 {
      margin: 0;
      font-size: 2.5rem;
      letter-spacing: -0.025em;
      background: linear-gradient(to right, #fff, var(--accent));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .header p {
      color: var(--text-muted);
      margin-top: 8px;
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      padding: 40px 20px;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 24px;
      margin-bottom: 40px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 24px;
      backdrop-filter: blur(16px);
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .card h3 {
      margin-top: 0;
      font-weight: 600;
      color: var(--text-muted);
      font-size: 0.875rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 20px;
    }
    .table-container {
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
    }
    th {
      text-align: left;
      padding: 12px 16px;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      font-weight: 600;
    }
    td {
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
    }
    tr:hover {
      background: rgba(255, 255, 255, 0.03);
    }
    .badge {
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .badge-success { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .badge-error { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    
    .xeon-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #0068b5 0%, #004a82 100%);
      padding: 8px 16px;
      border-radius: 8px;
      font-weight: 700;
      margin-bottom: 20px;
      box-shadow: 0 0 15px var(--accent-glow);
    }
    
    canvas {
      max-height: 300px;
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="xeon-badge">INTEL XEON 6</div>
    <h1>Inference Performance Analytics</h1>
    <p>vLLM Optimized for Sapphire Rapids & Emerald Rapids</p>
  </div>

  <div class="container">
    <div class="stats-grid">
      <div class="card">
        <h3>Throughput (Requests / Second)</h3>
        <canvas id="throughputChart"></canvas>
      </div>
      <div class="card">
        <h3>Latency Breakdown (Seconds)</h3>
        <canvas id="latencyChart"></canvas>
      </div>
      <div class="card">
        <h3>Success Rate</h3>
        <canvas id="successChart"></canvas>
      </div>
      <div class="card">
        <h3>Token Generation Velocity (Tokens/s)</h3>
        <canvas id="tokenChart"></canvas>
      </div>
    </div>

    <div class="card">
      <h3>Detailed Scenario Analysis</h3>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Concurrency</th>
              <th>Ctx Length</th>
              <th>P95 Latency</th>
              <th>TTFT</th>
              <th>TPOT</th>
              <th>Req/s</th>
              <th>Tok/s</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            __ROWS__
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const labels = __LABELS__;
    const throughput = __THROUGHPUT__;
    const p95_latency = __P95_LATENCY__;
    const ttft = __TTFT__;
    const tpot = __TPOT__;
    const success = __SUCCESS__;
    const tokens = __TOKENS__;

    const chartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: '#9ca3af', font: { family: 'Outfit' } }
        }
      },
      scales: {
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } },
        x: { grid: { display: false }, ticks: { color: '#9ca3af' } }
      }
    };

    new Chart(document.getElementById('throughputChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Requests/s',
          data: throughput,
          backgroundColor: '#38bdf8',
          borderRadius: 6
        }]
      },
      options: chartOptions
    });

    new Chart(document.getElementById('latencyChart'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'P95 Latency', data: p95_latency, borderColor: '#f59e0b', tension: 0.3 },
          { label: 'TTFT', data: ttft, borderColor: '#38bdf8', tension: 0.3 },
          { label: 'TPOT', data: tpot, borderColor: '#10b981', tension: 0.3 }
        ]
      },
      options: chartOptions
    });

    new Chart(document.getElementById('successChart'), {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Success %',
          data: success.map(s => s * 100),
          borderColor: '#10b981',
          fill: true,
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          tension: 0.3
        }]
      },
      options: { ...chartOptions, scales: { ...chartOptions.scales, y: { min: 0, max: 100, ticks: { callback: v => v + '%' } } } }
    });

    new Chart(document.getElementById('tokenChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Tokens/s',
          data: tokens,
          backgroundColor: '#818cf8',
          borderRadius: 6
        }]
      },
      options: chartOptions
    });
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate premium benchmark dashboard HTML")
    parser.add_argument("--stats-csv", required=True, help="Path to scenario_stats.csv")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    rows = []
    data = {
        "labels": [],
        "throughput": [],
        "p95_latency": [],
        "ttft": [],
        "tpot": [],
        "success": [],
        "tokens": []
    }

    with Path(args.stats_csv).open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row["scenario"]
            succ = float(row["success_rate"])
            
            data["labels"].append(scenario)
            data["throughput"].append(float(row["throughput_req_per_s"]))
            data["p95_latency"].append(float(row["p95_latency_s"]))
            data["ttft"].append(float(row.get("p95_ttft_s", 0)))
            data["tpot"].append(float(row.get("p95_tpot_s", 0)))
            data["success"].append(succ)
            data["tokens"].append(float(row["throughput_out_tok_per_s"]))
            
            status_cls = "badge-success" if succ >= 0.99 else "badge-error"
            status_text = "PASS" if succ >= 0.99 else "FAIL"
            
            rows.append(
                f"<tr>"
                f"<td>{scenario}</td>"
                f"<td>{row['concurrency']}</td>"
                f"<td>{row['context_len']}</td>"
                f"<td>{float(row['p95_latency_s']):.3f}s</td>"
                f"<td>{float(row.get('p95_ttft_s', 0)):.3f}s</td>"
                f"<td>{float(row.get('p95_tpot_s', 0)):.4f}s</td>"
                f"<td>{float(row['throughput_req_per_s']):.2f}</td>"
                f"<td>{float(row['throughput_out_tok_per_s']):.1f}</td>"
                f"<td><span class='badge {status_cls}'>{status_text}</span></td>"
                f"</tr>"
            )

    html = (
        HTML_TEMPLATE.replace("__ROWS__", "\n".join(rows))
        .replace("__LABELS__", json.dumps(data["labels"]))
        .replace("__THROUGHPUT__", json.dumps(data["throughput"]))
        .replace("__P95_LATENCY__", json.dumps(data["p95_latency"]))
        .replace("__TTFT__", json.dumps(data["ttft"]))
        .replace("__TPOT__", json.dumps(data["tpot"]))
        .replace("__SUCCESS__", json.dumps(data["success"]))
        .replace("__TOKENS__", json.dumps(data["tokens"]))
    )
    
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Premium dashboard written to {out}")


if __name__ == "__main__":
    main()
