#!/usr/bin/env python

from flask import Flask, render_template, url_for, request, redirect, session
from flask_session import Session
import json
import logging
import sys
import os
from time import sleep
import requests
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
from shapely.ops import cascaded_union
import folium
from folium.plugins import MarkerCluster, HeatMapWithTime, HeatMap, LocateControl


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

app = Flask(__name__, static_folder='static', static_url_path='')

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

@app.route('/come_back', methods=["POST", "GET"])
def come_back():
    return render_template('come_back.html')

@app.route('/offleash_response', methods=["POST", "GET"])
def offleash_response():
    lat = request.form.get('current_lat')
    lng = request.form.get('current_lng')
    lat = float(lat) if lat else None
    lng = float(lng) if lng else None
    if not lat:
        return redirect(url_for('index'))
    # # Apollo Crater - Designation: 0
    # lat = 45.476678
    # lng = -75.488533
    # # 6250 St Albans - Desgnation: 4 (Not even a park!)
    # lat = 45.474651
    # lng = -75.546493
    # # North Bilberry Valley - Designation: 0
    # lat = 45.47767229
    # lng = -75.53175637
    # # South Bilberry Valley - Designation: 0
    # lat = 45.461881
    # lng = -75.503509
    # # Riverside Memorial Park - Desgnation: 3
    # lat = 45.42453977
    # lng = -75.6657053
    # # Pony Park - Desgnation: 1
    # lat = 45.28512057
    # lng = -75.86566251
    # # Strathcona Park - Desgnation: 2 - no off-leash at all
    # lat = 45.42690936
    # lng = -75.67184788
    # # Britannia Park - Desgnation: 2
    # lat = 45.36227422
    # lng = -75.8006748
    # # Brewer Park - Desgnation: 2
    # lat = 45.38694591
    # lng = -75.6889477
    # # Big Bird Park - Desgnation: 2
    # lat = 45.48640872
    # lng = -75.50788845
    # # Jack Purcell Park - Desgnation: 2
    # lat = 45.41522433
    # lng = -75.68931824
    current_location = Point(lng, lat)
    api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=1%3D1&outFields=NAME,DOG_DESIGNATION,LONGITUDE,Shape,LATITUDE,Shape_Area,DOG_DESIGNATION_DETAILS&geometry={},{},{},{}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&returnCountOnly={}&outSR=4326&f=json'
    margin = 0.02
    count = 0
    while True:
        while True:
            try:
                response = json.loads(requests.get(api_call.format(lng-margin, lat+margin, lng+margin, lat-margin, 'true')).content)
                break
            except requests.ConnectionError:
                sleep(1)
        count = int(response['count'])
        if count >= 30 or margin > 0.14:
            break
        margin += 0.01
        print(f"result count only at {count} increasing margin to {margin}")
    while True:
        try:
            response = json.loads(requests.get(api_call.format(lng-margin, lat+margin, lng+margin, lat-margin, 'false')).content)
            break
        except requests.ConnectionError:
            sleep(1)
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
    designation = 4
    park_name = None
    details = None
    size = None
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
        designation = int(park['attributes']['DOG_DESIGNATION'])
        size = int(park['attributes']['Shape_Area'])
    return render_template('offleash_response.html', lat=lat, lng=lng, park_name=park_name, designation=designation, details=details, parks=near_parks, offleash_parks=offleash_parks, size=size)

@app.route('/get_mini_map', methods=["POST", "GET"])
def get_mini_map():
    name = request.args.get('name')
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    size = request.args.get('size')
    size = f"{round(float(size)*0.00024710538146717,1)} acres" if size else 'unknown size'  # convert to acres
    m = folium.Map(location=(lat, lng), zoom_start=14, min_zoom=11, width='100%', height='100%', disable_3D=False)
    popup=folium.map.Popup(html=f"""
            <style>
              root {{
                text-align: center;
                font-family: 'Noto Sans', sans-serif;
                font-size: 20%;
              }}
              h6 {{
                margin-bottom: -1em
              }}
            </style>
            <h6>{name}</h6>
            <p>
              {size}<br>
              {lat}, {lng}
            </p>
        """)
    m.add_child(folium.Marker(
        [lat, lng],
        popup=popup,
        icon=folium.Icon(prefix='fa', icon='circle', color='lightgray')
    ))
    #, width='70vw', height='60vh', max_width='250', max_height='200'
    LocateControl().add_to(m)
    return m.get_root().render()

if __name__ == "__main__":
	app.run(debug=False)
