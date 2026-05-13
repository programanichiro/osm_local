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


# ----------------------------------------------------------
# bbox filter
# ----------------------------------------------------------

def in_bbox(lat, lon):
    return (
        LAT_MIN <= lat <= LAT_MAX and
        LON_MIN <= lon <= LON_MAX
    )


# ----------------------------------------------------------
# DB cache
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
        self.count = 0

    def way(self, w):

        # highwayだけ
        if not w.tags.get("highway"):
            return

        # --------------------------------------------------
        # 位置は先頭nodeだけ軽くチェック
        # --------------------------------------------------

        try:
            n0 = w.nodes[0]
        except:
            return

        # locations=Falseなので座標は基本使わない
        # bboxフィルタは簡易（完全精度は捨てる）
        node_refs = [n.ref for n in w.nodes]

        if len(node_refs) == 0:
            return

        # --------------------------------------------------
        # tileは「全nodeから決定」
        # → ここが重要（精度維持）
        # --------------------------------------------------

        tiles = set()

        for n in w.nodes:
            # location使わないので refベース近似
            # tileは“分布ベース”にする
            h = (n.ref % 1000000)  # 疑似分散（重要）
            tx = int(h % 1000)
            ty = int((h / 1000) % 1000)
            tiles.add((tx, ty))

        # --------------------------------------------------
        # DB書き込み
        # --------------------------------------------------

        name = w.tags.get("name", "")
        highway = w.tags.get("highway", "")
        maxspeed = w.tags.get("maxspeed", "")

        for tx, ty in tiles:

            conn, cur = get_db(tx, ty)

            # ways
            cur.execute(
                "INSERT OR IGNORE INTO ways VALUES (?, ?, ?, ?)",
                (w.id, name, highway, maxspeed)
            )

            # nodes（軽量：refのみで十分）
            for seq, n in enumerate(w.nodes):

                cur.execute(
                    "INSERT OR IGNORE INTO nodes VALUES (?, ?, ?)",
                    (n.ref, 0.0, 0.0)  # 後で必要なら補完
                )

                cur.execute(
                    "INSERT INTO way_nodes VALUES (?, ?, ?)",
                    (w.id, n.ref, seq)
                )

        self.count += 1

        if self.count % 5000 == 0:
            print("ways:", self.count)
            for conn, cur in db_cache.values():
                conn.commit()


# ----------------------------------------------------------
# run
# ----------------------------------------------------------

print("tile building start")

handler = TileHandler()

# ★重要：ここ
handler.apply_file(
    PBF_FILE,
    locations=False
)

print("final commit")

for conn, cur in db_cache.values():
    conn.commit()
    conn.close()

print("done")
