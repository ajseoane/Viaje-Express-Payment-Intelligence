"""Run with Python 3.10+; no third-party dependencies."""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from payments.generate import generate
from payments.pipeline import ingest
from payments.report import dashboard, weekly_report

ROOT = Path(__file__).resolve().parent


def build(raw, output):
    records, quality = ingest(raw, output)
    dashboard(records, quality, output)
    weekly_report(records, output)
    return dict(transactions=records, quality=quality)


def serve(raw, output, port):
    lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, content, mime):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path in ('/', '/dashboard.html'):
                with lock:
                    self.respond(200, (output / 'dashboard.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/health':
                self.respond(200, b'{"ok": true}', 'application/json')
            else:
                self.respond(404, b'Not found', 'text/plain')

        def do_POST(self):
            # Require a custom same-origin request header. No CORS is enabled.
            if self.path != '/api/refresh':
                self.respond(404, b'Not found', 'text/plain')
                return
            allowed = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}
            if self.headers.get('X-ViajeExpress') != 'refresh' or self.headers.get('Origin') not in allowed:
                self.respond(403, b'Same-origin refresh required', 'text/plain')
                return
            try:
                with lock:
                    bundle = build(raw, output)
                self.respond(200, json.dumps(bundle).encode(), 'application/json')
            except Exception as exc:
                self.respond(500, json.dumps({'error': str(exc)}).encode(), 'application/json')
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Dashboard: http://127.0.0.1:{port}  (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate', action='store_true', help='Regenerate deterministic demo input files')
    parser.add_argument('--serve', action='store_true', help='Serve dashboard and enable pipeline refresh')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--raw', type=Path, default=ROOT / 'data' / 'raw')
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'processed')
    args = parser.parse_args()
    if args.generate or not (args.raw / 'manifest.json').exists():
        generate(args.raw)
    bundle = build(args.raw, args.output)
    print(json.dumps(bundle['quality'], indent=2))
    print(f'Dashboard saved: {args.output / "dashboard.html"}', flush=True)
    if args.serve:
        serve(args.raw, args.output, args.port)


if __name__ == '__main__':
    main()
