from flask import Flask, request, make_response
import xmltodict
import hmac
import hashlib
import os
import tweepy
import requests
import redis
import json
import base64
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

auth = tweepy.OAuthHandler(os.environ.get("TWITTER-CONSUMER-KEY"), os.environ.get("TWITTER-CONSUMER-SECRET"))
auth.set_access_token(os.environ.get("TWITTER-ACCESS-TOKEN"), os.environ.get("TWITTER-ACCESS-SECRET"))

PROJECT_ID = 'nl-notification-server'
BASE_URL = 'https://fcm.googleapis.com'
FCM_ENDPOINT = 'v1/projects/' + PROJECT_ID + '/messages:send'
FCM_URL = BASE_URL + '/' + FCM_ENDPOINT
SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']

sa_json = json.loads(base64.b64decode(os.environ.get("SERVICE-ACCOUNT-JSON")))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(sa_json, SCOPES)

r = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True) 
r.set("STREAM-STATUS", "")

def send_tweet(tweet):
    api = tweepy.API(auth)
    try:
        api.update_status(status=tweet)
        print("Tweet sent")
    except tweepy.TweepError as e:
        print("Tweet could not be sent\n{}".format(e.api_code))

def send_discord(data, platform):
    api = tweepy.API(auth)
    if platform.lower() == "youtube":
        content = "@everyone {}\n{}".format(data["title"], data["link"][0]["@href"])
        embed = {
                    "content": content,
                    "username": "newLEGACYinc",
                    "avatar_url": api.me().profile_image_url
                }
    elif platform.lower() == "twitch":
        url = "https://www.twitch.tv/{}/".format(data["user_login"])
        content = "@everyone {}\n<{}>".format(data["title"], url)
        embed = {
                    "content": content,
                    "username": "newLEGACYinc",
                    "avatar_url": api.me().profile_image_url,
                    "embeds": [
                        {
                            "title": data["title"],
                            "url": url,
                            "color": 16711680,
                            "author": {
                                "name": "newLEGACYinc"
                            },
                            "image": {
                                "url": data["thumbnail_url"].format(width=400, height=225)
                            },
                            "footer": {
                                "text": "Category/Game: {}".format(data["game_name"])
                            }
                        }
                    ]
                }
    result = requests.post(os.environ.get("DISCORD-WEBHOOK-URL"), json = embed)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Discord Notification Sent, code {}.".format(result.status_code))

def send_firebase(platform, data):
    access_token_info = credentials.get_access_token()
    url = "https://www.twitch.tv/{}/".format(data["user_login"])
    headers = {
    'Authorization': 'Bearer ' + access_token_info.access_token,
    'Content-Type': 'application/json; UTF-8',
    }

    if platform.lower() == "youtube":
        fcm_message = {
                        'message': {
                        'topic': platform,
                        'notification': {
                            'title': 'YouTube',
                            'body': data["title"]
                        },
                        "android": {
                        "direct_boot_ok": True,
                        "priority": "high"
                        }
                    }
                }
    elif platform.lower() == "twitch":
        fcm_message = {
                        'message': {
                        'topic': platform,
                        'body': url,
                        'notification': {
                            'title': 'Twitch',
                            'body': data["title"]
                        },
                        "android": {
                        "direct_boot_ok": True,
                        "priority": "high"
                        }
                    }
                }

    resp = requests.post(FCM_URL, data=json.dumps(fcm_message), headers=headers)

    if resp.status_code == 200:
        print('Message sent to Firebase for delivery, response:')
        print(resp.text)
    else:
        print('Unable to send message to Firebase')
        print(resp.text)
    
@app.route('/webhook/<type>', methods=['GET', 'POST'])
def webhook(type):
    if type == "twitch":
        headers = request.headers
        if headers["Twitch-Eventsub-Message-Type"] == "webhook_callback_verification":
            challenge = request.json["challenge"]
            if challenge:
                return make_response(challenge, 201)
        elif headers["Twitch-Eventsub-Message-Type"] == "notification":
            message = headers["Twitch-Eventsub-Message-Id"] + headers["Twitch-Eventsub-Message-Timestamp"] + str(request.get_data(True, True, False))
            key = bytes(os.environ.get("WEBHOOK-SECRET-KEY"), "utf-8")
            data = bytes(message, "utf-8")
            signature = hmac.new(key, data, digestmod=hashlib.sha256)
            expected_signature = "sha256=" + signature.hexdigest()
            if headers["Twitch-Eventsub-Message-Signature"] != expected_signature:
                print("Signature Mismatch")
                return make_response("failed", 403)
            else:
                print("Signature Match")
                print(request.json["subscription"]["type"])
                if request.json["subscription"]["type"] == "stream.online" and r.get("STREAM-STATUS") != "stream.online":
                    url = "https://api.twitch.tv/helix/streams?user_login={}".format(request.json["event"]["broadcaster_user_login"])
                    request_header =  {
                    'Authorization': 'Bearer {}'.format(os.environ.get("TWITCH-AUTHORIZATION")),
                    'Client-ID': os.environ.get("TWITCH-CLIENT-ID")
                    }
                    response = requests.get(url, headers=request_header).json()
                    twitch_url = "https://www.twitch.tv/{}/".format(response["data"][0]["user_login"])
                    tweet = "{}\n{}".format(response["data"][0]["title"], twitch_url)
                    send_tweet(tweet)
                    send_discord(response["data"][0], "twitch")
                    send_firebase("twitch",response["data"][0])
                r.set("STREAM-STATUS", request.json["subscription"]["type"])
                return make_response("success", 201)

    elif type == "youtube":
        challenge = request.args.get("hub.challenge")
        if challenge:
            return make_response(challenge, 201)
        xml_dict = xmltodict.parse(request.data.decode("utf-8"))
        print(request.data.decode("utf-8"))
        try:
            video_info = xml_dict["feed"]["entry"]
            video_title = video_info["title"]
            video_url = video_info["link"][0]["@href"]
            video_id = video_info["id"]
            if "twitch.tv/newlegacyinc" not in video_title.lower() and video_id not in r.smembers("VIDEOS-POSTED"):
                tweet = ("{}\n{}".format(video_title, video_url))
                send_tweet(tweet)
                send_discord(video_info, "youtube")
                send_firebase("youtube", video_info)
                r.sadd("VIDEOS-POSTED", video_id)
            else:
                print("Video already posted")
        except KeyError as e:
            print("Video not found")
        return make_response("success", 201)

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)