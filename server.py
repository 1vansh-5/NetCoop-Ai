import asyncio
import contextlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi import Request as HttpRequest
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from engine import diagnose
from netcoop import SCENARIOS, generate, normalize
from importer import extract_many
import provider as telemetry_provider
import os

ROOT=Path(__file__).resolve().parent
DB=ROOT/'data'/'incidents.sqlite3'
app=FastAPI(title='NetCoop AI',version='2.0.0')
gate=asyncio.Semaphore(3)

class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenario: str='congestion'
    telemetry: dict | None=None
    seed: int=Field(default=7,ge=0,le=1000000)
    mode: Literal['demo','gemini','groq']='demo'

def validate(body):
    if body.telemetry is None and body.scenario.startswith(telemetry_provider.PREFIX):
        info=telemetry_provider.inspect_provider()
        if not info['available']:
            raise HTTPException(422,'Telemetry provider unavailable: '+str(info['error']))
        if not telemetry_provider.has_scenario(body.scenario):
            raise HTTPException(422,f"Unknown provider scenario. {info['file']} offers: {', '.join(info['scenarios'])}")
    elif body.telemetry is None and body.scenario not in SCENARIOS:
        raise HTTPException(422,'Unknown scenario')
    if len(json.dumps(body.telemetry))>250000:
        raise HTTPException(413,'Telemetry is limited to 250 KB')

def connection():
    DB.parent.mkdir(exist_ok=True)
    db=sqlite3.connect(DB)
    db.execute('CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, created REAL, payload TEXT)')
    return db

def save(result):
    with connection() as db:
        r=result['report']
        db.execute('INSERT OR REPLACE INTO incidents VALUES (?,?,?)',(r['incident_id'],r['created_at'],json.dumps(result)))
        db.execute('DELETE FROM incidents WHERE id NOT IN (SELECT id FROM incidents ORDER BY created DESC LIMIT 100)')

@app.get('/api/health')
def health():
    return {'status':'ok','groq_configured':bool(os.getenv('GROQ_API_KEY','').strip()),'groq_model':os.getenv('GROQ_MODEL','llama-3.3-70b-versatile'),'gemini_configured':bool(os.getenv('GEMINI_API_KEY')),'model':os.getenv('GEMINI_MODEL','gemini-flash-latest'),'telemetry_source':'synthetic / provider script / user supplied','mcp_transport':'stdio','provider':telemetry_provider.inspect_provider()}

@app.get('/api/scenarios')
def scenarios():
    return SCENARIOS

@app.get('/api/provider')
def provider_info():
    return telemetry_provider.inspect_provider()

@app.get('/api/telemetry/{scenario}')
def telemetry(scenario: str):
    if scenario.startswith(telemetry_provider.PREFIX):
        try:
            return telemetry_provider.fetch(scenario)
        except ValueError as exc:
            raise HTTPException(422,str(exc)[:500])
    if scenario not in SCENARIOS:
        raise HTTPException(404,'Unknown scenario')
    return generate(scenario)

async def execute(body,emit=None):
    async with gate:
        result=await diagnose('custom' if body.telemetry is not None else body.scenario,body.telemetry,body.seed,body.mode=='gemini',emit,llm_provider=body.mode)
        await asyncio.to_thread(save,result)
        return result

@app.post('/api/diagnose')
async def run(body:Request):
    validate(body)
    return await execute(body)

@app.post('/api/diagnose/stream')
async def stream(body:Request):
    validate(body)
    async def events():
        queue=asyncio.Queue()
        async def work():
            try:
                result=await execute(body,queue.put)
                await queue.put({'event':'complete','data':result})
            except Exception:
                await queue.put({'event':'error','data':{'message':'Run failed; retry or check server logs.'}})
            finally:
                await queue.put(None)
        task=asyncio.create_task(work())
        try:
            while True:
                event=await queue.get()
                if event is None:
                    break
                yield json.dumps(event)+'\n'
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    return StreamingResponse(events(),media_type='application/x-ndjson',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

class ImportRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    filename: str=Field(max_length=200)
    content: str=Field(max_length=300000)
    replay: bool=False

def is_local(request):
    host=request.client.host if request.client else ''
    return host in ('127.0.0.1','::1','localhost','testclient') or os.getenv('NETCOOP_ALLOW_PY_IMPORT')=='1'

def describe_age(seconds):
    if seconds < 3600: return f'{round(seconds/60)} minutes'
    if seconds < 172800: return f'{seconds/3600:.1f} hours'
    return f'{seconds/86400:.1f} days'

@app.post('/api/import')
async def import_telemetry(body:ImportRequest,request:HttpRequest):
    """Read a .json or .py telemetry file (one snapshot or several named ones) and validate it immediately."""
    try:
        items,how=await asyncio.to_thread(extract_many,body.filename,body.content,is_local(request))
        datasets,stale_ages=[],[]
        for name,raw,notes in items:
            n=normalize(raw)
            if n['quality']['stale']:
                stamp=raw.get('timestamp')
                if body.replay:
                    when=raw.get('recorded_at') or 'missing'
                    raw=dict(raw,timestamp=time.time())
                    notes=notes+[f'Recorded snapshot (original timestamp: {when}) analysed as current; its age was not checked.']
                    n=normalize(raw)
                elif isinstance(stamp,(int,float)) and not isinstance(stamp,bool) and stamp<=time.time():
                    stale_ages.append(time.time()-stamp)
            if notes:
                raw=dict(raw,import_notes=list(raw.get('import_notes',[]))+notes)
            datasets.append({'name':name or body.filename,'telemetry':raw,'normalized':n,'notes':notes})
    except ValueError as exc:
        raise HTTPException(422,str(exc)[:500])
    first=datasets[0]
    return {'telemetry':first['telemetry'],'normalized':first['normalized'],'datasets':datasets,'source':how,'filename':body.filename,
            'stale':{'age':describe_age(max(stale_ages))} if stale_ages else None}

@app.get('/api/incidents')
def history():
    with connection() as db:
        return [json.loads(row[0])['report'] for row in db.execute('SELECT payload FROM incidents ORDER BY created DESC LIMIT 20')]

@app.get('/api/incidents/{incident}')
def detail(incident:str):
    with connection() as db:
        row=db.execute('SELECT payload FROM incidents WHERE id=?',(incident,)).fetchone()
    if not row:
        raise HTTPException(404,'Incident not found')
    return json.loads(row[0])

app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='dashboard')
