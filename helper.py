import tweepy
import os
import requests
import redis
import json
import base64
from oauth2client.service_account import ServiceAccountCredentials
import cv2
import firebase_admin
import firebase_admin.messaging as messaging

auth = tweepy.OAuthHandler(os.environ.get(
    "TWITTER-CONSUMER-KEY"), os.environ.get("TWITTER-CONSUMER-SECRET"))
auth.set_access_token(os.environ.get("TWITTER-ACCESS-TOKEN"),
                      os.environ.get("TWITTER-ACCESS-SECRET"))

BASE_URL = "https://fcm.googleapis.com"
FCM_ENDPOINT = "v1/projects/{}/messages:send".format(
    os.environ.get("FCM-PROJECT-ID"))
FCM_URL = BASE_URL + "/" + FCM_ENDPOINT
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

sa_json = json.loads(base64.b64decode(os.environ.get("SERVICE-ACCOUNT-JSON")))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(sa_json, SCOPES)

default_app = firebase_admin.initialize_app(firebase_admin.credentials.Certificate(sa_json))

r = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)

def send_discord_error(error):
    embed = {
        "username": "Server Error",
    }
    content = "<@120242625809743876> {}".format(error)
    embed["content"] = content
    result = requests.post(os.environ.get("DISCORD-ERROR-URL"), json=embed)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Error Sent, code {}.".format(result.status_code))

def thumbnail(url):
    request = requests.get(url, stream=True)
    if request.status_code == 200:
        with open("thumbnail.jpg", 'wb') as image:
            for chunk in request:
                image.write(chunk)

        imagecheck = cv2.imread("thumbnail.jpg", 0)
        if cv2.countNonZero(imagecheck) == 0:
            print("Thumbnail is empty")
            os.remove("thumbnail.jpg")
    else:
        print("Unable to download image")

def subscribe_topic(topic, token):
    response = messaging.subscribe_to_topic(token, topic, default_app)
    print(response)
    print(response.success_count, 'tokens were subscribed successfully')

def unsubscribe_topic(topic, token):
    response = messaging.unsubscribe_from_topic(token, topic, default_app)
    print(response)
    print(response.success_count, 'tokens were unsubscribed successfully')