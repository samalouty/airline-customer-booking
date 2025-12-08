import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure client to use Groq API
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

def get_answer(prompt, model="openai/gpt-oss-20b", temperature=0.1):
    """
    Send a prompt to Groq API and return the response.
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature
    )
    return response.choices[0].message.content
