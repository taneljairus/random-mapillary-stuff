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
import io
import re
from pymp4.parser import Box

parser = argparse.ArgumentParser()
parser.add_argument('--input', required = True, type=str) #input file or folder
parser.add_argument('--sampling_interval', default = '0.5', type=float) #distance between images in seconds.
parser.add_argument('--folder', default = 'output', type=str) #output folder, will be created if not exists
parser.add_argument('--timeshift', default = '0', type=float) #time shift in seconds, if the gps and video seem out of sync
parser.add_argument('--timezone', default = '0', type=float) #timezone difference in hours. Depends on video source, some provide GMT, others local
parser.add_argument('--min_speed', default = '-1', type=float) #minimum speed in m/s to filter out stops
parser.add_argument('--bearing_modifier', default = '0', type=float) #180 if rear camera
parser.add_argument('--min_coverage', default = '90', type=int) #percentage - how much video must have GPS data in order to interpolate missing
parser.add_argument('--min_points', default = '5', type=int) #how many points to allow video extraction
parser.add_argument('--metric_distance', default = '0', type=int) #distance between images, overrides sampling_interval. 
parser.add_argument('--csv', default = '0', type=int) #create csv from coordinates before and after interpolation.
parser.add_argument('--suppress_cv2_warnings', default = '1', type=int) #If disabled, will show lot of harmless warnings in console. Known to cause issues on Windows.
parser.add_argument('--device_override', default = '', type=str) #force treatment as specific device, B for B4k, V for Viofo
parser.add_argument('--mask', type=str) #masking image, must be same dimensionally as video
parser.add_argument('--crop_left', default = '0', type=int) #number of pixels to crop from left
parser.add_argument('--crop_right', default = '0', type=int) #number of pixels to crop from right
parser.add_argument('--crop_top', default = '0', type=int) #number of pixels to crop from top
parser.add_argument('--crop_bottom', default = '0', type=int) #number of pixels to crop from bottom
args = parser.parse_args()
print(args)
input_ts_file = args.input
folder = args.folder
timeshift = args.timeshift

if args.mask:
    mask = cv2.imread(args.mask,0)
# Define a context manager to suppress stdout and stderr.
class suppress_stdout_stderr(object): #from here: https://stackoverflow.com/questions/11130156/suppress-stdout-stderr-print-from-python-functions
    '''
    A context manager for doing a "deep suppression" of stdout and stderr in 
    Python, i.e. will suppress all print, even if the print originates in a 
    compiled C/Fortran sub-function.
       This will not suppress raised exceptions, since exceptions are printed
    to stderr just before a script exits, and after the context manager has
    exited (at least, I think that is why it lets exceptions through).      

    '''
    def __init__(self):
        # Open a pair of null files
        self.null_fds =  [os.open(os.devnull,os.O_RDWR) for x in range(2)]
        # Save the actual stdout (1) and stderr (2) file descriptors.
        self.save_fds = [os.dup(1), os.dup(2)]

    def __enter__(self):
        # Assign the null pointers to stdout and stderr.
        os.dup2(self.null_fds[0],1)
        os.dup2(self.null_fds[1],2)

    def __exit__(self, *_):
        # Re-assign the real stdout/stderr back to (1) and (2)
        os.dup2(self.save_fds[0],1)
        os.dup2(self.save_fds[1],2)
        # Close all file descriptors
        for fd in self.null_fds + self.save_fds:
            os.close(fd)

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


def lonlat_metric(xlon, xlat):
    mx = xlon * (2 * math.pi * 6378137 / 2.0) / 180.0
    my = math.log( math.tan((90 + xlat) * math.pi / 360.0 )) / (math.pi / 180.0)

    my = my * (2 * math.pi * 6378137 / 2.0) / 180.0
    return mx, my

def metric_lonlat(xmx, ymy):

    xlon = xmx / (2 * math.pi * 6378137 / 2.0) * 180.0
    xlat = ymy / (2 * math.pi * 6378137 / 2.0) * 180.0

    xlat = 180 / math.pi * (2 * math.atan( math.exp( lat * math.pi / 180.0)) - math.pi / 2.0)
    return xlon, xlat

