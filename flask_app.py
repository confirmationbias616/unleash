#!/usr/bin/env python

from flask import Flask, render_template, url_for, request, redirect, session
from flask_session import Session
import json
import logging
import sys
import os
import requests
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
from shapely.ops import cascaded_union


logger = logging.getLogger(__name__)
log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(funcName)s "
        "- line %(lineno)d"
    )
)
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

app = Flask(__name__)

#set up Flask-Sessions
app.config.from_object(__name__)
app.config['SESSION_TYPE'] = 'filesystem'

# trick from SO for properly relaoding CSS
app.config['TEMPLATES_AUTO_RELOAD'] = True

# this function works in conjunction with `dated_url_for` to make sure the browser uses
# the latest version of css stylesheet when modified and reloaded during testing
@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **values):
    if endpoint == "static":
        filename = values.get("filename", None)
        if filename:
            file_path = os.path.join(app.root_path, endpoint, filename)
            values["q"] = int(os.stat(file_path).st_mtime)
    return url_for(endpoint, **values)

@app.route('/', methods=["POST", "GET"])
def index():
    return redirect(url_for('offleash'))

@app.route('/offleash', methods=["POST", "GET"])
def offleash():
    return render_template('offleash.html')

@app.route('/offleash_response', methods=["POST", "GET"])
def offleash_response():
    lat = request.form.get('current_lat')
    lng = request.form.get('current_lng')
    lat = float(lat) if lat else None
    lng = float(lng) if lng else None
    print(lat)
    if not lat:
        return redirect(url_for('index'))
    # lat = 45.450648
    # lng = -75.492437
    # lat = 45.476678
    # lng = -75.488533
    # lat = 45.445807
    # lng = -75.485049
    # lat = 45.474651
    # lng = -75.546493
    # lat = 45.4152054
    # lng = -75.7292795
    # North Bilberry Valley
    lat = 45.47767229
    lng = -75.53175637
    # North Bilberry Valley
    lat = 45.461881
    lng = -75.503509
    current_location = Point(lng, lat)
    api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=1%3D1&outFields=NAME,DOG_DESIGNATION,LONGITUDE,Shape,LATITUDE,Shape_Area,DOG_DESIGNATION_DETAILS&geometry={},{},{},{}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&returnCountOnly={}&outSR=4326&f=json'
    margin = 0.02
    count = 0
    while True:
        response = json.loads(requests.get(api_call.format(lng-margin, lat+margin, lng+margin, lat-margin, 'true')).content)
        count = int(response['count'])
        if count >= 60:
            break
        margin += 0.01
        print(f"result count only at {count} increasing margin to {margin}")
    response = json.loads(requests.get(api_call.format(lng-margin, lat+margin, lng+margin, lat-margin, 'false')).content)
    parks = response['features']
    all_park_names = {}
    for i in range(len(parks)):
        park_name = parks[i]['attributes']['NAME']
        if park_name in all_park_names:
            all_park_names.update({park_name: all_park_names[park_name] + 1})
            parks[i]['attributes']['NAME'] = park_name + ' #' + str(all_park_names[park_name])
        else:
            all_park_names.update({park_name:1})
            # parks[i]['attributes']['NAME'] = park_name + ' #1'
    def distance_to_edge(park):
        radius = park['attributes']['Shape_Area']**0.5
        distance = (((park['attributes']['LATITUDE']-lat)**2 + (park['attributes']['LONGITUDE']-lng)**2)**0.5)*100000
        return distance - radius
    parks.sort(key=lambda park: distance_to_edge(park))
    parks = parks[:30]
    for park in parks:
        park['attributes'].update({'directions': f"https://www.google.com/maps/dir/{lat},{lng}/{park['attributes']['LATITUDE']},{park['attributes']['LONGITUDE']}/@{lat},{lng}"})
    offleash_parks = [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '0']
    near_parks = [park for park in parks if park['attributes']['NAME'] not in [park['attributes']['NAME'] for park in offleash_parks]]
    near_parks = near_parks[:10]
    permission = False
    park_name = None
    details = None
    for park in near_parks + offleash_parks:
        if len(park['geometry']['rings']) > 1:
            polygons = []
            for shape in park['geometry']['rings']:
                polygons.append(Polygon(shape))
            response_poly = cascaded_union(polygons)
        else:
            response_poly = Polygon(park['geometry']['rings'][0])
        in_park = response_poly.contains(current_location)
        if not in_park:
            print(f"not in {park['attributes']['NAME']}")
            continue
        print(f"You're in {park['attributes']['NAME']}")
        park_name = park['attributes']['NAME']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        is_off_leash = True if int(park['attributes']['DOG_DESIGNATION']) < 1 else False
        if is_off_leash:
            print("It's an offleash park!")
            permission = True
        else:
            print("Unfortunately, it's not an offleash park!")
        break
    return render_template('offleash_response.html', lat=lat, lng=lng, park_name=park_name, permission=permission, details=details, parks=near_parks, offleash_parks=offleash_parks)

if __name__ == "__main__":
	app.run(debug=False)
