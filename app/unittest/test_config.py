# Configuration for API Caller Tester
# Define your prompts and process descriptions here

# List of prompts to test with the API
# Each prompt can be either a string or a dictionary with more details
PROMPTS = [
    {
        "name": "Simple Process Query",
        "system_prompt": "You are a helpful assistant that answers questions about business processes.",
        "user_text": "What are the key components of a purchase order process?"
    },
    {
        "name": "BPMN Elements Explanation",
        "system_prompt": "You are a BPMN expert. Provide detailed and accurate information about BPMN elements.",
        "user_text": "Explain the difference between exclusive and inclusive gateways in BPMN."
    },
    # Simple string prompt example
    "Create a brief summary of what BPMN is used for in modern businesses.",
    
    # You can add more prompts here
]

# Process descriptions for BPMN conversion testing
PROCESS_DESCRIPTIONS = [
    {
        "name": "Order Processing",
        "description": """
        A customer submits an order through an online form. The system receives the order and checks inventory availability.
        If items are available, the order is processed, payment is collected, and the order is shipped to the customer.
        If items are not available, the system checks if they can be backordered. If yes, the system places a backorder and
        notifies the customer about the delay. If no, the system cancels the order and notifies the customer.
        After shipping or cancellation, the process ends.
        """
    },
    {
        "name": "Expense Approval",
        "description": """
        An employee submits an expense report. The system checks if the amount is under $500.
        If it's under $500, a team lead reviews it. Otherwise, it requires manager approval.
        After team lead review, if approved, the expense is processed for payment.
        If rejected, the employee is notified and can resubmit with changes.
        For manager approval, if approved, finance department reviews it for compliance.
        If finance approves, the expense is processed for payment. If finance rejects,
        the employee is notified and can resubmit with changes.
        After payment processing, the accounting department records the transaction, and the process ends.
        """
    },
    # Simple string example
    """
    A patient arrives at the hospital and checks in at the front desk. 
    The receptionist verifies insurance information. If the information is valid, 
    the patient waits to be called. If not, the patient must update their information. 
    Once called, a nurse takes vitals and records symptoms. Then a doctor examines the patient. 
    After examination, the doctor either prescribes medication or orders additional tests. 
    If tests are needed, the patient undergoes testing and then returns to the doctor for results review. 
    After medication prescription or test results review, the patient checks out and pays any required fees.
    """
]

# API call configuration
API_CONFIG = {
    "delay_between_calls": 2,  # Seconds to wait between API calls
    "save_results": True,      # Whether to save results to file
    "results_file": "api_test_results.json" # Output file for results
}