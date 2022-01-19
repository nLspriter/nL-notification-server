from flask import Flask, request, Response, make_response, render_template
from flask.helpers import send_file
import xmltodict
import os
import requests
from helper import *
import twitch
import youtube
import traceback

app = Flask(__name__)
app.config["REDIS_URL"] = os.environ.get("REDIS_URL")

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
        video_id = video_info["yt:videoId"]
    except:
        video_title = "No videos found"
        video_id = ""
    data = {
        "stream_status": "{} {}".format(stream_title, stream_game),
        "video_title": video_title,
        "video_id": video_id
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
        if video_id not in r.smembers("VIDEOS-POSTED"):
            r.sadd("VIDEOS-POSTED", video_id)
    except Exception:
        send_discord_error(traceback.format_exc())
    return make_response("success", 201)

@app.route("/trigger", methods=["GET", "POST"])
def trigger():
    def respond():
        if request.method == "POST":
            print("test")
            yield "data: {}\nevent: trigger\n\n"
        else:
            yield "data: {}\nevent: null\n\n"
    return Response(respond(), mimetype='text/event-stream')

@app.route("/notifications")
def notifications():
    data = load_data()
    return render_template("notifications.html", stitle=data["stream_status"], ytitle=data["video_title"])


@app.route("/thumbnail")
def thumbnail():
    return render_template("thumbnail.html")


@app.route("/overlay")
def overlay():
    return render_template("overlay.html")


@app.route("/")
def home():
    return render_template("home.html")

if __name__ == "__main__":
    app.run(ssl_context="adhoc", debug=True, port=443)
