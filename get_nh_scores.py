from time import sleep
import json
import requests
import folium
from folium.plugins import MarkerCluster, HeatMapWithTime, HeatMap, LocateControl
import numpy as np
import pandas as pd
from shapely import wkt, geometry
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
from shapely.ops import unary_union, transform, cascaded_union
from pprint import pprint
from openrouteservice import client, isochrones
from fetch_parks import get_all_parks, get_all_enclosures, get_all_pits
import pandas_bokeh
from functools import lru_cache
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import scipy.stats
import statistics



api_key = "5b3ce3597851110001cf624885cf8ae8a912419791393bcc5f10c901"
clnt = client.Client(key=api_key)

# initiate isochrone cache if none exists already
# try:
#     df_iso = pd.read_csv('isochrone_cache.csv')
# except FileNotFoundError:
#     df_iso = pd.DataFrame({'points': [], 'isochrones': []})
#     df_iso.to_csv('isochrone_cache.csv', index=False)

# def json_to_df(data):
#     df = pd.DataFrame(data)
#     for attr in df.iloc[0]['attributes'].keys():
#         df[attr] = df.attributes.apply(lambda x: x[attr])
#     df = df.drop('attributes', axis=1)
#     return df


def get_isochrones(points):
    input_points = points
    df_iso = pd.read_csv('isochrone_cache.csv')
    short_walk_iso, long_walk_iso, drive_iso = [], [], []
    for point in points:
        lat, lng = point[0], point[1]
        match = df_iso[(round(df_iso['lat'], 7) == round(lat, 7)) & (round(df_iso['lng'], 7) == round(lng, 7))]
        if len(match) and match.iloc[-1].short_walk_iso:
            short_walk_iso.append(eval(list(match.short_walk_iso)[-1]))
            long_walk_iso.append(eval(list(match.long_walk_iso)[-1]))
            drive_iso.append(eval(list(match.drive_iso)[-1]))
    if len(short_walk_iso) == len(points):
        print("utilized cache to bypass ORS API!")
        return short_walk_iso + long_walk_iso + drive_iso
    else:
        points = [[y, x] for x, y in points]  # switch lat/lng order
        walk_queries = {
            "locations":points,
            "range":[450, 1200],
            "profile":'foot-walking'
        }
        drive_query = {
            "locations":points,
            "range":[480],
            "profile":'driving-car'
        }
        while True:
            try:
                print('calling for short and long walk isochrones')
                walk_isos = clnt.isochrones(**walk_queries)['features']
                short_walk_iso = walk_isos[::2]
                long_walk_iso = walk_isos[1::2]
                break
            except:
                pass
        sleep(2.5)
        while True:
            try:
                print('calling for drive isochrone')
                drive_iso = clnt.isochrones(**drive_query)['features']
                break
            except:
                pass
        features = short_walk_iso + long_walk_iso + drive_iso
        isochrones = [feautre['geometry']['coordinates'][0] for feautre in features]
        isochrones = [[(y,x) for x,y in isochrone] for isochrone in isochrones]
        for i in range(len(input_points)):
            df_iso = df_iso.append({
                'lat': input_points[i][0],
                'lng': input_points[i][1],
                'short_walk_iso': isochrones[i],
                'long_walk_iso': isochrones[i+1],
                'drive_iso': isochrones[i+2],
            }, ignore_index=True)
        df_iso.to_csv('isochrone_cache.csv', index=False)
        return isochrones
    
def get_random_addresses(lat, lng, lat_diff, lng_diff, ward_num=False, nh=False, seed=0):
    if ward_num or nh:
        df = pd.read_csv('addresses_wards_nhs.csv')
        if nh:
            df = df[df.nh == nh][['lat', 'lng']]
        else:
            df = df[df.ward_num == ward_num][['lat', 'lng']]
        address_points = list(df.to_records(index=False))
    else:
        api_call = f"https://maps.ottawa.ca/arcgis/rest/services/Municipal_Address/MapServer/0/query?where=1%3D1&outFields=*&geometry={lng - lng_diff}%2C{lat - lat_diff}%2C{lng + lng_diff}%2C{lat + lat_diff}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelContains&outSR=4326&f=json"
        addresses = json.loads(requests.get(api_call).content)['features']
        address_points = [address['geometry'] for address in addresses]
        address_points = [(address_point['y'], address_point['x']) for address_point in address_points]
    
    address_points = np.array(address_points)
    np.random.seed(seed)
    if len(address_points) >= 5:
        idx = np.random.choice(len(address_points), 5, replace=False)
        selected_points = address_points[idx]
    elif len(address_points) >= 1:
        idx = np.random.choice(len(address_points), 1, replace=False)
        selected_points = np.array(list(address_points[idx])*5)
    selected_points = [selected_point.tolist() for selected_point in selected_points]
    return selected_points

