import sys
sys.path.insert(0, "/data/osm_work/pydeps")

import osmium
import sqlite3
import os
import math


PBF_FILE = "/data/osm_work/japan-latest.osm.pbf"

# 約20km
GRID_SIZE = 0.18

OUT_DIR = "../osm_work/tiles"

os.makedirs(OUT_DIR, exist_ok=True)


# ----------------------------------------------------------
# 日本範囲
# ----------------------------------------------------------

LAT_MIN = 24.0
LAT_MAX = 46.0

LON_MIN = 123.0
LON_MAX = 146.0


# ----------------------------------------------------------
# tile index
# ----------------------------------------------------------

def tile_xy(lat, lon):

    return (
        math.floor(lon / GRID_SIZE),
        math.floor(lat / GRID_SIZE)
    )


def tile_name(tx, ty):

    return f"tile_{ty}_{tx}.sqlite"


def tile_path(tx, ty):

    return os.path.join(
        OUT_DIR,
        tile_name(tx, ty)
    )


# ----------------------------------------------------------
# bbox
# ----------------------------------------------------------

def in_bbox(lat, lon):

    return (
        LAT_MIN <= lat <= LAT_MAX
        and
        LON_MIN <= lon <= LON_MAX
    )


# ----------------------------------------------------------
# db cache
# ----------------------------------------------------------

db_cache = {}


def get_db(tx, ty):

    key = (tx, ty)

    if key in db_cache:
        return db_cache[key]

    path = tile_path(tx, ty)

    # ------------------------------------------------------
    # 初回だけDB生成
    # ------------------------------------------------------

    is_new = not os.path.exists(path)

    conn = sqlite3.connect(path)

    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=OFF")
    cur.execute("PRAGMA synchronous=OFF")

    # ------------------------------------------------------
    # 新規DB時だけtable生成
    # ------------------------------------------------------

    if is_new:

        cur.execute("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            lat REAL,
            lon REAL
        )
        """)

        cur.execute("""
        CREATE TABLE ways (
            id INTEGER PRIMARY KEY,
            name TEXT,
            highway TEXT,
            maxspeed TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE way_nodes (
            way_id INTEGER,
            node_id INTEGER,
            seq INTEGER
        )
        """)

        cur.execute("""
        CREATE INDEX idx_nodes_latlon
        ON nodes(lat, lon)
        """)

        cur.execute("""
        CREATE INDEX idx_way_nodes_way
        ON way_nodes(way_id)
        """)

        cur.execute("""
        CREATE INDEX idx_way_nodes_node
        ON way_nodes(node_id)
        """)

        conn.commit()

    db_cache[key] = (
        conn,
        cur
    )

    return conn, cur


# ----------------------------------------------------------
# tile list
# 道路が跨ぐtile全部へ複製
# ----------------------------------------------------------

def touched_tiles(nodes):

    result = set()

    for n in nodes:

        try:
            lat = n.location.lat
            lon = n.location.lon
        except Exception:
            continue

        tx, ty = tile_xy(lat, lon)

        result.add((tx, ty))

    return result


# ----------------------------------------------------------
# handler
# ----------------------------------------------------------

class TileHandler(osmium.SimpleHandler):

    def __init__(self):

        super().__init__()

        self.inserted_nodes = {}

        self.way_count = 0

    def way(self, w):

        tags = w.tags

        highway = tags.get("highway")

        if not highway:
            return

        # --------------------------------------------------
        # bbox外skip
        # --------------------------------------------------

        try:

            first = w.nodes[0]

            lat = first.location.lat
            lon = first.location.lon

        except Exception:
            return

        if not in_bbox(lat, lon):
            return

        # --------------------------------------------------
        # way情報
        # --------------------------------------------------

        name = tags.get("name", "")

        maxspeed = tags.get("maxspeed", "")

        # --------------------------------------------------
        # 道路が触れたtile全部
        # --------------------------------------------------

        tiles = touched_tiles(w.nodes)

        if len(tiles) == 0:
            return

        # --------------------------------------------------
        # 各tileへ複製
        # --------------------------------------------------

        for tx, ty in tiles:

            conn, cur = get_db(tx, ty)

            # ----------------------------------------------
            # ways
            # ----------------------------------------------

            cur.execute("""
                INSERT OR IGNORE INTO ways(
                    id,
                    name,
                    highway,
                    maxspeed
                )
                VALUES (?, ?, ?, ?)
            """, (
                w.id,
                name,
                highway,
                maxspeed
            ))

            # ----------------------------------------------
            # nodes + links
            # ----------------------------------------------

            inserted = self.inserted_nodes.setdefault(
                (tx, ty),
                set()
            )

            for seq, n in enumerate(w.nodes):

                try:

                    nlat = n.location.lat
                    nlon = n.location.lon

                except Exception:
                    continue

                # ------------------------------------------
                # nodes
                # ------------------------------------------

                if n.ref not in inserted:

                    inserted.add(n.ref)

                    cur.execute("""
                        INSERT OR IGNORE INTO nodes(
                            id,
                            lat,
                            lon
                        )
                        VALUES (?, ?, ?)
                    """, (
                        n.ref,
                        nlat,
                        nlon
                    ))

                # ------------------------------------------
                # way_nodes
                # ------------------------------------------

                cur.execute("""
                    INSERT INTO way_nodes(
                        way_id,
                        node_id,
                        seq
                    )
                    VALUES (?, ?, ?)
                """, (
                    w.id,
                    n.ref,
                    seq
                ))

        # --------------------------------------------------
        # progress
        # --------------------------------------------------

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

handler.apply_file(
    PBF_FILE,
    locations=True
)

print("final commit")

for conn, cur in db_cache.values():

    conn.commit()

    conn.close()

print("done")
