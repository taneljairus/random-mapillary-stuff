import requests
import json

client_id = 'CLIENT_ID' #client id here
per_page = 1000 #do not go over 1000, pagination will fail
bbox = '58.13414,23.131211,58.25332,23.2411' #just random place
url_segmentations = "https://a.mapillary.com/v3/object_detections/segmentations"
url_images = "https://a.mapillary.com/v3/images"


#Just change the list however necessary, remove unwanted stuff, use wildcards and so on.
value_elems = """animal--bird
animal--ground-animal
construction--barrier--curb
construction--barrier--fence
construction--barrier--guard-rail
construction--barrier--other-barrier
construction--barrier--separator
construction--barrier--wall
construction--flat--bike-lane
construction--flat--crosswalk-plain
construction--flat--curb-cut
construction--flat--parking
construction--flat--pedestrian-area
construction--flat--rail-track
construction--flat--road-shoulder
construction--flat--road
construction--flat--service-lane
construction--flat--sidewalk
construction--flat--traffic-island
construction--structure--bridge
construction--structure--building
construction--structure--garage
construction--structure--tunnel
human--person
human--rider--bicyclist
human--rider--motorcyclist
human--rider--other-rider
marking--continuous--dashed
marking--continuous--solid
marking--discrete--crosswalk-zebra
marking--discrete--other-marking
marking--discrete--stop-line
marking--discrete--text
nature--beach
nature--desert
nature--mountain
nature--sand
nature--sky
nature--snow
nature--terrain
nature--vegetation
nature--water
object--banner
object--bench
object--bike-rack
object--billboard
object--catch-basin
object--cctv-camera
object--fire-hydrant
object--junction-box
object--mailbox
object--manhole
object--parking-meter
object--phone-booth
object--pothole
object--ramp
object--street-light
object--support--pole
object--support--traffic-sign-frame
object--support--utility-pole
object--traffic-cone
object--traffic-light--cyclists
object--traffic-light--general-horizontal-back
object--traffic-light--general-horizontal-front
object--traffic-light--general-horizontal-side
object--traffic-light--general-upright-back
object--traffic-light--general-upright-front
object--traffic-light--general-upright-side
object--traffic-light--other-traffic-light
object--traffic-light--pedestrians
object--traffic-light--temporary
object--traffic-sign--back
object--traffic-sign--direction-back
object--traffic-sign--direction-front
object--traffic-sign--front
object--traffic-sign--information-parking
object--traffic-sign--temporary-back
object--traffic-sign--temporary-front
object--trash-can
object--vehicle--bicycle
object--vehicle--boat
object--vehicle--bus
object--vehicle--car
object--vehicle--caravan
object--vehicle--motorcycle
object--vehicle--on-rails
object--vehicle--other-vehicle
object--vehicle--trailer
object--vehicle--truck
object--vehicle--wheeled-slow
object--water-valve
object--wire-group
void--car-mount
void--dynamic
void--ego-vehicle
void--ground
void--static""".split("\n")

output = {"type":"FeatureCollection","features":[]}


image_payload = {'client_id': client_id,'bbox':bbox, 'per_page':per_page}
image_keys = []
r = requests.get(url_images,params=image_payload)
data = r.json()
data_length = len(data['features'])
for f in data['features']:
    if f['properties']['key'] not in image_keys:
        image_keys.append(f['properties']['key'])
while data_length == per_page:
    link = r.links['next']['url'] 
    r = requests.get(link)
    data = r.json()
    for f in data['features']:
        if f['properties']['key'] not in image_keys:
            image_keys.append(f['properties']['key'])
    data_length = len(data['features'])
print ("Number of images in bbox: ", len(image_keys))
#Split for usability
n = 50
image_keys_split = [image_keys[i * n:(i + 1) * n] for i in range((len(image_keys) + n - 1) // n )]  

for image_keys in image_keys_split:
    for value_filter in value_elems:
        payload = {'client_id': client_id,'values':value_filter,'image_keys':' '.join([str(key) for key in image_keys]), 'per_page':per_page}
        r = requests.get(url_segmentations,params=payload)
        data = r.json()
        data_length = len(data['features'])
        for f in data['features']:
            output['features'].append(f)
        while data_length == per_page:
            link = r.links['next']['url'] 
            r = requests.get(link)
            data = r.json()
            for f in data['features']:
                output['features'].append(f)

print ("Number of segmentations", len(output['features']))
with open('segmentations.json', 'w') as outfile:
    json.dump(output, outfile)

