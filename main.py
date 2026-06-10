import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/owl-alpha"

PROMPTS = {
    "twitter": """You are a Twitter/X expert. Convert the content into a viral thread.
Rules:
- Start with a hook tweet that stops the scroll — make it punchy and bold
- Write 6 to 10 tweets, each strictly under 280 characters
- Number each tweet: 1/, 2/, 3/ etc.
- Last tweet must be a strong CTA
- Maximum 2 hashtags for the entire thread
- No filler phrases like 'Great thread!' or 'In conclusion'
Output only the thread. No explanation or preamble.""",

    "linkedin": """You are a LinkedIn content strategist. Rewrite for LinkedIn.
Rules:
- Open with a single bold hook line — no 'I am excited to share'
- Short paragraphs, maximum 2 lines each
- Include 3 to 5 bullet points highlighting key insights
- End with an open question to drive comments
- Tone: professional but conversational
- Length: 150 to 220 words
Output only the LinkedIn post. No explanation or preamble.""",

    "email": """You are an email newsletter writer. Rewrite this as a newsletter section.
Rules:
- First line: suggest a subject line prefixed with 'Subject:'
- Blank line after subject
- Friendly direct tone — like writing to a smart friend
- Include one clear key insight or takeaway
- End with one specific actionable tip
- Length: 180 to 230 words
Output only the email content. No explanation or preamble.""",

    "tldr": """Summarize this content as a TL;DR.
Rules:
- Exactly 3 bullet points
- Each bullet starts with a relevant emoji
- Each bullet is one insight, plain language, under 20 words
- No intro sentence, no conclusion sentence
Output only the 3 bullet points. No explanation or preamble.""",

    "hooks": """Generate 5 headline and hook options for this content.
Rules:
- Each hook creates curiosity or makes a bold claim
- Each hook is under 12 words
- Suitable for blog titles, ad copy, or email subject lines
- Number them 1 to 5
- One hook per line, no explanation after each
Output only the numbered list. No explanation or preamble."""
}

class RepurposeRequest(BaseModel):
    content: str
    formats: list[str] = ["twitter", "linkedin", "email", "tldr", "hooks"]

async def call_llm(client: httpx.AsyncClient, format_name: str, content: str) -> dict:
    system_prompt = PROMPTS.get(format_name, "Rewrite this content clearly and concisely.")
    try:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is the content to repurpose:\n\n{content}"}
                ],
                "max_tokens": 900,
                "temperature": 0.75
            },
            timeout=45.0
        )
        if response.status_code != 200:
            return {"format": format_name, "result": None, "error": f"API error {response.status_code}"}
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        return {"format": format_name, "result": text, "error": None}
    except Exception as e:
        return {"format": format_name, "result": None, "error": str(e)}

@app.get("/")
def root():
    return FileResponse("index.html")

@app.post("/repurpose")
async def repurpose(req: RepurposeRequest):
    if not req.content.strip():
        return {"error": "Content cannot be empty"}
    if len(req.content) < 50:
        return {"error": "Content is too short. Paste at least a paragraph."}

    async with httpx.AsyncClient() as client:
        tasks = [call_llm(client, fmt, req.content) for fmt in req.formats]
        results = await asyncio.gather(*tasks)

    output = {}
    for item in results:
        output[item["format"]] = {
            "result": item["result"],
            "error": item["error"]
        }

    word_count = len(req.content.split())
    return {
        "outputs": output,
        "meta": {
            "formats_requested": len(req.formats),
            "word_count": word_count,
            "model": MODEL
        }
    }

@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL, "key_set": bool(OPENROUTER_KEY)}
