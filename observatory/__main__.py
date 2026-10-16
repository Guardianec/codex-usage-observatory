import argparse
import json
import logging
import os
from pathlib import Path
from .db import connect
from .ingest import scan
from .service import health, aggregate
from .api import Server


def main():
    parser = argparse.ArgumentParser(description='Local Codex usage foundation')
    parser.add_argument('command',choices=['import','status','serve'])
    parser.add_argument('--codex-home',type=Path,default=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex')))
    parser.add_argument('--db',type=Path,default=Path('.local/observatory.sqlite'))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--interval',type=float,default=2)
    parser.add_argument('--debug',action='store_true')
    args = parser.parse_args()
    if args.db.resolve().is_relative_to(args.codex_home.resolve()):
        parser.error('database must be outside the Codex source directory')
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)
    db = connect(args.db)
    try:
        if args.command == 'import':
            print(json.dumps(scan(db,args.codex_home),indent=2))
        if args.command in ('import','status'):
            print(json.dumps({'health':health(db),'usage':aggregate(db)},indent=2))
    finally:
        db.close()
    if args.command == 'serve':
        server = Server(args.db,args.codex_home,args.port,args.interval)
        server.start_collector()
        print(f'Listening on http://127.0.0.1:{server.server_address[1]} (Ctrl+C to stop)')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
