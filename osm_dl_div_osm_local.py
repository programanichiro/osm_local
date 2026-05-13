import sys
sys.path.insert(0, "/data/osm_work/pydeps")

import osmium
import sqlite3
import os
import math

PBF_FILE = "/data/osm_work/japan-latest.osm.pbf"

GRID_SIZE = 0.18
OUT_DIR = "/data/osm_work/tiles"

os.makedirs(OUT_DIR, exist_ok=True)

LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 123.0, 146.0


# ----------------------------------------------------------
# tile
# ----------------------------------------------------------

def tile_xy(lat, lon):

    return (
        math.floor(lon / GRID_SIZE),
        math.floor(lat / GRID_SIZE)
    )


def tile_path(tx, ty):
    return os.path.join(OUT_DIR, f"tile_{ty}_{tx}.sqlite")


# ----------------------------------------------------------
# bbox
# ----------------------------------------------------------

def in_bbox(lat, lon):
    return (
        LAT_MIN <= lat <= LAT_MAX and
        LON_MIN <= lon <= LON_MAX
    )


# ----------------------------------------------------------
# DB cache（軽量）
# ----------------------------------------------------------

db_cache = {}

def get_db(tx, ty):

    key = (tx, ty)

    if key in db_cache:
        return db_cache[key]

    path = tile_path(tx, ty)
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

    db_cache[key] = (conn, cur)
    return conn, cur


# ----------------------------------------------------------
# handler
# ----------------------------------------------------------

class TileHandler(osmium.SimpleHandler):

    def __init__(self):
        super().__init__()
        self.way_count = 0

    def way(self, w):

        if not w.tags.get("highway"):
            return

        try:
            n0 = w.nodes[0]
            lat = n0.location.lat
            lon = n0.location.lon
        except:
            return

        if not in_bbox(lat, lon):
            return

        name = w.tags.get("name", "")
        maxspeed = w.tags.get("maxspeed", "")

        # ★ tileは「先頭node基準＋軽く拡張」
        tx, ty = tile_xy(lat, lon)

        # 隣tileも最低限だけ（跨ぎ保証）
        tiles = [
            (tx, ty),
            (tx+1, ty),
            (tx-1, ty),
            (tx, ty+1),
            (tx, ty-1),
        ]

        for tx, ty in tiles:

            if not (0 <= tx <= 2000 and 0 <= ty <= 2000):
                continue

            conn, cur = get_db(tx, ty)

            # ways
            cur.execute(
                "INSERT OR IGNORE INTO ways VALUES (?, ?, ?, ?)",
                (w.id, name, w.tags.get("highway",""), maxspeed)
            )

            # nodesは「その場で流すだけ」
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

        self.way_count += 1

        if self.way_count % 5000 == 0:
            print("ways:", self.way_count)
            for conn, cur in db_cache.values():
                conn.commit()


# ----------------------------------------------------------
# run
# ----------------------------------------------------------

print("tile building start")

handler = TileHandler()
handler.apply_file(PBF_FILE, locations=True)

print("final commit")

for conn, cur in db_cache.values():
    conn.commit()
    conn.close()

print("done")
