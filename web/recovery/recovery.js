const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 30;
let data;
let mode = "objects";
let page = 0;

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value != null) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function byteSize(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
}

function validLink(url) {
  try {
    const resolved = new URL(url, window.location.href);
    return resolved.origin === window.location.origin || (resolved.protocol === "https:" && resolved.hostname === "github.com");
  } catch { return false; }
}

function badge(row) {
  if (mode === "expectations") {
    if (row.status === "exact_hash_recovered") return ["Exact identity recovered", "pass"];
    if (row.status === "exact_hash_reproduced") return ["Exact bytes reproduced", "pass"];
    if (row.status === "identity_unresolved_name_candidates") return ["Identity unresolved", ""];
    return [row.expected_sha256 ? "Bytes not recovered" : "Unresolved reference", "fail"];
  }
  if (mode === "reproductions") return [row.decode === "passed" ? "Reproduced · decode passed" : "Reproduced · bytes verified", row.decode === "passed" ? "pass" : ""];
  if (mode === "retained_outputs") return [row.decode === "passed" ? "Executed · decode passed" : "Executed · bytes verified", row.decode === "passed" ? "pass" : ""];
  if (row.decode === "passed") return ["Decode passed", "pass"];
  if (row.decode === "failed") return ["Decode failed", "fail"];
  if (row.decode === "not_applicable") return ["Bytes verified", ""];
  return ["Decode pending", ""];
}

function artifactCard(row) {
  const article = element("article", null, "artifact");
  const head = element("div");
  const name = mode !== "expectations" ? row.names[0] : row.name;
  head.append(element("h3", name));
  const meta = element("p", null, "meta");
  const parts = ["reproductions", "retained_outputs"].includes(mode)
    ? [row.type, byteSize(row.bytes), `${row.occurrences} recipe output${row.occurrences === 1 ? "" : "s"}`, "Privately preserved reproduction"]
    : mode === "objects"
    ? [row.type.replaceAll("_", " "), byteSize(row.bytes), `${row.occurrences} recorded location${row.occurrences === 1 ? "" : "s"}`, row.links.length ? "Workbench source present" : "Cataloged for recovery"]
    : [row.category.replaceAll("_", " "), row.expected_bytes != null ? byteSize(row.expected_bytes) : "Referenced identity under review"];
  for (const part of parts) meta.append(element("span", part));
  head.append(meta);
  article.append(head);
  const [label, cls] = badge(row);
  article.append(element("span", label, `badge ${cls}`));
  const details = element("details");
  details.append(element("summary", "Identity and verification"));
  const body = element("div", null, "detail-body");
  const hash = mode !== "expectations" ? row.sha256 : row.expected_sha256;
  const line = element("p");
  line.append(element("span", hash ? "SHA-256 · " : "No historical checksum recorded."));
  if (hash) line.append(element("code", hash));
  body.append(line);
  if (mode !== "expectations") {
    if (row.names.length > 1) body.append(element("p", `Recorded names: ${row.names.join(" · ")}`));
    if (row.decode === "failed") body.append(element("p", "The bytes are preserved, but this media file failed complete decoding. A successful archive CRC does not make the contained media usable."));
    if (row.type === "image") body.append(element("p", row.image_verification || "Hash identity is verified. Complete image decoding is recorded separately where available."));
    if (row.download_pending) body.append(element("p", "The exact media source is preserved. Online download verification is pending, so this catalog has not enabled its download link."));
    if (mode === "retained_outputs") {
      const run = data.retained_execution_availability.runs.find((entry) => entry.binding_id === row.binding_id);
      body.append(element("p", `Required output of ${row.binding_id}, preserved with complete byte identity and the recorded technical checks. Producing revision: ${run.producing_source.actual_commit}. Verification revision: ${run.verification_source.actual_commit}.`));
      body.append(element("p", run.verification_mode === "post_hoc_existing_products" ? data.retained_execution_availability.room_verification_qualification : "The native execution includes its output verification. This does not establish retrieval of the historical original copy or artistic acceptance."));
    } else if (mode === "reproductions") {
      body.append(element("p", "Matching bytes were produced by the retained baseline recipe and are privately preserved. This record adds availability without asserting retrieval of the historical original copy."));
      body.append(element("p", `Recipe revision: ${data.reproduction_availability.pinned_revision}. Artistic acceptance remains unassessed. The reproduced media are not exposed by this view.`));
    } else if (row.baseline_reproduction) {
      body.append(element("p", `This exact byte identity was also reproduced by the retained baseline recipe at ${row.baseline_reproduction.pinned_revision}. That additional copy is privately preserved. Artistic acceptance remains unassessed.`));
    } else {
      body.append(element("p", "Retained for recovery review. Artistic acceptance and reproducible rendering are not established by this inventory."));
    }
    for (const link of row.links) {
      if (!validLink(link.href)) continue;
      const a = element("a", link.label);
      a.href = link.href;
      body.append(a);
    }
    if (row.code_url && validLink(row.code_url)) {
      const a = element("a", "Inspect preserved code on GitHub ↗");
      a.href = row.code_url;
      body.append(a);
    }
    if (!row.links.length && !row.code_url) body.append(element("p", "Location details are recorded in the owner recovery index. This row does not expose private media."));
  } else {
    body.append(element("p", row.qualification || "This is a historical reference record, not an additional recovered object."));
    if (row.status === "exact_hash_reproduced") {
      body.append(element("p", `Reproduced output: ${row.reproduced_names.join(" · ")}. Frozen checkpoint status: ${row.frozen_status.replaceAll("_", " ")}.`));
    }
    if (row.candidates.length && !["exact_hash_reproduced", "exact_hash_recovered"].includes(row.status)) body.append(element("p", `${row.candidates.length} name candidate${row.candidates.length === 1 ? "" : "s"}; filenames alone do not establish identity.`));
    if (["exact_hash_recovered", "exact_hash_reproduced"].includes(row.status) && row.matched_sha256) {
      const reproduced = row.status === "exact_hash_reproduced";
      const retained = reproduced && row.reproduction_scope === "retained_native_execution";
      const b = element("button", retained ? "Find the retained execution record" : reproduced ? "Find the private reproduction record" : "Find the recovered object");
      b.type = "button";
      b.addEventListener("click", () => { changeMode(retained ? "retained_outputs" : reproduced ? "reproductions" : "objects"); $("search").value = row.matched_sha256; render(); $("inventory-title").scrollIntoView({ block: "start" }); });
      body.append(b);
    }
  }
  details.append(body);
  article.append(details);
  return article;
}

