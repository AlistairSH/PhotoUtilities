"""Explicit local review session: one report, allowlisted sources, verified archives."""
from __future__ import annotations
import hmac
import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional, cast
from urllib.parse import parse_qs,urlparse
from . import database
from .review_archive import archive_selected,checked,review_job
from .similarity_native import SimilarityError


def make_server(job_id: str, *, archive_root: Optional[Path] = None) -> tuple[HTTPServer,str]:
    payload=review_job(job_id);report=Path(payload['report'])
    checked(report,payload['report_sha256']);document=report.read_bytes();token=secrets.token_urlsafe(32)
    state=database.state_dir()
    class Handler(BaseHTTPRequestHandler):
        def handle_one_request(self) -> None:
            with database.use_state(state):super().handle_one_request()
        def log_message(self,format: str,*args: Any) -> None:pass
        def host_ok(self) -> bool:
            return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'  # type: ignore[attr-defined]
        def authorized(self) -> bool:
            supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
            if not supplied:supplied=parse_qs(urlparse(self.path).query).get('token',[''])[0]
            return self.host_ok() and hmac.compare_digest(supplied,token)
        def reply(self,status: int,data: bytes,content_type: str) -> None:
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def json_reply(self,status: int,value: Any) -> None:self.reply(status,json.dumps(value).encode(),'application/json')
        def do_GET(self) -> None:
            path=urlparse(self.path).path
            if not self.host_ok():self.json_reply(403,{'error':'Invalid local host'});return
            if path=='/':self.reply(200,document,'text/html; charset=utf-8');return
            if not self.authorized():self.json_reply(403,{'error':'Invalid review session'});return
            if path=='/state':
                indices: list[int]=[]
                with database.transaction() as db:
                    for i,img in enumerate(payload['images']):
                        row=db.execute('SELECT status FROM assets WHERE asset_id=?',(img['asset_id'],)).fetchone()
                        if row and row['status']=='archived':indices.append(i)
                self.json_reply(200,{'archived_indices':indices});return
            if path.startswith('/image/'):
                try:
                    i=int(path.removeprefix('/image/'))
                    if not 0<=i<len(payload['images']):raise ValueError('Invalid image index')
                    img=payload['images'][i]
                    with database.transaction() as db:
                        row=db.execute('SELECT path FROM assets WHERE asset_id=?',(img['asset_id'],)).fetchone()
                    source=Path(row['path'] if row else img['path']);checked(source,img['sha256'])
                    self.reply(200,source.read_bytes(),mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
                except (ValueError,OSError,SimilarityError) as exc:self.json_reply(404,{'error':str(exc)})
                return
            self.json_reply(404,{'error':'Unknown endpoint'})
        def do_POST(self) -> None:
            origin=self.headers.get('Origin')
            expected=f'http://127.0.0.1:{self.server.server_port}'  # type: ignore[attr-defined]
            if self.path!='/archive' or not self.authorized() or origin not in (None,expected):self.json_reply(403,{'error':'Invalid archive request'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192 or self.headers.get('Content-Type')!='application/json':raise ValueError('Invalid request body')
                request: Any=json.loads(self.rfile.read(length))
                if not isinstance(request,dict):raise ValueError('Select image indices')
                data=cast(dict[str, Any],request)
                if not isinstance(data.get('indices'),list):raise ValueError('Select image indices')
                indices=cast(list[Any],data['indices'])
                if any(type(i) is not int for i in indices):raise ValueError('Invalid selection')
                self.json_reply(200,archive_selected(job_id,cast(list[int],indices),archive_root=archive_root))
            except (ValueError,KeyError,TypeError,OSError,SimilarityError,database.DatabaseError) as exc:self.json_reply(400,{'error':str(exc)})
    server=HTTPServer(('127.0.0.1',0),Handler)
    return server,f'http://127.0.0.1:{server.server_port}/#{token}'


def serve_review(job_id: str, *, archive_root: Optional[Path] = None) -> None:
    server,url=make_server(job_id,archive_root=archive_root)
    print('Open review:',url,flush=True);print('Listening only on 127.0.0.1. Ctrl-C ends the review session.',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
