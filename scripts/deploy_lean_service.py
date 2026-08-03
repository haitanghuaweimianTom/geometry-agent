#!/usr/bin/env python3
"""Deploy the Lean verification service to rdzs02.

Strategy:
1. SSH into target (default rdzs02@10.42.0.124), ensure Docker is available.
2. Copy Dockerfile.lean + lean_service.py to ~/lean-svc/.
3. Stop any existing container/process on port 9407.
4. Try Docker build+run; if that fails, fall back to a direct install
   (elan + pip) and run uvicorn under nohup.
5. Wait for /health to respond; report result.

Defaults can be overridden via --host/--password or env LEAN_SSH_HOST/LEAN_SSH_PASS.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REMOTE_DIR = "~/lean-svc"
PORT = 9407
SCRIPT_DIR = Path(__file__).resolve().parent


class Deployer:
    def __init__(self, host: str, password: str):
        self.host = host
        self.password = password
        self.ssh_base = [
            "sshpass", "-p", password, "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
            "-o", "NumberOfPasswordPrompts=1",
            host,
        ]
        self.scp_base = [
            "sshpass", "-p", password, "scp",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
        ]

    def ssh(self, cmd: str, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess:
        print(f"[ssh] {cmd}")
        r = subprocess.run(self.ssh_base + [cmd], capture_output=True, text=True, timeout=timeout)
        if r.stdout.strip():
            print("   stdout:", r.stdout.strip()[:400])
        if r.stderr.strip() and "password" not in r.stderr.lower():
            print("   stderr:", r.stderr.strip()[:400])
        if check and r.returncode != 0:
            raise RuntimeError(f"ssh command failed ({r.returncode}): {cmd}\n{r.stderr}")
        return r

    def scp(self, src: Path, dst: str) -> None:
        print(f"[scp] {src} -> {self.host}:{dst}")
        r = subprocess.run(self.scp_base + [str(src), f"{self.host}:{dst}"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"scp failed: {r.stderr}")

    def wait_for_health(self, timeout: int = 60) -> bool:
        deadline = time.time() + timeout
        url = f"http://127.0.0.1:{PORT}/health"
        while time.time() < deadline:
            r = self.ssh(f"curl -sf {url} || true", timeout=10)
            out = r.stdout
            if '"ok"' in out or '"status":"ok"' in out or '"status": "ok"' in out:
                return True
            time.sleep(2)
        return False

    def ensure_docker(self) -> bool:
        r = self.ssh("which docker && docker --version", timeout=15)
        if r.returncode != 0:
            print("Docker not found. Attempting install...")
            r = self.ssh(
                f"echo {self.password} | sudo -S apt-get update -y && "
                f"echo {self.password} | sudo -S apt-get install -y docker.io python3-pip",
                timeout=300,
            )
            if r.returncode != 0:
                print("Docker install failed.")
                return False
        self.ssh(f"echo {self.password} | sudo -S usermod -aG docker $(whoami)", timeout=30)
        self.ssh(f"echo {self.password} | sudo -S systemctl start docker 2>/dev/null; "
                 f"echo {self.password} | sudo -S service docker start 2>/dev/null; true",
                 timeout=60)
        r = self.ssh(f"echo {self.password} | sudo -S docker ps", timeout=30)
        return r.returncode == 0

    def kill_existing(self) -> None:
        self.ssh(f"echo {self.password} | sudo -S docker rm -f lean-svc 2>/dev/null; true",
                 timeout=30)
        self.ssh(f"pkill -f 'uvicorn lean_service' 2>/dev/null; true", timeout=10)
        self.ssh(f"fuser -k {PORT}/tcp 2>/dev/null; true", timeout=10)

    def deploy_docker(self) -> bool:
        print("\n=== Attempting Docker deployment ===")
        self.ssh(f"mkdir -p {REMOTE_DIR}", timeout=10)
        self.scp(SCRIPT_DIR / "lean_service.py", f"{REMOTE_DIR}/lean_service.py")
        self.scp(SCRIPT_DIR / "Dockerfile.lean", f"{REMOTE_DIR}/Dockerfile")
        print("Building Docker image (this may take several minutes)...")
        r = self.ssh(
            f"cd {REMOTE_DIR} && echo {self.password} | sudo -S docker build -t lean-svc .",
            timeout=1200,
        )
        if r.returncode != 0:
            print("Docker build failed.")
            return False
        print("Running container...")
        r = self.ssh(
            f"cd {REMOTE_DIR} && echo {self.password} | sudo -S docker run -d --rm "
            f"--name lean-svc -p {PORT}:{PORT} lean-svc",
            timeout=60,
        )
        if r.returncode != 0:
            print("Docker run failed.")
            return False
        return True

    def deploy_direct(self) -> bool:
        print("\n=== Falling back to direct (no-Docker) deployment ===")
        self.ssh(f"mkdir -p {REMOTE_DIR}", timeout=10)
        self.scp(SCRIPT_DIR / "lean_service.py", f"{REMOTE_DIR}/lean_service.py")

        self.ssh(
            f"echo {self.password} | sudo -S apt-get update -y && "
            f"echo {self.password} | sudo -S apt-get install -y --no-install-recommends "
            f"curl ca-certificates python3-pip",
            timeout=300,
        )
        self.ssh(
            "pip3 install --break-system-packages --user fastapi uvicorn pydantic requests "
            "2>&1 | tail -3", timeout=300,
        )
        r = self.ssh("which lean", timeout=10)
        if r.returncode != 0:
            print("Installing elan/lean ...")
            self.ssh(
                "curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh "
                "-sSf | sh -s -- -y --default-toolchain stable",
                timeout=600,
            )
        start_cmd = (
            f"cd {REMOTE_DIR} && "
            f"export PATH=$HOME/.elan/bin:$HOME/.local/bin:$PATH && "
            f"nohup python3 -m uvicorn lean_service:app --host 0.0.0.0 --port {PORT} "
            f"> {REMOTE_DIR}/svc.log 2>&1 & echo PID=$!"
        )
        self.ssh(start_cmd, timeout=15)
        time.sleep(3)
        return True

    def run(self, no_docker: bool) -> int:
        try:
            r = self.ssh("echo connected && whoami && uname -a", timeout=15)
            if r.returncode != 0:
                print("ERROR: cannot SSH to host; check credentials/network.")
                return 2
        except Exception as e:
            print(f"ERROR: SSH failed: {e}")
            return 2

        print(f"Checking port {PORT}...")
        self.ssh(f"ss -tlnp | grep {PORT} || echo 'port free'", timeout=10)
        self.kill_existing()

        used_docker = False
        if not no_docker:
            if self.ensure_docker():
                used_docker = self.deploy_docker()
            else:
                print("Docker unavailable.")

        if not used_docker:
            if not self.deploy_direct():
                print("Direct deploy failed too.")
                return 1

        print("\nWaiting for /health ...")
        if self.wait_for_health(timeout=90):
            r = self.ssh(
                f'curl -s -X POST http://127.0.0.1:{PORT}/verify '
                f'-H "Content-Type: application/json" '
                f"-d '{{\"conclusion\":\"1+1=2\"}}'",
                timeout=20,
            )
            print("\nSmoke test /verify:", r.stdout.strip())
            host_ip = self.host.split("@")[-1]
            print(f"\nSUCCESS: Lean service is up at http://{host_ip}:{PORT}")
            print(f"  (deployed via {'Docker' if used_docker else 'direct (nohup uvicorn)'})")
            return 0
        print("Timed out waiting for /health.")
        self.ssh(f"tail -40 {REMOTE_DIR}/svc.log 2>/dev/null; echo '---docker logs---'; "
                 f"echo {self.password} | sudo -S docker logs lean-svc 2>&1 | tail -40",
                 timeout=20)
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy Lean 4 verification service.")
    ap.add_argument("--no-docker", action="store_true",
                    help="Skip Docker, do direct install.")
    ap.add_argument("--host", default=os.environ.get("LEAN_SSH_HOST", "rdzs02@10.42.0.124"))
    ap.add_argument("--password", default=os.environ.get("LEAN_SSH_PASS", "rdzs123"))
    args = ap.parse_args()

    d = Deployer(args.host, args.password)
    return d.run(no_docker=args.no_docker)


if __name__ == "__main__":
    sys.exit(main())
