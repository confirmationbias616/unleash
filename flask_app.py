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
from fetch_parks import get_all_parks, get_all_enclosures, get_all_pits
from get_nh_scores import get_isochrones


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

try:
    with open(".secret.json") as f:
        api_key = json.load(f)["geo_api_key"]
except FileNotFoundError:  # no `.secret.json` file if running in CI
    api_key = None

def api_call(address_param):
    if not api_key:
        return {}
    api_request = "https://maps.googleapis.com/maps/api/geocode/json?address={}, Ottawa, Ontario, Canada&bounds=41.6765559,-95.1562271|56.931393,-74.3206479&key={}"
    response = requests.get(api_request.format(address_param, api_key))
    results_list = json.loads(response.content)['results']
    for result in results_list:
        if 'ottawa' in str(result).lower():
            return result
    return {}

def get_address_latlng(address_input):
    if (not address_input) or (address_input == 'null'):
        return {}
    info = api_call(f"{address_input}")
    if info:
        lat_diff = (
            info['geometry']['viewport']['northeast']['lat'] - 
            info['geometry']['viewport']['southwest']['lat']
        )
        if lat_diff < 0.04:
            zoom = 17
        elif lat_diff < 0.05:
            zoom = 16
        elif lat_diff < 0.06:
            zoom = 15
        elif lat_diff < 0.08:
            zoom = 14
        else:
            zoom = 13
        return info['geometry']['location'], zoom
    return {}, 14

def coordinate_area_to_m2(area):
    return float(area) * 8684148731

def m2_to_acres(area):
    return float(area) * 0.000247105

def get_offleashscore(lat, lng):
    isochrones = get_isochrones([[lat, lng]])
    walk_score = int(get_iso_walk_score(isochrones[0]))
    drive_score = int(get_iso_drive_score(isochrones[1]))
    score = walk_score + drive_score
    return score, walk_score, drive_score

@app.route('/', methods=["POST", "GET"])
def index():
    return render_template('index.html')

@app.route('/about', methods=["POST", "GET"])
def about():
    return render_template('about.html')

@app.route('/score', methods=["POST", "GET"])
def score():
    return render_template('score.html')

