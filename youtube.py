from flask import make_response
import os
import xmltodict
from helper import *
from datetime import datetime
import traceback


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
        "username": os.getenv("USERNAME"),
        "avatar_url": api.me().profile_image_url
    }

    url = data["link"]["@href"]
    embed["content"] = "@everyone {}\n{}".format(data["title"], url)
    for count in range(5):
        result = requests.post(os.getenv(
            "DISCORD-WEBHOOK-URL"), json=embed)

        if result.status_code == 204:
            break
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Discord Notification Sent, code {}.".format(result.status_code))


def send_mobile(data):
    access_token_info = credentials.get_access_token()
    headers = {
        "Authorization": "Bearer " + access_token_info.access_token,
        "Content-Type": "application/json; UTF-8",
    }

    url = data["link"]["@href"]
    title = data["title"]
    fcm_message = {
        "message": {
            "topic": "youtube",
            "notification": {
                "title": "YouTube",
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


def send_browser(data):
    access_token_info = credentials.get_access_token()
    headers = {
        "Authorization": "Bearer " + access_token_info.access_token,
        "Content-Type": "application/json; UTF-8",
    }

    url = data["link"]["@href"]
    title = data["title"]
    fcm_message = {
        "message": {
            "topic": "youtube-browser",
            "data": {
                "title": "YouTube",
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


def webhook(request):
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
                os.getenv("YOUTUBE-API-KEY"), video_id)
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
                send_discord(video_info)
                send_mobile(video_info)
                send_browser(video_info)
                r.set("LAST-VIDEO", video_id)
                r.set("LAST-VIDEO-TITLE", video_title)
                r.set("LAST-VIDEO-DATE", video_published)

        except KeyError:
            print("Video deleted, retrieving last video from channel")
            try:
                req = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id={}".format(
                    os.getenv("YOUTUBE-CHANNEL-ID")))
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
    except Exception:
        send_discord_error(traceback.format_exc())


def comparedate(newdate, lastdate):
    if lastdate == None:
        r.set("LAST-VIDEO-DATE", newdate)
        return True
    if datetime.fromisoformat(newdate) > datetime.fromisoformat(lastdate):
        return True
    else:
        return False


def load_videos():
    pageToken = ""
    while True:
        url = "https://youtube.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId=UU5iCLgl2ccta5MqTf2VU8bQ&&key={}{}".format(
            os.getenv("YOUTUBE-API-KEY"), pageToken)
        response = requests.get(url).json()
        for x in response["items"]:
            if x["snippet"]["resourceId"]["videoId"] not in r.smembers("VIDEOS-LIBRARY"):
                videoDetails = {
                    "id": x["snippet"]["resourceId"]["videoId"],
                    "details": {
                        "title": x["snippet"]["title"],
                        "thumbnail": "https://img.youtube.com/vi/{}/maxresdefault.jpg".format(x["snippet"]["resourceId"]["videoId"]),
                        "publishedAt": x["snippet"]["publishedAt"]
                    }
                }
                rdata = json.dumps(videoDetails)
                r.sadd("VIDEO-LIBRARY", rdata)
        if "nextPageToken" in response:
            pageToken = response["nextPageToken"]
        else:
            break
