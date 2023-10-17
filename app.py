from flask import Flask, request, Response, make_response, render_template, jsonify
from flask.helpers import send_file
import config
import xmltodict
import os
import requests
from helper import *
import twitch
import youtube
import traceback

app = Flask(__name__)
app.config["REDIS_URL"] = os.getenv("REDIS_URL")


@app.route("/status", methods=["GET"])
def status():
    if (r.get("STREAM-STATUS") == "stream.offline"):
        stream_status = "Offline"
    else:
        stream_status = "{} {}".format(
            r.get("STREAM-TITLE"), r.get("STREAM-GAME"))
    data = {
        "stream_status": stream_status,
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
            # youtube.load_videos()
            return youtube.webhook(request)
    except Exception:
        send_discord_error(traceback.format_exc())


@app.route("/data")
def load_data():
    twitch_url = "https://api.twitch.tv/helix/streams?user_login={}".format(
        os.getenv("USERNAME").lower())
    request_header = {
        "Authorization": "Bearer {}".format(os.getenv("TWITCH-AUTHORIZATION")),
        "Client-ID": os.getenv("TWITCH-CLIENT-ID")
    }
    twitch_response = requests.get(twitch_url, headers=request_header).json()
    try:
        stream_title = twitch_response["data"][0]["title"]
        stream_game = "[{}]".format(twitch_response["data"][0]["game_name"])
        r.set("STREAM-TITLE", stream_title.rstrip())
        r.set("STREAM-GAME", "{}".format(stream_game))
    except:
        stream_title = "Offline"
        stream_game = ""
        r.set("STREAM-TITLE", "Offline")
        r.set("STREAM-GAME", "")
    try:
        youtube_response = requests.get(
            "https://www.youtube.com/feeds/videos.xml?channel_id=UC{}".format(os.getenv("YOUTUBE-ID")))
        xml_dict = xmltodict.parse(youtube_response.content)
        video_info = xml_dict["feed"]["entry"][0]
        video_title = video_info["title"]
        video_id = video_info["yt:videoId"]
        video_published = video_info["published"]
        r.set("LAST-VIDEO", video_id)
        r.set("LAST-VIDEO-TITLE", video_title)
        r.set("LAST-VIDEO-DATE", video_published)
    except:
        video_title = "No videos found"
        video_id = ""
    data = {
        "stream_status": "{} {}".format(stream_title, stream_game),
        "video_title": video_title,
        "video_id": video_id
    }
    youtube.load_videos()
    return data


@app.route("/post-twitch/<type>")
def post_twitch(type):
    twitch_url = "https://api.twitch.tv/helix/streams?user_login={}".format(
        os.getenv("USERNAME").lower())
    request_header = {
        "Authorization": "Bearer {}".format(os.getenv("TWITCH-AUTHORIZATION")),
        "Client-ID": os.getenv("TWITCH-CLIENT-ID")
    }
    response = requests.get(twitch_url, headers=request_header).json()
    try:
        stream_title = response["data"][0]["title"].rstrip()
        stream_game = "{}".format(response["data"][0]["game_name"])
        twitch_url = "https://www.twitch.tv/{}/".format(
            os.getenv("USERNAME").lower())
        tweet = "{} [{}]".format(stream_title, stream_game)
        r.set("STREAM-TITLE", stream_title.rstrip())
        r.set("STREAM-GAME", "[{}]".format(stream_game))
        thumbnail("https://static-cdn.jtvnw.net/previews-ttv/live_user_{}.jpg".format(
            os.getenv("USERNAME").lower()))
        match type:
            case "twitter":
                twitch.send_tweet(tweet, twitch_url)
            case "discord":
                twitch.send_discord()
            case "firebase":
                twitch.send_mobile()
                twitch.send_browser()
            case _:
                twitch.send_tweet(tweet, twitch_url)
                twitch.send_discord()
                twitch.send_mobile()
                twitch.send_browser()
                twitch.send_atproto(tweet, twitch_url)
    except Exception:
        send_discord_error(traceback.format_exc())
    return make_response("success", 201)


@app.route("/post-youtube/<type>")
def post_youtube(type):
    req = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id=UC{}".format(
        os.getenv("YOUTUBE-ID")))
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
        match type:
            case "twitter":
                youtube.send_tweet(video_title, video_url)
            case "discord":
                youtube.send_discord(video_info)
            case "firebase":
                youtube.send_mobile(video_info)
                youtube.send_browser(video_info)
            # case "instagram":
            #     youtube.send_instagram(tweet)
            case _:
                youtube.send_tweet(video_title, video_url)
                youtube.send_discord(video_info)
                youtube.send_mobile(video_info)
                youtube.send_browser(video_info)
                youtube.send_atproto(video_title, video_url)
        # r.set("LAST-VIDEO", video_id)
        # r.set("LAST-VIDEO-TITLE", video_title)
        # r.set("LAST-VIDEO-DATE", video_published)
        # if video_id not in r.smembers("VIDEOS-POSTED"):
        #     r.sadd("VIDEOS-POSTED", video_id)
    except Exception:
        send_discord_error(traceback.format_exc())
    return make_response("success", 201)


@app.route("/subscribe-twitch/<token>", methods=["POST"])
def subscribe_twitch(token):
    subscribe_topic("twitch-browser", token)
    return make_response("success", 201)


@app.route("/unsubscribe-twitch/<token>", methods=["POST"])
def unsubscribe_twitch(token):
    unsubscribe_topic("twitch-browser", token)
    return make_response("success", 201)


@app.route("/subscribe-youtube/<token>", methods=["POST"])
def subscribe_youtube(token):
    subscribe_topic("youtube-browser", token)
    return make_response("success", 201)


@app.route("/unsubscribe-youtube/<token>", methods=["POST"])
def unsubscribe_youtube(token):
    unsubscribe_topic("youtube-browser", token)
    return make_response("success", 201)


@app.route("/load-youtube-library")
def load_youtube_library():
    video_list = youtube.load_videos()
    video_list.sort(key=lambda r: r["details"]["publishedAt"], reverse=True)
    return make_response(jsonify(video_list), 201)


@app.route("/youtube-library")
def youtube_library():
    video_list = [x for x in json.loads(r.get("VIDEO-LIBRARY"))]
    video_list.sort(key=lambda r: r["details"]["publishedAt"], reverse=True)
    return make_response(jsonify(video_list), 201)


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
@requires_auth
def notifications():
    data = load_data()
    return render_template("notifications.html", stitle=data["stream_status"], ytitle=data["video_title"])


@app.route("/thumbnail")
@requires_auth
def thumbnail_overlay():
    return render_template("thumbnail.html")


@app.route("/overlay")
def overlay():
    return render_template("overlay.html")


@app.route("/")
def home():
    return render_template("home.html")


if __name__ == "__main__":
    app.run(ssl_context="adhoc", debug=True, port=443)
