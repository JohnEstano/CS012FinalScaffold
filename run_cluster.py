import subprocess
import sys
import os

def main():
    print("==================================================")
    print(" Starting MENDO Distributed Cloud Simulation...")
    print("==================================================")

    processes = []

    # Define your worker nodes here
    # The 3 MENDO machines. Each one gets its own port and API key.
    workers = [
        {"id": "MENDO-01", "port": "8101", "is_private": "false", "key": "key-mendo-01"},
        {"id": "MENDO-02", "port": "8102", "is_private": "false", "key": "key-mendo-02"},
        {"id": "MENDO-03", "port": "8103", "is_private": "false", "key": "key-mendo-03"},
    ]

    for w in workers:
        print(f"[Cluster Manager] Starting {w['id']} on http://localhost:{w['port']}")
        cmd = [
            sys.executable, "-m", "uvicorn", "node.main:app",
            "--host", "127.0.0.1",
            "--port", w["port"],
            "--log-level", "warning"
        ]
        env = {
            "NODE_ID": w["id"],
            "PORT": w["port"],
            "IS_PRIVATE": w["is_private"],
            "API_KEY": w["key"],
            "CLOUD_URL": "http://127.0.0.1:8000",
        }
        p = subprocess.Popen(cmd, env={**os.environ, **env})
        processes.append(p)

    # MENDO Cloud
    print("[Cluster Manager] Starting MENDO Cloud on http://localhost:8000")
    coord_cmd = [
        sys.executable, "-m", "uvicorn", "coordinator.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--log-level", "warning"
    ]
    coord_env = {
        "WORKERS": ",".join(f"http://127.0.0.1:{w['port']}" for w in workers),
        "MACHINE_KEYS": ",".join(f"{w['id']}={w['key']}" for w in workers),
        "ADMIN_KEY": "admin-demo",
    }
    p_coord = subprocess.Popen(coord_cmd, env={**os.environ, **coord_env})
    processes.append(p_coord)

    print("\n[Cluster Online] Open http://localhost:8000")
    print("Interactive Swagger Docs: http://localhost:8000/docs")
    print("Press Ctrl+C to stop all cluster processes.\n")

    try:
        p_coord.wait()
    except KeyboardInterrupt:
        print("\n[Cluster Manager] Shutting down all cluster nodes...")
        for p in processes:
            p.terminate()
        print("[Cluster Manager] Cluster stopped successfully.")

if __name__ == "__main__":
    main()
