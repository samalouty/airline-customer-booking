import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure client to use Groq API
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

def get_answer(prompt, model="llama-3.1-8b-instant", temperature=0.1):
    """
    Send a prompt to Groq API and return the response.
    Default model: llama-3.1-8b-instant (fast, free on Groq)
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature
    )
    return response.choices[0].message.content

def get_openai_gpt4_answer(prompt, model="gpt-4o", temperature=0.1):
    """
    Send a prompt to the official OpenAI API (GPT-4o) using OPENAI_API_KEY.
    """
    # Create a transient client to avoid conflict with the global Groq client
    # or rely on environment variables if using the default constructor.
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Error: OPENAI_API_KEY not found in environment variables."
        
    client = OpenAI(api_key=api_key)
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error calling OpenAI: {str(e)}"
