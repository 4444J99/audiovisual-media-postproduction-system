#!/usr/bin/env python3
"""Compare fixed God-here HTTP text routes with a local public/ snapshot.

Read exactly one JSON object from standard input:
  origin, workbench_root, receipt_path, optional dispatch_bearer (raw token).

The caller supplies any already-authorized credential through hidden stdin.
On a TTY, echo is disabled before printing Ready and reading one compact JSON
line; the original terminal settings are restored afterward. A pipe reads to EOF.
This program never discovers credentials, follows redirects, retries requests,
prints input or response bodies, or writes to the workbench. Only the requested
metadata receipt is written. Exit codes: 0 pass, 1 content/route failure,
2 input/preflight/transport/receipt failure, 3 access denied.
"""

from __future__ import annotations

import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import sys
import tempfile
import termios
import time
import urllib.error
import urllib.request


ORIGIN = "https://god-here-five-realities.ajpadavano.chatgpt.site"
MAX_TEXT_BYTES = 3_000_000
MAX_INPUT_BYTES = 65_536
REQUEST_TIMEOUT_SECONDS = 20
BODY_DEADLINE_SECONDS = 40
CHUNK_BYTES = 65_536

# All URLs and source paths are constants, never supplied by remote responses.
TEXT_ROUTES = (
    ("/", "public/index.html"),
    ("/recovery/", "public/recovery/index.html"),
    ("/recovery/recovery.js", "public/recovery/recovery.js"),
    ("/recovery/recovery.css", "public/recovery/recovery.css"),
    ("/recovery/catalog.json", "public/recovery/catalog.json"),
    ("/fx/", "public/fx/index.html"),
    ("/fx/app.mjs", "public/fx/app.mjs"),
    ("/fx/core.mjs", "public/fx/core.mjs"),
    ("/fx/audio-engine.mjs", "public/fx/audio-engine.mjs"),
    ("/fx/audio-worker.mjs", "public/fx/audio-worker.mjs"),
    ("/fx/visual-engine.mjs", "public/fx/visual-engine.mjs"),
    ("/fx/workbench-state.mjs", "public/fx/workbench-state.mjs"),
    ("/fx/preview-provenance.mjs", "public/fx/preview-provenance.mjs"),
    ("/fx/engine-provenance.json", "public/fx/engine-provenance.json"),
    ("/fx/watch", "public/fx/watch.html"),
    ("/review", "public/review.html"),
    ("/room-tone/", "public/room-tone/index.html"),
    ("/color-studies/", "public/color-studies/index.html"),
)
REDIRECT_ROUTES = (
    ("/recovery/index.html", "/recovery/"),
    ("/review.html", "/review"),
    ("/recovery", "/recovery/"),
    ("/fx/watch.html", "/fx/watch"),
)
REDIRECT_STATUSES = (307, 308)


