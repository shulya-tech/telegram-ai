from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn
import asyncio
import warnings
from pydantic import BaseModel
from typing import List, Optional

warnings.filterwarnings("ignore", message=".*pin_memory.*no accelerator.*")

app = FastAPI()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    image_base64: Optional[str] = None

class SummarizeRequest(BaseModel):
    messages: List[Message]

class AnalyzeImageRequest(BaseModel):
    image_base64: str

@app.get("/health")
async def health():
    return {"status": "ok"}


from vlm import vlm_instance

# Load VLM on startup asynchronously in the background so it doesn't block
@app.on_event("startup")
async def startup_event():
    # Only load in the background if we're actually running the server
    asyncio.create_task(asyncio.to_thread(vlm_instance.load))

from llm_orchestrator import llm_orchestrator

@app.post("/analyze-image")
async def analyze_image_endpoint(request: AnalyzeImageRequest):
    description = await asyncio.to_thread(vlm_instance.analyze_image, request.image_base64)
    return {"description": description}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    image_context = None
    if request.image_base64:
        # Run VLM inference asynchronously to not block
        image_context = await asyncio.to_thread(vlm_instance.analyze_image, request.image_base64)

    streamer = llm_orchestrator.generate_stream(request.messages, image_context)

    async def stream_generator():
        # TextIteratorStreamer is a blocking iterator, we need to iterate it in a separate thread
        def get_next():
            try:
                return next(streamer)
            except StopIteration:
                return None

        while True:
            text = await asyncio.to_thread(get_next)
            if text is None:
                break
            if text:
                yield text


    return StreamingResponse(stream_generator(), media_type="text/plain")

@app.on_event("startup")
async def startup_event_llm():
    # Pre-load LLM model
    asyncio.create_task(asyncio.to_thread(llm_orchestrator.load))

@app.post("/summarize")
async def summarize_endpoint(request: SummarizeRequest):
    summary = await asyncio.to_thread(llm_orchestrator.summarize, request.messages)
    return {"summary": summary}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
