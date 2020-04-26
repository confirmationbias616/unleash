#!/usr/bin/env python

from flask import Flask, render_template, url_for, request, redirect, session
from flask_session import Session
from jinja2.exceptions import TemplateNotFound
import json
import re
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

def get_all_parks():
    api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=OBJECTID%20%3E%3D%200%20AND%20OBJECTID%20%3C%3D%201000&outFields=NAME,ADDRESS,PARK_TYPE,DOG_DESIGNATION,LATITUDE,LONGITUDE,DOG_DESIGNATION_DETAILS,OBJECTID,PARK_ID,OPEN,ACCESSIBLE,WARD_NAME,WATERBODY_ACCESS,Shape_Area&returnGeometry=true&outSR=4326&f=json'
    response = json.loads(requests.get(api_call).content)
    parks_1 = response['features']
    api_call = 'https://maps.ottawa.ca/arcgis/rest/services/Parks_Inventory/MapServer/24/query?where=OBJECTID%20%3E%3D%201001%20AND%20OBJECTID%20%3C%3D%205000&outFields=NAME,ADDRESS,PARK_TYPE,DOG_DESIGNATION,LATITUDE,LONGITUDE,DOG_DESIGNATION_DETAILS,OBJECTID,PARK_ID,OPEN,ACCESSIBLE,WARD_NAME,WATERBODY_ACCESS,Shape_Area&returnGeometry=true&outSR=4326&f=json'
    response = json.loads(requests.get(api_call).content)
    parks_2 = response['features']
    parks = parks_1 + parks_2
    return parks

@app.route('/', methods=["POST", "GET"])
def index():
    return render_template('index.html')

@app.route('/about', methods=["POST", "GET"])
def about():
    return render_template('about.html')

@app.route('/offleash', methods=["POST", "GET"])
def offleash():
    skip = request.args.get('skip', 'False')
    return render_template('offleash.html', skip=skip)

@app.route('/come_back', methods=["POST", "GET"])
def come_back():
    return render_template('come_back.html')

@app.route('/offleash_response', methods=["POST", "GET"])
def offleash_response():
    skip = request.args.get('skip', 'False')
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
        park['attributes'].update({'directions': f"https://www.google.com/maps/dir/?api=1&destination={park['attributes']['LATITUDE']}%2C{park['attributes']['LONGITUDE']}"})
    offleash_parks = [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '0']
    near_parks = [park for park in parks if park['attributes']['NAME'] not in [park['attributes']['NAME'] for park in offleash_parks]]
    near_parks = [park for park in near_parks if park['attributes']['DOG_DESIGNATION'] != '3']
    near_parks = near_parks[:10]
    designation = 4  #default of 'undesignated'
    park_name = None
    park_lat = None
    park_lng = None
    details = None
    size = None
    for park in parks:
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
        park_lat = park['attributes']['LATITUDE']
        park_lng = park['attributes']['LONGITUDE']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        designation = int(park['attributes']['DOG_DESIGNATION'])
        size = int(park['attributes']['Shape_Area'])
    return render_template('offleash_response.html', skip=skip, lat=lat, lng=lng, park_name=park_name, park_lat=park_lat, park_lng=park_lng, designation=designation, details=details, parks=near_parks, offleash_parks=offleash_parks, size=size)

@app.route('/get_mini_map', methods=["POST", "GET"])
def get_mini_map():
    name = request.args.get('name')
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    size = request.args.get('size')
    if size:
        size_in_acres = round(float(size)*0.00024710538146717,1)
        size_text= f"{size_in_acres} acres"
        zoom_start = int(15 + 10 / size_in_acres)
    else:
        size_text = 'unknown size'
        zoom_start = 14
    m = folium.Map(location=(lat, lng), zoom_start=zoom_start, min_zoom=12, width='100%', height='100%', disable_3D=False)
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
              {size_text}<br>
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

