from time import sleep
import json
import requests
import numpy as np
import pandas as pd
from openrouteservice import client
from get_nh_scores import get_isochrones, get_random_addresses
from fetch_parks import get_all_parks, get_all_enclosures, get_all_pits


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
    for attr in df.iloc[0]['attributes'].keys():
        df[attr] = df.attributes.apply(lambda x: x[attr])
    df = df.drop('attributes', axis=1)
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

def json_to_df(data):
    df = pd.DataFrame(data)
    for attr in df.iloc[0]['properties'].keys():
        df[attr] = df.properties.apply(lambda x: x[attr])
    df = df.drop('properties', axis=1)
    return df

for s in range(4, 1000, 2):
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
