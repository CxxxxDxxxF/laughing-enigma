/**
 * Mock data for UI development
 * 
 * This module provides mock data that matches the API response structure.
 * Used during initial development before connecting to real API.
 */

export const mockExperiments = [
  {
    name: 'momentum_strategy',
    version: 'v1',
    config: { daily_trend: 0.0001 },
    created_at: '2024-01-15T10:30:00',
    description: 'Simple momentum strategy test',
  },
  {
    name: 'mean_reversion',
    version: 'v1',
    config: { daily_trend: -0.00005 },
    created_at: '2024-01-16T14:20:00',
    description: 'Mean reversion strategy',
  },
]

export const mockRuns = [
  {
    id: '550e8400-e29b-41d4-a716-446655440000',
    experiment_name: 'momentum_strategy',
    experiment_version: 'v1',
    status: 'success',
    started_at: '2024-01-20T09:00:00',
    completed_at: '2024-01-20T09:00:05',
    error_message: null,
  },
  {
    id: '550e8400-e29b-41d4-a716-446655440001',
    experiment_name: 'mean_reversion',
    experiment_version: 'v1',
    status: 'success',
    started_at: '2024-01-20T10:00:00',
    completed_at: '2024-01-20T10:00:05',
    error_message: null,
  },
  {
    id: '550e8400-e29b-41d4-a716-446655440002',
    experiment_name: 'momentum_strategy',
    experiment_version: 'v1',
    status: 'failed',
    started_at: '2024-01-20T11:00:00',
    completed_at: '2024-01-20T11:00:02',
    error_message: 'Invalid date range',
  },
]

export const mockMetrics = {
  run_id: '550e8400-e29b-41d4-a716-446655440000',
  computed_at: '2024-01-20T09:00:05',
  equity_curve: [
    100000, 100100, 100250, 100180, 100320, 100450, 100380, 100520,
    100680, 100750, 100820, 100910, 101050, 101180, 101250, 101380,
  ],
  final_value: 101380,
  max_drawdown: 0.023,
  max_drawdown_duration: 3,
  monthly_returns: [0.0138, 0.0125, 0.0112],
  total_return: 0.0138,
  sharpe_ratio: 1.25,
  volatility: 0.15,
  turnover: 0.0,
}

