from flask import Flask, request, abort, make_response, jsonify, Response
import xmltodict
import hmac
import hashlib
import os
import tweepy
import requests
import redis

app = Flask(__name__)

def auth_twitter():
    auth = tweepy.OAuthHandler(os.environ.get("TWITTER-CONSUMER-KEY"), os.environ.get("TWITTER-CONSUMER-SECRET"))
    auth.set_access_token(os.environ.get("TWITTER-ACCESS-TOKEN"), os.environ.get("TWITTER-ACCESS-SECRET"))
    api = tweepy.API(auth)
    return api

def send_tweet(tweet):
    api = auth_twitter()
    try:
        api.update_status(status=tweet)
        print("Tweet sent")
    except tweepy.TweepError as e:
        print("Tweet could not be sent\n{}".format(e.api_code))

def send_discord(url, title, platform):
    # embed = {
    #             "content": "<{}>".format(url),
    #             "username": "newLEGACYinc",
    #             "embeds": [
    #                 {
    #                 "title": "{}".format(title),
    #                 "url": "{}".format(url),
    #                 "color": 16711680,
    #                 "author": {
    #                     "name": "{}".format(platform)
    #                 },
    #                 "timestamp": "2021-07-28T11:58:00.000Z",
    #                 "image": {
    #                     "url": "{}".format(image)
    #                 }
    #                 }
    #             ]
    #         }        
    embed = {
                "content": "@everyone {}\n{}".format(title, url),
                "username": "newLEGACYinc"
            }
    result = requests.post(os.environ.get("DISCORD-WEBHOOK-URL"), json = embed)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(err)
    else:
        print("Discord Notification Sent, code {}.".format(result.status_code))

    
@app.route('/webhook/<type>', methods=['GET', 'POST'])
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
                url = "https://api.twitch.tv/helix/streams?user_login={}".format(request.json["event"]["broadcaster_user_login"])
                request_header =  {
                'Authorization': 'Bearer {}'.format(os.environ.get("TWITCH-AUTHORIZATION")),
                'Client-ID': os.environ.get("TWITCH-CLIENT-ID")
                }
                response = requests.get(url, headers=request_header).json()
                tweet = "{}\nhttps://www.twitch.tv/{}/".format(response["data"][0]["title"], request.json["event"]["broadcaster_user_login"])
                send_tweet(tweet)
                return make_response("success", 201)

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
            r = redis.from_url(os.environ.get("REDIS_URL")) 
            last_video = {"LAST-VIDEO": video_id}
            r.mset(last_video)
            if "twitch.tv/newlegacyinc" not in video_title.lower() and video_id != r.get("LAST-VIDEO").decode("utf-8"):
                tweet = ("{}\n{}".format(video_title, video_url))
                send_tweet(tweet)
                send_discord(video_url, video_title, "YouTube")
        except KeyError as e:
            print("Video not found")
        return make_response("success", 201)

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)