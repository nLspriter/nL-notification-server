from flask import make_response
import os
import xmltodict
from helper import *
from datetime import datetime
import traceback


def send_tweet(title, url):
    try:
        if os.path.exists("thumbnail.jpg"):
            media = api.media_upload("thumbnail.jpg")
            media_ids = [media.media_id]
            initial = client.create_tweet(
                text="NEW VIDEO!\n{}".format(title), media_ids=media_ids
            )
            reply = client.create_tweet(
                text="Click here to watch! {}".format(url), in_reply_to_tweet_id=initial.data["id"])
        else:
            initial = client.create_tweet(
                text="NEW VIDEO!\n{}".format(title))
            reply = client.create_tweet(
                text=url, in_reply_to_tweet_id=initial.data["id"])
        print("Tweet sent")
    except tweepy.TweepyException as e:
        print("Tweet could not be sent\n{}".format(e.api_code))


def send_discord(data):
    embed = {
        "username": os.getenv("USERNAME"),
        "avatar_url": "https://newlegacyinc.tv/nL%20Logo.png"
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


# def send_instagram(title):
#     try:
#         if os.path.exists("thumbnail.jpg"):
#             cl.photo_upload("thumbnail.jpg", "NEW VIDEO!\n{}\n\nLink is in our bio!\n\n#wwe #aew #wwegames #wweraw #wwesmackdown #aewdynamite #wcw #ecw".format(title))
#             print("Instagram Post made")
#         else:
#             print("Instagram Post could not be made")
#     except:
#         print("Instagram Post could not be sent")


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

            response = requests.get("https://youtube.googleapis.com/youtube/v3/videos?part=snippet&key={}&id={}".format(
                os.getenv("YOUTUBE-API-KEY"), video_id)).json()

            if video_id not in r.smembers("VIDEOS-POSTED"):
                if response["items"][0]["snippet"]["liveBroadcastContent"].lower() != "upcoming":
                    r.sadd("VIDEOS-POSTED", video_id)
                else:
                    print("Video is not live yet")
                    return make_response("success", 201)
                
            else:
                print("Video already posted")
                return make_response("success", 201)

            if not is_short(video_id):
                if "twitch.tv/newlegacyinc" not in video_title.lower() and comparedate(video_published, r.get("LAST-VIDEO-DATE")):
                    tweet = ("{}\n\n{}".format(video_title, video_url))
                    thumbnail(
                        "https://img.youtube.com/vi/{}/maxresdefault.jpg".format(video_id))
                    send_tweet(video_title, video_url)
                    send_discord(video_info)
                    send_mobile(video_info)
                    send_browser(video_info)
                    # send_instagram(video_title)
                    r.set("LAST-VIDEO", video_id)
                    r.set("LAST-VIDEO-TITLE", video_title)
                    r.set("LAST-VIDEO-DATE", video_published)
        except KeyError:
            print("Video deleted, retrieving last video from channel")
            try:
                req = requests.get("https://www.youtube.com/feeds/videos.xml?channel_id=UC{}".format(
                    os.getenv("YOUTUBE-ID")))
                xml_dict = xmltodict.parse(req.content)
                video_info = xml_dict["feed"]["entry"][0]
                video_id = video_info["yt:videoId"]
                video_title = video_info["title"]
                video_published = video_info["published"]
                load_videos()
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


def is_short(vid):
    url = 'https://www.youtube.com/shorts/' + vid
    ret = requests.head(url)
    if ret.status_code == 200:
        return True
    else:  # whether 303 or other values, it's not short
        return False


def load_videos():
    pageToken = ""
    video_list = []
    while True:
        id_list = []
        playlist_url = "https://youtube.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId=UU{}&key={}{}".format(
            os.getenv("YOUTUBE-ID"), os.getenv("YOUTUBE-API-KEY"), pageToken)
        playlist_response = requests.get(playlist_url).json()
        for x in playlist_response["items"]:
            if "twitch.tv/newlegacyinc" not in x["snippet"]["title"].lower():
                id_list.append(x["snippet"]["resourceId"]["videoId"])
        video_url = "https://youtube.googleapis.com/youtube/v3/videos?part=snippet%2CcontentDetails%2Cstatistics&id={}&key={}".format(
            "%2C".join(id_list), os.getenv("YOUTUBE-API-KEY"))
        video_response = requests.get(video_url).json()
        for y in video_response["items"]:
            videoDetails = {
                "id": y["id"],
                "details": {
                    "title": y["snippet"]["title"],
                    "thumbnail": "https://img.youtube.com/vi/{}/maxresdefault.jpg".format(y["id"]),
                    "publishedAt": y["snippet"]["publishedAt"][:-1],
                    "duration": y["contentDetails"]["duration"]
                }
            }
            video_list.append(videoDetails)
        if "nextPageToken" in playlist_response:
            pageToken = "&pageToken={}".format(
                playlist_response["nextPageToken"])
        else:
            break
    r.set("VIDEO-LIBRARY", json.dumps(video_list))
    return video_list
