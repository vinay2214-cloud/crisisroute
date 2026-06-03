from google import genai

client = genai.Client(
    vertexai=True,
    project="crisisroute-2026-498212",
    location="us-central1"
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say hello"
)

print(response.text)