function render() {
  if (!data) return;
  const query = $("search").value.trim().toLocaleLowerCase();
  const type = $("type").value;
  const verification = $("verification").value;
  const rows = (data[mode] || []).filter((row) => {
    const names = mode !== "expectations" ? row.names.join(" ") : `${row.name} ${(row.reproduced_names || []).join(" ")}`;
    const hash = mode !== "expectations" ? row.sha256 : row.expected_sha256 || "";
    if (query && !`${names} ${hash}`.toLocaleLowerCase().includes(query)) return false;
    if (mode === "expectations") return verification === "all" || row.status === verification;
    if (type === "audio-video" && !["audio", "video"].includes(row.type)) return false;
    if (!["all", "audio-video"].includes(type) && row.type !== type) return false;
    if (verification === "workbench") return row.links.length > 0;
    if (verification !== "all" && row.decode !== verification) return false;
    return true;
  });
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  page = Math.min(page, pages - 1);
  $("results").replaceChildren(...rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(artifactCard));
  if (!rows.length) $("results").append(element("p", "No records match these filters. Try a shorter name or clear the filters.", "empty"));
  $("result-count").textContent = `${rows.length.toLocaleString()} ${mode === "objects" ? "frozen identities" : mode === "reproductions" ? "supplemental reproduced identities" : mode === "retained_outputs" ? "additional retained-output identities" : "reference records"}`;
  $("page-label").textContent = `Page ${page + 1} of ${pages}`;
  $("previous").disabled = page === 0;
  $("next").disabled = page >= pages - 1;
  $("results").setAttribute("aria-busy", "false");
}

