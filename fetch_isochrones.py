from time import sleep
import json
import requests
import numpy as np
import pandas as pd
from openrouteservice import client


def get_isochrones(points):
    input_points = points
    df_iso = pd.read_csv('isochrone_cache.csv')
    match = df_iso[df_iso.points == repr(points)]
    if len(match):
        return eval(list(match.isochrones)[-1])
    else:
        points = [[y, x] for x, y in points]  # switch lat/lng order
        walk_query = {
            "locations":points,
            "range":[1200],
            "profile":'foot-walking'
        }
        drive_query = {
            "locations":points,
            "range":[480],
            "profile":'driving-car'
        }
        while True:
            try:
                print('calling for walk isochrone')
                walk_isochrone = clnt.isochrones(**walk_query)['features']
                break
            except:
                pass
        sleep(2.5)
        while True:
            try:
                print('calling for drive isochrone')
                drive_isochrone = clnt.isochrones(**drive_query)['features']
                break
            except:
                pass
        features = walk_isochrone + drive_isochrone
        isochrones = [feautre['geometry']['coordinates'][0] for feautre in features]
        isochrones = [[(y,x) for x,y in isochrone] for isochrone in isochrones]
        df_iso = df_iso.append({'points': input_points, 'isochrones': isochrones}, ignore_index=True)
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
    else:
        selected_points = np.array([list(np.array([lat, lng]))]*5)
    selected_points = [selected_point.tolist() for selected_point in selected_points]
    return selected_points

def zone_score(curr_lng, curr_lat, lng_diff, lat_diff, ward_num=False, nh=False, seed=0):
    selected_points = get_random_addresses(curr_lat, curr_lng, lat_diff, lng_diff, ward_num=ward_num, nh=nh, seed=seed)
    if not selected_points:
        print("skipped area and logged score of 0!")
        return 0
    selected_points = [list(x) for x in selected_points]  # convert to tuples to make hashble for lru_cache
    isochrones = get_isochrones(selected_points)
    return

def json_to_df(data):
    df = pd.DataFrame(data)
    for attr in df.iloc[0]['properties'].keys():
        df[attr] = df.properties.apply(lambda x: x[attr])
    df = df.drop('properties', axis=1)
    return df

parks = json_to_df(get_all_parks())
parks = parks[parks.DOG_DESIGNATION == '0'][['NAME', 'LONGITUDE', 'LATITUDE', 'geometry']]
parks['type_of_park'] = 'park'
enclosures = json_to_df(get_all_enclosures())
enclosures['type_of_park'] = 'enclosure'
pits = json_to_df(get_all_pits())
pits = pits[pits.subscription != 'paid']
pits['type_of_park'] = 'pit'
parks = parks.append(enclosures).append(pits)

for s in range(15, 1000, 2):
    with open(".secret.json") as f:
        api_key = json.load(f)["ors_api_key"]
    clnt = client.Client(key=api_key)
    url = "https://opendata.arcgis.com/datasets/32fe76b71c5e424fab19fec1f180ec18_0.geojson"
    nh_data = json.loads(requests.get(url).content)['features']
    df_nh = json_to_df(nh_data)
    try:
        df_iso = pd.read_csv('isochrone_cache.csv')
    except FileNotFoundError:
        df_iso = pd.DataFrame({'points': [], 'isochrones': []})
        df_iso.to_csv('isochrone_cache.csv', index=False)
    for i, nh in df_nh.iterrows():
        print(f"{i}: {nh.Name}")
        seed_start, seed_end = s, s + 1 
        for seed in range(seed_start, seed_end + 1):
            print(f"collecting isochrones for seed {seed}")
            zone_score(0, 0, 0, 0, nh=nh.Name, seed=seed)
    print("Done collecting isochrones for the day.")
    sleep(60 * 60 * 24 + 60 * 5)
