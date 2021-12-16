from flask import Flask, request, make_response, render_template
from flask.helpers import send_file
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
from datetime import datetime

app = Flask(__name__)

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

r = redis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)


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
        print("Discord Notification Sent, code {}.".format(result.status_code))


def send_discord(data, platform):
    api = tweepy.API(auth)

    embed = {
        "username": os.environ.get("USERNAME"),
        "avatar_url": api.me().profile_image_url
    }

    if platform.lower() == "youtube":
        url = data["link"]["@href"]
        content = "@everyone {}\n{}".format(data["title"], url)

    elif platform.lower() == "twitch":
        if os.path.exists("thumbnail.jpg"):
            thumbnail = rnd(data["thumbnail_url"].format(
                width=400, height=225))
        else:
            thumbnail = "https://static-cdn.jtvnw.net/ttv-static/404_preview-400x225.jpg"

        url = "https://www.twitch.tv/{}/".format(
            os.environ.get("USERNAME").lower())
        content = "@everyone We're live! \n<{}>".format(url)
        embed["embeds"] = [
            {
                "title": r.get("STREAM-TITLE"),
                "url": url,
                "color": 16711680,
                "author": {
                    "name": os.environ.get("USERNAME")
                },
                "image": {
                    "url": thumbnail
                },
                "footer": {
                    "text": "Category/Game: {}".format(r.get("STREAM-GAME"))
                }
            }
        ]

    embed["content"] = content
    result = requests.post(os.environ.get("DISCORD-WEBHOOK-URL"), json=embed)
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
        url = data["link"]["@href"]
        title = data["title"]
    elif platform.lower() == "twitch":
        url = "https://www.twitch.tv/{}/".format(
            os.environ.get("USERNAME").lower())
        title = "{} {}".format(r.get("STREAM-TITLE"), r.get("STREAM-GAME"))
    fcm_message = {
        "message": {
            "topic": platform,
            "notification": {
                "title": platform.capitalize(),
                "body": title
            },
            "data": {
                "url": url,
            },
            "android": {
                "notification": {
                    "channel_id": "high_importance_channel"
                },
                "direct_boot_ok": True,
                "priority": "high"
            }
        }
    }

    resp = requests.post(FCM_URL, data=json.dumps(
        fcm_message), headers=headers)

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


def comparedate(newdate, lastdate):
    if lastdate == None:
        r.set("LAST-VIDEO-DATE", newdate)
        return True
    if datetime.fromisoformat(newdate) > datetime.fromisoformat(lastdate):
        return True
    else:
        return False


@app.route("/status", methods=["GET"])
def status():
    data = {
        "stream_status": "{} {}".format(r.get("STREAM-TITLE"), r.get("STREAM-GAME")),
        "video_id": r.get("LAST-VIDEO"),
        "video_title": r.get("LAST-VIDEO-TITLE")
    }
    return make_response(data, 201)


@app.route("/webhook/<type>", methods=["GET", "POST"])
def webhook(type):
    try:
        if type == "twitch":
            headers = request.headers

            if headers["Twitch-Eventsub-Message-Type"] == "webhook_callback_verification":
                challenge = request.json["challenge"]

                if challenge:
                    return make_response(challenge, 201)

            elif headers["Twitch-Eventsub-Message-Type"] == "notification":
                message = headers["Twitch-Eventsub-Message-Id"] + \
                    headers["Twitch-Eventsub-Message-Timestamp"] + \
                    str(request.get_data(True, True, False))
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
                        r.set("STREAM-STATUS",
                              request.json["subscription"]["type"])

                    if r.get("STREAM-STATUS") == "stream.online":
                        if "id" in request.json["event"]:
                            if request.json["event"]["id"] not in r.smembers("STREAM-POSTED"):
                                r.sadd("STREAM-POSTED",
                                       request.json["event"]["id"])
                            else:
                                print("Stream already posted")
                                return make_response("success", 201)
                        url = "https://api.twitch.tv/helix/streams?user_login={}".format(
                            os.environ.get("USERNAME").lower())
                        request_header = {
                            "Authorization": "Bearer {}".format(os.environ.get("TWITCH-AUTHORIZATION")),
                            "Client-ID": os.environ.get("TWITCH-CLIENT-ID")
                        }
                        response = requests.get(
                            url, headers=request_header).json()
                        twitch_url = "https://www.twitch.tv/{}/".format(
                            os.environ.get("USERNAME").lower())

                        if request.json["subscription"]["type"] == "channel.update":
                            stream_title = request.json["event"]["title"]
                            stream_game = request.json["event"]["category_name"]
                        else:
                            stream_title = response["data"][0]["title"]
                            stream_game = response["data"][0]["game_name"]
                        if (r.get("STREAM-GAME") != "[{}]".format(stream_game)):
                            tweet = "{} [{}]\n\n{}".format(
                                stream_title, stream_game, twitch_url)
                            r.set("STREAM-TITLE", stream_title.rstrip())
                            r.set("STREAM-GAME", "[{}]".format(stream_game))
                            print(r.get("STREAM-TITLE"))
                            thumbnail("https://static-cdn.jtvnw.net/previews-ttv/live_user_{}.jpg".format(
                                os.environ.get("USERNAME").lower()))
                            send_tweet(tweet)
                            send_discord(response["data"][0], "twitch")
                            send_firebase("twitch", response["data"][0])
                    else:
                        r.set("STREAM-TITLE", "Offline")
                        r.set("STREAM-GAME", "")
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
                video_published = video_info["published"]

                url = "https://youtube.googleapis.com/youtube/v3/videos?part=snippet&key={}&id={}".format(
                    os.environ.get("YOUTUBE-API-KEY"), video_id)
                response = requests.get(url).json()

                if video_id not in r.smembers("VIDEOS-POSTED"):
                    if response["items"][0]["snippet"]["liveBroadcastContent"].lower() != "upcoming":
                        r.sadd("VIDEOS-POSTED", video_id)
                    else:
                        print("Video is not live yet")
                        return make_response("success", 201)
                else:
                    print("Video already posted")
                    return make_response("success", 201)

                if "twitch.tv/newlegacyinc" not in video_title.lower() and comparedate(video_published, r.get("LAST-VIDEO-DATE")):
                    tweet = ("{}\n\n{}".format(video_title, video_url))
                    thumbnail(
                        "https://img.youtube.com/vi/{}/maxresdefault.jpg".format(video_id))
                    send_tweet(tweet)
                    send_discord(video_info, "youtube")
                    send_firebase("youtube", video_info)
                    r.set("LAST-VIDEO", video_id)
                    r.set("LAST-VIDEO-TITLE", video_title)
                    r.set("LAST-VIDEO-DATE", video_published)

            except KeyError:
                print("Video deleted, retrieving last video from channel")
                try:
                    req = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id={}".format(
                        os.environ.get("YOUTUBE-CHANNEL-ID")))
                    xml_dict = xmltodict.parse(req.content)
                    video_info = xml_dict["feed"]["entry"][0]
                    video_id = video_info["yt:videoId"]
                    video_title = video_info["title"]
                    video_published = video_info["published"]
                    r.set("LAST-VIDEO", video_id)
                    r.set("LAST-VIDEO-TITLE", video_title)
                    r.set("LAST-VIDEO-DATE", video_published)
                except KeyError:
                    print("No videos found")
                    r.set("LAST-VIDEO", "None")
        if os.path.exists("thumbnail.jpg"):
            os.remove("thumbnail.jpg")
        return make_response("success", 201)
    except Exception as e:
        send_discord_error(e)


