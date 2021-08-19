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
from random import choice
from string import ascii_letters
import cv2
import instagrapi
import email
import imaplib
import re

app = Flask(__name__)

auth = tweepy.OAuthHandler(os.environ.get("TWITTER-CONSUMER-KEY"), os.environ.get("TWITTER-CONSUMER-SECRET"))
auth.set_access_token(os.environ.get("TWITTER-ACCESS-TOKEN"), os.environ.get("TWITTER-ACCESS-SECRET"))

BASE_URL = "https://fcm.googleapis.com"
FCM_ENDPOINT = "v1/projects/{}/messages:send".format(os.environ.get("FCM-PROJECT-ID"))
FCM_URL = BASE_URL + "/" + FCM_ENDPOINT
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

sa_json = json.loads(base64.b64decode(os.environ.get("SERVICE-ACCOUNT-JSON")))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(sa_json, SCOPES)

r = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)

igclient = instagrapi.Client()

def rnd(url):
    return url + "?rnd=" + "".join([choice(ascii_letters) for _ in range(6)])

def send_tweet(tweet):
    api = tweepy.API(auth)
    try:
        if os.path.exists("thumbnail.jpg"):
            api.update_with_media("thumbnail.jpg", status=tweet)
            print("Tweet sent")
        else:
            api.update_status(status=tweet)
    except tweepy.TweepError as e:
        print("Tweet could not be sent\n{}".format(e.api_code))

def send_instagram(message):
    igclient.login(os.environ.get("INSTAGRAM-USERNAME"), os.environ.get("INSTAGRAM-PASSWORD"))
    try:
        if os.path.exists("thumbnail.jpg"):
            igclient.photo_upload("thumbnail.jpg", status=message)
            print("Instagram post sent")
    except:
        print("Could not post to Instagram")

