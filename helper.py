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
from functools import wraps
from flask import request, Response
import atproto
# from instagrapi import Client as igc

twitterAuth = tweepy.OAuth1UserHandler(os.getenv(
    "TWITTER-CONSUMER-KEY"), os.getenv("TWITTER-CONSUMER-SECRET"), os.getenv("TWITTER-ACCESS-TOKEN"),
    os.getenv("TWITTER-ACCESS-SECRET"))
twitterClient = tweepy.Client(os.getenv("TWITTER-BEARER-TOKEN"), os.getenv(
    "TWITTER-CONSUMER-KEY"), os.getenv("TWITTER-CONSUMER-SECRET"), os.getenv("TWITTER-ACCESS-TOKEN"),
    os.getenv("TWITTER-ACCESS-SECRET"))
twitterAPI = tweepy.API(twitterAuth)


blueSkyClient = atproto.Client()
blueSkyProfile = blueSkyClient.login(os.getenv("BSKY-USER"), os.getenv("BSKY-PASS"))

# cl = igc()
# cl.login(os.getenv("INSTAGRAM-USERNAME"), os.getenv("INSTAGRAM-PASSWORD"))

BASE_URL = "https://fcm.googleapis.com"
FCM_ENDPOINT = "v1/projects/{}/messages:send".format(
    os.getenv("FCM-PROJECT-ID"))
FCM_URL = BASE_URL + "/" + FCM_ENDPOINT
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

sa_json = json.loads(base64.b64decode(os.getenv("SERVICE-ACCOUNT-JSON")))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(sa_json, SCOPES)

default_app = firebase_admin.initialize_app(
    firebase_admin.credentials.Certificate(sa_json))

r = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)


def send_discord_error(error):
    embed = {
        "username": "Server Error",
    }
    content = "<@120242625809743876> {}".format(error)
    embed["content"] = content
    result = requests.post(os.getenv("DISCORD-ERROR-URL"), json=embed)
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
    print(response.success_count,
          'tokens were subscribed to {} successfully'.format(topic))


def unsubscribe_topic(topic, token):
    response = messaging.unsubscribe_from_topic(token, topic, default_app)
    print(response.success_count,
          'tokens were unsubscribed {} successfully'.format(topic))


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == 'admin' and password == os.getenv("SERVER-PASSWORD")


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
