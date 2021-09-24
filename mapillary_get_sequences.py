import requests
import json
import os
from vt2geojson.tools import vt_bytes_to_geojson

import math
import argparse
import time

start = time.time()

parser = argparse.ArgumentParser()
parser.add_argument('--user_id', required=True, type=int) #input user ID
parser.add_argument('--outputfolder', default = ".", type=str) #output folder
parser.add_argument('--zoom', default=10, type=int) #at what zoom level should end result be - higher values mean more accurate but slower result
parser.add_argument('--token', default="MLY12345", type=str) #Mapillary token - can be set as default



args = parser.parse_args()
print(args)


seen = []


def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

output = {"type":"FeatureCollection","features":[]}

MAP_ACCESS_TOKEN = args.token
outputfolder = args.outputfolder
user_id = args.user_id
maxzoom = args.zoom
#set zoom levels and corner coordinates

def checkme(z1,x1,y1):
    url = f"https://tiles.mapillary.com/maps/vtp/mly1/2/{z1}/{x1}/{y1}?access_token={MAP_ACCESS_TOKEN}"
    if url in seen:
        return 1
    seen.append(url)
    r = requests.get(url)
    assert r.status_code == 200, r.content
    vt_content = r.content

    features = vt_bytes_to_geojson(vt_content, x1, y1, z1)

    if str(user_id) in (json.dumps(features)): 
        if z1<maxzoom:
            print (z1,x1,y1)
            checkme(z1+1,2*x1,2*y1)
            checkme(z1+1,2*x1+1,2*y1)
            checkme(z1+1,2*x1,2*y1+1)
            checkme(z1+1,2*x1+1,2*y1+1)
        else:
            for f in features["features"]:
                
                if (f["geometry"]["type"]).lower().endswith("string") and f["properties"]["creator_id"] == user_id:
                    output['features'].append(f)
                    

z = 1 #At what zoom to start

##Set the corners for search area
ll_lat = 1  
ll_lon = 1 
ur_lat = 80  
ur_lon = 80 
llx,lly = deg2num (ll_lat, ll_lon, z)
urx,ury = deg2num (ur_lat, ur_lon, z)
types = ["mly1"]
 
#Start at high zoom and for every level do the split and recheck.
if True:
    llx,lly = deg2num (ll_lat, ll_lon, z)
    urx,ury = deg2num (ur_lat, ur_lon, z)
    output = {"type":"FeatureCollection","features":[]}
    for x in range(min(llx,urx),max(llx,urx)+1,1):
        for y in range(min(lly,ury),max(lly,ury)+1,1):
            checkme(z,x,y)

with open(outputfolder + os.path.sep + str(user_id) + '.geojson', 'w') as outfile:
    json.dump(output, outfile)
    
end = time.time()
print("Total runtime: ", end - start)