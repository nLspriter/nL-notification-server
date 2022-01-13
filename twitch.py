from flask import Flask, request, make_response
import os
from app import *

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

def send_discord(data):
    api = tweepy.API(auth)

    embed = {
        "username": os.environ.get("USERNAME"),
        "avatar_url": api.me().profile_image_url
    }

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

def webhook(request):
    try:
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
                        send_discord(response["data"][0])
                        send_firebase("twitch", response["data"][0])
                else:
                    r.set("STREAM-TITLE", "Offline")
                    r.set("STREAM-GAME", "")
            return make_response("success", 201)
    except Exception as e:
        app.send_discord_error(e)