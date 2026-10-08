// Renders Chart.js charts from the JSON in <script id="chart-data">.
// Money values arrive as decimal strings and are only converted for drawing.
(function () {
  "use strict";
  var dataEl = document.getElementById("chart-data");
  if (!dataEl || typeof Chart === "undefined") return;
  var data = JSON.parse(dataEl.textContent);
  var charts = [];

  var symbol = document.body.dataset.currency || "$";
  var money = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  function fmt(v) {
    return symbol + money.format(v);
  }
  function num(list) {
    return (list || []).map(Number);
  }

  function palette() {
    var dark = document.documentElement.classList.contains("dark");
    return {
      text: dark ? "#9ca3af" : "#6b7280",
      grid: dark ? "rgba(255,255,255,0.06)" : "rgba(17,24,39,0.06)",
      emerald: dark ? "#34d399" : "#059669",
      emeraldSoft: dark ? "rgba(52,211,153,0.35)" : "rgba(5,150,105,0.25)",
      slate: dark ? "#64748b" : "#94a3b8",
      surface: dark ? "#111827" : "#ffffff",
    };
  }

  function baseOptions(p, stacked) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: p.text, usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: function (ctx) { return " " + ctx.dataset.label + ": " + fmt(ctx.parsed.y); } } },
      },
      scales: {
        x: { stacked: stacked, grid: { display: false }, ticks: { color: p.text } },
        y: {
          stacked: stacked,
          beginAtZero: true,
          grid: { color: p.grid },
          border: { display: false },
          ticks: { color: p.text, callback: function (v) { return fmt(v); } },
        },
      },
    };
  }

  function render() {
    charts.forEach(function (c) { c.destroy(); });
    charts = [];
    var p = palette();

    var trendEl = document.getElementById("trend-chart");
    if (trendEl && data.trend) {
      charts.push(new Chart(trendEl, {
        type: "bar",
        data: {
          labels: data.trend.labels,
          datasets: [
            { label: "Bill payments", data: num(data.trend.bills), backgroundColor: p.emerald, borderRadius: 6, maxBarThickness: 36 },
            { label: "Other expenses", data: num(data.trend.other), backgroundColor: p.emeraldSoft, borderRadius: 6, maxBarThickness: 36 },
          ],
        },
        options: baseOptions(p, true),
      }));
    }

    var catEl = document.getElementById("category-chart");
    if (catEl && data.categories && data.categories.labels.length) {
      charts.push(new Chart(catEl, {
        type: "doughnut",
        data: {
          labels: data.categories.labels,
          datasets: [{ data: num(data.categories.values), backgroundColor: data.categories.colors, borderColor: p.surface, borderWidth: 3 }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "68%",
          plugins: {
            legend: {
              display: catEl.dataset.legend !== "none",
              position: "bottom",
              labels: { color: p.text, usePointStyle: true, boxWidth: 8 },
            },
            tooltip: { callbacks: { label: function (ctx) { return " " + ctx.label + ": " + fmt(ctx.parsed); } } },
          },
        },
      }));
    }

    var cmpEl = document.getElementById("comparison-chart");
    if (cmpEl && data.comparison) {
      var opts = baseOptions(p, false);
      charts.push(new Chart(cmpEl, {
        type: "bar",
        data: {
          labels: data.comparison.labels,
          datasets: [
            { label: cmpEl.dataset.lastLabel, data: num(data.comparison.last), backgroundColor: p.slate, borderRadius: 6, maxBarThickness: 28 },
            { label: cmpEl.dataset.thisLabel, data: num(data.comparison.this), backgroundColor: p.emerald, borderRadius: 6, maxBarThickness: 28 },
          ],
        },
        options: opts,
      }));
    }
  }

  render();
  document.addEventListener("themechange", render);
})();
