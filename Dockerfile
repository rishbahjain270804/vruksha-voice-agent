# Hugging Face Spaces (Docker SDK). Lean image: STT=groq and TTS=elevenlabs need no local models.
FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart pydantic python-dotenv httpx groq

COPY app ./app
COPY frontend ./frontend

# Non-secret defaults; the 3 real keys are set as Space secrets, never baked in.
ENV PROOF_DRY_RUN=1 \
    STT_PROVIDER=groq \
    LLM_PROVIDER=groq \
    GROQ_MODEL=openai/gpt-oss-120b \
    TTS_PROVIDER=elevenlabs \
    ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL \
    ELEVENLABS_MODEL=eleven_multilingual_v2 \
    DEFAULT_LANG=en \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

# HF Spaces expects the app on port 7860.
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