def detect_file_type(input_file):
    device = "X"
    make = "unknown"
    model = "unknown"
    if input_file.lower().endswith(".ts"):
        with open(input_file, "rb") as f:
            device = "A"
            input_packet = f.read(188) #First packet, try to autodetect
            if bytes("\xB0\x0D\x30\x34\xC3", encoding="raw_unicode_escape") in input_packet[4:20] or args.device_override == "V":
                device = "V"
                make = "Viofo"
                model = "A119 V3"
                
            if bytes("\x40\x1F\x4E\x54\x39", encoding="raw_unicode_escape") in input_packet[4:20] or args.device_override == "B":
                device = "B"
                make = "Blueskysea"
                model = "B4K"
               
            while device == "A":
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
                        break
                    
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
                        break
    if input_file.lower().endswith(".mp4"): #Guess which MP4 method is used: Novatek, Subtitle, NMEA
        device = "N"
        make = "Novatek"
        model = "unknown"
        with open(input_file, "rb") as fx:
            if True:
                fx.seek(0, io.SEEK_END)
                eof = fx.tell()
                fx.seek(0)
                lines = []
                while fx.tell() < eof:
                    try:
                        box = Box.parse_stream(fx)
                    except:
                        pass
                    #print (box.type.decode("utf-8"))
                    if box.type.decode("utf-8") == "free":
                        length = len(box.data)
                        offset = 0
                        while offset < length:
                            inp = Box.parse(box.data[offset:])
                            #print (inp.type.decode("utf-8"))
                            if inp.type.decode("utf-8") == "gps": #NMEA-based
                                lines = inp.data
                                for line in lines.splitlines():
                                    m = str(line).lstrip("[]0123456789")
                                    if "$GPGGA" in m:
                                        device = "N"
                                        make = "NMEA-based video"
                                        model = "unknown"
                                        break
                            offset += inp.end
                    if box.type.decode("utf-8") == "moov": #has Novatek-specific stuff
                        fx.seek(0)
                        largeelem = fx.read()
                        startbytes = [m.start() for m in re.finditer(b'freeGPS', largeelem)]
                        del largeelem
                        if len(startbytes)>0:
                            make = "Novatek"
                            model = "MP4"
                            device = "T"
                            break
                    if box.type.decode("utf-8") == "moov":
                        try:
                            length = len(box.data)
                        except:
                            length = 0
                        offset = 0
                        while offset < length:
                            inp = Box.parse(box.data[offset:])
                            #print (inp.type.decode("utf-8"))
                            if inp.type.decode("utf-8") == "gps": #NMEA-based
                                lines = inp.data
                                print (len(inp.data))
                                for line in lines.splitlines():
                                    m = str(line).lstrip("[]0123456789")
                                    if "$GPGGA" in m:
                                        device = "N"
                                        make = "NMEA-based video"
                                        model = "unknown"
                                        #break
                            offset += inp.end
            else:
                pass
    return device,make,model
    
def get_gps_data_nt (input_ts_file, device):
    packetno = 0
    locdata = {}
    with open(input_ts_file, "rb") as f:
        largeelem = f.read()
        startbytes = [m.start() for m in re.finditer(b'freeGPS', largeelem)]
        for startbyte in startbytes:
            currentdata = {}
            input_packet = largeelem[startbyte+2:startbyte+188]
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
            currentdata["speed"] = speed
            currentdata["mx"],currentdata["my"] = lonlat_metric(lon,lat)
            currentdata["metric"] = 0
            currentdata["prevdist"] = 0
            if active == "A":
                locdata[packetno] = currentdata
            packetno += 1
            #print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
        
            del currentdata
    del largeelem
    return locdata
        
    
def get_gps_data_ts (input_ts_file, device):
    packetno = 0
    locdata = {}
    prevpacket = None
    with open(input_ts_file, "rb") as f:
        input_packet = f.read(188) #First packet, try to autodetect

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
                currentdata["bearing"] = bearing
                currentdata["speed"] = speed
                currentdata["mx"],currentdata["my"] = lonlat_metric(lon,lat)
                currentdata["metric"] = 0
                currentdata["prevdist"] = 0
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
                currentdata["speed"] = speed
                currentdata["mx"],currentdata["my"] = lonlat_metric(lon,lat)
                currentdata["metric"] = 0
                currentdata["prevdist"] = 0
                if active == "A":
                    locdata[packetno] = currentdata
                packetno += 1
                #print ('20{0:02}-{1:02}-{2:02} {3:02}:{4:02}:{5:02}'.format(year,month,day,hour,minute,second),active,lathem,lonhem,lat,lon,speed,bearing, sep=';')
            prevpacket = input_packet
            del currentdata
    return locdata

try:
    os.mkdir(folder)
except:
    pass

if os.path.isfile(input_ts_file):
    inputfiles = [input_ts_file]
if os.path.isdir(input_ts_file):
    inputfiles = glob.glob(input_ts_file + os.path.sep + '*.ts')
    inputfiles.extend(glob.glob(input_ts_file + os.path.sep + '*.mp4'))
   
   