function changeMode(nextMode) {
  mode = nextMode;
  page = 0;
  $("search").value = "";
  $("type").value = "all";
  $("type-label").hidden = mode === "expectations";
  $("show-objects").setAttribute("aria-pressed", String(mode === "objects"));
  $("show-reproductions").setAttribute("aria-pressed", String(mode === "reproductions"));
  $("show-retained-outputs").setAttribute("aria-pressed", String(mode === "retained_outputs"));
  $("show-expectations").setAttribute("aria-pressed", String(mode === "expectations"));
  const options = ["reproductions", "retained_outputs"].includes(mode)
    ? [["all", "All statuses"], ["passed", "Decode passed"], ["not_applicable", "Bytes verified"]]
    : mode === "objects"
    ? [["all", "All statuses"], ["passed", "Decode passed"], ["failed", "Decode failed"], ["pending", "Decode pending"], ["workbench", "In this workbench"]]
    : [["all", "All statuses"], ["exact_hash_recovered", "Exact identity recovered"], ["exact_hash_reproduced", "Exact bytes reproduced"], ["identity_unresolved_name_candidates", "Identity unresolved"], ["unavailable", "Unresolved / unavailable"]];
  $("verification").replaceChildren(...options.map(([value, label]) => { const option = element("option", label); option.value = value; return option; }));
  $("view-explanation").textContent = mode === "retained_outputs"
    ? "These 35 required output identities were absent from the frozen catalog, baseline supplement and exact PR49 inputs. They are privately preserved from five verified retained bindings. The 60 exact matches to existing custody are counted separately, and no new private output has a playback link."
    : mode === "reproductions"
    ? "These exact output hashes were absent from the frozen object catalog and are now privately preserved through the verified baseline recipe. They are an additive availability record; no reproduced media links are exposed."
    : mode === "objects"
    ? "Each row represents one identity in the frozen recovery catalog. Later reproduction evidence is annotated separately. Different revisions stay separate even when their filenames match."
    : "Historical registers, reported deliverables and dependencies are reference records. Several rows can point to one object. Their count does not measure missing works. Code examples, templates and runtime export contracts are excluded from this view.";
  render();
}

$("filters").addEventListener("submit", (event) => event.preventDefault());
$("search").addEventListener("input", () => { page = 0; render(); });
for (const id of ["type", "verification"]) $(id).addEventListener("change", () => { page = 0; render(); });
$("clear").addEventListener("click", () => changeMode(mode));
$("show-objects").addEventListener("click", () => changeMode("objects"));
$("show-reproductions").addEventListener("click", () => changeMode("reproductions"));
$("show-retained-outputs").addEventListener("click", () => changeMode("retained_outputs"));
$("show-expectations").addEventListener("click", () => changeMode("expectations"));
$("previous").addEventListener("click", () => { page--; render(); });
$("next").addEventListener("click", () => { page++; render(); });

function retainedRunCard(run) {
  const article = element("article", null, "artifact");
  const head = element("div");
  const labels = {"direction-proof-directed": "PR49 · Directed proof", "direction-proof-reference": "PR49 · Reference proof", "directed-integrated-excerpt": "PR50 · Integrated excerpt", "fx-demo-delay": "FX · Delay demonstration", "room-stretch-full": "Room · Full-film stretch and stack"};
  head.append(element("h3", labels[run.binding_id] || run.binding_id));
  head.append(element("p", `${run.required_output_identities} required outputs · ${run.full_decode_passes} media decode passes · ${run.existing_exact_identities} existing identities · ${run.new_output_identities} new identities`, "meta"));
  article.append(head, element("span", run.verification_mode === "post_hoc_existing_products" ? "Outputs verified later" : "Native outputs verified", "badge pass"));
  const details = element("details");
  details.append(element("summary", "Native clocks and source evidence"));
  const body = element("div", null, "detail-body");
  const output = run.clocks.output;
  body.append(element("p", output.frames ? `${output.frames} frames at ${output.frame_rate.num / output.frame_rate.den} fps · ${output.dimensions.join(" × ")} · ${output.pcm_samples_per_channel.toLocaleString()} target PCM samples per channel at ${output.audio_sample_rate.toLocaleString()} Hz.` : `${output.samples_per_channel.toLocaleString()} target PCM samples per channel at ${output.sample_rate.toLocaleString()} Hz · ${output.samples_per_channel / output.sample_rate} seconds. Source reel: ${run.clocks.source_reel_samples.toLocaleString()} samples.`));
  for (const [label, source] of [["Produced", run.producing_source], ["Verified", run.verification_source]]) {
    body.append(element("p", `${label} at ${source.actual_commit}.`));
    if (validLink(source.public_code_url)) {
      const a = element("a", `${label}: inspect the equal declared code closure ↗`);
      a.href = source.public_code_url;
      body.append(a);
    }
  }
  body.append(element("p", "The linked public commits match the declared native code files and binding bytes. This does not assert equality of complete Git trees or runtimes."));
  if (run.clocks.source_consumption) body.append(element("p", run.clocks.source_consumption));
  if (run.verification_mode === "post_hoc_existing_products") body.append(element("p", data.retained_execution_availability.room_verification_qualification));
  body.append(element("p", `Native receipt SHA-256: ${run.native_execution_receipt.sha256}. Verification receipt SHA-256: ${run.verification_receipt.sha256}. Artistic acceptance remains pending.`));
  details.append(body);
  article.append(details);
  return article;
}

