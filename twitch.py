from flask import make_response
import os
from helper import *
from random import choice
from string import ascii_letters
import hmac
import hashlib
import traceback


def rnd(url):
    return url + "?rnd=" + "".join([choice(ascii_letters) for _ in range(6)])


def send_tweet(title, url):
    try:
        if os.path.exists("thumbnail.jpg"):
            media = twitterAPI.media_upload("thumbnail.jpg")
            media_ids = [media.media_id]
            initial = twitterClient.create_tweet(
                text="WE'RE LIVE!\n{}".format(title), media_ids=media_ids
            )
            reply = twitterClient.create_tweet(
                text="Click here to watch! {}".format(url), in_reply_to_tweet_id=initial.data["id"])
        else:
            initial = twitterClient.create_tweet(
                text="WE'RE LIVE!\n{}".format(title))
            reply = twitterClient.create_tweet(
                text=url, in_reply_to_tweet_id=initial.data["id"])
        print("Tweet sent")
    except tweepy.TweepyException as e:
        print("Tweet could not be sent\n{}".format(e.api_code))


def send_discord():
    embed = {
        "username": os.getenv("USERNAME"),
        "avatar_url": "https://newlegacyinc.tv/nL%20Logo.png"
    }

    if os.path.exists("thumbnail.jpg"):
        thumbnail = rnd("https://static-cdn.jtvnw.net/previews-ttv/live_user_{}-400x225.jpg".format(
            os.getenv("USERNAME").lower()))
    else:
        thumbnail = "https://static-cdn.jtvnw.net/ttv-static/404_preview-400x225.jpg"

    url = "https://www.twitch.tv/{}/".format(
        os.getenv("USERNAME").lower())
    content = "@everyone We're live! \n<{}>".format(url)
    embed["embeds"] = [
        {
            "title": r.get("STREAM-TITLE"),
            "url": url,
            "color": 16711680,
            "author": {
                "name": os.getenv("USERNAME")
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
    for _ in range(5):
        result = requests.post(os.getenv("DISCORD-WEBHOOK-URL"), json=embed)
        if result.status_code == 204:
            break
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Discord Notification Sent, code {}.".format(result.status_code))


def send_mobile():
    access_token_info = credentials.get_access_token()
    headers = {
        "Authorization": "Bearer " + access_token_info.access_token,
        "Content-Type": "application/json; UTF-8",
    }

    url = "https://www.twitch.tv/{}/".format(
        os.getenv("USERNAME").lower())
    title = "{} {}".format(r.get("STREAM-TITLE"), r.get("STREAM-GAME"))
    fcm_message = {
        "message": {
            "topic": "twitch",
            "notification": {
                "title": "Twitch",
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
        print("Message sent to Firebase Mobile for delivery, response:")
        print(resp.text)
    else:
        print("Unable to send message to Firebase")
        print(resp.text)


def send_browser():
    access_token_info = credentials.get_access_token()
    headers = {
        "Authorization": "Bearer " + access_token_info.access_token,
        "Content-Type": "application/json; UTF-8",
    }

    url = "https://www.twitch.tv/{}/".format(
        os.getenv("USERNAME").lower())
    title = "{} {}".format(r.get("STREAM-TITLE"), r.get("STREAM-GAME"))
    fcm_message = {
        "message": {
            "topic": "twitch-browser",
            "data": {
                "title": "Twitch",
                "body": title,
                "url": url,
            }
        }
    }

    resp = requests.post(FCM_URL, data=json.dumps(
        fcm_message), headers=headers)

    if resp.status_code == 200:
        print("Message sent to Firebase Browser for delivery, response:")
        print(resp.text)
    else:
        print("Unable to send message to Firebase")
        print(resp.text)


def send_atproto(title, url):
    text = ("WE'RE LIVE!\n{}\n\nClick here to watch!".format(title))
    url_positions = extract_url_byte_positions(text)
    facets = []

    for link in url_positions:
        facets.append(
            atproto.models.AppBskyRichtextFacet.Main(
                features=[atproto.models.AppBskyRichtextFacet.Link(uri=url)],
                index=atproto.models.AppBskyRichtextFacet.ByteSlice(
                    byte_start=link[1], byte_end=link[2]),
            )
        )

    if os.path.exists("thumbnail.jpg"):
        with open('thumbnail.jpg', 'rb') as f:
            img_data = f.read()

            upload = blueSkyClient.com.atproto.repo.upload_blob(img_data)
            images = [atproto.models.AppBskyEmbedImages.Image(
                alt='Img alt', image=upload.blob)]
            embed = atproto.models.AppBskyEmbedImages.Main(images=images)

            blueSkyClient.com.atproto.repo.create_record(
                atproto.models.ComAtprotoRepoCreateRecord.Data(
                    repo=blueSkyClient.me.did,
                    collection=atproto.models.ids.AppBskyFeedPost,
                    record=atproto.models.AppBskyFeedPost.Main(
                        created_at=blueSkyClient.get_current_time_iso(), text=text, embed=embed, facets=facets
                    ),
                )
            )


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
            key = bytes(os.getenv("WEBHOOK-SECRET-KEY"), "utf-8")
            data = bytes(message, "utf-8")
            signature = hmac.new(key, data, digestmod=hashlib.sha256)
            expected_signature = "sha256=" + signature.hexdigest()

            if headers["Twitch-Eventsub-Message-Signature"] != expected_signature:
                return make_response("failed", 403)

            if "stream" in request.json["subscription"]["type"]:
                r.set("STREAM-STATUS",
                      request.json["subscription"]["type"])

            if r.get("STREAM-STATUS") == "stream.online":
                if "id" in request.json["event"]:
                    if request.json["event"]["id"] not in r.smembers("STREAM-POSTED"):
                        r.sadd("STREAM-POSTED",
                               request.json["event"]["id"])
                    else:
                        return make_response("success", 201)
                url = "https://api.twitch.tv/helix/streams?user_login={}".format(
                    os.getenv("USERNAME").lower())
                request_header = {
                    "Authorization": "Bearer {}".format(os.getenv("TWITCH-AUTHORIZATION")),
                    "Client-ID": os.getenv("TWITCH-CLIENT-ID")
                }
                response = requests.get(url, headers=request_header).json()
                twitch_url = "https://www.twitch.tv/{}/".format(
                    os.getenv("USERNAME").lower())

                if request.json["subscription"]["type"] == "channel.update":
                    r.set("STREAM-TITLE",
                          request.json["event"]["title"].rstrip())
                    stream_game = request.json["event"]["category_name"]
                    if (r.get("STREAM-GAME") != "[{}]".format(stream_game)):
                        r.set("STREAM-GAME", "[{}]".format(stream_game))
                    else:
                        return make_response("success", 201)
                tweet = "{} {}".format(
                    r.get("STREAM-TITLE"), r.get("STREAM-GAME"))
                thumbnail("https://static-cdn.jtvnw.net/previews-ttv/live_user_{}.jpg".format(
                    os.getenv("USERNAME").lower()))
                send_tweet(tweet, twitch_url)
                send_discord()
                send_mobile()
                send_browser()
                send_atproto(tweet, twitch_url)
            else:
                if request.json["subscription"]["type"] == "channel.update":
                    r.set(
                        "STREAM-TITLE", request.json["event"]["title"].rstrip())
                    r.set(
                        "STREAM-GAME", "[{}]".format(request.json["event"]["category_name"]))
            return make_response("success", 201)
    except Exception:
        send_discord_error(traceback.format_exc())
