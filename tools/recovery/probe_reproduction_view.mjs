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
assert(nodes.get("reproduction-counts").textContent.includes("24 additional") && nodes.get("reproduction-counts").textContent.includes("left 189 unmatched"), "Baseline summary retains its scoped 24 new and 189 unmatched");
api.changeMode("reproductions");
assert(nodes.get("results").children.length === 24, "Reproduction mode contains 24 rows");
assert(descendants(nodes.get("results")).filter((node) => node.tagName === "a").length === 0, "No supplemental playback or download links exist");
api.changeMode("expectations");
nodes.get("verification").value = "exact_hash_reproduced"; api.render();
const resolvedCards = [...nodes.get("results").children];
while (!nodes.get("next").disabled) {
  nodes.get("next").handlers.click();
  resolvedCards.push(...nodes.get("results").children);
}
const hasRetained = Boolean(data.retained_execution_availability);
assert(resolvedCards.length === (hasRetained ? 121 : 7), "Exact reproduction filter shows complete baseline and retained reference coverage");
const resolvedHashes = new Set();
const baselineHashes = new Set(data.reproductions.map((row) => row.sha256));
const retainedHashes = new Set((data.retained_outputs || []).map((row) => row.sha256));
for (const card of resolvedCards) {
  assert(card.textContent.includes("Exact bytes reproduced"), "Resolved reference badge states exact reproduction");
  assert(!card.textContent.includes("Bytes not recovered"), "Resolved reference no longer claims current unavailability");
  const button = descendants(card).find((node) => node.tagName === "button");
  const expectedHash = descendants(card).find((node) => node.tagName === "code").textContent;
  resolvedHashes.add(expectedHash);
  assert(Boolean(button), "Resolved reference has a metadata navigation button");
  button.handlers.click();
  assert(nodes.get("result-count").textContent === (retainedHashes.has(expectedHash) ? "1 additional retained-output identities" : "1 supplemental reproduced identities"), "Reference navigation resolves to the correct exact supplemental layer");
  assert(descendants(nodes.get("results")).find((node) => node.tagName === "code").textContent === expectedHash, "Reference navigation preserves the exact expected SHA-256");
  assert(descendants(nodes.get("results")).filter((node) => node.tagName === "a").length === 0, "Reference navigation exposes no private media URL");
}
assert(resolvedHashes.size === (hasRetained ? 34 : 5), "Resolved reference rows have the exact expected distinct identity count");
assert([...resolvedHashes].filter((sha) => baselineHashes.has(sha)).length === 5, "Five baseline expected-hash matches remain unchanged");
if (hasRetained) {
  assert(!nodes.get("retained-summary").hidden && !nodes.get("show-retained-outputs").hidden, "Retained execution section and tab are visible");
  assert(nodes.get("retained-counts").textContent.includes("95 verified") && nodes.get("retained-counts").textContent.includes("60 match") && nodes.get("retained-counts").textContent.includes("35 are newly"), "Retained summary separates 95 required, 60 existing and 35 new outputs");
  assert(nodes.get("retained-availability-counts").textContent.includes("29 more") && nodes.get("retained-availability-counts").textContent.includes("114 reference") && nodes.get("retained-availability-counts").textContent.includes("160 expected hashes remain"), "Retained summary reports exact 29-hash/114-row gains and 160 remainder");
  assert(nodes.get("retained-availability-counts").textContent.includes("3,213") && nodes.get("retained-availability-counts").textContent.includes("3 separately preserved inputs"), "Scoped union labels supporting inputs separately");
  assert(nodes.get("retained-runs").children.length === 5, "All five native bindings have separate summary cards");
  const runText = nodes.get("retained-runs").textContent;
  assert(runText.includes("994a24550e9ba9d1969db47292c0610ebc96566b") && runText.includes("7469ea42e2a7058d9846ac8032e03075dabc9647"), "Actual producing and verification revisions remain visible");
  assert(runText.includes("original failed execution receipt remains failed") && runText.includes("did not execute a new native render"), "Room later verification does not rewrite its original execution or invent a rerender");
  const anchors = descendants(nodes.get("retained-runs")).filter((node) => node.tagName === "a");
  assert(anchors.length === 10 && anchors.every((node) => /^https:\/\/github\.com\/4444J99\/audiovisual-media-postproduction-system\/tree\/(08ff7f287eaea4d6bae1cd54de3b8dcebe6ab1f0|e12dff1ef58add8315b2365fad9ea0ce83075bc6)$/.test(node.href)), "Native evidence links use only the two immutable public code anchors");
  assert(nodes.get("retained-inputs").children.length === 3 && descendants(nodes.get("retained-inputs")).every((node) => node.tagName !== "a"), "Three supporting inputs expose identities without media links");
  assert(nodes.get("retained-inputs").textContent.includes("font dependency retrieved from its distribution"), "Font retrieval is qualified as dependency distribution bytes");
  assert(nodes.get("retained-failure-note").textContent.includes("first PR50 attempt remains failed") && nodes.get("retained-failure-note").textContent.includes("40 reconstructible temporary files"), "Initial failure and excluded incidental files remain explicit");
  api.changeMode("retained_outputs");
  const addedCards = [...nodes.get("results").children];
  while (!nodes.get("next").disabled) { nodes.get("next").handlers.click(); addedCards.push(...nodes.get("results").children); }
  assert(addedCards.length === 35, "Retained output mode contains exactly 35 new identities across pagination");
  assert(addedCards.every((card) => descendants(card).every((node) => node.tagName !== "a")), "No newly retained private output has a playback or download link");
  assert([...resolvedHashes].filter((sha) => retainedHashes.has(sha)).length === 29, "Twenty-nine later expected hashes navigate to retained outputs");
}
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
