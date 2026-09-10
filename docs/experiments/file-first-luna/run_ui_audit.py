"""One real-page audit with owned short-lived server and headless Chrome.

Run AFTER cost experiments to avoid adding browser load to their timings.
Never attaches to or stops the user's existing browser/services. Leaves logs and
screenshot artifacts, then terminates only helper process trees created here.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ready(url, proc):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Owned helper exited during startup")
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except urllib.error.HTTPError:
            return  # HTTP error still proves this listener is ready.
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise TimeoutError("Owned helper startup timed out")


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill.exe","/PID",str(proc.pid),"/T","/F"],capture_output=True,timeout=20)
    else:
        proc.terminate()
    proc.wait(timeout=20)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--rep", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    case = json.loads((args.case / "case.json").read_text(encoding="utf-8"))
    if args.out.exists() or args.out.resolve().is_relative_to(Path(case["pool"]).resolve()):
        raise ValueError("Output must be new and outside raw pool")
    run = args.case / "runs/tools" / f"rep{args.rep}"
    metric = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    if not metric.get("verdict_ok"):
        raise ValueError("This happy-path browser check requires an accepted document; do not hide rejected submissions")
    args.out.mkdir(parents=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(Path(case["source"]) / "src"), MIGLOOP_FROZEN_POOL=case["pool"],
        MIGLOOP_FROZEN_ANCHOR=case["current_root"], MIGLOOP_FROZEN_ROOTS=json.dumps(case["roots"]))
    server_port, chrome_port = port(), port()
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not chrome.is_file():
        raise FileNotFoundError("Expected installed Chrome not found")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    server = browser = None
    outcome = {"case":case["case"], "rep":args.rep, "status":"starting", "semantic_checked":False}
    try:
        with (args.out/"server.log").open("wb") as server_log, (args.out/"chrome.log").open("wb") as chrome_log:
            server = subprocess.Popen([sys.executable,"-X","utf8","-m","migloop.cli",case["current_root"],
                "--serve","--host","127.0.0.1","--port",str(server_port)],cwd=case["source"],env=env,
                stdout=server_log,stderr=subprocess.STDOUT,creationflags=flags)
            ready(f"http://127.0.0.1:{server_port}/robots.txt", server)
            browser = subprocess.Popen([str(chrome),"--headless=new","--disable-gpu","--no-first-run",
                "--no-default-browser-check","--disable-background-networking","--disable-sync",
                f"--remote-debugging-port={chrome_port}",f"--user-data-dir={args.out.resolve()/'chrome-profile'}","about:blank"],
                stdout=chrome_log,stderr=subprocess.STDOUT,creationflags=flags)
            ready(f"http://127.0.0.1:{chrome_port}/json/version", browser)
            sid = Path(case["current_root"]).stem[:8]
            url = f"http://127.0.0.1:{server_port}/api/insight1/fixchain/{sid}?probe=" + urllib.parse.quote(str(run.resolve()),safe="")
            test = Path(case["source"]) / "tests/browser/probe_smoke.cjs"
            result = subprocess.run(["node",str(test),url,str(args.out.resolve()/"page.png"),
                                     f"http://127.0.0.1:{chrome_port}","bound"],capture_output=True,timeout=150)
            (args.out/"browser.stdout.txt").write_bytes(result.stdout)
            (args.out/"browser.stderr.txt").write_bytes(result.stderr)
            outcome.update(status="passed" if result.returncode==0 else "failed",returncode=result.returncode,
                           screenshot=str(args.out.resolve()/"page.png"),
                           details=result.stdout.decode("utf-8",errors="replace"),
                           error=result.stderr.decode("utf-8",errors="replace"))
    except Exception as exc:
        outcome.update(status="error",error=repr(exc))
    finally:
        stop(browser)
        stop(server)
        outcome["owned_helpers_stopped"] = all(p is None or p.poll() is not None for p in (browser,server))
        with (args.out/"audit.json").open("x",encoding="utf-8") as handle:
            json.dump(outcome,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in outcome.items() if k!="details"},ensure_ascii=False))
    return 0 if outcome["status"]=="passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
