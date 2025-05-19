from flask import Flask, request, jsonify

from app.backend.modeltransformer import ModelTransformer
from gpt_process import ApiCaller
from app.config import TRANSFORMER_BASE_URL

app = Flask(__name__)
# app.config['APPLICATION_ROOT'] = '/t2p-2.0'
url = TRANSFORMER_BASE_URL + "/transform"


@app.route('/test_connection', methods=['GET'])
def test():
    try:
        return jsonify("Successful"), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api_call', methods=['POST'])
def api_call():
    try:
        data = request.json

        # Check for missing 'text' or 'api_key' in the request data
        if 'text' not in data or 'api_key' not in data:
            missing = []
            if 'text' not in data:
                missing.append('text')
            if 'api_key' not in data:
                missing.append('api_key')
            return jsonify({"error": f"Missing data for: {', '.join(missing)}"}), 400

        # Create the ApiCaller class object with the extracted API key
        ac = ApiCaller(api_key=data['api_key'])
        transformer = ModelTransformer()

        # Process the data using the run method of ApiCaller
        result_bpmn = ac.conversion_pipeline(data['text'])

        result = transformer.transform(result_bpmn)
        # If the result contains an error message, return it with a 500 status code
        if "{'error': {'message':" in result:
            return jsonify({"error": result}), 500

        # Return the outcome of the run method
        return jsonify({"result": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/_/_/echo')
def echo():
    return jsonify(success=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
