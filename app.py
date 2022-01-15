from flask import Flask, request, make_response, render_template
from pyasn1.type.univ import Null
import xmltodict
import os
import requests
from helper import *
import twitch
import youtube
import traceback

app = Flask(__name__)

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
            return twitch.webhook(request)
        elif type == "youtube":
            return youtube.webhook(request)
    except Exception:
        send_discord_error(traceback.format_exc())

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
        twitch.send_tweet(tweet)
        twitch.send_discord(response["data"][0])
        twitch.send_firebase("twitch", response["data"][0])
    except Exception:
        send_discord_error(traceback.format_exc())
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
        youtube.send_tweet(tweet)
        youtube.send_discord(video_info)
        youtube.send_firebase(video_info)
        r.set("LAST-VIDEO", video_id)
        r.set("LAST-VIDEO-TITLE", video_title)
        r.set("LAST-VIDEO-DATE", video_published)
    except Exception:
        send_discord_error(traceback.format_exc())
    return make_response("success", 201)

@app.route("/")
def home():
    data = load_data()
    return render_template("home.html", stitle=data["stream_status"], ytitle=data["video_title"])

if __name__ == "__main__":
    app.run(ssl_context="adhoc", debug=True, port=443)
