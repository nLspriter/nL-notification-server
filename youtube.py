from flask import Flask, request, make_response
import os
import xmltodict
from app import *

def send_tweet(tweet):
    api = tweepy.API(app.auth)
    try:
        if os.path.exists("thumbnail.jpg"):
            api.update_with_media("thumbnail.jpg", status=tweet)
            print("Tweet sent")
        else:
            api.update_status(status=tweet)
    except tweepy.TweepError as e:
        print("Tweet could not be sent\n{}".format(e.api_code))

def send_discord(data, platform):
    api = tweepy.API(app.auth)

    embed = {
        "username": os.environ.get("USERNAME"),
        "avatar_url": api.me().profile_image_url
    }

    url = data["link"]["@href"]
    embed["content"] = "@everyone {}\n{}".format(data["title"], url)
    result = requests.post(os.environ.get("DISCORD-WEBHOOK-URL"), json=embed)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Discord Notification Sent, code {}.".format(result.status_code))

def send_firebase(platform, data):
    access_token_info = app.credentials.get_access_token()
    headers = {
        "Authorization": "Bearer " + access_token_info.access_token,
        "Content-Type": "application/json; UTF-8",
    }

    url = data["link"]["@href"]
    title = data["title"]
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


def webhook():
    try:        
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

            if video_id not in app.r.smembers("VIDEOS-POSTED"):
                if response["items"][0]["snippet"]["liveBroadcastContent"].lower() != "upcoming":
                    app.r.sadd("VIDEOS-POSTED", video_id)
                else:
                    print("Video is not live yet")
                    return make_response("success", 201)
            else:
                print("Video already posted")
                return make_response("success", 201)

            if "twitch.tv/newlegacyinc" not in video_title.lower() and comparedate(video_published, app.r.get("LAST-VIDEO-DATE")):
                tweet = ("{}\n\n{}".format(video_title, video_url))
                app.thumbnail(
                    "https://img.youtube.com/vi/{}/maxresdefault.jpg".format(video_id))
                send_tweet(tweet)
                send_discord(video_info, "youtube")
                send_firebase("youtube", video_info)
                app.r.set("LAST-VIDEO", video_id)
                app.r.set("LAST-VIDEO-TITLE", video_title)
                app.r.set("LAST-VIDEO-DATE", video_published)

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
                app.r.set("LAST-VIDEO", video_id)
                app.r.set("LAST-VIDEO-TITLE", video_title)
                app.r.set("LAST-VIDEO-DATE", video_published)
            except KeyError:
                print("No videos found")
                app.r.set("LAST-VIDEO", "None")
        if os.path.exists("thumbnail.jpg"):
            os.remove("thumbnail.jpg")
        return make_response("success", 201)
    except Exception as e:
        send_discord_error(e)


def comparedate(newdate, lastdate):
    if lastdate == None:
        app.r.set("LAST-VIDEO-DATE", newdate)
        return True
    if datetime.fromisoformat(newdate) > datetime.fromisoformat(lastdate):
        return True
    else:
        return False