class SafeFailure(Exception):
    """Contains a constant, non-sensitive reason code only."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def within(path, directory):
    return path == directory or directory in path.parents


def read_input():
    if sys.stdin.isatty():
        # Disable both character and newline echo before announcing readiness.
        # The caller sends a single compact JSON line only after seeing Ready.
        try:
            descriptor = sys.stdin.fileno()
            original = termios.tcgetattr(descriptor)
            hidden = original.copy()
            hidden[3] &= ~(termios.ECHO | termios.ECHONL)
        except (OSError, termios.error):
            raise SafeFailure("cannot_prepare_hidden_terminal_input") from None
        echo_disabled = False
        try:
            termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
            echo_disabled = True
            print("Ready", flush=True)
            raw = sys.stdin.buffer.readline(MAX_INPUT_BYTES + 1)
        except (OSError, termios.error):
            raise SafeFailure("hidden_terminal_input_failed") from None
        finally:
            if echo_disabled:
                try:
                    termios.tcsetattr(descriptor, termios.TCSANOW, original)
                except (OSError, termios.error):
                    raise SafeFailure("terminal_restore_failed") from None
    else:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise SafeFailure("input_exceeds_cap")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SafeFailure("invalid_input_json") from None
    finally:
        del raw
    allowed = {"origin", "dispatch_bearer", "workbench_root", "receipt_path"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise SafeFailure("invalid_input_fields")
    if value.get("origin") != ORIGIN:
        raise SafeFailure("origin_is_not_the_canonical_origin")
    bearer = value.get("dispatch_bearer")
    if bearer is not None and (
        not isinstance(bearer, str)
        or not 1 <= len(bearer) <= 16_384
        or any(not 33 <= ord(char) <= 126 for char in bearer)
    ):
        raise SafeFailure("dispatch_bearer_must_be_a_raw_printable_token")
    for key in ("workbench_root", "receipt_path"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise SafeFailure("missing_required_path")
        if not Path(value[key]).is_absolute():
            raise SafeFailure("paths_must_be_absolute")
    try:
        root = Path(value["workbench_root"]).resolve(strict=True)
        supplied_receipt = Path(value["receipt_path"])
        # Resolve the parent, but never follow a final receipt symlink.
        receipt = supplied_receipt.parent.resolve(strict=True) / supplied_receipt.name
        if not root.is_dir() or not receipt.parent.is_dir():
            raise SafeFailure("invalid_root_or_receipt_directory")
        if receipt.is_symlink() or (receipt.exists() and not receipt.is_file()):
            raise SafeFailure("receipt_must_be_a_regular_file_path")
        if within(receipt, root):
            raise SafeFailure("receipt_must_be_outside_the_workbench")
    except (OSError, ValueError, RuntimeError):
        raise SafeFailure("invalid_root_or_receipt_path") from None
    return root, receipt, bearer


def write_receipt(path, receipt):
    """Atomically write only controlled metadata to the authorized receipt."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".god-here-http-receipt-", suffix=".json", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(receipt, handle, indent=2, sort_keys=True, ensure_ascii=True)
            handle.write("\n")
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise SafeFailure("receipt_write_failed") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def source_identity(root, relative_path):
    try:
        public = (root / "public").resolve(strict=True)
        source = (root / relative_path).resolve(strict=True)
        if not within(public, root) or not within(source, public):
            raise SafeFailure("source_resolves_outside_public")
        with source.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SafeFailure("source_is_not_a_regular_file")
            if before.st_size > MAX_TEXT_BYTES:
                raise SafeFailure("source_exceeds_cap")
            data = handle.read(MAX_TEXT_BYTES + 1)
            after = os.fstat(handle.fileno())
        if len(data) > MAX_TEXT_BYTES:
            raise SafeFailure("source_exceeds_cap")
        fingerprint = lambda item: (
            item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns,
        )
        if fingerprint(before) != fingerprint(after) or len(data) != after.st_size:
            raise SafeFailure("source_changed_during_preflight")
        if fingerprint(after) != fingerprint(source.stat()):
            raise SafeFailure("source_changed_during_preflight")
        return {"expected_sha256": hashlib.sha256(data).hexdigest(),
                "expected_bytes": len(data)}
    except FileNotFoundError:
        raise SafeFailure("source_missing") from None
    except (OSError, ValueError, RuntimeError):
        raise SafeFailure("source_unreadable") from None


def transport_reason(error):
    # Never serialize exceptions: they can include URL/header/body data.
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "transport_timeout"
    if isinstance(reason, ssl.SSLError):
        return "tls_error"
    if isinstance(reason, http.client.IncompleteRead):
        return "incomplete_response"
    return "transport_error"


