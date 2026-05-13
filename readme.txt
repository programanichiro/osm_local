

mkdir /data/osm_work

https://download.geofabrik.de/asia/japan-latest.osm.pbfをダウンロードして
/data/osm_work/japan-latest.osm.pbfの名前で保存

curl -L "https://download.geofabrik.de/asia/japan-latest.osm.pbf" -o /data/osm_work/japan-latest.osm.pbf

python3.12 -m pip install --target /data/osm_work/pydeps osmium


import sys

sys.path.insert(0, "/data/osm_work/pydeps")

import osmium

python3.12 ./osm_dl_div_osm_local.py

