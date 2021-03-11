#For this: https://forum.mapillary.com/t/blueskysea-b4k-viofo-a119v3-and-mapillary
#Usage: python tss_gps_data.py 20210109161626_000009A.tts

import struct
import sys
try:
    input_ts_file = sys.argv[1]
except:
    print ("Usage: python tss_gps_data.py file [type]")
    exit()
try:
    device = sys.argv[2]
except:
    # B for Blueskysea, V for Viofo. This could be made more automatically at some point.
    if input_ts_file.lower().endswith(".tts"):
        device = 'B'
    else:
        device = 'V'

def fix_coordinates(hemisphere,coordinate_input): #From here: https://sergei.nz/extracting-gps-data-from-viofo-a119-and-other-novatek-powered-cameras/
    coordinate, = coordinate_input
    minutes = coordinate % 100.0
    degrees = coordinate - minutes
    coordinate = degrees / 100.0 + (minutes / 60.0)
    if hemisphere == 'S' or hemisphere == 'W':
        return -1*float(coordinate)
    else:
        return float(coordinate)
    
prevpacket = None
with open(input_ts_file, "rb") as f:
    print ("timestamp","GPS active","NW hemisphere","EW hemisphere","lat","lon","speed","bearing",sep=';')
    while True:
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
            print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
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
            print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
        prevpacket = input_packet