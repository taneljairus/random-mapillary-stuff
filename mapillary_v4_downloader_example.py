import requests
import json
import os
from vt2geojson.tools import vt_bytes_to_geojson

import math
def deg2num(lat_deg, lon_deg, zoom):
  lat_rad = math.radians(lat_deg)
  n = 2.0 ** zoom
  xtile = int((lon_deg + 180.0) / 360.0 * n)
  ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
  return (xtile, ytile)

MAP_ACCESS_TOKEN = "MLY|1234567899" ##Change this
outputfolder = "E:/yield_folder/yield_traffic_sign.geojson"  ##Change this

#set zoom levels and corner coordinates

z = 14
ll_lat = 49.6265 
ll_lon = 28.9991
ur_lat = 51.3965 
ur_lon = 31.9874
llx,lly = deg2num (ll_lat, ll_lon, z)
urx,ury = deg2num (ur_lat, ur_lon, z)

#remove the layers you don't want to use
#description are in official docs: https://www.mapillary.com/developer/api-documentation/

types = ["mly_map_feature_traffic_sign"]

for type in types:
    output = {"type":"FeatureCollection","features":[]}
    for x in range(min(llx,urx),max(llx,urx),1):
        for y in range(min(lly,ury),max(lly,ury),1):
            print (type,x,y)
            url = f"https://tiles.mapillary.com/maps/vtp/{type}/2/{z}/{x}/{y}?access_token={MAP_ACCESS_TOKEN}"
            r = requests.get(url)
            assert r.status_code == 200, r.content
            vt_content = r.content
            features = vt_bytes_to_geojson(vt_content, x, y, z)
            for f in features["features"]:
                output['features'].append(f)
    with open(outputfolder + os.path.sep + type + "_" + str(z) + "_" + str(llx) + "_" + str(urx) + "_" + str(lly) + "_" + str(ury) + ".geojson", "w") as fx:
        json.dump(output, fx)

