from google import genai
import os

def get_vertex_client() -> genai.Client:
    """Returns a GenAI client initialized for Vertex AI using system/environment config."""
    return genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
    )
