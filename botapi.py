import os
import google.generativeai as genai
import requests
import ast
import http.client
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')

os.environ['GOOGLE_API_KEY'] = GOOGLE_API_KEY
genai.configure(api_key=os.environ['GOOGLE_API_KEY'])

model = genai.GenerativeModel('gemini-pro')
chat_model = genai.GenerativeModel('gemini-pro')
chat = chat_model.start_chat(history=[])
starter = """
    You are my travel chatbot. From the texts I give you, you have to identify the kind of text this is.
    "Type 1" - I am asking about a place where I wish to travel today, if this is the case,
    extract start and end locations from the given text. If a start location isn't explicitly mentioned, take start location as "null".
    Return in the form of a tuple having ("Type_1", [startlocation, endlocation]). Do not forget to enclose "Type_1" in double quotes!
    
    "Type 2" - I am asking about current weather conditions of a place, if this is the case,
    extract the location whose current weather conditions I am asking. If I do not mention location, take it as "null".
    Return in the form of a tuple having ("Type_2", location). Do not forget to enclose "Type_2" in double quotes!
    
    "Type 3" - I am generally asking about anything else, apart from the two types above, if this is the case,
    respond normally as you would. Return in the form of a tuple having ("Type_3", your_normal_response). Do not forget to enclose "Type_3" in double quotes!
"""
response = chat.send_message(starter)
print(response.text)

app = FastAPI()

class UserPrompt(BaseModel):
    prompt: str
    lat:float
    lon:float

def get_current_location():
    try:
        response = requests.get("http://ip-api.com/json/")
        response.raise_for_status()
        data = response.json()
        return data['lat'], data['lon'], data['city']
    except requests.RequestException as e:
        print(f"Error fetching current location: {e}")
        return 0, 0, "unknown"

def remove_spaces(text):
    return text.replace(" ", "")

def get_latlon_from_add(add):
    try:
        add = remove_spaces(add)
        conn = http.client.HTTPSConnection("map-geocoding.p.rapidapi.com")
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': "map-geocoding.p.rapidapi.com"
        }
        conn.request("GET", f"/json?address={add}", headers=headers)
        res = conn.getresponse()
        data = res.read()
        data = json.loads(data)
        latitude = data['results'][0]['geometry']['location']['lat']
        longitude = data['results'][0]['geometry']['location']['lng']
        return latitude, longitude
    except Exception as e:
        print(f"Error fetching lat/lon for address '{add}': {e}")
        return 0, 0

def get_weather(add, lat, lon):
    try:
        if lat == 0 and lon == 0:
            lat, lon = get_latlon_from_add(add)
        conn = http.client.HTTPSConnection("open-weather13.p.rapidapi.com")
        headers = {
            'x-rapidapi-key': RAPIDAPI_KEY,
            'x-rapidapi-host': "open-weather13.p.rapidapi.com"
        }
        conn.request("GET", f"/city/latlon/{lat}/{lon}", headers=headers)
        res = conn.getresponse()
        data = res.read()
        return json.loads(data)
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return None

def extract_items(input_string):
    items = input_string.strip("()").split(", ")
    first_item = items[0]
    second_item = items[1]
    return first_item, second_item

def mainbot(user_prompt, ulat, ulon):
    try:
        response = chat.send_message(user_prompt)
        converted_data = ast.literal_eval(response.text)
        
        if converted_data[0] in ("Type_1", "Type 1", "Type1"):
            start = converted_data[1][0]
            end = converted_data[1][1]
            if start == "null":
                startlat = ulat
                startlon = ulon
            else:
                startlat, startlon = get_latlon_from_add(start)
            endlat, endlon = get_latlon_from_add(end)
            return 1, response.text, [startlat, startlon, endlat, endlon]
        
        elif converted_data[0] in ("Type_2", "Type 2", "Type2"):
            if converted_data[1] == "null":
                wlat, wlon, _ = get_current_location()
                weather_data = get_weather("current location", wlat, wlon)
            else:
                weather_data = get_weather(converted_data[1], 0, 0)
            return 2, response.text, weather_data
        
        elif converted_data[0] in ("Type_3", "Type 3", "Type3"):
            return 3, response.text, []
        
        else:
            return None, "Unknown response type", []

    except Exception as e:
        print(f"Error processing user prompt: {e}")
        return None, "Error processing user prompt", []

@app.get("/home/")
async def home():
    return {"message": "Bot is live and working!"}

@app.post("/process_prompt/")
async def process_prompt(user_prompt: UserPrompt):
    try:
        geminires = mainbot(user_prompt.prompt, user_prompt.lat, user_prompt.lon)
        return {"result": geminires}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reset_context/")
async def reset_context():
    global chat
    chat = chat_model.start_chat(history=[])
    starter = """
    You are my travel chatbot. From the texts I give you, you have to identify the kind of text this is.
    "Type 1" - I am asking about a place where I wish to travel today, if this is the case,
    extract start and end locations from the given text. If a start location isn't explicitly mentioned, take start location as "null".
    Return in the form of a tuple having ("Type_1", [startlocation, endlocation]). Do not forget to enclose "Type_1" in double quotes!
    
    "Type 2" - I am asking about current weather conditions of a place, if this is the case,
    extract the location whose current weather conditions I am asking. If I do not mention location, take it as "null".
    Return in the form of a tuple having ("Type_2", location). Do not forget to enclose "Type_2" in double quotes!
    
    "Type 3" - I am generally asking about anything else, apart from the two types above, if this is the case,
    respond normally as you would. Return in the form of a tuple having ("Type_3", your_normal_response). Do not forget to enclose "Type_3" in double quotes!
    """
    response = chat.send_message(starter)
    print(response.text)
    return {"message": "Chat context has been reset."}

# uvicorn botapi:app --reload
