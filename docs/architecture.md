# Architecture

## Phase 1 Architecture

```
UI
│
API
│
Core Domain
│   ├── Experiment
│   ├── Run
│   ├── Metrics
│   └── Artifacts
│
Research Engines
    ├── BaseResearchEngine
    └── QlibAdapter (optional)
```

### Design Principles

- **Determinism**: Same inputs → same outputs, always
- **Reproducibility**: Can replay any run from stored inputs
- **Engine-agnostic**: Swap engines without changing core domain
- **Explainability**: Every metric must be explainable line-by-line