def check_route(opener, headers, check):
    response = None
    started = time.monotonic()
    try:
        request = urllib.request.Request(ORIGIN + check["route"], headers=headers, method="GET")
        try:
            response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            response = error  # Inspect status only; never read an error body.
        code = response.getcode()
        check["http_status"] = code if isinstance(code, int) else None
        if code in (401, 403):
            check.update(status="access_denied", reason="http_access_denied")
            return True
        if check["kind"] == "canonical_redirect":
            locations = response.headers.get_all("Location", [])
            matches = locations == [check["expected_location"]]
            # Unrecognized header values are deliberately withheld.
            check["location_matches_expected"] = matches
            check["actual_location"] = check["expected_location"] if matches else None
            if code in check["accepted_http_statuses"] and matches:
                check["status"] = "passed"
            else:
                check.update(status="failed", reason="redirect_status_or_location_mismatch")
            return False
        if code != 200:
            check.update(status="failed", reason="unexpected_http_status")
            return False
        raw_length = response.headers.get("Content-Length")
        if raw_length and len(raw_length) <= 20 and raw_length.isdecimal():
            declared_length = int(raw_length)
            if declared_length > MAX_TEXT_BYTES:
                check.update(status="failed", reason="response_exceeds_cap")
                return False
        digest = hashlib.sha256()
        total = 0
        while True:
            if time.monotonic() - started > BODY_DEADLINE_SECONDS:
                check.update(status="error", reason="response_deadline_exceeded")
                return False
            chunk = response.read(min(CHUNK_BYTES, MAX_TEXT_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            check["observed_bytes"] = total
            if total > MAX_TEXT_BYTES:
                check.update(status="failed", reason="response_exceeds_cap")
                return False
            digest.update(chunk)
        check["response_complete"] = True
        check["actual_sha256"] = digest.hexdigest()
        if total == check["expected_bytes"] and check["actual_sha256"] == check["expected_sha256"]:
            check["status"] = "passed"
        else:
            check.update(status="failed", reason="full_response_bytes_mismatch")
        return False
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        check.update(status="error", reason=transport_reason(error))
        return False
    finally:
        if response is not None:
            response.close()


def emit_summary(status, saved, checks=(), reason=None):
    result = {"status": status, "receipt_saved": saved,
              "checks_total": len(checks),
              "checks_passed": sum(item["status"] == "passed" for item in checks)}
    if reason is not None:
        result["reason"] = reason
    print(json.dumps(result, sort_keys=True))


def main():
    receipt_path = None
    receipt = None
    try:
        root, receipt_path, bearer = read_input()
        checks = []
        receipt = {
            "schema": "god-here.deployed-text-verification.v1",
            "origin": ORIGIN,
            "started_at_utc": now_utc(),
            "finished_at_utc": None,
            "status": "source_preflight",
            "request_method": "GET",
            "dispatch_bearer_supplied": bearer is not None,
            "max_text_bytes": MAX_TEXT_BYTES,
            "redirects_followed": False,
            "request_retries": 0,
            "response_bodies_saved": False,
            "verification_scope": "Full text bytes at fixed canonical routes and exact HTML canonicalization redirects",
            "checks": checks,
        }
        identities = {}
        source_failed = False
        for route, source_path in TEXT_ROUTES:
            check = {"route": route, "source_path": source_path, "kind": "exact_text_bytes",
                     "status": "pending", "expected_http_status": 200,
                     "expected_sha256": None, "expected_bytes": None,
                     "http_status": None, "actual_sha256": None,
                     "observed_bytes": 0, "response_complete": False}
            try:
                if source_path not in identities:
                    identities[source_path] = source_identity(root, source_path)
                check.update(identities[source_path])
            except SafeFailure as error:
                check.update(status="source_preflight_failed", reason=str(error))
                source_failed = True
            checks.append(check)
        for route, expected_location in REDIRECT_ROUTES:
            checks.append({"route": route, "kind": "canonical_redirect",
                           "status": "pending", "accepted_http_statuses": list(REDIRECT_STATUSES),
                           "expected_location": expected_location, "http_status": None,
                           "location_matches_expected": None, "actual_location": None})
        if source_failed:
            for check in checks:
                if check["status"] == "pending":
                    check["status"] = "not_requested_source_preflight_failed"
            receipt.update(status="source_preflight_failed", finished_at_utc=now_utc())
            write_receipt(receipt_path, receipt)
            emit_summary(receipt["status"], True, checks)
            return 2
        # Preserve the runtime's normal proxy discovery and HTTPS behavior.
        # Disable redirects only: one request per fixed route, no alternate
        # origin or retry path, and no access-control workaround.
        opener = urllib.request.build_opener(NoRedirects())
        headers = {"Accept-Encoding": "identity", "Cache-Control": "no-cache",
                   "User-Agent": "God-here-consolidation-text-verifier/1"}
        if bearer is not None:
            headers["OAI-Sites-Authorization"] = "Bearer " + bearer
        receipt["status"] = "in_progress"
        write_receipt(receipt_path, receipt)
        denied = False
        for check in checks:
            if denied:
                check["status"] = "not_requested_access_denied"
                continue
            denied = check_route(opener, headers, check)
            write_receipt(receipt_path, receipt)
        if denied:
            receipt.update(status="access_denied",
                           qualification="Access was denied; later routes were not requested.")
            exit_code = 3
        elif all(check["status"] == "passed" for check in checks):
            receipt["status"] = "passed"
            exit_code = 0
        else:
            receipt["status"] = "failed"
            exit_code = 2 if any(check["status"] == "error" for check in checks) else 1
        receipt["finished_at_utc"] = now_utc()
        write_receipt(receipt_path, receipt)
        emit_summary(receipt["status"], True, checks)
        return exit_code
    except (Exception, KeyboardInterrupt) as error:
        # Controlled codes only: no exception repr, traceback, input, credential,
        # response body, redirect URL, or arbitrary remote header is persisted.
        reason = str(error) if isinstance(error, SafeFailure) else "verification_interrupted_or_internal_error"
        saved = False
        if receipt is not None and receipt_path is not None:
            receipt.update(status="error", reason=reason, finished_at_utc=now_utc())
            for check in receipt["checks"]:
                if check["status"] == "pending":
                    check["status"] = "not_completed"
            try:
                write_receipt(receipt_path, receipt)
                saved = True
            except SafeFailure:
                pass
        emit_summary("error", saved, receipt["checks"] if receipt else (), reason)
        return 2


if __name__ == "__main__":
    sys.exit(main())