try {
  const response = await fetch("catalog.json");
  if (!response.ok) throw new Error(`Inventory response ${response.status}`);
  data = await response.json();
  if (data.schema_version !== "god-here.workbench-recovery.v1" || !Array.isArray(data.objects) || !Array.isArray(data.expectations)) throw new Error("Unsupported inventory format");
  const counts = data.counts;
  for (const [id, key] of [["objects-count", "unique_sha256_objects"], ["decoded-count", "audio_video_full_decode_passes"], ["failed-count", "audio_video_full_decode_failures"], ["pending-count", "audio_video_full_decode_pending"]]) $(id).textContent = counts[key].toLocaleString();
  const status = [];
  if (data.delivery?.registered_downloads_verified) status.push(`${data.delivery.registered_downloads_verified.toLocaleString()} media downloads verified`);
  const images = data.image_validation;
  if (images) status.push(`${images.passed.toLocaleString()} images decoded; ${images.pending.toLocaleString()} await decoding`);
  $("supplemental-status").textContent = status.length ? `${status.join(". ")}.` : "";
  if (data.reproduction_availability && Array.isArray(data.reproductions)) {
    const added = data.reproduction_availability.counts;
    $("reproduction-summary").hidden = false;
    $("show-reproductions").hidden = false;
    $("reproduction-counts").textContent = `${added.supplemental_new_unique_outputs.toLocaleString()} additional byte identities are privately preserved, including ${added.supplemental_new_audio_video_decode_passes.toLocaleString()} audio/video decode passes. This baseline-only checkpoint reproduced ${added.previously_unmatched_hashes_now_reproduced.toLocaleString()} previously unmatched expected checksums and left ${added.remaining_unmatched_expected_hashes.toLocaleString()} unmatched. The frozen ${added.frozen_catalog_unique_objects.toLocaleString()}-identity catalog stays unchanged.`;
  }
  if (data.retained_execution_availability && Array.isArray(data.retained_outputs) && Array.isArray(data.retained_inputs)) {
    const retained = data.retained_execution_availability;
    const c = retained.counts;
    $("retained-summary").hidden = false;
    $("show-retained-outputs").hidden = false;
    $("retained-counts").textContent = `${c.bound_retained_recipes} concrete bindings have ${c.unique_required_output_identities} verified required output identities: ${c.existing_custody_matches} match existing custody and ${c.new_required_output_identities} are newly preserved (${c.new_required_media_decode_passes} media decode passes and ${c.new_required_output_identities - c.new_required_media_decode_passes} metadata records). ${c.fully_decoded_required_media} required audio/video files pass complete decoding.`;
    $("retained-availability-counts").textContent = `${c.additional_expected_hashes_reproduced} more formerly unmatched hashes now have exact reproduced bytes, resolving ${c.expectation_rows_updated} reference rows. ${c.remaining_unmatched_expected_hashes} expected hashes remain unmatched. The scoped union is ${c.frozen_baseline_pr49_retained_scoped_identity_union.toLocaleString()}: ${c.frozen_catalog_unique_objects.toLocaleString()} frozen identities + ${c.baseline_additional_unique_outputs} baseline additions + ${c.additional_exact_pr49_input_identities} separately preserved inputs + ${c.new_required_output_identities} retained-output additions. Carrier archives and temporary intermediates are excluded from that union.`;
    $("retained-runs").replaceChildren(...retained.runs.map(retainedRunCard));
    $("retained-inputs").replaceChildren(...data.retained_inputs.map((row) => {
      const item = element("li", `${row.names[0]} · ${byteSize(row.bytes)} · ${row.exact_dependency_bytes_retrieved ? "Exact font dependency retrieved from its distribution" : "Exact historical input reproduced"}. SHA-256: `);
      item.append(element("code", row.sha256));
      return item;
    }));
    $("retained-failure-note").textContent = `The first PR50 attempt remains failed and is preserved separately; its fresh retry has verified outputs. The room run retains its original failed wrapper receipt and later output verification, with no new native render for that check. ${retained.incidental_intermediates.count} reconstructible temporary files are identified but not retained or counted as required outputs. Artistic acceptance remains pending.`;
  }
  $("snapshot-date").textContent = `Frozen snapshot ${new Date(data.generated_at_utc).toISOString().slice(0, 10)}`;
  $("catalog-hash").textContent = `Public source manifest SHA-256: ${data.source_catalog_sha256}`;
  render();
} catch (error) {
  $("result-count").textContent = "The inventory could not load.";
  $("results").replaceChildren(element("p", "The workbench links above remain available. Open Recovery PR for the preserved manifests and current status.", "empty"));
  $("results").setAttribute("aria-busy", "false");
  $("catalog-hash").textContent = "Unavailable in this view; see the full manifests.";
}
