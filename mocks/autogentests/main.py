import json
import pathlib
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="autogentests-mock")
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


class QueryRequest(BaseModel):
    query: str
    domain: str = "general"
    context: dict = {}


@app.post("/query")
async def query(req: QueryRequest):
    fixture = FIXTURES / f"{req.domain}-patterns.json"
    if not fixture.exists():
        fixture = FIXTURES / "general-patterns.json"
    return json.loads(fixture.read_text())


@app.get("/health")
async def health():
    return {"status": "ok"}
