# MENDO Distributed Cloud System (CS012 Final Project)

Our thesis MENDO (a symptom-to-medicine vending machine) redesigned as 3 MENDO machines connected to 1 cloud.
Built on the [CS012 scaffold](https://github.com/ctrl-siege/CS012FinalScaffold).

## Run

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run_cluster.py
```

Open http://localhost:8000 and press **Start simulation**. The 3D view loads Three.js from a CDN, so the page needs internet. The presentation script is in [DEMO_GUIDE.md](DEMO_GUIDE.md).

## Files

* `run_cluster.py` starts the cloud (port 8000) and MENDO-01/02/03 (ports 8101–8103).
* `coordinator/main.py` is the cloud. It keeps the scaffold's `/cluster/health`, `/api/v1/write` and `/api/v1/read/{key}`, and adds heartbeats, sync, the dashboard, alerts and backup/restore.
* `node/main.py` is one MENDO machine. It keeps the scaffold's `/health`, `/store`, `/read/{key}` and `/compute-parallel`, and adds the recommender, 10 medicines, sales, the local queue and sync to the cloud.
* `common/models.py` holds the scaffold models plus the MENDO ones.
* `common/logger.py` is the scaffold's trace logger, plus writing events to `logs/`.
* `web/index.html` is the page: machine screens, cloud dashboard, scaffold API buttons and logs.
* `web/world.js` is the low-poly 3D view of the cloud and the three locations.

Machine ports are 8101–8103 instead of the scaffold's 8001–8003 because 8002 was already in use on our computer.