for input_ts_file in inputfiles:
    
    print (input_ts_file)
    device,make,model = detect_file_type(input_ts_file)
    print (make,model)

    video = cv2.VideoCapture(input_ts_file)
    fps = video.get(cv2.CAP_PROP_FPS)
    length = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    print ("FPS : {0}; LEN: {1}".format(fps,length))
    
    interval = int(args.sampling_interval*fps)
    if interval == 0:
        interval = 1
    locdata = {}
    if device in "BV":
        locdata = get_gps_data_ts(input_ts_file, device)
    if device in "T":
        locdata = get_gps_data_nt(input_ts_file, device)
    if device in "M":
        locdata = get_gps_data_mp4(input_ts_file, device)


    print ("GPS data analysis ended, no of points ", len(locdata))
    
    ###Logging
    if args.csv == 1:
        with open(input_ts_file.split(os.path.sep)[-1].replace(".ts","_")+"pre_interp.csv", "w") as xf:
            print ("i;lat;lon;ts;speed;bearing", file=xf)
            for i in locdata:
                print (i,locdata[i]["lat"],locdata[i]["lon"],locdata[i]["speed"],locdata[i]["bearing"], sep=";", file=xf)
    
    ###
    
    if len(locdata)<args.min_coverage*length*0.01/fps:
        print ("Not enough GPS data for interpolation",args.min_coverage,"% needed, ",len(locdata)*100/length*fps,"% found")
    else:
        if len(locdata)<length/fps:
            print ("Interpolating missing points")
            i = 0
            while i < length/fps:
                if i not in locdata:
                    #Find previous existing
                    prev_data = i - 1
                    next_data = i + 1
                    while prev_data not in locdata and prev_data>0:
                        prev_data -= 1
                 
                    #Find next existing
                    while next_data not in locdata and next_data<length/fps:
                        next_data += 1
                    if prev_data in locdata and next_data in locdata:
                        currentdata = {}

                        current_position = float(i-prev_data)/float(next_data-prev_data)
                        currentdata["ts"] = locdata[prev_data]["ts"]+(locdata[(next_data)]["ts"]-locdata[prev_data]["ts"])*current_position
                        currentdata["lat"] = locdata[prev_data]["lat"]+(locdata[(next_data)]["lat"]-locdata[prev_data]["lat"])*current_position
                        currentdata["lon"] = locdata[prev_data]["lon"]+(locdata[(next_data)]["lon"]-locdata[prev_data]["lon"])*current_position
                        currentdata["mx"] = locdata[prev_data]["mx"]+(locdata[(next_data)]["mx"]-locdata[prev_data]["mx"])*current_position
                        currentdata["my"] = locdata[prev_data]["my"]+(locdata[(next_data)]["my"]-locdata[prev_data]["my"])*current_position
                        currentdata["bearing"] = locdata[prev_data]["bearing"]+(locdata[(next_data)]["bearing"]-locdata[prev_data]["bearing"])*current_position
                        currentdata["speed"] = locdata[prev_data]["speed"]+(locdata[(next_data)]["speed"]-locdata[prev_data]["speed"])*current_position
                        currentdata["metric"] = 0
                        currentdata["prevdist"] = 0
                        locdata[i] = currentdata
                        del currentdata
                i=i+1
        i=0
        while not i in locdata:
            i+=1  #extrapolate down
        
        while i > -5:
            if not i in locdata:
                currentdata = {}
                
                currentdata["ts"] = locdata[i+1]["ts"]-(locdata[(i+2)]["ts"]-locdata[i+1]["ts"])
                currentdata["lat"] = locdata[i+1]["lat"]-(locdata[(i+2)]["lat"]-locdata[i+1]["lat"])
                currentdata["lon"] = locdata[i+1]["lon"]-(locdata[(i+2)]["lon"]-locdata[i+1]["lon"])
                currentdata["mx"] = locdata[i+1]["mx"]-(locdata[(i+2)]["mx"]-locdata[i+1]["mx"])
                currentdata["my"] = locdata[i+1]["my"]-(locdata[(i+2)]["my"]-locdata[i+1]["my"])
                currentdata["bearing"] = locdata[i+1]["bearing"]-(locdata[(i+2)]["bearing"]-locdata[i+1]["bearing"])
                currentdata["speed"] = locdata[i+1]["speed"]-(locdata[(i+2)]["speed"]-locdata[i+1]["speed"])
                currentdata["metric"] = 0
                currentdata["prevdist"] = 0
                locdata[i] = currentdata
                del currentdata
            i-=1
        i=0
        while i in locdata:
            i+=1
        while i < length / fps * 1.1:
            if not i in locdata:
                currentdata = {}
                
                currentdata["ts"] = locdata[i-1]["ts"]-(locdata[(i-2)]["ts"]-locdata[i-1]["ts"])
                currentdata["lat"] = locdata[i-1]["lat"]-(locdata[(i-2)]["lat"]-locdata[i-1]["lat"])
                currentdata["lon"] = locdata[i-1]["lon"]-(locdata[(i-2)]["lon"]-locdata[i-1]["lon"])
                currentdata["mx"] = locdata[i-1]["mx"]-(locdata[(i-2)]["mx"]-locdata[i-1]["mx"])
                currentdata["my"] = locdata[i-1]["my"]-(locdata[(i-2)]["my"]-locdata[i-1]["my"])
                currentdata["bearing"] = locdata[i-1]["bearing"]-(locdata[(i-2)]["bearing"]-locdata[i-1]["bearing"])
                currentdata["speed"] = locdata[i-1]["speed"]-(locdata[(i-2)]["speed"]-locdata[i-1]["speed"])
                currentdata["metric"] = 0
                currentdata["prevdist"] = 0
                locdata[i] = currentdata
                del currentdata
            i+=1
    i=1
    while i in locdata:
        locdata[i]["prevdist"] = math.cos(math.radians(locdata[i]["lat"])) * math.sqrt(pow(locdata[i-1]["mx"]-locdata[i]["mx"],2)+pow(locdata[i-1]["my"]-locdata[i]["my"],2))
        locdata[i]["metric"] = locdata[i-1]["metric"] + locdata[i]["prevdist"]
        i += 1

    ###Logging
    if args.csv == 1:
        with open(input_ts_file.split(os.path.sep)[-1].replace(".ts","_")+"post_interp.csv", "w") as xf:
            print ("no;lat;lon;ts;speed;bearing", file=xf)
            for i in locdata:
                print (i,locdata[i]["lat"],locdata[i]["lon"],locdata[i]["speed"],locdata[i]["bearing"], sep=";", file=xf)
    
    ###     

    if len(locdata)<args.min_points:
        print ("Not enough GPS data for frame extraction.")
    else:
        print ("Video extraction started")
        framecount = 0
        errormessage = 0
        count = 0
        meters = 0
        success,image = video.read()
        while success:

            if True:
                #interpolate time and coordinates
                prev_dataframe = (float(math.trunc(float(framecount+timeshift*fps)/fps)))
                while prev_dataframe+1 not in locdata and prev_dataframe >= length/fps - 2:
                    prev_dataframe -= 1
                if prev_dataframe in locdata and prev_dataframe + 1 in locdata:
                    current_position = (framecount + timeshift*fps - prev_dataframe*fps)/fps 
                    new_speed = locdata[prev_dataframe]["speed"]+(locdata[(prev_dataframe+1)]["speed"]-locdata[prev_dataframe]["speed"])*current_position
                    if new_speed >= args.min_speed or args.metric_distance > 0:
                        meter = locdata[prev_dataframe]["metric"]+(locdata[(prev_dataframe+1)]["metric"]-locdata[prev_dataframe]["metric"])*current_position
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
                        if args.mask:
                            image = cv2.bitwise_and(image,image,mask = mask)
                        if args.crop_top + args.crop_bottom + args.crop_left + args.crop_right > 0:
                            height, width, channels = image.shape
                            image = image[args.crop_top : height - args.crop_bottom,args.crop_left : width - args.crop_right]
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
                        datetime_taken = datetime.fromtimestamp(new_ts+args.timezone*3600)
                        e_image.datetime_original = datetime_taken.strftime(DATETIME_STR_FORMAT)
                        
                        with open(folder+os.path.sep+input_ts_file.split(os.path.sep)[-1].replace(".ts","_") + "_"+"%06d" % count + ".jpg", 'wb') as new_image_file:
                            new_image_file.write(e_image.get_file())
                        #print('Frame: ', framecount)
                        count += 1
                else:
                    if errormessage == 0:
                        print ("No valid GPS for frame %d, this frame and others will be skipped." % framecount)
                        errormessage = 1

            if args.metric_distance > 0:
                meters = meters + args.metric_distance
                i = 1
                while i in locdata and not (meters >= locdata[i-1]["metric"] and meters<=locdata[i]["metric"]):
                    i+=1
                if i in locdata and meters >= locdata[i-1]["metric"] and meters<=locdata[i]["metric"]:
                    try:
                        framecount = int(i*fps + fps * float(meters-locdata[i]["metric"])/float(locdata[i]["prevdist"]))
                    except:
                        framecount = int(i*fps)
                else:
                    framecount = length + 1
                
            else:
                framecount += int(fps*args.sampling_interval)
            #print('Frame: ', framecount)
            if args.suppress_cv2_warnings == 1:
                with suppress_stdout_stderr(): #Just to keep the console clear from OpenCV warning messages
                    video.set(1,framecount)
                success,image = video.read()
            else:
                video.set(1,framecount)
                success,image = video.read()
        video.release()
        try:
            os.unlink("tmp.jpg")
            print (input_ts_file, " processed, ", count, " images extracted")
        except:
            pass
        
