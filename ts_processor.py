#For this: https://forum.mapillary.com/t/blueskysea-b4k-viofo-a119v3-and-mapillary
#Usage: python ts_processor.py --input 20210311080720_000421.TS  --sampling_interval 0.5 --folder output

import struct
import sys
import cv2
from exif import Image, DATETIME_STR_FORMAT
from datetime import datetime,timezone
import argparse
import math
import os
import glob

parser = argparse.ArgumentParser()
parser.add_argument('--input', required = True, type=str)
parser.add_argument('--sampling_interval', default = '0.5', type=float)
parser.add_argument('--folder', default = 'output', type=str)
parser.add_argument('--timeshift', default = '0', type=float)
parser.add_argument('--bearing_modifier', default = '0', type=float) #180 if rear camera
args = parser.parse_args()
print(args)
input_ts_file = args.input
folder = args.folder
timeshift = args.timeshift




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

if os.path.isfile(input_ts_file):
    inputfiles = [input_ts_file]
if os.path.isdir(input_ts_file):
    inputfiles = glob.glob(input_ts_file + os.path.sep + '*.ts')
   
   
for input_ts_file in inputfiles:
    device = "A"
    print (input_ts_file)
    video = cv2.VideoCapture(input_ts_file)
    fps = video.get(cv2.CAP_PROP_FPS)
    length = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    print ("FPS : {0}; LEN: {1}".format(fps,length))
    
    interval = int(args.sampling_interval*fps)
    make = "unknown"
    model = "unknown"
    packetno = 0
    locdata = {}
    prevpacket = None
    with open(input_ts_file, "rb") as f:
        
        while True:
            currentdata = {}
            input_packet = f.read(188)
            if not input_packet:
                break
            #Autodetect camera type
            if device == 'A' and input_packet.startswith(bytes("\x47\x03\x00", encoding="raw_unicode_escape")):
                bs = list(input_packet)
                active = chr(bs[156])
                lathem = chr(bs[157])
                lonhem = chr(bs[158])
                if lathem in "NS" and lonhem in "EW":
                    device = "B"
                    make = "Blueskysea"
                    model = "B4K"
                    print ("Autodetected as Blueskysea B4K")
            if device == 'A' and input_packet.startswith(bytes("\x47\x43\x00", encoding="raw_unicode_escape")):
                bs = list(input_packet)
                active = chr(bs[34])
                lathem = chr(bs[35])
                lonhem = chr(bs[36])            
                if lathem in "NS" and lonhem in "EW":
                    device = "V"
                    print ("Autodetected as Viofo A119 V3")
                    make = "Viofo"
                    model = "A119 V3"              
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
                currentdata["bearing"] = bearing
                if active == "A":
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
                if active == "A":
                    locdata[packetno] = currentdata
                packetno += 1
                #print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
            prevpacket = input_packet
            del currentdata
            

    if len(locdata)<5:
        print ("No GPS data")
    else:
        framecount = 0
        count = 0
        success,image = video.read()
        while success:
            if framecount % interval == 0:
                try:
                    #interpolate time and coordinates
                    prev_dataframe = (float(math.trunc((framecount+timeshift*fps)/fps)))
                    
                    current_position = (framecount + timeshift*fps - prev_dataframe*fps)/fps 
                    new_ts = locdata[prev_dataframe]["ts"]+(locdata[(prev_dataframe+1)]["ts"]-locdata[prev_dataframe]["ts"])*current_position
                    new_lat = locdata[prev_dataframe]["lat"]+(locdata[(prev_dataframe+1)]["lat"]-locdata[prev_dataframe]["lat"])*current_position
                    new_lon = locdata[prev_dataframe]["lon"]+(locdata[(prev_dataframe+1)]["lon"]-locdata[prev_dataframe]["lon"])*current_position
                    new_bear = args.bearing_modifier + locdata[prev_dataframe]["bearing"]+(locdata[(prev_dataframe+1)]["bearing"]-locdata[prev_dataframe]["bearing"])*current_position
                    while new_bear < 0:
                        new_bear += 360
                    while new_bear > 360:
                        new_bear -= 360
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
                    e_image.make = make
                    e_image.model = model
                    datetime_taken = datetime.fromtimestamp(new_ts)
                    e_image.datetime_original = datetime_taken.strftime(DATETIME_STR_FORMAT)
                    
                    with open(folder+os.path.sep+input_ts_file.replace(".ts","_")+"%06d.jpg" % count, 'wb') as new_image_file:
                        new_image_file.write(e_image.get_file())
                    #print('Frame: ', framecount)
                    count += 1
                except:
                    print ("No GPS data for frame %d, skipped." % framecount)
            
            framecount += int(fps*args.sampling_interval)
            #print('Frame: ', framecount)
            video.set(1,framecount)
            success,image = video.read()
        video.release()
        os.unlink("tmp.jpg")
