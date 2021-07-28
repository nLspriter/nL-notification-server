from flask import Flask, request, abort, make_response, jsonify, Response
import xmltodict
import hmac
import hashlib
import os
import tweepy
import requests

app = Flask(__name__)

def auth_twitter():
    auth = tweepy.OAuthHandler(os.environ.get("TWITTER-CONSUMER-KEY"), os.environ.get("TWITTER-CONSUMER-SECRET"))
    auth.set_access_token(os.environ.get("TWITTER-ACCESS-TOKEN"), os.environ.get("TWITTER-ACCESS-SECRET"))
    api = tweepy.API(auth)
    return api

def send_tweet(request, response, api):
    tweet = "{}\nhttps://www.twitch.tv/{}/".format(response.json["data"]["title"], request.json["event"]["broadcaster_user_login"])
    api.update_status(status=tweet)
    print("Tweet sent")
    

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
                response = requests.request("GET", url, headers=request_header)
                api = auth_twitter()
                send_tweet(request, response, api)
                return make_response("success", 201)

    elif type == "youtube":
        challenge = request.args.get("hub.challenge")
        if challenge:
            return challenge    
        xml_dict = xmltodict.parse(request.data)
        video_info = xml_dict["feed"]["entry"]
        video_title = video_info["title"]
        video_url = video_info["link"]["@href"]
        print("{}: {}".format(video_title, video_url))
        return make_response("success", 201)

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)