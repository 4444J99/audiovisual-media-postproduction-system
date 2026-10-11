#!/usr/bin/env node
// Execute the recovery view against real metadata and a minimal DOM fixture.
// No browser, media, network, or artistic acceptance is inferred by this check.
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const options = {};
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  if (!["--root", "--output"].includes(key) || !process.argv[index + 1]) throw new Error("Usage: probe_reproduction_view.mjs [--root REPOSITORY] --output RECEIPT.json");
  options[key] = process.argv[index + 1];
}
if (!options["--output"]) throw new Error("--output is required");
const root = path.resolve(options["--root"] || path.join(path.dirname(fileURLToPath(import.meta.url)), "../.."));
const html = fs.readFileSync(path.join(root, "web/recovery/index.html"), "utf8");
const source = fs.readFileSync(path.join(root, "web/recovery/recovery.js"), "utf8");
const payload = fs.readFileSync(path.join(root, "web/recovery/catalog.json"));
const data = JSON.parse(payload);
const digest = (value) => crypto.createHash("sha256").update(value).digest("hex");

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.handlers = {}; this.attributes = {}; this.value = ""; this.hidden = false; this._text = ""; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this._text = ""; if (this.tagName === "select") this.value = nodes[0]?.value || ""; }
  addEventListener(type, handler) { this.handlers[type] = handler; }
  setAttribute(name, value) { this.attributes[name] = value; }
  scrollIntoView() {}
}

const nodes = new Map([...html.matchAll(/<([a-z0-9-]+)\b[^>]*\bid="([^"]+)"[^>]*>/gi)].map((match) => [match[2], new Element(match[1])]));
for (const id of ["type", "verification"]) nodes.get(id).value = "all";
const document = {
  getElementById(id) { if (!nodes.has(id)) throw new Error("Missing actual HTML element " + id); return nodes.get(id); },
  createElement: (tag) => new Element(tag),
};
const window = { location: { href: "https://example.test/recovery/", origin: "https://example.test" } };
const api = await new Function("document", "window", "fetch", `return (async()=>{${source}\nreturn {changeMode,render};})();`)(document, window, async () => ({ ok: true, json: async () => structuredClone(data) }));
const assertions = [];
function assert(condition, message) { assertions.push({ check: message, passed: Boolean(condition) }); if (!condition) throw new Error(message); }
function descendants(node) { return [node, ...node.children.flatMap(descendants)]; }

assert(nodes.get("objects-count").textContent === "3,151", "Frozen object count remains 3151");
assert(!nodes.get("reproduction-summary").hidden && !nodes.get("show-reproductions").hidden, "Supplement summary and tab are visible");
assert(nodes.get("reproduction-counts").textContent.includes("24 additional") && nodes.get("reproduction-counts").textContent.includes("189 remain unmatched"), "Summary gives 24 new and 189 unmatched");
api.changeMode("reproductions");
assert(nodes.get("results").children.length === 24, "Reproduction mode contains 24 rows");
assert(descendants(nodes.get("results")).filter((node) => node.tagName === "a").length === 0, "No supplemental playback or download links exist");
api.changeMode("expectations");
nodes.get("verification").value = "exact_hash_reproduced"; api.render();
const resolvedCards = [...nodes.get("results").children];
assert(resolvedCards.length === 7, "Exact reproduction filter shows seven reference records");
const resolvedHashes = new Set();
for (const card of resolvedCards) {
  assert(card.textContent.includes("Exact bytes reproduced"), "Resolved reference badge states exact reproduction");
  assert(!card.textContent.includes("Bytes not recovered"), "Resolved reference no longer claims current unavailability");
  const button = descendants(card).find((node) => node.tagName === "button");
  const expectedHash = descendants(card).find((node) => node.tagName === "code").textContent;
  resolvedHashes.add(expectedHash);
  assert(Boolean(button), "Resolved reference has a metadata navigation button");
  button.handlers.click();
  assert(nodes.get("result-count").textContent === "1 supplemental reproduced identities", "Reference navigation resolves to one exact supplemental identity");
  assert(descendants(nodes.get("results")).find((node) => node.tagName === "code").textContent === expectedHash, "Reference navigation preserves the exact expected SHA-256");
  assert(descendants(nodes.get("results")).filter((node) => node.tagName === "a").length === 0, "Reference navigation exposes no private media URL");
}
assert(resolvedHashes.size === 5, "Seven resolved reference rows represent five distinct exact identities");
api.changeMode("objects");
assert(nodes.get("result-count").textContent === "3,151 frozen identities", "Switching back retains the frozen denominator");
const report = {
  schema_version: "god-here.reproduction-view-metadata-check.v1", status: "passed",
  scope: "Node execution of the current JS with a minimal DOM fixture derived from actual HTML and the current JSON; no browser, media or network verification.",
  input_sha256: { "web/recovery/index.html": digest(html), "web/recovery/recovery.js": digest(source), "web/recovery/catalog.json": digest(payload) },
  script_sha256: digest(fs.readFileSync(fileURLToPath(import.meta.url))),
  checks: assertions.length, assertions,
};
const output = path.resolve(options["--output"]);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify({ status: report.status, checks: report.checks, input_sha256: report.input_sha256 }, null, 2));