@app.route('/map_score', methods=["POST", "GET"])
def map_score():
    locate = request.args.get('locate')
    if locate:
        zoom_level = 14
        lat, lng = None, None
        geocode_center, zoom_level = get_address_latlng(locate)
        logger.info(f"geocode_center: {geocode_center}")
        lat = geocode_center.get('lat')
        lng = geocode_center.get('lng')
        score, walk_score, drive_score = get_offleashscore(lat, lng)
        if lat:
            with open('templates/score.html', 'r+') as f:
                reloc_map = f.read()
            reloc_map = reloc_map.replace(
                'center: [45.39, -75.65]',
                f'center: [{lat}, {lng}]'
            )
            reloc_map = reloc_map.replace(
                'zoom: 11',
                f'zoom: {zoom_level}'
            )
            # return reloc_map
            return render_template('ols.html', score=score, walk_score=walk_score, drive_score=drive_score)
    return render_template('map_score.html') # location not found or not specified

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
    # # Thurso - frickin far
    # lat = 45.626073
    # lng = -75.167246
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
    parks_in_area = response['features']
    all_park_names = {}
    for i in range(len(parks_in_area)):
        park_name = parks_in_area[i]['attributes']['NAME']
        if park_name in all_park_names:
            all_park_names.update({park_name: all_park_names[park_name] + 1})
            parks_in_area[i]['attributes']['NAME'] = park_name + ' #' + str(all_park_names[park_name])
        else:
            all_park_names.update({park_name:1})
            # parks_in_area[i]['attributes']['NAME'] = park_name + ' #1'
    def distance_to_edge(park):
        radius = park['attributes']['Shape_Area']**0.5
        distance = (((park['attributes']['LATITUDE']-lat)**2 + (park['attributes']['LONGITUDE']-lng)**2)**0.5)*100000
        return distance - radius
    parks_in_area.sort(key=lambda park: distance_to_edge(park))
    parks_in_area = parks_in_area[:30]
    for park in parks_in_area:
        park['attributes'].update({'directions': f"https://www.google.com/maps/dir/?api=1&destination={park['attributes']['LATITUDE']}%2C{park['attributes']['LONGITUDE']}"})
    offleash_parks = [park for park in parks_in_area if park['attributes']['DOG_DESIGNATION'] == '0']
    near_parks = [park for park in parks_in_area if park['attributes']['NAME'] not in [park['attributes']['NAME'] for park in offleash_parks]]
    near_parks = [park for park in parks_in_area if park['attributes']['DOG_DESIGNATION'] != '3']
    near_parks = near_parks[:10]
    designation = 4  #default of 'undesignated'
    park_name = None
    park_lat = None
    park_lng = None
    details = None
    size = None
    for park in parks_in_area:
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
        size_in_acres = round(m2_to_acres(size),1)
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
        size_in_acres = round(m2_to_acres(size),1)
        size_text= f"{size_in_acres} acres"
        zoom_start = int(15 + 10 / size_in_acres)
    else:
        size_text = 'unknown size'
        zoom_start = 14
    zoom_start -= 2
    with open('templates/full_map.html', 'r+') as f:
        reloc_map = f.read()
    reloc_map = reloc_map.replace(
        'center: [45.4096666, -75.6944444]',
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
        size_in_acres = round(m2_to_acres(size),1)
        size_text= f"{size_in_acres} acres"
        zoom_start = int(14 + 10 / size_in_acres)
    else:
        size_text = 'unknown size'
        zoom_start = 14
    try:
        parks
    except NameError:
        parks = get_all_parks()
        enclosures = get_all_enclosures()
        pits = get_all_pits()
    logger.info('done loading...')
    parks_in_focus = [park for park in parks if park['attributes']['NAME'] == focus]
    fill_opacity = 0.08
    line_weight = 3
    m = folium.Map(tile=None, name='', location=(lat, lng), zoom_start=zoom_start, width='100%', height='100%', disable_3D=False)
    #folium.TileLayer('openstreetmap', control=False, overlay=False, name='').add_to(m)
    feature_group = folium.FeatureGroup(name="off leash", overlay=False, show=True, control=False)
    color_map = {'0':'green', '1':'black', '2':'purple', '3':'red', '4':'black'}
    layer_color = color_map[designation]
    for park in [park for park in parks_in_focus if park['attributes']['DOG_DESIGNATION'] == designation]:
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
    try:
        locate = request.args.get('locate')
        if locate:
            zoom_level = 14
            lat, lng = None, None
            try:
                parks
            except NameError:
                parks = get_all_parks()
                enclosures = get_all_enclosures()
                pits = get_all_pits()
            for park in parks + pits + enclosures:  # see if query is park name
                if locate.lower() in park['attributes']['NAME'].lower():
                    lat = park['attributes']['LATITUDE']
                    lng = park['attributes']['LONGITUDE']
            if not lat:  # get google to geocode it
                geocode_center, zoom_level = get_address_latlng(locate)
                logger.info(f"geocode_center: {geocode_center}")
                lat = geocode_center.get('lat')
                lng = geocode_center.get('lng')
            if lat: 
                with open('templates/full_map.html', 'r+') as f:
                    reloc_map = f.read()
                reloc_map = reloc_map.replace(
                    'center: [45.4096666, -75.6944444]',
                    f'center: [{lat}, {lng}]'
                )
                reloc_map = reloc_map.replace(
                    'zoom: 14',
                    f'zoom: {zoom_level}'
                )
                return reloc_map
        else: # location not found or not specified
            return render_template('full_map.html')
    except TemplateNotFound:
        logger.info("template 'full_map.html' requested but not found")
        pass
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
            {}
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
            &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp
            &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp &nbsp
        </details>
    """
    website_html = """
        <button onclick="window.open('{}', '_blank', 'noopener')" style="font-weight: bold; color: purple;">website</button>
    """

    m = folium.Map(tile=None, name='', location=(45.4096666, -75.6944444), zoom_start=14, width='100%', height='100%', disable_3D=False)
    folium.TileLayer('openstreetmap', control=False, overlay=False, name='').add_to(m)

    feature_group = folium.FeatureGroup(name="off leash", overlay=True, show=True)
    layer_color = 'green'
    try:
        parks
    except NameError:
        parks = get_all_parks()
        enclosures = get_all_enclosures()
        pits = get_all_pits()
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '0']:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = park['attributes']['directions']
        if size:
            size_in_acres = round(m2_to_acres(size),1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, '', size_text, lat, lng, details), max_width='220', max_height='200')
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

    feature_group = folium.FeatureGroup(name="on leash", overlay=True, show=True)
    layer_color = 'black'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] in ['1', '4']]:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = park['attributes']['directions']
        if size:
            size_in_acres = round(m2_to_acres(size),1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, '', size_text, lat, lng, details), max_width='220', max_height='200')
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

    feature_group = folium.FeatureGroup(name="mixed designation", overlay=True, show=True)
    layer_color = 'purple'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '2']:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = park['attributes']['directions']
        if size:
            size_in_acres = round(m2_to_acres(size),1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, '', size_text, lat, lng, details), max_width='220', max_height='200')
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
    
    feature_group = folium.FeatureGroup(name="no dogs allowed", overlay=True, show=True)
    layer_color = 'red'
    for park in [park for park in parks if park['attributes']['DOG_DESIGNATION'] == '3']:
        name = park['attributes']['NAME']
        lat = park['attributes']['LATITUDE']
        lng = park['attributes']['LONGITUDE']
        size = park['attributes']['Shape_Area']
        details = park['attributes']['DOG_DESIGNATION_DETAILS']
        directions = park['attributes']['directions']
        if size:
            size_in_acres = round(m2_to_acres(size),1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, '', size_text, lat, lng, details), max_width='220', max_height='200')
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
    feature_group = folium.FeatureGroup(name="off-leash enclosures", overlay=True, show=True)
    layer_color = 'orange'
    for enclosure in enclosures:
        name = enclosure['attributes']['NAME']
        lat = enclosure['attributes']['LATITUDE']
        lng = enclosure['attributes']['LONGITUDE']
        size_text = 'N/A'
        details = 'Off-leash enclosure'
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lng}"
        popup=folium.map.Popup(html=popup_html.format(name, directions, '', size_text, lat, lng, details), max_width='220', max_height='200')
        folium.Marker(
            [lat, lng],
            popup=popup,
            icon=folium.Icon(prefix='fa', icon='paw', color=layer_color)
        ).add_to(feature_group)
    feature_group.add_to(m)
    layer_color = 'darkgreen'
    feature_group = folium.FeatureGroup(name="off leash pits", overlay=True, show=True)
    for pit in pits:
        name = pit['attributes']['NAME']
        lat = pit['attributes']['LATITUDE']
        lng = pit['attributes']['LONGITUDE']
        size = coordinate_area_to_m2(Polygon(pit['geometry']['rings'][0]).area)
        details = pit['attributes']['details']
        subscription = pit['attributes'].get('subscription', None)
        website = pit['attributes'].get('website')
        directions = f"https://www.google.com/maps/dir/?api=1&destination={lat}%2C{lng}"
        if size:
            size_in_acres = round(m2_to_acres(size),1)
            size_text= f"{size_in_acres} acres"
        else:
            size_text = 'unknown size'
        popup=folium.map.Popup(html=popup_html.format(name, directions, website_html.format(website) if website else '', size_text, lat, lng, details), max_width='220', max_height='200')
        folium.Marker(
            [lat, lng],
            popup=popup,
            icon=folium.Icon(prefix='fa', icon='dollar' if subscription else 'circle', color=layer_color)
        ).add_to(feature_group)
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            ring for ring in pit['geometry']['rings']
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
            fill_opacity = fill_opacity,
            line_weight=line_weight
        ).add_to(feature_group)
    feature_group.add_to(m)

    LocateControl().add_to(m)
    folium.LayerControl(collapsed=True, position='topleft').add_to(m)
    logger.info('ok, map is ready')
    m.save('templates/full_map.html')
    return m.get_root().render()

@app.route('/map', methods=["POST", "GET"])
def map():
    return render_template('map.html')

if __name__ == "__main__":
    parks = get_all_parks()
    enclosures = get_all_enclosures()
    pits = get_all_pits()
    app.run(debug=False)