def get_iso_walk_score(short_walk_iso, long_walk_iso):
    short_walk_iso = Polygon(short_walk_iso)
    short_walk_iso = transform(lambda x, y: (y, x), short_walk_iso)
    short_walk_area = 0
    long_walk_iso = Polygon(long_walk_iso)
    long_walk_iso = transform(lambda x, y: (y, x), long_walk_iso)
    long_walk_area = 0
    for _, park in parks[(parks.type_of_park == 'park') | (parks.type_of_park == 'pit')].iterrows():
        for ring in park['geometry']['rings']:
            short_walk_area += Polygon(ring).intersection(short_walk_iso).area
            long_walk_area += Polygon(ring).intersection(long_walk_iso).area
    enclosure_near_short = 0
    enclosure_near_long = 0
    for _, park in parks[parks.type_of_park == 'enclosure'].iterrows():
        if Point(park.LONGITUDE, park.LATITUDE).within(short_walk_iso):
            enclosure_near_short += 1
        elif Point(park.LONGITUDE, park.LATITUDE).within(long_walk_iso):
            enclosure_near_long += 1
    score = ((short_walk_area**0.8) * 150000 + ((max(long_walk_area - short_walk_area, 0))**0.8) * 80000 + enclosure_near_short * 8 + enclosure_near_long * 4) * 2
    score = max(20, score) if (short_walk_area or enclosure_near_short) else score
    return score

def get_iso_drive_score(long_walk_iso, drive_iso):
    drive_iso = Polygon(drive_iso)
    long_walk_iso = Polygon(long_walk_iso)
    drive_iso = transform(lambda x, y: (y, x), drive_iso)
    long_walk_iso = transform(lambda x, y: (y, x), long_walk_iso)
    walk_area = 0
    drive_reach = 0
    for _, park in parks[(parks.type_of_park == 'park') | (parks.type_of_park == 'pit')].iterrows():
        for ring in park['geometry']['rings']:
            if Polygon(ring).intersects(drive_iso):
                drive_reach += 1 if not Polygon(ring).intersects(long_walk_iso) else 0
                walk_area += Polygon(ring).area - Polygon(ring).intersection(long_walk_iso).area
    enclosure_near = False
    for _, park in parks[parks.type_of_park == 'enclosure'].iterrows():
        if Point(park.LONGITUDE, park.LATITUDE).within(drive_iso):
            if not Point(park.LONGITUDE, park.LATITUDE).within(long_walk_iso):
                enclosure_near = True
                break
    score = ((walk_area**0.8) * 20000 + enclosure_near * 4 + drive_reach**0.5) * 2
    return score

def zone_score(curr_lng, curr_lat, lng_diff, lat_diff, ward_num=False, nh=False, seed=0):
    if (not ward_num) and (not nh):
        parks = parks[abs(parks.LONGITUDE - curr_lng) < 0.05]
        parks = parks[abs(parks.LATITUDE - curr_lat) < 0.05]
    selected_points = get_random_addresses(curr_lat, curr_lng, lat_diff, lng_diff, ward_num=ward_num, nh=nh, seed=seed)
    if not selected_points:
        print("skipped area and logged score of 0!")
        return 0
    selected_points = [list(x) for x in selected_points]  # convert to tuples to make hashble for lru_cache
    isochrones = get_isochrones(selected_points)
    total_scores = []
    for isochrone_walk, isochrone_drive in zip(isochrones[:5], isochrones[5:]):
        walk_score = get_iso_walk_score(isochrone_walk)
        drive_score = get_iso_drive_score(isochrone_walk, isochrone_drive)
        total_score = walk_score + drive_score
        total_score = 100 if total_score > 100 else total_score
        total_scores.append(total_score)
    return total_scores

def json_to_df(data):
    df = pd.DataFrame(data)
    for attr in df.iloc[0]['properties'].keys():
        df[attr] = df.properties.apply(lambda x: x[attr])
    df = df.drop('properties', axis=1)
    return df

url = "https://opendata.arcgis.com/datasets/32fe76b71c5e424fab19fec1f180ec18_0.geojson"
nh_data = json.loads(requests.get(url).content)['features']
df_nh = json_to_df(nh_data)

def json_to_df(data):
    df = pd.DataFrame(data)
    for attr in df.iloc[0]['attributes'].keys():
        df[attr] = df.attributes.apply(lambda x: x[attr])
    df = df.drop('attributes', axis=1)
    return df

def get_shape(coordinates):
    shape = []
    for area in coordinates:
        try:
            shape.append(Polygon(area))
        except ValueError:
            shape.append(Polygon(area[0]))
    polygon = cascaded_union(shape)
    return polygon

def mean_confidence_interval(data, confidence=0.95):
    a = 1.0 * np.array(data)
    n = len(a)
    m, se = np.mean(a), scipy.stats.sem(a)
    h = se * scipy.stats.t.ppf((1 + confidence) / 2., n-1)
    return m, h

