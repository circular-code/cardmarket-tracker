(function () {
  const PRICE_FIELDS = [
    { field: "avg", label: "AVG", color: "#1f6f8b" },
    { field: "low", label: "Low", color: "#7d5a00" },
    { field: "trend", label: "Trend", color: "#8b3f64" },
    { field: "avg1", label: "AVG1", color: "#2f7d32" },
    { field: "avg7", label: "AVG7", color: "#7556a8" },
    { field: "avg30", label: "AVG30", color: "#b34b27" },
  ];

  const state = {
    rows: [],
    products: [],
    selectedProductId: null,
  };

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    try {
      const manifest = await fetchJson("data/manifest.json");
      const priceFiles = manifest.priceFiles || [];
      state.rows = await loadPriceRows(priceFiles);
      state.products = buildProducts(state.rows);
      renderProductSelect();
      updateStatus(manifest);
      if (!state.products.length) {
        document.getElementById("emptyState").innerHTML = "<h2>No snapshots yet</h2><p>Run the snapshot collector and refresh this page.</p>";
      }
    } catch (error) {
      showFatalError(error);
    }
  }

  async function fetchJson(url) {
    const response = await fetch(`${url}?v=${Date.now()}`);
    if (!response.ok) {
      throw new Error(`Could not load ${url}`);
    }
    return response.json();
  }

  async function fetchText(url) {
    const response = await fetch(`${url}?v=${Date.now()}`);
    if (!response.ok) {
      throw new Error(`Could not load ${url}`);
    }
    return response.text();
  }

  async function loadPriceRows(priceFiles) {
    const files = priceFiles.length ? priceFiles : [`prices/${new Date().getFullYear()}.csv`];
    const chunks = await Promise.all(
      files.map(async (file) => {
        try {
          return parseCsv(await fetchText(`data/${file}`));
        } catch (error) {
          if (priceFiles.length) {
            throw error;
          }
          return [];
        }
      })
    );

    return chunks
      .flat()
      .map(normalizeRow)
      .filter((row) => row.idProduct && row.snapshotDate instanceof Date && !Number.isNaN(row.snapshotDate.valueOf()));
  }

  function parseCsv(text) {
    const rows = [];
    let row = [];
    let cell = "";
    let inQuotes = false;

    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      const next = text[i + 1];

      if (char === '"') {
        if (inQuotes && next === '"') {
          cell += '"';
          i += 1;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === "," && !inQuotes) {
        row.push(cell);
        cell = "";
      } else if ((char === "\n" || char === "\r") && !inQuotes) {
        if (char === "\r" && next === "\n") {
          i += 1;
        }
        row.push(cell);
        if (row.some((value) => value !== "")) {
          rows.push(row);
        }
        row = [];
        cell = "";
      } else {
        cell += char;
      }
    }

    if (cell || row.length) {
      row.push(cell);
      rows.push(row);
    }

    const header = rows.shift() || [];
    return rows.map((values) => Object.fromEntries(header.map((key, index) => [key, values[index] || ""])));
  }

  function normalizeRow(row) {
    const normalized = {
      snapshot_date: row.snapshot_date,
      snapshotDate: parseDate(row.snapshot_date),
      idProduct: String(row.idProduct || ""),
      name: row.name || "Unknown product",
      categoryName: row.categoryName || "",
      idExpansion: row.idExpansion || "",
      dateAdded: row.dateAdded || "",
    };

    PRICE_FIELDS.forEach(({ field }) => {
      normalized[field] = parsePrice(row[field]);
    });

    return normalized;
  }

  function parseDate(value) {
    if (!value) {
      return null;
    }
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function parsePrice(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    const parsed = Number(String(value).replace(",", "."));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function buildProducts(rows) {
    const byId = new Map();
    rows.forEach((row) => {
      if (!byId.has(row.idProduct)) {
        byId.set(row.idProduct, {
          idProduct: row.idProduct,
          name: row.name,
          categoryName: row.categoryName,
          idExpansion: row.idExpansion,
          dateAdded: row.dateAdded,
          points: 0,
        });
      }
      byId.get(row.idProduct).points += 1;
    });

    return Array.from(byId.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  function renderProductSelect() {
    $("#productSelect").dxSelectBox({
      dataSource: state.products,
      displayExpr: (item) => (item ? `${item.name} (${item.points} snapshots)` : ""),
      valueExpr: "idProduct",
      searchEnabled: true,
      searchExpr: ["name", "idProduct"],
      placeholder: state.products.length ? "Choose a collector display..." : "No price snapshots found",
      noDataText: "No collector displays found",
      disabled: !state.products.length,
      onValueChanged: (event) => {
        state.selectedProductId = event.value;
        renderSelectedProduct();
      },
    });
  }

  function renderSelectedProduct() {
    const product = state.products.find((item) => item.idProduct === state.selectedProductId);
    if (!product) {
      document.getElementById("chartPanel").hidden = true;
      document.getElementById("emptyState").hidden = false;
      return;
    }

    const rows = state.rows
      .filter((row) => row.idProduct === product.idProduct)
      .sort((a, b) => a.snapshotDate - b.snapshotDate);

    document.getElementById("emptyState").hidden = true;
    document.getElementById("chartPanel").hidden = false;
    document.getElementById("chartTitle").textContent = product.name;
    document.getElementById("chartMeta").textContent = buildMetaText(product, rows);
    renderLatestValues(rows.at(-1));
    renderChart(rows);
  }

  function buildMetaText(product, rows) {
    const first = rows[0]?.snapshot_date || "n/a";
    const last = rows.at(-1)?.snapshot_date || "n/a";
    const parts = [`${rows.length} snapshots`, `${first} to ${last}`, `idProduct ${product.idProduct}`];
    if (product.dateAdded) {
      parts.push(`added ${product.dateAdded}`);
    }
    return parts.join(" · ");
  }

  function renderLatestValues(row) {
    const target = document.getElementById("latestValues");
    target.innerHTML = "";
    PRICE_FIELDS.forEach(({ field, label }) => {
      const value = row ? row[field] : null;
      const metric = document.createElement("div");
      metric.className = "metric";
      metric.innerHTML = `<span>${label}</span><strong>${formatEuro(value)}</strong>`;
      target.appendChild(metric);
    });
  }

  function renderChart(rows) {
    $("#priceChart").dxChart({
      dataSource: rows,
      palette: PRICE_FIELDS.map((item) => item.color),
      commonSeriesSettings: {
        argumentField: "snapshotDate",
        type: "line",
        width: 2,
        point: { visible: false },
      },
      series: PRICE_FIELDS.map(({ field, label }) => ({
        valueField: field,
        name: label,
      })),
      argumentAxis: {
        argumentType: "datetime",
        label: { format: "yyyy-MM-dd" },
        grid: { visible: true },
      },
      valueAxis: {
        title: "EUR",
        label: { customizeText: (event) => formatEuro(event.value) },
      },
      legend: {
        verticalAlignment: "bottom",
        horizontalAlignment: "center",
        orientation: "horizontal",
        itemTextPosition: "right",
      },
      tooltip: {
        enabled: true,
        shared: true,
        customizeTooltip: (event) => {
          const lines = event.points
            .map((point) => `${point.seriesName}: ${formatEuro(point.value)}`)
            .join("<br>");
          return { html: `<strong>${formatDate(event.argument)}</strong><br>${lines}` };
        },
      },
      crosshair: {
        enabled: true,
        label: { visible: true },
      },
      zoomAndPan: {
        argumentAxis: "both",
      },
      scrollBar: {
        visible: true,
      },
      onLegendClick: (event) => {
        const series = event.target;
        if (series.isVisible()) {
          series.hide();
        } else {
          series.show();
        }
      },
      export: {
        enabled: true,
      },
    });
  }

  function updateStatus(manifest) {
    const status = document.getElementById("statusPill");
    const latest = manifest.latestSnapshotDate || "no snapshots yet";
    status.textContent = `${state.products.length} products · latest ${latest}`;
  }

  function showFatalError(error) {
    console.error(error);
    document.getElementById("statusPill").textContent = "Data load failed";
    document.getElementById("emptyState").innerHTML = "<h2>Could not load data</h2><p>Run the snapshot collector and refresh this page.</p>";
  }

  function formatEuro(value) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return "n/a";
    }
    return new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 2,
    }).format(value);
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("en-CA").format(value);
  }
})();
