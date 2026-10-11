# God-here recovery catalog tools

`build_catalog.py` merges explicit recovery receipts into a public content catalog,
a reference/expectations register, and a separate private custody index. It reads
JSON receipts and observes whether recorded local paths exist. It does not fetch
files, execute production recipes, change remote storage, or grant acceptance.

## Compile and check

Use Python 3 with the standard library. Point `--base` at the directory containing
the selected `local-audit`, `recovery-audit`, `repo-audit`, `site-media-audit`, and
`history-audit` evidence directories.

```sh
python tools/recovery/build_catalog.py --base /absolute/path/reconciliation --output-dir /absolute/path/compiled
python tools/recovery/verify_catalog.py --catalog /absolute/path/compiled/god-here-recovery-catalog.json --expectations /absolute/path/compiled/expectations.json
```

The compiler refuses inconsistent SHA/size identities and archive members without
verified outer objects. The checker independently validates object and occurrence
counts, exact-hash resolution, archive relationships, acceptance evidence, and
the public/private locator boundary.

## Output boundaries

| Output | Intended custody | Contents |
| --- | --- | --- |
| `god-here-recovery-catalog.json` | Public repository | Unique SHA-256 objects, logical names, byte counts, qualified origins, preservation and validation status |
| `expectations.json` | Public repository | Historical identity expectations; repository, site and recovered-document reference records; explicit name candidates and unavailable identities |
| `recovered-document-reference-register.json` | Public repository | Bounded static document/code reference scan, unexecuted command counts, literal dependencies and inline-media markers |
| `private-custody-index.json` | Private custody | Original Library, Drive, Page, chat, source and local locators; original aliases; archive member paths; release history |
| `private-input-evidence/` | Private custody | Selected input snapshots needed to reconstruct the catalog; broad unrelated Library and runtime scans are excluded |
| `snapshot-index.json` | Private custody | Original input hashes and separately recorded hashes of the normalized/redacted stored snapshots |

Owner-only performer-reference aliases are opaque in public output. Exact
original filenames and archive paths remain in private custody. Public source
filenames are retained when the same object already has a verified public origin.

## Reconstruct from the private evidence bundle

After unpacking the private custody bundle, use its `private-input-evidence`
directory as the input base:

```sh
python tools/recovery/build_catalog.py --base /absolute/path/unpacked-custody/private-input-evidence --output-dir /absolute/path/reconstructed-catalog
python tools/recovery/verify_catalog.py --catalog /absolute/path/reconstructed-catalog/god-here-recovery-catalog.json --expectations /absolute/path/reconstructed-catalog/expectations.json
```

This reconstructs object identities and semantic counts. It is not a promise of
byte-identical report JSON: generated timestamps, currently observed local path
availability, and the hashes of normalized input JSON naturally differ. Use
`snapshot-index.json` to verify the stored evidence bytes and retain the original
input digest separately. Local file-origin IDs use logical paths so they do not
depend on the directory in which the evidence is unpacked.

## Meaning of the gates

A unique object is one complete byte string identified by full SHA-256 and size.
A file occurrence is a source location, branch-tip path, historical Git blob,
site-source path, or container-hash/member-path pair. Archive bytes and member
bytes both have identities; their summed byte counts are not disk usage.

Textual references are separate records and never increase the recovered-object
count. Expected hashes resolve only against exact recovered hashes and compatible
sizes. Names provide candidates. Tests, examples, parameterized names, runtime
export contracts, unexecuted commands and ordinary links retain their own scopes.

ZIP CRC success proves preservation of the member bytes contained in that ZIP.
Those bytes can still encode an incomplete or invalid media file. Full media
decode, browser playback, reproducible rendering and artistic acceptance remain
separate gates. Images without explicit image-validation receipts retain
checksum-only status. Inline media remains preserved within its document bytes
unless a separate payload identity has been inventoried.

Current and historical Site source files have distinct origin kinds. A current
URL must not be used to identify a historical source version. A local working-tree
repair remains marked as awaiting deployment until separate deployment evidence
updates that status.

## Generate the canonical workbench view

`build_workbench_index.py` projects the public catalog and expectations into the
searchable recovery page. It verifies the SHA-256 of each candidate media file
in the current Site checkout. It reads media bytes but does not transform, copy
or publish them. The historical catalog retains its original source paths while
the projection resolves the current `public/`, `dist/client/` or `dist/` layout.

```sh
python tools/recovery/build_workbench_index.py --catalog manifests/artifacts/god-here-recovery-catalog.json --expectations manifests/artifacts/god-here-recovery-expectations.json --workbench-root /absolute/path/workbench --output web/recovery/catalog.json
```

The registered media manifest under `lib/` identifies files retained outside the
static package. Their exact source bytes must exist under `room-media-source/`.
Those rows remain explicitly pending with no download link until a completed
production receipt verifies HEAD metadata, actual middle-range bytes, and the
full-download SHA-256. Pass that receipt with `--room-media-receipt` when available;
it must match the canonical origin and current registration manifest.

Pass `--image-validation-supplement` with the separately committed later image
receipt to add complete decode results for existing frozen identities. The
builder checks catalog binding, hash/size identity, non-repetition, complete
frame evidence and totals. The original catalog bytes and snapshot counts stay
unchanged; the projection exposes current image validation separately.

Copy the four `web/recovery/` files into the selected Site's `public/recovery/`,
retain its root navigation and recovery directory route, and use the Site's
existing source/build/publication workflow. Record deployment and response
verification separately. A successful local projection does not establish that
the currently deployed version serves those bytes.

## Verify the deployed text routes

`verify_deployed_text.py` performs read-only GETs against the fixed canonical
workbench origin. It compares eighteen complete text responses, including the
reconciled FX runtime and demonstration player, with the selected checkout and
checks four exact canonical redirect targets. It follows no
redirects, retries no requests, saves no response bodies, and caps each response
at 3,000,000 bytes. It does not upload or verify media, exercise a browser, or
claim artistic acceptance.

```sh
python tools/recovery/verify_deployed_text.py
```

The helper prints `Ready` and reads one JSON object from standard input. Required
fields are `origin`, `workbench_root`, and `receipt_path`; provide the authorized
`dispatch_bearer` when the Site's dispatch requires it. Use the canonical origin
and absolute local paths. Terminal echo is disabled for the input; do not put
credentials in shell arguments or files. The receipt records whether dispatch
authorization was supplied without storing its value.

The completed `god-here-media-delivery-verified.json` receipt covers all 52
registered files after explicit payload approval. The earlier interrupted
per-file observation remains historical evidence and must not be used in place
of that complete receipt.

## Verify the committed checkpoint

```sh
python3 tools/recovery/verify_checkpoint.py
```

This standard-library check binds the frozen manifests, later evidence files,
workbench projection, approved payload, saved Site version and deployment. It
rejects changed evidence bytes, duplicate or incomplete media receipts, stale
completion counts and unsupported image pass claims. It does not contact a
storage service, read private media, decode a stream or certify artistic quality.
The Recovery integrity GitHub workflow runs this check together with the catalog
validator on relevant pull requests and pushes.
