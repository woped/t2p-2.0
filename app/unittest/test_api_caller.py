import json
import os
import time
from backend.gpt_process import ApiCaller

class ApiCallerTester:
    """
    Test class for ApiCaller that reads prompts from a config file
    and sends them to the OpenAI API using the ApiCaller.
    """
    
    def __init__(self, api_key):
        """
        Initialize the tester with an API key.
        
        Args:
            api_key (str, optional): OpenAI API key. If not provided, it will be read from environment variable.
        """
        self.api_key = "API_KEY"
        if not self.api_key:
            raise ValueError("API key not provided and not found in environment variables")
        
        self.api_caller = ApiCaller(self.api_key)
    
    def load_prompts_from_config(self, config_module):
        """
        Load prompts from a config module.
        
        Args:
            config_module: The imported config module containing the prompts list
            
        Returns:
            list: List of prompts
        """
        if not hasattr(config_module, 'PROMPTS'):
            raise AttributeError("Config module doesn't have a PROMPTS attribute")
        
        return config_module.PROMPTS
    
    def test_prompts(self, prompts, system_prompt=None, delay=1, save_results=True, output_file="api_results.json"):
        """
        Test a list of prompts using the ApiCaller.
        
        Args:
            prompts (list): List of prompt strings or dictionaries
            system_prompt (str, optional): Default system prompt to use if not specified in prompt dict
            delay (int, optional): Delay between API calls in seconds
            save_results (bool, optional): Whether to save results to a file
            output_file (str, optional): File name to save results
            
        Returns:
            list: List of response dictionaries
        """
        results = []
        
        for i, prompt in enumerate(prompts):
            print(f"\n[{i+1}/{len(prompts)}] Processing prompt...")
            
            # Handle both string prompts and dictionary prompts
            if isinstance(prompt, dict):
                user_text = prompt.get('user_text', '')
                curr_system_prompt = prompt.get('system_prompt', system_prompt)
                prompt_name = prompt.get('name', f'Prompt {i+1}')
            else:
                user_text = prompt
                curr_system_prompt = system_prompt
                prompt_name = f'Prompt {i+1}'
            
            # Skip empty prompts
            if not user_text and not curr_system_prompt:
                print(f"Skipping empty prompt: {prompt_name}")
                continue
                
            print(f"Executing: {prompt_name}")
            try:
                # Call the API
                start_time = time.time()
                response = self.api_caller.call_api(
                    system_prompt=curr_system_prompt,
                    user_text=user_text
                )
                elapsed_time = time.time() - start_time
                
                result = {
                    'name': prompt_name,
                    'system_prompt': curr_system_prompt,
                    'user_text': user_text,
                    'response': response,
                    'elapsed_time': elapsed_time
                }
                
                results.append(result)
                
                print(f"Response received in {elapsed_time:.2f}s:")
                print("-" * 40)
                print(response[:500] + "..." if len(response) > 500 else response)
                print("-" * 40)
                
            except Exception as e:
                print(f"Error processing prompt '{prompt_name}': {str(e)}")
                results.append({
                    'name': prompt_name,
                    'system_prompt': curr_system_prompt,
                    'user_text': user_text,
                    'error': str(e)
                })
            
            # Add delay between API calls to avoid rate limiting
            if i < len(prompts) - 1 and delay > 0:
                print(f"Waiting {delay} second(s) before next API call...")
                time.sleep(delay)
        
        # Save results to file
        if save_results and results:
            try:
                with open(output_file, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"\nResults saved to {output_file}")
            except Exception as e:
                print(f"Error saving results to file: {str(e)}")
        
        return results
    
    def test_bpmn_conversion(self, process_descriptions, delay=1, save_results=True, output_file="bpmn_results.json"):
        """
        Test BPMN conversion for a list of process descriptions.
        
        Args:
            process_descriptions (list): List of process description strings or dictionaries
            delay (int, optional): Delay between API calls in seconds
            save_results (bool, optional): Whether to save results to a file
            output_file (str, optional): File name to save results
            
        Returns:
            list: List of response dictionaries
        """
        results = []
        
        for i, desc in enumerate(process_descriptions):
            print(f"\n[{i+1}/{len(process_descriptions)}] Processing BPMN conversion...")
            
            # Handle both string descriptions and dictionary descriptions
            if isinstance(desc, dict):
                description = desc.get('description', '')
                desc_name = desc.get('name', f'Process {i+1}')
            else:
                description = desc
                desc_name = f'Process {i+1}'
                
            # Skip empty descriptions
            if not description:
                print(f"Skipping empty description: {desc_name}")
                continue
                
            print(f"Converting: {desc_name}")
            try:
                # Call the conversion pipeline
                start_time = time.time()
                xml_result = self.api_caller.conversion_pipeline(description)
                elapsed_time = time.time() - start_time
                
                result = {
                    'name': desc_name,
                    'description': description,
                    'xml_result': xml_result,
                    'elapsed_time': elapsed_time
                }
                
                results.append(result)
                
                print(f"Conversion completed in {elapsed_time:.2f}s")
                print("-" * 40)
                print(xml_result[:500] + "..." if len(xml_result) > 500 else xml_result)
                print("-" * 40)
                
            except Exception as e:
                print(f"Error converting process '{desc_name}': {str(e)}")
                results.append({
                    'name': desc_name,
                    'description': description,
                    'error': str(e)
                })
            
            # Add delay between API calls to avoid rate limiting
            if i < len(process_descriptions) - 1 and delay > 0:
                print(f"Waiting {delay} second(s) before next conversion...")
                time.sleep(delay)
        
        # Save results to file
        if save_results and results:
            try:
                with open(output_file, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"\nResults saved to {output_file}")
            except Exception as e:
                print(f"Error saving results to file: {str(e)}")
        
        return results

if __name__ == "__main__":
    # Example usage
    import app.unittest.test_config as test_config  # Import your config module
    
    # Initialize the tester
    tester = ApiCallerTester()
    
    # Load prompts from config
    prompts = tester.load_prompts_from_config(test_config)
    
    # Test regular prompts if they exist
    if hasattr(test_config, 'PROMPTS'):
        print(f"Testing {len(test_config.PROMPTS)} regular prompts...")
        tester.test_prompts(test_config.PROMPTS)
    
    # Test BPMN process descriptions if they exist
    if hasattr(test_config, 'PROCESS_DESCRIPTIONS'):
        print(f"\nTesting {len(test_config.PROCESS_DESCRIPTIONS)} BPMN process descriptions...")
        tester.test_bpmn_conversion(test_config.PROCESS_DESCRIPTIONS)