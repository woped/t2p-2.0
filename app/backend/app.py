from flask import Flask, request, jsonify
from gpt_process import ApiCaller

app = Flask(__name__)

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

        # Process the data using the run method of ApiCaller
        result = ac.run(data['text'])

        # Return the outcome of the run method
        return jsonify({"result": result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')