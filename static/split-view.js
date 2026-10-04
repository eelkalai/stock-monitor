(function () {
  function getPane() {
    return document.getElementById("detail-pane");
  }

  function getAnalysisPane() {
    return document.getElementById("analysis-pane");
  }

  function renderChart(pane) {
    const canvas = pane.querySelector("#chart");
    if (!canvas || typeof Chart === "undefined") return;
    const history = JSON.parse(canvas.dataset.history || "[]");
    if (window.__stockChart) window.__stockChart.destroy();
    window.__stockChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: history.map((p) => p.date),
        datasets: [
          {
            label: canvas.dataset.label,
            data: history.map((p) => p.close),
            borderColor: "#2f6fed",
            backgroundColor: "rgba(47,111,237,0.1)",
            fill: true,
            pointRadius: 0,
            tension: 0.15,
          },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 10 } } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `$${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
        elements: { point: { hoverRadius: 5, hitRadius: 12 } },
      },
    });
  }

  function renderAnalysisChart(pane) {
    if (window.__analysisChart) {
      window.__analysisChart.destroy();
      window.__analysisChart = null;
    }
    const canvas = pane && pane.querySelector("#analysis-chart");
    if (!canvas || typeof Chart === "undefined") return;
    const chart = JSON.parse(canvas.dataset.chart || "{}");
    window.__analysisChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: chart.labels || [],
        datasets: (chart.series || []).map((s, i) => ({
          label: s.label,
          data: s.data,
          borderColor: i === 0 ? "#2f6fed" : "#8a8f98",
          borderDash: i === 0 ? [] : [4, 4],
          pointRadius: 0,
          tension: 0.15,
        })),
      },
      options: {
        aspectRatio: 1.2,
        interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 10 } } },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
        elements: { point: { hoverRadius: 5, hitRadius: 12 } },
      },
    });
  }

  function loadFragment(url, pane, onLoaded) {
    if (!pane) return;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("bad response");
        return res.text();
      })
      .then((html) => {
        pane.innerHTML = html;
        try {
          onLoaded(pane);
        } catch (e) {
          console.error("render failed", e);
        }
      })
      .catch(() => {
        pane.innerHTML = '<p class="error">Could not load details. Try again.</p>';
      });
  }

  document.addEventListener("click", function (event) {
    const stockLink = event.target.closest(".list-pane a.stock-link");
    if (stockLink) {
      event.preventDefault();
      const pane = stockLink.closest(".list-pane");
      pane.querySelectorAll("tr.selected").forEach((tr) => tr.classList.remove("selected"));
      const row = stockLink.closest("tr");
      if (row) row.classList.add("selected");

      loadFragment(stockLink.href, getPane(), renderChart);

      const analysisPane = getAnalysisPane();
      const symbol = stockLink.dataset.symbol;
      if (analysisPane && symbol) {
        const linkUrl = new URL(stockLink.href, window.location.origin);
        const origin = linkUrl.searchParams.get("origin") || "dashboard";
        const tab = new URLSearchParams(window.location.search).get("tab");
        let analysisUrl = `/stocks/${encodeURIComponent(symbol)}/analysis?origin=${encodeURIComponent(origin)}`;
        if (tab) analysisUrl += `&tab=${encodeURIComponent(tab)}`;
        loadFragment(analysisUrl, analysisPane, renderAnalysisChart);
      }
      return;
    }

    const periodLink = event.target.closest("#detail-pane .period-links a");
    if (periodLink) {
      event.preventDefault();
      periodLink.parentElement
        .querySelectorAll("a.active")
        .forEach((a) => a.classList.remove("active"));
      periodLink.classList.add("active");
      loadFragment(periodLink.href, getPane(), renderChart);
    }
  });

  const SPLIT_WIDTH_PREFIX = "stockMonitorPaneWidth:";

  function initResizer() {
    document.querySelectorAll(".split-divider").forEach(function (divider) {
      const pane = divider.previousElementSibling;
      const container = divider.closest(".split-view");
      if (!pane || !container) return;
      const key = SPLIT_WIDTH_PREFIX + (pane.id || pane.className);

      let savedWidth = null;
      try {
        savedWidth = parseFloat(localStorage.getItem(key));
      } catch (e) {}
      if (savedWidth) pane.style.flex = `0 0 ${savedWidth}px`;

      function onMouseMove(event) {
        const containerRect = container.getBoundingClientRect();
        const paneRect = pane.getBoundingClientRect();
        const min = 160;
        const max = Math.max(min, containerRect.right - paneRect.left - 240);
        const width = Math.min(Math.max(event.clientX - paneRect.left, min), max);
        pane.style.flex = `0 0 ${width}px`;
      }

      function onMouseUp() {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        divider.classList.remove("dragging");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        try {
          localStorage.setItem(key, pane.getBoundingClientRect().width);
        } catch (e) {}
      }

      divider.addEventListener("mousedown", function (event) {
        event.preventDefault();
        divider.classList.add("dragging");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
      });
    });
  }

  function initScreenerPicker() {
    const select = document.getElementById("screener-select");
    const form = document.getElementById("screener-run-form");
    if (!select || !form) return;

    function sync() {
      form.action = `/screeners/${encodeURIComponent(select.value)}/run`;
      form.querySelectorAll(".param-group").forEach(function (group) {
        const active = group.dataset.script === select.value;
        group.hidden = !active;
        group.querySelectorAll("input").forEach((input) => {
          input.disabled = !active;
        });
      });
    }

    select.addEventListener("change", sync);
    sync();
  }

  document.addEventListener("DOMContentLoaded", function () {
    initResizer();
    initScreenerPicker();
    const pane = getPane();
    if (pane) {
      try {
        renderChart(pane);
      } catch (e) {
        console.error("chart render failed", e);
      }
    }
    const analysisPane = getAnalysisPane();
    if (analysisPane) {
      try {
        renderAnalysisChart(analysisPane);
      } catch (e) {
        console.error("analysis chart render failed", e);
      }
    }
  });
})();
