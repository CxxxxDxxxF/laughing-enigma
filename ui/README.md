# Backtest Control Plane UI

Phase 2 UI for quant research and backtesting.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Start development server:
```bash
npm run dev
```

The UI will be available at http://localhost:3000

## Configuration

The UI uses mock data by default. To connect to the real API:

1. Make sure the FastAPI backend is running on http://localhost:8000
2. Set `USE_MOCK_DATA = false` in the page components:
   - `src/pages/Overview.jsx`
   - `src/pages/Experiments.jsx`
   - `src/pages/Runs.jsx`
   - `src/pages/RunDetail.jsx`

## Pages

- **Overview**: Dashboard with summary statistics and recent runs
- **Experiments**: List and create experiments
- **Runs**: List all backtest runs
- **Run Detail**: View detailed metrics and charts for a specific run

## API Integration

The API client is in `src/api/client.js`. It provides functions for:
- Listing and creating experiments
- Listing runs and fetching metrics
- Health checks

