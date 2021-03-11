#For this: https://forum.mapillary.com/t/blueskysea-b4k-viofo-a119v3-and-mapillary
#Usage: python ts_processor.py --input 20210311080720_000421.TS  --interval 2 --device B --folder output --prefix this_video_frame_

import struct
import sys
import cv2
from exif import Image, DATETIME_STR_FORMAT
from datetime import datetime,timezone
import argparse
import math
import os

parser = argparse.ArgumentParser()
parser.add_argument('--input', required = True, type=str)
parser.add_argument('--interval', default = '2', type=float)
parser.add_argument('--device', default = 'B', type=str)
parser.add_argument('--folder', default = 'output', type=str)
parser.add_argument('--prefix', default = 'picture_', type=str)
args = parser.parse_args()
print(args)

input_ts_file = args.input
device = args.device
interval = args.interval
folder = args.folder
prefix = args.prefix

def fix_coordinates(hemisphere,coordinate_input): #From here: https://sergei.nz/extracting-gps-data-from-viofo-a119-and-other-novatek-powered-cameras/
    coordinate, = coordinate_input
    minutes = coordinate % 100.0
    degrees = coordinate - minutes
    coordinate = degrees / 100.0 + (minutes / 60.0)
    if hemisphere == 'S' or hemisphere == 'W':
        return -1*float(coordinate)
    else:
        return float(coordinate)
    
def to_gps_latlon(v, refs):
    ref = refs[0] if v >= 0 else refs[1]
    dd = abs(v)
    d = int(dd)
    mm = (dd - d) * 60
    m = int(mm)
    ss = (mm - m) * 60
    s = int(ss * 100)
    r = (d, m, ss)
    return (ref, r)    


try:
    os.mkdir(folder)
except:
    pass
video = cv2.VideoCapture(input_ts_file)
fps = video.get(cv2.CAP_PROP_FPS)
length = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
print ("FPS : {0}; LEN: {1}".format(fps,length))
packetno = 0
locdata = {}
prevpacket = None
with open(input_ts_file, "rb") as f:
    
    while True:
        currentdata = {}
        input_packet = f.read(188)
        if not input_packet:
            break
        if device == 'B' and prevpacket and input_packet.startswith(bytes("\x47\x03\x00", encoding="raw_unicode_escape")):
            bs = list(input_packet)
            hour = int.from_bytes(prevpacket[174:178], byteorder='little')
            minute = int.from_bytes(prevpacket[178:182], byteorder='little')
            second = int.from_bytes(prevpacket[182:186], byteorder='little')
            year = int.from_bytes(prevpacket[186:188] + input_packet[146:148], byteorder='little')
            month = int.from_bytes(input_packet[148:152], byteorder='little')
            day = int.from_bytes(input_packet[152:156], byteorder='little')
            active = chr(bs[156])
            lathem = chr(bs[157])
            lonhem = chr(bs[158])
            lat = fix_coordinates(lathem,struct.unpack('<f', input_packet[160:164]))
            lon = fix_coordinates(lonhem,struct.unpack('<f', input_packet[164:168]))
            speed_knots, = struct.unpack('<f', input_packet[168:172])
            speed = speed_knots * 1.6 / 3.6
            bearing, = struct.unpack('<f', input_packet[172:176])
            currentdata["ts"] = datetime(year=2000+year, month=month, day=day, hour=hour, minute=minute, second=second).replace(tzinfo=timezone.utc).timestamp()
            currentdata["lat"] = lat
            currentdata["latR"] = lathem
            currentdata["lon"] = lon
            currentdata["lonR"] = lonhem
            locdata[packetno] = currentdata
            packetno += 1
            #print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
        if device == 'V' and input_packet.startswith(bytes("\x47\x43\x00", encoding="raw_unicode_escape")):
            bs = list(input_packet)
            hour = int.from_bytes(input_packet[10:14], byteorder='little')
            minute = int.from_bytes(input_packet[14:18], byteorder='little')
            second = int.from_bytes(input_packet[18:22], byteorder='little')
            year = int.from_bytes(input_packet[22:26], byteorder='little')
            month = int.from_bytes(input_packet[26:30], byteorder='little')
            day = int.from_bytes(input_packet[30:34], byteorder='little')
            active = chr(bs[34])
            lathem = chr(bs[35])
            lonhem = chr(bs[36])
            lat = fix_coordinates(lathem,struct.unpack('<f', input_packet[38:42]))
            lon = fix_coordinates(lonhem,struct.unpack('<f', input_packet[42:46]))
            speed_knots, = struct.unpack('<f', input_packet[46:50])
            speed = speed_knots * 1.6 / 3.6
            bearing, = struct.unpack('<f', input_packet[50:54])
            currentdata["ts"] = datetime(year=2000+year, month=month, day=day, hour=hour, minute=minute, second=second).replace(tzinfo=timezone.utc).timestamp()
            currentdata["lat"] = lat
            currentdata["latR"] = lathem
            currentdata["lon"] = lon
            currentdata["lonR"] = lonhem
            currentdata["bearing"] = bearing
            locdata[packetno] = currentdata
            packetno += 1
            #print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
        prevpacket = input_packet
        del currentdata
        


framecount = 0
count = 0
success,image = video.read()
while success:
    if framecount % int(fps/interval) == 0:
        #interpolate time and coordinates
        prev_dataframe = min(len(locdata)-1,float(math.trunc(framecount/fps)))
        
        current_position = (framecount - prev_dataframe*fps)/fps
        new_ts = locdata[prev_dataframe]["ts"]+(locdata[min(len(locdata)-1,prev_dataframe+1)]["ts"]-locdata[prev_dataframe]["ts"])*current_position
        new_lat = locdata[prev_dataframe]["lat"]+(locdata[min(len(locdata)-1,prev_dataframe+1)]["lat"]-locdata[prev_dataframe]["lat"])*current_position
        new_lon = locdata[prev_dataframe]["lon"]+(locdata[min(len(locdata)-1,prev_dataframe+1)]["lon"]-locdata[prev_dataframe]["lon"])*current_position
        new_bear = locdata[prev_dataframe]["bearing"]+(locdata[min(len(locdata)-1,prev_dataframe+1)]["bearing"]-locdata[prev_dataframe]["bearing"])*current_position
        lonref, lon2 = to_gps_latlon(new_lon, ('E', 'W'))
        latref, lat2 = to_gps_latlon(new_lat, ('N', 'S'))
        cv2.imwrite("tmp.jpg", image)
        e_image = Image("tmp.jpg")
        e_image.gps_latitude = lat2
        e_image.gps_latitude_ref = latref
        e_image.gps_longitude  = lon2
        e_image.gps_longitude_ref = lonref
        e_image.gps_img_direction = new_bear
        e_image.gps_dest_bearing = new_bear
        e_image.make = "Potato"
        datetime_taken = datetime.fromtimestamp(new_ts)
        e_image.datetime_original = datetime_taken.strftime(DATETIME_STR_FORMAT)
        
        with open(folder+os.path.sep+prefix+"%d.jpg" % count, 'wb') as new_image_file:
            new_image_file.write(e_image.get_file())
        success,image = video.read()
        #print('Frame: ', framecount)
        count += 1
    framecount += 1
    success,image = video.read()
video.release()
os.unlink("tmp.jpg")
