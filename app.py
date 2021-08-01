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
api = tweepy.API(auth)

PROJECT_ID = 'nl-notification-server'
BASE_URL = 'https://fcm.googleapis.com'
FCM_ENDPOINT = 'v1/projects/' + PROJECT_ID + '/messages:send'
FCM_URL = BASE_URL + '/' + FCM_ENDPOINT
SCOPES = ['https://www.googleapis.com/auth/firebase.messaging']

sa_json = json.loads(base64.b64decode(os.environ.get("SERVICE-ACCOUNT-JSON")))
credentials = ServiceAccountCredentials.from_json(sa_json, SCOPES)
access_token_info = credentials.get_access_token()

def send_tweet(tweet):
    try:
        api.update_status(status=tweet)
        print("Tweet sent")
    except tweepy.TweepError as e:
        print("Tweet could not be sent\n{}".format(e.api_code))

def send_discord(url, title, platform, image=None):
    content = "@everyone {}\n{}".format(title, url)
    if platform.lower() == "youtube":
        embed = {
                    "content": content,
                    "username": "newLEGACYinc",
                    "avatar_url": api.me().profile_image_url
                }
    elif platform.lower() == "twitch":
        embed = {
                    "content": content,
                    "username": "newLEGACYinc",
                    "avatar_url": api.me().profile_image_url,
                    "embeds": [
                        {
                            "title": title,
                            "url": url,
                            "color": 16711680,
                            "fields": [
                                {
                                "name": "あｓｄasd",
                                "value": "dfg",
                                "inline": True
                                },
                                {
                                "name": "weeeeeee",
                                "value": "dfg",
                                "inline": True
                                }
                            ],
                            "author": {
                                "name": platform
                            },
                            "timestamp": "2021-07-28T11:58:00.000Z",
                            "image": {
                                "url": image.format(width=320, height=180)
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

def send_firebase(platform):
    headers = {
    'Authorization': 'Bearer ' + access_token_info.access_token,
    'Content-Type': 'application/json; UTF-8',
    }

    fcm_message = {
                    'message': {
                    'topic': platform,
                    'notification': {
                        'title': 'FCM Notification',
                        'body': 'Notification from FCM'
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
                url = "https://api.twitch.tv/helix/streams?user_login={}".format(request.json["event"]["broadcaster_user_login"])
                request_header =  {
                'Authorization': 'Bearer {}'.format(os.environ.get("TWITCH-AUTHORIZATION")),
                'Client-ID': os.environ.get("TWITCH-CLIENT-ID")
                }
                response = requests.get(url, headers=request_header).json()
                twitch_url = "https://www.twitch.tv/{}/".format(response["data"][0]["user_login"])
                tweet = "{}\n{}".format(response["data"][0]["title"], twitch_url)
                send_tweet(tweet)
                send_discord(twitch_url, response["data"][0]["title"], "twitch", response["data"][0]["thumbnail_url"])
                send_firebase("twitch")
                return make_response("success", 201)

    elif type == "youtube":
        challenge = request.args.get("hub.challenge")
        if challenge:
            return make_response(challenge, 201)
        xml_dict = xmltodict.parse(request.data)
        try:
            video_info = xml_dict["feed"]["entry"]
            video_title = video_info["title"]
            video_url = video_info["link"]["@href"]
            video_id = video_info["yt:videoId"]
            r = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True) 
            if "twitch.tv/newlegacyinc" not in video_title.lower() and video_id not in r.smembers("VIDEOS-POSTED"):
                r.sadd("VIDEOS-POSTED", video_id)
                tweet = ("{}\n{}".format(video_title, video_url))
                send_tweet(tweet)
                send_discord(video_url, video_title, "youtube")
                send_firebase("youtube")
            else:
                print("Video already posted")
        except KeyError as e:
            print("Video not found")
        return make_response("success", 201)

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)