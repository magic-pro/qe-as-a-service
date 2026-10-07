import json
import pathlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="autogentests-mock")
FIXTURES = pathlib.Path(__file__).parent / "fixtures"

KNOWN_DOMAINS = {"general", "identity", "payments"}


class QueryRequest(BaseModel):
    query: str
    domain: str = "general"
    context: dict = {}


@app.post("/query")
async def query(req: QueryRequest):
    if req.domain not in KNOWN_DOMAINS:
        raise HTTPException(status_code=422, detail=f"Unknown domain '{req.domain}'. Valid: {sorted(KNOWN_DOMAINS)}")
    return json.loads((FIXTURES / f"{req.domain}-patterns.json").read_text())


@app.get("/health")
async def health():
    return {"status": "ok"}
