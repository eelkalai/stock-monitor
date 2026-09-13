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
        scales: { x: { ticks: { maxTicksLimit: 10 } } },
        plugins: { legend: { display: false } },
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
        renderChart(pane);
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

  document.addEventListener("DOMContentLoaded", function () {
    const pane = getPane();
    if (pane) renderChart(pane);
  });
})();