@app.route("/data")
def load_data():
    twitch_url = "https://api.twitch.tv/helix/streams?user_login={}".format(
        os.environ.get("USERNAME").lower())
    request_header = {
        "Authorization": "Bearer {}".format(os.environ.get("TWITCH-AUTHORIZATION")),
        "Client-ID": os.environ.get("TWITCH-CLIENT-ID")
    }
    twitch_response = requests.get(twitch_url, headers=request_header).json()
    try:
        stream_title = twitch_response["data"][0]["title"]
        stream_game = "[{}]".format(twitch_response["data"][0]["game_name"])
    except:
        stream_title = "Offline"
        stream_game = ""
    try:
        youtube_response = requests.get(
            "https://www.youtube.com/feeds/videos.xml?channel_id={}".format(os.environ.get("YOUTUBE-CHANNEL-ID")))
        xml_dict = xmltodict.parse(youtube_response.content)
        video_info = xml_dict["feed"]["entry"][0]
        video_title = video_info["title"]
    except:
        video_title = "No videos found"
    data = {
        "stream_status": "{} {}".format(stream_title, stream_game),
        "video_title": video_title
    }
    return data


@app.route("/post-twitch")
def post_twitch():
    twitch_url = "https://api.twitch.tv/helix/streams?user_login={}".format(
        os.environ.get("USERNAME").lower())
    request_header = {
        "Authorization": "Bearer {}".format(os.environ.get("TWITCH-AUTHORIZATION")),
        "Client-ID": os.environ.get("TWITCH-CLIENT-ID")
    }
    response = requests.get(twitch_url, headers=request_header).json()
    try:
        stream_title = response["data"][0]["title"].rstrip()
        stream_game = "{}".format(response["data"][0]["game_name"])
        twitch_url = "https://www.twitch.tv/{}/".format(
            os.environ.get("USERNAME").lower())
        tweet = "{} [{}]\n\n{}".format(stream_title, stream_game, twitch_url)
        r.set("STREAM-TITLE", stream_title.rstrip())
        r.set("STREAM-GAME", "[{}]".format(stream_game))
        thumbnail("https://static-cdn.jtvnw.net/previews-ttv/live_user_{}.jpg".format(
            os.environ.get("USERNAME").lower()))
        send_tweet(tweet)
        send_discord(response["data"][0], "twitch")
        send_firebase("twitch", response["data"][0])
    except Exception as e:
        send_discord_error(e)
    return make_response("success", 201)


@app.route("/post-youtube")
def post_youtube():
    req = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id={}".format(
        os.environ.get("YOUTUBE-CHANNEL-ID")))
    xml_dict = xmltodict.parse(req.content)
    try:
        video_info = xml_dict["feed"]["entry"][0]
        video_url = video_info["link"]["@href"]
        video_id = video_info["yt:videoId"]
        video_title = video_info["title"]
        video_published = video_info["published"]
        tweet = ("{}\n\n{}".format(video_title, video_url))
        thumbnail(
            "https://img.youtube.com/vi/{}/maxresdefault.jpg".format(video_id))
        send_tweet(tweet)
        send_discord(video_info, "youtube")
        send_firebase("youtube", video_info)
        r.set("LAST-VIDEO", video_id)
        r.set("LAST-VIDEO-TITLE", video_title)
        r.set("LAST-VIDEO-DATE", video_published)
    except Exception as e:
        send_discord_error(e)
    return make_response("success", 201)


@app.route("/notifications")
def notifications():
    data = load_data()
    return render_template("notifications.html", stitle=data["stream_status"], ytitle=data["video_title"])

@app.route("/thumbnail")
def notifications():
    data = load_data()
    return render_template("thumbnail.html")

@app.route("/")
def home():
    return render_template("home.html")

if __name__ == "__main__":
    app.run(ssl_context="adhoc", debug=True, port=443)