parks = json_to_df(get_all_parks())
parks = parks[parks.DOG_DESIGNATION == '0'][['NAME', 'LONGITUDE', 'LATITUDE', 'geometry']]
parks['type_of_park'] = 'park'
enclosures = json_to_df(get_all_enclosures())
enclosures['type_of_park'] = 'enclosure'
pits = json_to_df(get_all_pits())
pits = pits[pits.subscription != 'paid']
pits['type_of_park'] = 'pit'
parks = parks.append(enclosures).append(pits)

# for s in range(15, 1000, 2):
#     m = folium.Map(location=(45.39, -75.65), zoom_start=11)
#     feature_group_markers = folium.FeatureGroup(name="info markers", overlay=True, show=True)
#     feature_group_choropleths = folium.FeatureGroup(name="choropleths", overlay=True, show=True)
#     ottawa_scores = []
#     for _, nh in df_nh.iterrows():
#         print(f"neighbourhood: {nh.Name}")
#         scores = []
#         seed_start, seed_end = s, s + 1 
#         for seed in range(seed_start, seed_end + 1):
#             sample_scores = zone_score(0, 0, 0, 0, nh=nh.Name, seed=seed)
#             scores += sample_scores
#         ottawa_scores += scores
#         print(f"min: {min(scores)}")
#         print(f"max: {max(scores)}")
#         confidence = 0.95
#         mean, interval = mean_confidence_interval(scores, confidence=confidence)
#         print(f"mean: {mean} ±{interval}")
#         median = statistics.median(scores)
#         print(f"median: {median}")
#         score = median
#         plt.figure(figsize=(4,2), dpi=300)
#         p = plt.hist(scores, range=(0,150), bins=30, color='gray')
#         plt.axvline(x=median, color='blue', linestyle='--', label='local')
#         plt.axvline(x=27.83, color='orange', linestyle='--', label='city-wide')
#         plt.legend(title='Median:')
#         plt.title('OffLeashScore Distribution')
#         tmpfile = BytesIO()
#         plt.savefig(tmpfile, format='png')
#         plt.clf()
#         encoded = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
#         shape = get_shape(nh['geometry']['coordinates'])
#         geojson_input = nh['geometry']['coordinates']
#         geojson = {
#             "type": "FeatureCollection",
#             "features": [
#                 {
#                     "type": "Feature",
#                     "geometry": {
#                         "type": f"{'MultiPolygon' if repr(nh.geometry['coordinates'])[3] =='[' else 'Polygon'}",
#                         "coordinates": geojson_input
#                     },
#                 },
#             ]
#         }
#         folium.features.Choropleth(
#             geo_data=geojson,
#             highlight=True,
#             fill_color=f'rgb(1,1,{score*2.2})',
#             fill_opacity = 0.5,
#         ).add_to(feature_group_choropleths)
#         folium.Marker(
#             location=(shape.centroid.y, shape.centroid.x),
#             icon=folium.Icon(color='black'),
#             popup=folium.map.Popup(html=f"""
#                 <style>
#                     table {{
#                         width: 180px;
#                     }}
#                 </style>
#                 <h5>{nh.Name}</h5>
#                 <table style="font-size: 120%;">
#                     <tr>
#                         <th><b>median score</b></th>
#                         <td style="color: blue; font-weight: bold;">{int(round(score, 0))}</td>
#                     </tr>
#                 </table> 
#                 <br>
#                 <img src=\'data:image/png;base64,{encoded}\' style="width: 300px;">
#                 <br>
#                 <details>
#                 <summary>stats</summary>
#                     <table>
#                         <tr>
#                             <th><b>median</b></th>
#                             <td>{round(median, 1)}</td>
#                         </tr>
#                         <tr>
#                             <th><b>mean</b></th>
#                             <td>{round(mean, 1)} ±{round(interval, 1)} ({int(confidence*100)}%)</td>
#                         </tr>
#                         <tr>
#                             <th><b>sample min</b></th>
#                             <td>{round(min(scores), 1)}</td>
#                         </tr>
#                         <tr>
#                             <th><b>sample max</b></th>
#                             <td>{round(max(scores), 1)}</td>
#                         </tr>
#                     </table> 
#                 </details>
#             """)
#         ).add_to(feature_group_markers)
#     feature_group_markers.add_to(m)
#     feature_group_choropleths.add_to(m)
#     LocateControl().add_to(m)
#     folium.LayerControl(collapsed=True, position='topleft').add_to(m)
#     print(f"Ottawa min: {min(ottawa_scores)}")
#     print(f"Ottawa max: {max(ottawa_scores)}")
#     confidence = 0.95
#     mean, interval = mean_confidence_interval(ottawa_scores, confidence=confidence)
#     print(f"Ottawa mean: {mean} ±{interval}")
#     median = statistics.median(ottawa_scores)
#     print(f"Ottawa median: {median}")
#     m.save(f'nhs_choropleth_s{seed_start}-s{seed_end}.html')
#     sleep(60 * 60 * 24 + 60 * 5)
