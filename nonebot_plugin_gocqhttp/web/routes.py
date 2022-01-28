from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from nonebot.utils import escape_tag
from pydantic import BaseModel
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from ..log import logger
from ..plugin_config import AccountConfig
from ..process import (
    GoCQProcess,
    ProcessAccount,
    ProcessesManager,
    ProcessInfo,
    ProcessLog,
)

app = FastAPI(
    title="nonebot-plugin-gocqhttp",
    description="go-cqhttp process manager API",
)


def RunningProcess():
    async def dependency(uin: int):
        process = ProcessesManager.get(uin)
        if not process:
            raise HTTPException(status_code=404, detail="Process not found")
        return process

    return Depends(dependency)


@app.get("/", response_model=List[int])
async def all_processes():
    return [process.account.uin for process in ProcessesManager.all()]


class AccountCreation(BaseModel):
    password: Optional[str] = None
    config_extra: Optional[Dict[str, Any]] = None
    device_extra: Optional[Dict[str, Any]] = None


@app.put(
    "/{uin}",
    response_model=ProcessAccount,
    response_model_exclude={"config"},
    status_code=201,
)
async def create_process(uin: int, account: Optional[AccountCreation] = None):
    process = ProcessesManager.create(
        account=AccountConfig(uin=uin, **account.dict() if account else {})
    )
    return process.account


@app.get("/{uin}/status", response_model=ProcessInfo)
async def process_status(process: GoCQProcess = RunningProcess()):
    return await process.status()


@app.get("/{uin}/device")
async def process_device(process: GoCQProcess = RunningProcess()):
    return process.account.device


@app.get("/{uin}/logs", response_model=List[ProcessLog])
async def process_logs_history(
    reverse: bool = False,
    process: GoCQProcess = RunningProcess(),
):
    return process.logs.list(reverse=reverse)


@app.websocket("/{uin}/logs")
async def process_logs_realtime(
    websocket: WebSocket,
    process: GoCQProcess = RunningProcess(),
):
    await websocket.accept()

    async def log_listener(log: ProcessLog):
        await websocket.send_text(log.json())

    process.log_listeners.add(log_listener)
    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            recv = await websocket.receive()
            logger.trace(f"Websocket received <e>{escape_tag(repr(recv))}</e>")
    except WebSocketDisconnect:
        pass
    finally:
        process.log_listeners.remove(log_listener)
    return


@app.delete("/{uin}/process", status_code=204)
async def process_stop(process: GoCQProcess = RunningProcess()):
    await process.stop()
    return


@app.put("/{uin}/process", status_code=201)
async def process_start(process: GoCQProcess = RunningProcess()):
    await process.start()
    return
