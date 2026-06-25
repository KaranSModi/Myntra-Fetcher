const form = document.getElementById("upload-form");
const fileInput = document.getElementById("csv-file");
const fileLabelText = document.getElementById("file-label-text");
const submitBtn = document.getElementById("submit-btn");
const statusPanel = document.getElementById("status-panel");
const jobStatus = document.getElementById("job-status");
const progressBar = document.getElementById("progress-bar");
const progressText = document.getElementById("progress-text");
const successCount = document.getElementById("success-count");
const partialCount = document.getElementById("partial-count");
const failedCount = document.getElementById("failed-count");
const downloadBtn = document.getElementById("download-btn");
const warningsBox = document.getElementById("warnings");
const resultsBody = document.getElementById("results-body");
const historyList = document.getElementById("history-list");
const refreshHistoryBtn = document.getElementById("refresh-history-btn");

const LAST_JOB_KEY = "myntra_fetcher_last_job_id";

let currentJobId = null;
let pollTimer = null;
let cachedResults = [];

document.addEventListener("DOMContentLoaded", async () => {
  await loadHistory();

  const urlJobId = new URLSearchParams(window.location.search).get("job");
  const savedJobId = localStorage.getItem(LAST_JOB_KEY);
  const jobToLoad = urlJobId || savedJobId;

  if (jobToLoad) {
    await loadJob(jobToLoad, { resumePolling: false });
  }
});

refreshHistoryBtn.addEventListener("click", () => {
  loadHistory();
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  fileLabelText.textContent = file ? file.name : "Choose CSV file";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files?.[0];
  if (!file) return;

  submitBtn.disabled = true;
  warningsBox.classList.add("hidden");
  warningsBox.textContent = "";

  const body = new FormData();
  body.append("file", file);

  try {
    const response = await fetch("/api/v1/jobs", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to create job.");
    }

    if (payload.errors?.length) {
      warningsBox.classList.remove("hidden");
      warningsBox.textContent = payload.errors.join(" ");
    }

    currentJobId = payload.data.job.job_id;
    rememberJob(currentJobId);
    statusPanel.classList.remove("hidden");
    downloadBtn.classList.add("hidden");
    await loadHistory();
    startPolling();
  } catch (error) {
    alert(error.message);
    submitBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", () => {
  if (!currentJobId) return;
  window.location.href = `/api/v1/jobs/${currentJobId}/download`;
});

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollJob, 1500);
  pollJob();
}

async function loadHistory() {
  try {
    const response = await fetch("/api/v1/jobs?limit=20");
    const payload = await response.json();
    if (!response.ok) return;

    const jobs = payload.data.jobs || [];
    renderHistory(jobs);
  } catch {
    // History is optional UI; ignore transient failures.
  }
}

