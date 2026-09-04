const navigation = document.querySelector("#navigation");
const article = document.querySelector("#article");
const status = document.querySelector("#status");
const search = document.querySelector("#search");
let docs = [];

const esc = (text) => text.replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const docLink = (href) => href.endsWith(".md") || href.includes(".md#") ? `#${href.replace(/^\.\.\//, "docs/")}` : href;

function markdown(source) {
  const lines = source.replace(/\r/g, "").split("\n");
  let html = "", list = false, code = false;
  for (let line of lines) {
    if (line.startsWith("```")) { html += code ? "</code></pre>" : "<pre><code>"; code = !code; continue; }
    if (code) { html += `${esc(line)}\n`; continue; }
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    if (heading) { if (list) { html += "</ul>"; list = false; } const level = heading[1].length; html += `<h${level}>${inline(heading[2])}</h${level}>`; continue; }
    if (/^\s*[-*]\s+/.test(line)) { if (!list) { html += "<ul>"; list = true; } html += `<li>${inline(line.replace(/^\s*[-*]\s+/, ""))}</li>`; continue; }
    if (list) { html += "</ul>"; list = false; }
    if (!line.trim()) continue;
    if (/^\|/.test(line) || /^[-| :]+$/.test(line)) continue;
    html += `<p>${inline(line)}</p>`;
  }
  return html + (list ? "</ul>" : "") + (code ? "</code></pre>" : "");
}

function inline(text) {
  return esc(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => `<a href="${docLink(href)}">${label}</a>`);
}

function renderNav() {
  const query = search.value.trim().toLowerCase();
  const groups = docs.filter(doc => doc.title.toLowerCase().includes(query)).reduce((all, doc) => {
    (all[doc.section] ??= []).push(doc); return all;
  }, {});
  navigation.innerHTML = Object.entries(groups).map(([section, entries]) =>
    `<section><h2>${section}</h2>${entries.map(doc => `<a href="#${doc.path}" data-path="${doc.path}">${doc.title}</a>`).join("")}</section>`
  ).join("");
}

async function openDocument() {
  const path = decodeURIComponent(location.hash.slice(1)) || "docs/wiki/INDEX.md";
  const current = docs.find(doc => doc.path === path);
  if (!current) return;
  status.textContent = current.path;
  document.title = `${current.title} — Water Regime GIS`;
  const response = await fetch(`/api/document?path=${encodeURIComponent(path)}`);
  article.innerHTML = response.ok ? markdown(await response.text()) : "<h1>Документ не найден</h1>";
  navigation.querySelectorAll("a").forEach(link => link.classList.toggle("active", link.dataset.path === path));
}

async function loadDocs() {
  const fresh = await (await fetch("/api/documents")).json();
  if (JSON.stringify(fresh) !== JSON.stringify(docs)) { docs = fresh; renderNav(); }
  await openDocument();
}

search.addEventListener("input", renderNav);
window.addEventListener("hashchange", openDocument);
loadDocs().catch(error => { status.textContent = "Не удалось загрузить wiki"; article.textContent = error.message; });
setInterval(() => loadDocs().catch(() => {}), 10000);
