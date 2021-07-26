from flask import Flask, request, abort, make_response, jsonify, Response
import hmac
import hashlib
import xmltodict

app = Flask(__name__)

@app.route('/webhook/<type>', methods=['GET', 'POST'])
def webhook(type):
    if type == "twitch":
        challenge = request.json['challenge']
        if challenge:
            return make_response(challenge, 201)
        headers = request.headers
        message = headers["Twitch-Eventsub-Message-Id"] + headers["Twitch-Eventsub-Message-Timestamp"] + str(request.get_data(True, True, False))
        key = bytes("wh474r3y0ubl1nd", "utf-8")
        data = bytes(message, "utf-8")
        signature = hmac.new(key, data, digestmod=hashlib.sha256)
        expected_signature = "sha256=" + signature.hexdigest()
        if headers["Twitch-Eventsub-Message-Signature"] != expected_signature:
            print("it worked but it didn't get accepted")
            return make_response("failed", 403)
        else:
            print("it worked bitch")
            return make_response("success", 201)

    elif type == "youtube":
        challenge = request.args.get("hub.challenge")
        if challenge:
            return challenge    
        xml_dict = xmltodict.parse(request.data)
        video_url = xml_dict["feed"]["entry"]["link"]["@href"]
        print("New video URL: {}".format(video_url))
        return make_response("success", 201)

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)