function renderHistory(jobs) {
  if (!jobs.length) {
    historyList.innerHTML = '<p class="empty-state">No saved runs yet.</p>';
    return;
  }

  historyList.innerHTML = "";
  jobs.forEach((job) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-item history-item--${job.status}${job.job_id === currentJobId ? " active" : ""}`;
    button.dataset.jobId = job.job_id;

    const created = formatDateTime(job.created_at);
    const statusLabel = job.status.charAt(0).toUpperCase() + job.status.slice(1);

    button.innerHTML = `
      <div class="history-item-main">
        <div class="history-item-title">
          <span class="history-status history-status--${job.status}">${statusLabel}</span>
          <span class="history-item-count">${job.total} products</span>
        </div>
        <div class="history-item-meta">${created} · ${job.job_id.slice(0, 8)}…</div>
      </div>
      <div class="history-item-stats">
        <span class="stat-ok">${job.success_count} ok</span>
        <span class="stat-sep">·</span>
        <span class="stat-partial">${job.partial_count} partial</span>
        <span class="stat-sep">·</span>
        <span class="stat-failed">${job.failed_count} failed</span>
      </div>
    `;

    button.addEventListener("click", () => {
      loadJob(job.job_id, { resumePolling: job.status === "running" || job.status === "pending" });
    });

    historyList.appendChild(button);
  });
}

async function loadJob(jobId, { resumePolling = false } = {}) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  const response = await fetch(`/api/v1/jobs/${jobId}`);
  const payload = await response.json();
  if (!response.ok) {
    alert(payload.detail || "Could not load saved run.");
    return;
  }

  currentJobId = jobId;
  rememberJob(jobId);
  await loadHistory();

  const job = payload.data.job;
  const results = payload.data.results || [];
  cachedResults = results;

  statusPanel.classList.remove("hidden");
  applyJobSummary(job);
  renderResults(results);

  if (job.status === "completed") {
    submitBtn.disabled = false;
    downloadBtn.classList.remove("hidden");
  } else if (job.status === "failed") {
    submitBtn.disabled = false;
    downloadBtn.classList.add("hidden");
  } else if (resumePolling) {
    submitBtn.disabled = true;
    downloadBtn.classList.add("hidden");
    startPolling();
  } else {
    submitBtn.disabled = false;
    downloadBtn.classList.add("hidden");
  }
}

function rememberJob(jobId) {
  localStorage.setItem(LAST_JOB_KEY, jobId);
  const url = new URL(window.location.href);
  url.searchParams.set("job", jobId);
  window.history.replaceState({}, "", url);
}

function applyJobSummary(job) {
  jobStatus.textContent = job.status;
  const percent = job.total ? Math.round((job.processed / job.total) * 100) : 0;
  progressBar.style.width = `${percent}%`;
  progressText.textContent = `${job.processed} / ${job.total} processed`;
  successCount.textContent = job.success_count;
  partialCount.textContent = job.partial_count;
  failedCount.textContent = job.failed_count;
}

async function pollJob() {
  if (!currentJobId) return;

  const response = await fetch(`/api/v1/jobs/${currentJobId}`);
  const payload = await response.json();
  if (!response.ok) {
    clearInterval(pollTimer);
    submitBtn.disabled = false;
    alert(payload.detail || "Failed to fetch job.");
    return;
  }

  const job = payload.data.job;
  const results = payload.data.results || [];
  cachedResults = results;

  applyJobSummary(job);
  renderResults(results);

  if (job.status === "completed" || job.status === "failed") {
    clearInterval(pollTimer);
    submitBtn.disabled = false;
    rememberJob(currentJobId);
    await loadHistory();
    if (job.status === "completed") {
      downloadBtn.classList.remove("hidden");
    }
  }
}

function renderResults(results) {
  if (!results.length) {
    resultsBody.innerHTML = '<tr><td colspan="8" class="empty">Waiting for results...</td></tr>';
    return;
  }

  resultsBody.innerHTML = results
    .map((result, index) => {
      const product = result.product || {};
      const rating =
        result.product?.rating != null
          ? `${Number(result.product.rating).toFixed(1)} (${result.product.rating_count ?? 0})`
          : "-";
      const deliverySummary = formatDeliverySummary(result.delivery);
      return `
        <tr class="result-row" data-index="${index}">
          <td>${result.product_id}</td>
          <td><span class="badge ${result.status}">${result.status}</span></td>
          <td>${escapeHtml(product.title || "-")}</td>
          <td>${escapeHtml(product.category || "-")}</td>
          <td>${rating}</td>
          <td>${result.category_ads?.length || 0}</td>
          <td>${deliverySummary}</td>
          <td>
            <button class="toggle-btn" type="button" data-index="${index}">View</button>
          </td>
        </tr>
        <tr class="detail-row hidden" id="detail-row-${index}">
          <td colspan="8">
            <div class="detail-panel-wrap" id="detail-${index}"></div>
          </td>
        </tr>
      `;
    })
    .join("");

  resultsBody.querySelectorAll(".toggle-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const index = button.dataset.index;
      const detailRow = document.getElementById(`detail-row-${index}`);
      const container = document.getElementById(`detail-${index}`);
      const result = cachedResults[index];
      const isHidden = detailRow.classList.contains("hidden");

      resultsBody.querySelectorAll(".detail-row").forEach((row) => row.classList.add("hidden"));
      resultsBody.querySelectorAll(".toggle-btn").forEach((btn) => {
        btn.textContent = "View";
      });
      resultsBody.querySelectorAll(".result-row").forEach((row) => row.classList.remove("expanded"));

      if (isHidden) {
        container.innerHTML = "";
        container.appendChild(buildDetailPanel(result));
        detailRow.classList.remove("hidden");
        button.textContent = "Hide";
        button.closest(".result-row")?.classList.add("expanded");
        detailRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    });
  });
}

function buildDetailPanel(result) {
  const panel = document.createElement("div");
  panel.className = "detail-panel";

  panel.appendChild(buildProductStrip(result.product));

  const topGrid = document.createElement("div");
  topGrid.className = "detail-top-grid";

  const overview = document.createElement("div");
  overview.className = "detail-overview";
  overview.appendChild(buildSection("Description", buildDescriptionBlock(result.product)));

  if (result.product?.images?.length) {
    const imageTitle = result.product.images.length > 1 ? "More images" : "Product image";
    const imagesSection = buildSection(imageTitle, buildImagesBlock(result.product));
    imagesSection.classList.add("detail-section-images");
    overview.appendChild(imagesSection);
  }

  const deliveryAside = document.createElement("div");
  deliveryAside.className = "detail-delivery-aside";
  deliveryAside.appendChild(buildSection("Delivery by pincode", buildDeliveryBlock(result.delivery)));

  topGrid.appendChild(overview);
  topGrid.appendChild(deliveryAside);
  panel.appendChild(topGrid);

  panel.appendChild(buildSponsoredAdsSection(result.category_ads));

  if (result.errors?.length) {
    panel.appendChild(buildSection("Warnings", buildWarningsBlock(result.errors)));
  }

  return panel;
}

function buildProductStrip(product = {}) {
  const strip = document.createElement("div");
  strip.className = "detail-product-strip";

  const thumb = document.createElement("div");
  thumb.className = "detail-product-thumb";
  if (product.images?.[0]) {
    const img = document.createElement("img");
    img.src = product.images[0];
    img.alt = product.title || "Product";
    img.loading = "lazy";
    thumb.appendChild(img);
  } else {
    thumb.innerHTML = '<span class="empty-state">No image</span>';
  }

  const meta = document.createElement("div");
  meta.className = "detail-product-meta";

  const title = document.createElement("h4");
  title.className = "detail-product-title";
  title.textContent = product.title || "Untitled product";

  const priceRow = document.createElement("div");
  priceRow.className = "detail-product-price-row";
  if (product.price != null) {
    const price = document.createElement("span");
    price.className = "detail-product-price";
    price.textContent = `Rs. ${Number(product.price).toLocaleString("en-IN")}`;
    priceRow.appendChild(price);
  }
  if (product.mrp != null && product.mrp !== product.price) {
    const mrp = document.createElement("span");
    mrp.className = "detail-product-mrp";
    mrp.textContent = `Rs. ${Number(product.mrp).toLocaleString("en-IN")}`;
    priceRow.appendChild(mrp);
  }

  const ratingRow = document.createElement("div");
  ratingRow.className = "detail-product-rating";
  if (product.rating != null) {
    ratingRow.innerHTML = `<strong>${Number(product.rating).toFixed(1)}</strong> <span>(${product.rating_count ?? 0} ratings)</span>`;
  } else {
    ratingRow.innerHTML = '<span class="muted">No rating</span>';
  }

  meta.appendChild(title);
  if (priceRow.childNodes.length) {
    meta.appendChild(priceRow);
  }
  meta.appendChild(ratingRow);

  strip.appendChild(thumb);
  strip.appendChild(meta);
  return strip;
}

function buildSponsoredAdsSection(ads = []) {
  const section = document.createElement("section");
  section.className = "detail-section detail-section-ads";

  const header = document.createElement("div");
  header.className = "ads-section-header";

  const heading = document.createElement("h3");
  heading.textContent = "Sponsored category ads";

  const badge = document.createElement("span");
  badge.className = "sponsored-section-badge";
  badge.textContent = "Sponsored";

  header.appendChild(heading);
  header.appendChild(badge);

  const hint = document.createElement("p");
  hint.className = "ads-section-hint";
  hint.textContent = "Paid placements from this product’s category on Myntra";

  section.appendChild(header);
  section.appendChild(hint);
  section.appendChild(buildAdsBlock(ads));
  return section;
}

function buildSection(title, content) {
  const section = document.createElement("section");
  section.className = "detail-section";

  const heading = document.createElement("h3");
  heading.textContent = title;
  section.appendChild(heading);
  section.appendChild(content);
  return section;
}

function buildDescriptionBlock(product = {}) {
  const card = document.createElement("div");
  card.className = "description-card";

  const description = (product.description || "").trim();
  if (!description) {
    card.innerHTML = '<p class="empty-state">No description available.</p>';
    return card;
  }

  const parts = description.split(/\n+/).map((part) => part.trim()).filter(Boolean);
  parts.forEach((part) => {
    const paragraph = document.createElement("p");
    paragraph.textContent = part;
    card.appendChild(paragraph);
  });

  return card;
}

function buildImagesBlock(product = {}) {
  const gallery = document.createElement("div");
  gallery.className = "image-gallery";

  const images = product.images || [];
  if (!images.length) {
    gallery.innerHTML = '<p class="empty-state">No images available.</p>';
    return gallery;
  }

  images.forEach((url) => {
    const img = document.createElement("img");
    img.src = url;
    img.alt = product.title || "Product image";
    img.loading = "lazy";
    gallery.appendChild(img);
  });

  return gallery;
}

function buildAdsBlock(ads = []) {
  const scroll = document.createElement("div");
  scroll.className = "ads-scroll";

  if (!ads.length) {
    scroll.innerHTML = '<p class="empty-state">No sponsored ads returned for this category.</p>';
    return scroll;
  }

  const grid = document.createElement("div");
  grid.className = "ads-grid ads-grid-horizontal";

  ads.forEach((ad) => {
    const card = document.createElement("article");
    card.className = "ad-card";

    const imageWrap = document.createElement("div");
    imageWrap.className = "ad-image-wrap";

    if (ad.image) {
      const img = document.createElement("img");
      img.src = ad.image;
      img.alt = ad.title || "Sponsored product";
      img.loading = "lazy";
      imageWrap.appendChild(img);
    } else {
      imageWrap.style.display = "flex";
      imageWrap.style.alignItems = "center";
      imageWrap.style.justifyContent = "center";
      imageWrap.innerHTML = '<span class="empty-state">No image</span>';
    }

    const badge = document.createElement("span");
    badge.className = "ad-badge";
    badge.textContent = "AD";
    imageWrap.appendChild(badge);

    const body = document.createElement("div");
    body.className = "ad-body";

    const title = document.createElement("p");
    title.className = "ad-title";
    title.textContent = ad.title || "Unknown product";

    const priceRow = document.createElement("div");
    priceRow.className = "ad-price-row";

    const price = document.createElement("span");
    price.className = "ad-price";
    price.textContent = ad.price != null ? `Rs. ${formatNumber(ad.price)}` : "Price N/A";
    priceRow.appendChild(price);

    if (ad.mrp && ad.mrp !== ad.price) {
      const mrp = document.createElement("span");
      mrp.className = "ad-mrp";
      mrp.textContent = `Rs. ${formatNumber(ad.mrp)}`;
      priceRow.appendChild(mrp);
    }

    const rating = document.createElement("p");
    rating.className = "ad-rating";
    if (ad.rating != null) {
      rating.innerHTML = `<strong>${Number(ad.rating).toFixed(1)}</strong> (${ad.rating_count ?? 0} ratings)`;
    } else {
      rating.textContent = "No ratings yet";
    }

    body.appendChild(title);
    body.appendChild(priceRow);
    body.appendChild(rating);

    card.appendChild(imageWrap);
    card.appendChild(body);
    grid.appendChild(card);
  });

  scroll.appendChild(grid);
  return scroll;
}

function buildDeliveryBlock(delivery = []) {
  if (!delivery.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No delivery data available.";
    return empty;
  }

  const table = document.createElement("table");
  table.className = "delivery-table";

  table.innerHTML = `
    <thead>
      <tr>
        <th>City</th>
        <th>Pincode</th>
        <th>Est. days</th>
        <th>Delivery promise</th>
      </tr>
    </thead>
  `;

  const body = document.createElement("tbody");
  delivery.forEach((entry) => {
    const row = document.createElement("tr");
    if (entry.serviceable === false) {
      row.classList.add("unserviceable");
    }

    const promise =
      entry.delivery_text ||
      (entry.serviceable ? "Serviceable" : entry.serviceable === false ? "Not serviceable" : "—");

    row.innerHTML = `
      <td class="delivery-table-city">${escapeHtml(entry.city || "—")}</td>
      <td class="delivery-table-pin">${escapeHtml(entry.pincode || "—")}</td>
      <td><span class="days-badge ${entry.estimated_days == null ? "neutral" : ""}">${formatDaysBadge(entry.estimated_days)}</span></td>
      <td class="delivery-table-promise">${escapeHtml(promise)}</td>
    `;
    body.appendChild(row);
  });

  table.appendChild(body);
  return table;
}

function buildWarningsBlock(errors = []) {
  const list = document.createElement("ul");
  list.className = "warnings-list";
  errors.forEach((error) => {
    const item = document.createElement("li");
    item.textContent = error;
    list.appendChild(item);
  });
  return list;
}

function formatDeliverySummary(delivery = []) {
  if (!delivery.length) {
    return '<span class="delivery-chip muted">—</span>';
  }

  const days = delivery
    .map((entry) => entry.estimated_days)
    .filter((value) => value != null);

  if (days.length) {
    const min = Math.min(...days);
    const max = Math.max(...days);
    const label = min === max ? `${min} day${min === 1 ? "" : "s"}` : `${min}–${max} days`;
    return `<span class="delivery-chip" title="Estimated delivery across checked pincodes">${label}</span>`;
  }

  const serviceableCount = delivery.filter((entry) => entry.serviceable).length;
  if (serviceableCount) {
    return `<span class="delivery-chip">${serviceableCount} pincode${serviceableCount === 1 ? "" : "s"} OK</span>`;
  }

  return '<span class="delivery-chip muted">Unavailable</span>';
}

function formatDaysBadge(days) {
  if (days == null) return "—";
  if (days === 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

function formatNumber(value) {
  return Number(value).toLocaleString("en-IN");
}

function formatDateTime(value) {
  if (!value) return "Unknown time";
  const date = new Date(value);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
