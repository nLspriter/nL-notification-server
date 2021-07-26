from flask import Flask, request, abort, make_response, jsonify, Response
import hmac
import hashlib

app = Flask(__name__)

@app.route('/webhook/<type>', methods=['POST'])
def webhook(type):
    if type == "twitch":
        print(request.json)
        headers = request.headers
        if headers["Twitch-Eventsub-Message-Type"] == "webhook_callback_verification":
            challenge = request.json['challenge']
            print(challenge)
            return make_response(challenge, 201)
        elif headers["Twitch-Eventsub-Message-Type"] == "notification":
            message = str(headers["Twitch-Eventsub-Message-Id"]) + str(headers["Twitch-Eventsub-Message-Timestamp"]) + str(request)
            signature = hmac.new(bytes("wh474r3y0ubl1nd", 'latin-1'), message, digestmod=hashlib.sha256).hexdigest()
            expected_signature = "sha256=" + signature
            print(expected_signature)
            if headers["Twitch-Eventsub-Message-Signature"] != expected_signature:
                return 403
            else:
                print("it worked bitch")
                return 201

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)