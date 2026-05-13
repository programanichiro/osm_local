import sys
sys.path.insert(0, "/data/osm_work/pydeps")

import osmium
import sqlite3
import os
import math

# ----------------------------------------------------------
# input / output
# ----------------------------------------------------------

PBF_FILE = "/data/osm_work/japan-latest.osm.pbf"
OUT_DIR = "/data/osm_work/tiles"

os.makedirs(OUT_DIR, exist_ok=True)

# ----------------------------------------------------------
# grid
# ----------------------------------------------------------

GRID_SIZE = 0.18

LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 123.0, 146.0


# ----------------------------------------------------------
# tile
# ----------------------------------------------------------

def tile_xy(lat, lon):
    return (
        int(lon / GRID_SIZE),
        int(lat / GRID_SIZE)
    )


def tile_path(tx, ty):
    return os.path.join(OUT_DIR, f"tile_{ty}_{tx}.sqlite")


def ensure_db(path):

    is_new = not os.path.exists(path)

    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=OFF")
    cur.execute("PRAGMA synchronous=OFF")

    if is_new:
        cur.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            lat REAL,
            lon REAL
        );

        CREATE TABLE ways (
            id INTEGER PRIMARY KEY,
            name TEXT,
            highway TEXT,
            maxspeed TEXT
        );

        CREATE TABLE way_nodes (
            way_id INTEGER,
            node_id INTEGER,
            seq INTEGER
        );

        CREATE INDEX idx_way_nodes_way ON way_nodes(way_id);
        """)

    return conn, cur


# ----------------------------------------------------------
# bbox
# ----------------------------------------------------------

def in_bbox(lat, lon):
    return (
        LAT_MIN <= lat <= LAT_MAX and
        LON_MIN <= lon <= LON_MAX
    )


# ----------------------------------------------------------
# handler
# ----------------------------------------------------------

class TileHandler(osmium.SimpleHandler):

    def __init__(self):
        super().__init__()
        self.count = 0

    def way(self, w):

        if not w.tags.get("highway"):
            return

        # --------------------------------------------------
        # bbox軽チェック（完全精度は捨てる）
        # --------------------------------------------------

        try:
            n0 = w.nodes[0]
            lat = n0.location.lat
            lon = n0.location.lon
        except:
            return

        if not in_bbox(lat, lon):
            return

        name = w.tags.get("name", "")
        highway = w.tags.get("highway", "")
        maxspeed = w.tags.get("maxspeed", "")

        # --------------------------------------------------
        # tile決定（全nodeベース）
        # --------------------------------------------------

        tiles = set()
        for n in w.nodes:
            try:
                lat2 = n.location.lat
                lon2 = n.location.lon
            except:
                continue

            tx, ty = tile_xy(lat2, lon2)
            tiles.add((tx, ty))

        if not tiles:
            return

        # --------------------------------------------------
        # 各tileへ書き込み（即open→即close）
        # --------------------------------------------------

        for tx, ty in tiles:

            path = tile_path(tx, ty)
            conn, cur = ensure_db(path)

            # ways
            cur.execute(
                "INSERT OR IGNORE INTO ways VALUES (?, ?, ?, ?)",
                (w.id, name, highway, maxspeed)
            )

            # nodes + way_nodes
            for seq, n in enumerate(w.nodes):

                try:
                    lat2 = n.location.lat
                    lon2 = n.location.lon
                except:
                    continue

                cur.execute(
                    "INSERT OR IGNORE INTO nodes VALUES (?, ?, ?)",
                    (n.ref, lat2, lon2)
                )

                cur.execute(
                    "INSERT INTO way_nodes VALUES (?, ?, ?)",
                    (w.id, n.ref, seq)
                )

            conn.commit()
            conn.close()

        self.count += 1

        if self.count % 5000 == 0:
            print("ways:", self.count)


# ----------------------------------------------------------
# run
# ----------------------------------------------------------

print("tile building start")

handler = TileHandler()

handler.apply_file(
    PBF_FILE,
    locations=True
)

print("done")
