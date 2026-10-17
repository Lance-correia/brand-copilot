"""Serve the production UI beside /api for the single-process local app."""
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

class StudioFiles(StaticFiles):
    async def get_response(self,path,scope):
        if path=='api' or path.startswith('api/'):
            raise HTTPException(404,'Not Found')
        try:
            response=await super().get_response(path,scope)
        except HTTPException as error:
            # React routes reload correctly; missing API routes and build assets stay 404.
            if error.status_code!=404 or path.startswith('assets/') or Path(path).suffix:
                raise
            response=await super().get_response('index.html',scope)
        if response.media_type=='text/html':response.headers['Cache-Control']='no-store'
        elif path.startswith('assets/'):response.headers['Cache-Control']='public, max-age=31536000, immutable'
        return response

def mount_web(app,directory):
    directory=Path(directory)
    if not (directory/'index.html').is_file():
        raise RuntimeError('The web build is missing. Run npm run build before starting the local app.')
    app.mount('/',StudioFiles(directory=directory,html=True),name='studio-web')