@app.route('/get_mini_map_2', methods=["POST", "GET"])
def get_mini_map_2():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    size = request.args.get('size')
    designation = int(request.args.get('designation'))
    designation = 1 if designation == 4 else designation
    if size:
        size_in_acres = round(float(size)*0.00024710538146717,1)
        size_text= f"{size_in_acres} acres"
        zoom_start = int(15 + 10 / size_in_acres)
    else:
        size_text = 'unknown size'
        zoom_start = 14
    zoom_start -= 2
    with open('templates/full_map.html', 'r+') as f:
        reloc_map = f.read()
    reloc_map = reloc_map.replace(
        'center: [45.4166666, -75.6944444]',
        f'center: [{lat}, {lng}]'
    )
    reloc_map = reloc_map.replace(
        'zoom: 12',
        f'zoom: {zoom_start}'
    )
    group_ids = {x[0]:x[1] for x in zip([0,1,2,3], re.findall("""\".*\" : feature_group_(.*),""", reloc_map))}
    reloc_map = reloc_map.replace(f"feature_group_{group_ids[designation]}.remove();", f"feature_group_{group_ids[0]}.remove();")
    try:
        return reloc_map
    except TemplateNotFound:
        pass

@app.route('/get_mini_map_3', methods=["POST", "GET"])
def get_mini_map_3():
    focus = request.args.get('focus', None)
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    size = request.args.get('size')
    designation = str(request.args.get('designation'))
    if size:
        size_in_acres = round(float(size)*0.00024710538146717,1)
        size_text= f"{size_in_acres} acres"
        zoom_start = int(14 + 10 / size_in_acres)
    else:
        size_text = 'unknown size'
        zoom_start = 14

    logger.info('done loading...')
    while True:
        try:
            parks = get_all_parks()
            break
        except requests.ConnectionError:
            sleep(1)
    parks = [park for park in parks if park['attributes']['NAME'] == focus]
    fill_opacity = 0.08
    line_weight = 3
    m = folium.Map(tile=None, name='', location=(lat, lng), zoom_start=zoom_start, width='100%', height='100%', disable_3D=False)
    #folium.TileLayer('openstreetmap', control=False, overlay=False, name='').add_to(m)
    feature_group = folium.FeatureGroup(name="off leash", overlay=False, show=True, control=False)
    color_map = {'0':'green', '1':'black', '2':'purple', '3':'red', '4':'black'}
    layer_color = color_map[designation]
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == designation]:
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            ring for ring in park['geometry']['rings']
                        ]
                    },
                },
            ]
        }
        folium.features.Choropleth(
            geo_data=geojson,
            highlight=True,
            line_color=layer_color,
            fill_color=layer_color,
            fill_opacity = fill_opacity,
            line_weight=line_weight
        ).add_to(feature_group)
    feature_group.add_to(m)
    # folium.LayerControl(collapsed=True).add_to(m)
    # LocateControl().add_to(m)
    return m.get_root().render()

