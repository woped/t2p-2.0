import requests

import app.config


class model_transformer:
    def __init__(self, model, tokenizer):
        self.transformer_url = app.config.TRANSFORMER_BASE_URL + "/transform"

    def transform(self, bpmn_xml):
        """
        Transform the BPMN XML using the transformer model.
        :param bpmn_xml: The BPMN XML to transform.
        :return: The transformed BPMN XML.
        """
        query_params = {
            "direction": "bpmntopnml"
        }
        request_body_data = {
            "bpmn": bpmn_xml
        }

        try:
            response = requests.post(
                self.transformer_url,
                params=query_params,
                data=request_body_data  # Use 'data' for form-urlencoded body
            )

            # Check if the request was successful (status code 2xx)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

            # If successful, the response content is the transformed XML
            transformed_xml_text = response.text

            return transformed_xml_text

        except requests.exceptions.RequestException as e:
            # Handle any errors that occurred during the request (e.g., network issues, API returning an error)
            print(f"An error occurred during the API call: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Status Code: {e.response.status_code}")
                # The error response body might contain details about the error
                print(f"Error Response Body: {e.response.text}")

