"""HTTP surface for riffing with the digest, plus the page that uses it."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import riffing
from .config import Settings
from .digest import DigestError, OpenAIJsonClient, latest_digest, load_feeds

PAGE = Path(__file__).parent / "static" / "riff.html"


class StartThread(BaseModel):
    kind: str
    index: int | None = None
    text: str | None = Field(default=None, max_length=4000)


class Message(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    wander: bool = False


def build_router(resolve_settings: Callable[[], Settings]) -> APIRouter:
    router = APIRouter(tags=["riff"])

    def context(request: Request, settings: Settings = Depends(resolve_settings)) -> dict:
        profile = Path(os.environ.get("RIFF_PROFILE", "config/profile.md"))
        return {
            "database_url": settings.database_url,
            "call": request.app.state.riff_call or OpenAIJsonClient(settings.reasoning_api_key or "", base_url=settings.reasoning_base_url),
            "source_ids": [feed.source_id for feed in load_feeds(os.environ.get("RIFF_DIGEST_FEEDS", "config/digest_feeds.json"))],
            "profile": profile.read_text(encoding="utf-8") if profile.exists() else "",
            "model": os.environ.get("RIFF_RIFF_MODEL", riffing.DEFAULT_RIFF_MODEL),
        }

    def guarded(action):
        try:
            return action()
        except riffing.RiffingError as exc:
            code = status.HTTP_404_NOT_FOUND if "unknown thread" in str(exc) else status.HTTP_400_BAD_REQUEST
            raise HTTPException(status_code=code, detail=str(exc)) from exc
        except DigestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @router.get("/riff", response_class=HTMLResponse, include_in_schema=False)
    def page() -> str:
        return PAGE.read_text(encoding="utf-8")

    @router.get("/riff/api/state")
    def state(settings: Settings = Depends(resolve_settings)) -> dict:
        digest = latest_digest(settings.database_url)
        if digest is not None:
            digest = {name: digest[name] for name in ("digest_id", "run_date", "article_count", "payload")}
        return {"digest": digest, "threads": riffing.list_threads(settings.database_url)}

    @router.post("/riff/api/threads")
    def start(body: StartThread, ctx: dict = Depends(context)) -> dict:
        return guarded(lambda: riffing.start_thread(ctx["database_url"], call=ctx["call"], source_ids=ctx["source_ids"], profile=ctx["profile"], kind=body.kind, index=body.index, text=body.text, model=ctx["model"]))

    @router.get("/riff/api/threads/{thread_id}")
    def read(thread_id: str, settings: Settings = Depends(resolve_settings)) -> dict:
        return guarded(lambda: riffing.get_thread(settings.database_url, thread_id))

    @router.post("/riff/api/threads/{thread_id}/messages")
    def say(thread_id: str, body: Message, ctx: dict = Depends(context)) -> dict:
        return guarded(lambda: riffing.take_turn(ctx["database_url"], thread_id, call=ctx["call"], source_ids=ctx["source_ids"], profile=ctx["profile"], text=body.text, wander=body.wander, model=ctx["model"]))

    @router.post("/riff/api/threads/{thread_id}/distill")
    def distill(thread_id: str, ctx: dict = Depends(context)) -> dict:
        return guarded(lambda: riffing.distill(ctx["database_url"], thread_id, call=ctx["call"], model=ctx["model"]))

    return router
