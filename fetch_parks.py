import json
import requests

def get_all_parks():
    while True:
        try:
            api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=OBJECTID%20%3E%3D%200%20AND%20OBJECTID%20%3C%3D%201000&outFields=NAME,ADDRESS,PARK_TYPE,DOG_DESIGNATION,LATITUDE,LONGITUDE,DOG_DESIGNATION_DETAILS,OBJECTID,PARK_ID,OPEN,ACCESSIBLE,WARD_NAME,WATERBODY_ACCESS,Shape_Area&returnGeometry=true&outSR=4326&f=json'
            response = json.loads(requests.get(api_call).content)
            parks_1 = response['features']
            api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=OBJECTID%20%3E%3D%201001%20AND%20OBJECTID%20%3C%3D%205000&outFields=NAME,ADDRESS,PARK_TYPE,DOG_DESIGNATION,LATITUDE,LONGITUDE,DOG_DESIGNATION_DETAILS,OBJECTID,PARK_ID,OPEN,ACCESSIBLE,WARD_NAME,WATERBODY_ACCESS,Shape_Area&returnGeometry=true&outSR=4326&f=json'
            response = json.loads(requests.get(api_call).content)
            parks_2 = response['features']
            parks = parks_1 + parks_2
            parks = [park for park in parks if park['attributes']['NAME']]  # filter out NoneType names
            for park in parks:
                park['attributes'].update({'directions': f"https://www.google.com/maps/dir/?api=1&destination={park['attributes']['LATITUDE']}%2C{park['attributes']['LONGITUDE']}"})
            all_park_names = {}
            for i in range(len(parks)):
                park_name = parks[i]['attributes']['NAME']
                if park_name in all_park_names:
                    all_park_names.update({park_name: all_park_names[park_name] + 1})
                    parks[i]['attributes']['NAME'] = park_name + ' #' + str(all_park_names[park_name])
                else:
                    all_park_names.update({park_name:1})
            return parks
        except requests.ConnectionError:
            sleep(1)

def get_all_pits():
    with open('ncc_pits.json', 'r') as f:
        ncc_pits = json.loads(f.read())
    with open('private_pits.json', 'r') as f:
        private_pits = json.loads(f.read())
    pits = ncc_pits + private_pits
    for pit in pits:  # swap lat and lng to conform with City of Ottawa JSON format
        pit['geometry'].update({'rings': [[[y,x] for x,y in pit['geometry']['rings'][0]]]})
    return pits

def get_all_enclosures():
    with open('enclosures.json', 'r') as f:
        enclosures = json.loads(f.read())
    return enclosures