@app.route('/get_full_map', methods=["POST", "GET"])
def get_full_map():
    while True:
        try:
            parks = get_all_parks()
            break
        except requests.ConnectionError:
            sleep(1)
    all_park_names = {}
    for i in range(len(parks)):
        park_name = parks[i]['attributes']['NAME']
        if park_name in all_park_names:
            all_park_names.update({park_name: all_park_names[park_name] + 1})
            parks[i]['attributes']['NAME'] = park_name + ' #' + str(all_park_names[park_name])
        else:
            all_park_names.update({park_name:1})
    
    fill_opacity = 0.08
    line_weight = 3
    popup_html = """
        <style>
        root {{
            text-align: center;
            font-family: 'Noto Sans', sans-serif;
            font-size: 20%;
        }}
        h6 {{
            font-size:110%;
        }}
        </style>
        <h6 align='center'>{}</h6>
        <div align='center'>
            <button onclick="window.open('{}', '_blank', 'noopener')" style='font-weight: bold;'>directions</button>
            <br><br>
            <table align='center' style="width:100%">
                <tr>
                    <th><b>park area</b></th>
                    <td>{}</td>
                </tr>
                <tr>
                    <th><b>latitude</b></th>
                    <td>{}</td>
                </tr>
                <tr>
                    <th><b>longitude</b></th>
                    <td>{}</td>
                </tr>
            </table>
        </div>
        <br>
        <details open>
            <summary><b>details</b></summary>
            <i>{}</i>
        </details>
    """

    m = folium.Map(tile=None, name='', location=(45.4166666, -75.6944444), zoom_start=12, width='100%', height='100%', disable_3D=False)
    folium.TileLayer('openstreetmap', control=False, overlay=False, name='').add_to(m)

    feature_group = folium.FeatureGroup(name="off leash", overlay=True, show=True)
    layer_color = 'green'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '0']:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lng}"
        if size:
            size_in_acres = round(float(size)*0.00024710538146717,1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, size_text, lat, lng, details), max_width='220', max_height='200')
        folium.Marker(
            [lat, lng],
            popup=popup,
            icon=folium.Icon(prefix='fa', icon='circle', color=layer_color)
        ).add_to(feature_group)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            ring for ring in park['geometry']['rings']
                        ]
                    },
                },
            ]
        }
        folium.features.Choropleth(
            geo_data=geojson,
            highlight=True,
            line_color=layer_color,
            fill_color=layer_color,
            fill_opacity = fill_opacity,
            line_weight=line_weight
        ).add_to(feature_group)
    feature_group.add_to(m)

    feature_group = folium.FeatureGroup(name="on leash", overlay=True, show=False)
    layer_color = 'black'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] in ['1', '4']]:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lng}"
        if size:
            size_in_acres = round(float(size)*0.00024710538146717,1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, size_text, lat, lng, details), max_width='220', max_height='200')
        folium.Marker(
            [lat, lng],
            popup=popup,
            icon=folium.Icon(prefix='fa', icon='circle', color=layer_color)
        ).add_to(feature_group)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            ring for ring in park['geometry']['rings']
                        ]
                    },
                },
            ]
        }
        folium.features.Choropleth(
            geo_data=geojson,
            highlight=True,
            line_color=layer_color,
            fill_color=layer_color,
            fill_opacity=fill_opacity,
            line_weight=line_weight
        ).add_to(feature_group)
    feature_group.add_to(m)

    feature_group = folium.FeatureGroup(name="mixed designation", overlay=True, show=False)
    layer_color = 'purple'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '2']:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lng}"
        if size:
            size_in_acres = round(float(size)*0.00024710538146717,1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, size_text, lat, lng, details), max_width='220', max_height='200')
        folium.Marker(
            [lat, lng],
            popup=popup,
            icon=folium.Icon(prefix='fa', icon='circle', color=layer_color)
        ).add_to(feature_group)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            ring for ring in park['geometry']['rings']
                        ]
                    },
                },
            ]
        }
        folium.features.Choropleth(
            geo_data=geojson,
            highlight=True,
            line_color=layer_color,
            fill_color=layer_color,
            fill_opacity=fill_opacity,
            line_weight=line_weight
        ).add_to(feature_group)
    feature_group.add_to(m)
    
    feature_group = folium.FeatureGroup(name="no dogs allowed", overlay=True, show=False)
    layer_color = 'red'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '3']:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lng}"
        if size:
            size_in_acres = round(float(size)*0.00024710538146717,1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, size_text, lat, lng, details), max_width='220', max_height='200')
        folium.Marker(
            [lat, lng],
            popup=popup,
            icon=folium.Icon(prefix='fa', icon='circle', color=layer_color)
        ).add_to(feature_group)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            ring for ring in park['geometry']['rings']
                        ]
                    },
                },
            ]
        }
        folium.features.Choropleth(
            geo_data=geojson,
            highlight=False,
            line_color=layer_color,
            fill_color=layer_color,
            fill_opacity = 0.5,  #overwrite
            line_weight=line_weight
        ).add_to(feature_group)
    feature_group.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    LocateControl().add_to(m)
    logger.info('ok, map is ready')
    m.save('templates/full_map.html')
    return m.get_root().render()

@app.route('/map', methods=["POST", "GET"])
def map():
    return render_template('map.html')

if __name__ == "__main__":
	app.run(debug=False)