def send_discord(data, platform):
    api = tweepy.API(auth)
    if platform.lower() == "youtube":
        content = "@everyone {}\n{}".format(data["title"], data["link"]["@href"])
        embed = {
                    "content": content,
                    "username": os.environ.get("USERNAME"),
                    "avatar_url": api.me().profile_image_url
                }
    elif platform.lower() == "twitch":
        if os.path.exists("thumbnail.jpg"):
            thumbnail = rnd(data["thumbnail_url"].format(width=400, height=225))
        else:
            thumbnail = "https://static-cdn.jtvnw.net/ttv-static/404_preview-400x225.jpg"
        url = "https://www.twitch.tv/{}/".format(data["user_login"])
        content = "@everyone {}\n<{}>".format(data["title"], url)
        embed = {
                    "content": content,
                    "username": os.environ.get("USERNAME"),
                    "avatar_url": api.me().profile_image_url,
                    "embeds": [
                        {
                            "title": data["title"],
                            "url": url,
                            "color": 16711680,
                            "author": {
                                "name": os.environ.get("USERNAME")
                            },
                            "image": {
                                "url": thumbnail
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
    headers = {
    "Authorization": "Bearer " + access_token_info.access_token,
    "Content-Type": "application/json; UTF-8",
    }

    if platform.lower() == "youtube":
        fcm_message = {
                        "message": {
                        "topic": platform,
                        "data": {
                            "url": data["link"]["@href"],
                            "title": "YouTube",
                            "body": data["title"]
                        },
                        "android": {
                            "direct_boot_ok": True,
                            "priority": "high"
                        }
                    }
                }
    elif platform.lower() == "twitch":
        url = "https://www.twitch.tv/{}/".format(data["user_login"])
        fcm_message = {
                        "message": {
                        "topic": platform,
                        "data": {
                            "url": url,
                            "title": "Twitch",
                            "body": data["title"]
                        },
                        "android": {
                            "direct_boot_ok": True,
                            "priority": "high"
                        }
                    }
                }

    resp = requests.post(FCM_URL, data=json.dumps(fcm_message), headers=headers)

    if resp.status_code == 200:
        print("Message sent to Firebase for delivery, response:")
        print(resp.text)
    else:
        print("Unable to send message to Firebase")
        print(resp.text)
    
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

def get_code_from_email(username):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(os.environ.get("INSTAGRAM_EMAIL_ACCOUNT"), os.environ.get("INSTAGRAM_EMAIL_PASSWORD"))
    mail.select("inbox")
    result, data = mail.search(None, "(UNSEEN)")
    assert result == "OK", "Error1 during get_code_from_email: %s" % result
    ids = data.pop().split()
    for num in reversed(ids):
        mail.store(num, "+FLAGS", "\\Seen")  # mark as read
        result, data = mail.fetch(num, "(RFC822)")
        assert result == "OK", "Error2 during get_code_from_email: %s" % result
        msg = email.message_from_string(data[0][1].decode())
        payloads = msg.get_payload()
        if not isinstance(payloads, list):
            payloads = [msg]
        code = None
        for payload in payloads:
            body = payload.get_payload(decode=True).decode()
            if "<div" not in body:
                continue
            match = re.search(">([^>]*?({u})[^<]*?)<".format(u=username), body)
            if not match:
                continue
            print("Match from email:", match.group(1))
            match = re.search(r">(\d{6})<", body)
            if not match:
                print('Skip this email, "code" not found')
                continue
            code = match.group(1)
        return code
    return False


def get_code_from_sms(username):
    while True:
        code = input(f"Enter code (6 digits) for {username}: ").strip()
        if code and code.isdigit():
            return code
    return None


def challenge_code_handler(username, choice):
    if choice == 0:
        return get_code_from_sms(username)
    elif choice == 1:
        return get_code_from_email(username)
    return False


@app.route("/status", methods=["GET"])
def status():
    data = {
        "stream_status": r.get("STREAM-TITLE"),
        "video_id": r.get("LAST-VIDEO"),
        "video_title": r.get("LAST-VIDEO-TITLE")
    }
    return make_response(data, 201)


@app.route("/webhook/<type>", methods=["GET", "POST"])
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

                if "stream" in request.json["subscription"]["type"]:
                    r.set("STREAM-STATUS", request.json["subscription"]["type"])

                if request.json["subscription"]["type"] == "stream.online":
                    if request.json["event"]["id"] not in r.smembers("STREAM-POSTED"):
                        r.sadd("STREAM-POSTED", request.json["event"]["id"])
                    else: 
                        print("Stream already posted")
                        return make_response("success", 201)

                    url = "https://api.twitch.tv/helix/streams?user_login={}".format(request.json["event"]["broadcaster_user_login"])
                    request_header =  {
                    "Authorization": "Bearer {}".format(os.environ.get("TWITCH-AUTHORIZATION")),
                    "Client-ID": os.environ.get("TWITCH-CLIENT-ID")
                    }
                    response = requests.get(url, headers=request_header).json()
                    twitch_url = "https://www.twitch.tv/{}/".format(response["data"][0]["user_login"])
                    message = "{} [{}]\n\n{}".format(response["data"][0]["title"],response["data"][0]["game_name"], twitch_url)
                    r.set("STREAM-TITLE", response["data"][0]["title"])
                    thumbnail("https://static-cdn.jtvnw.net/previews-ttv/live_user_{}.jpg".format(response["data"][0]["user_login"]))
                    send_tweet(message)
                    send_instagram(message)
                    send_discord(response["data"][0], "twitch")
                    send_firebase("twitch",response["data"][0])
                else:
                    r.set("STREAM-TITLE", "Offline")
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

            if video_id not in r.smembers("VIDEOS-POSTED"):
                r.sadd("VIDEOS-POSTED", video_id)
            else:
                print("Video already posted")
                return make_response("success", 201)
        
            if "twitch.tv/newlegacyinc" not in video_title.lower():
                message = ("{}\n\n{}".format(video_title, video_url))
                thumbnail("https://img.youtube.com/vi/{}/maxresdefault.jpg".format(video_id))
                send_tweet(message)
                send_instagram(message)
                send_discord(video_info, "youtube")
                send_firebase("youtube", video_info)
                r.set("LAST-VIDEO", video_id)
                r.set("LAST-VIDEO-TITLE", video_title)

        except KeyError:
            print("Video deleted, retrieving last video from channel")
            try:
                req = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id={}".format(os.environ.get("YOUTUBE-CHANNEL-ID")))
                xml_dict = xmltodict.parse(req.content)
                video_info = xml_dict["feed"]["entry"][0]
                video_id = video_info["yt:videoId"]
                video_title = video_info["title"]
                r.set("LAST-VIDEO", video_id)
                r.set("LAST-VIDEO-TITLE", video_title)
            except KeyError:
                print("No videos found")
                r.set("LAST-VIDEO", "None")
    if os.path.exists("thumbnail.jpg"):
        os.remove("thumbnail.jpg")
    return make_response("success", 201)

if __name__ == "__main__":
    igclient.challenge_code_handler = challenge_code_handler
    app.run(ssl_context="adhoc", debug=True, port=443)