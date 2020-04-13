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

Session(app)

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
    lat = float(request.form.get('current_lat'))
    lng = float(request.form.get('current_lng'))
    current_location = Point(lng, lat)
    margin = 0.005
    api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=1%3D1&outFields=NAME,DOG_DESIGNATION,LONGITUDE,Shape,LATITUDE,Shape_Area,DOG_DESIGNATION_DETAILS&geometry={},{},{},{}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outSR=4326&f=json'
    response = json.loads(requests.get(api_call.format(lng-margin, lat+margin, lng+margin, lat-margin)).content)
    parks = response['features']
    permission = False
    park_name = None
    details = None
    for park in parks:
        response_poly = Polygon(park['geometry']['rings'][0])
        in_park = response_poly.contains(current_location)
        if not in_park:
            print(f"not in {park['attributes']['NAME']}")
            continue
        print(f"You're in {park['attributes']['NAME']}")
        park_name = park['attribute']['NAME']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        is_off_leash = True if int(response['features'][0]['attributes']['DOG_DESIGNATION']) <= 1 else False
        if is_off_leash:
            print("It's an offleash park!")
            permission = True
        else:
            print("Unfortunately, it's not an offleash park!")
        break
    return render_template('offleash_response.html', lat=lat, lng=lng, park_name=park_name, permission=permission, details=details)

if __name__ == "__main__":
	app.run(debug=True)
    # app.run(debug=False)