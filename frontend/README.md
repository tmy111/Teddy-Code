# TeddyCode Web UI

The frontend is a React + TypeScript + Vite client for the local FastAPI adapter.

```bash
# repository root
teddycode web --cwd .

# another terminal
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The development server proxies `/api` to
`http://127.0.0.1:8000`.

Create a production bundle with:

```bash
npm run build
```
