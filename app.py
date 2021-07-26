from flask import Flask, request, abort, make_response, jsonify, Response

app = Flask(__name__)

@app.route('/webhook/twitch', methods=['POST'])
def webhook():
    print(request.json)
    print(request.headers)
    data = request.json['challenge']
    print(data)
    return make_response(data, 201)

if __name__ == '__main__':
    app.run(ssl_context='adhoc', debug=True, port=443)