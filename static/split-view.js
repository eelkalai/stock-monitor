(function () {
  function getPane() {
    return document.getElementById("detail-pane");
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

  function loadFragment(url) {
    const pane = getPane();
    if (!pane) return;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("bad response");
        return res.text();
      })
      .then((html) => {
        pane.innerHTML = html;
        try {
          renderChart(pane);
        } catch (e) {
          console.error("chart render failed", e);
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
      loadFragment(stockLink.href);
      return;
    }

    const periodLink = event.target.closest("#detail-pane .period-links a");
    if (periodLink) {
      event.preventDefault();
      periodLink.parentElement
        .querySelectorAll("a.active")
        .forEach((a) => a.classList.remove("active"));
      periodLink.classList.add("active");
      loadFragment(periodLink.href);
    }
  });

  const SPLIT_WIDTH_KEY = "stockMonitorListPaneWidth";

  function initResizer() {
    const divider = document.getElementById("split-divider");
    const listPane = document.getElementById("list-pane");
    const container = divider && divider.closest(".split-view");
    if (!divider || !listPane || !container) return;

    let savedWidth = null;
    try {
      savedWidth = parseFloat(localStorage.getItem(SPLIT_WIDTH_KEY));
    } catch (e) {}
    if (savedWidth) listPane.style.flex = `0 0 ${savedWidth}px`;

    function onMouseMove(event) {
      const rect = container.getBoundingClientRect();
      const min = 160;
      const max = rect.width - 240;
      const width = Math.min(Math.max(event.clientX - rect.left, min), Math.max(min, max));
      listPane.style.flex = `0 0 ${width}px`;
    }

    function onMouseUp() {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      divider.classList.remove("dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      try {
        localStorage.setItem(SPLIT_WIDTH_KEY, listPane.getBoundingClientRect().width);
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
  }

  document.addEventListener("DOMContentLoaded", function () {
    initResizer();
    const pane = getPane();
    if (!pane) return;
    try {
      renderChart(pane);
    } catch (e) {
      console.error("chart render failed", e);
    }
  });
})();
