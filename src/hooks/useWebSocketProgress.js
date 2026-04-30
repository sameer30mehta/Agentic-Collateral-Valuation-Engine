import { useEffect, useState, useRef } from 'react';

/**
 * Hook for WebSocket real-time progress tracking
 * 
 * Usage:
 * const { progress, status, error } = useWebSocketProgress(valuationId);
 * 
 * Progress includes:
 * - type: 'stage_update', 'task_update', 'complete', 'error'
 * - stage: Current stage name
 * - progress_percent: 0-100
 * - task: Current task name
 * - status: 'running', 'completed', 'failed'
 * - elapsed_seconds: Time elapsed
 * - total_time_seconds: Final time (on complete)
 */
export function useWebSocketProgress(valuationId) {
  const [progress, setProgress] = useState(null);
  const [status, setStatus] = useState('connecting'); // connecting, active, completed, error
  const [error, setError] = useState(null);
  const [taskUpdates, setTaskUpdates] = useState({});
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  useEffect(() => {
    if (!valuationId) return;

    const connectWebSocket = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(
          `${protocol}://${window.location.host}/ws/progress/${valuationId}`
        );

        ws.onopen = () => {
          console.log(`[WebSocket] Connected to progress stream for ${valuationId}`);
          setStatus('active');
          setError(null);
        };

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data);
          console.log('[WebSocket] Progress update:', data);

          setProgress(data);

          if (data.type === 'task_update') {
            setTaskUpdates(prev => ({
              ...prev,
              [data.task]: {
                status: data.status,
                details: data.details,
                timestamp: data.timestamp
              }
            }));
          } else if (data.type === 'complete') {
            setStatus('completed');
          } else if (data.type === 'error') {
            setStatus('error');
            setError(data.error);
          }
        };

        ws.onerror = (err) => {
          console.error('[WebSocket] Error:', err);
          setStatus('error');
          setError('WebSocket connection failed');
        };

        ws.onclose = () => {
          console.log('[WebSocket] Connection closed');
          setStatus('disconnected');
          
          // Attempt to reconnect after 3 seconds
          if (status !== 'completed') {
            reconnectTimeoutRef.current = setTimeout(connectWebSocket, 3000);
          }
        };

        wsRef.current = ws;

        // Heartbeat to keep connection alive
        const heartbeatInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30000);

        return () => clearInterval(heartbeatInterval);

      } catch (err) {
        console.error('[WebSocket] Connection error:', err);
        setError(err.message);
        setStatus('error');
      }
    };

    connectWebSocket();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [valuationId, status]);

  return {
    progress,
    status,
    error,
    taskUpdates,
    progressPercent: progress?.progress_percent || 0,
    currentStage: progress?.stage,
    elapsedSeconds: progress?.elapsed_seconds,
    totalTimeSeconds: progress?.total_time_seconds,
  };
}

/**
 * Progress Indicator Component
 * Shows real-time pipeline progress with task details
 */
export function ProgressIndicator({ valuationId, onComplete }) {
  const { progress, status, error, taskUpdates, progressPercent, currentStage, elapsedSeconds } = 
    useWebSocketProgress(valuationId);

  useEffect(() => {
    if (status === 'completed' && onComplete) {
      onComplete(progress);
    }
  }, [status, progress, onComplete]);

  const getStatusColor = () => {
    switch (status) {
      case 'active': return 'bg-blue-500';
      case 'completed': return 'bg-green-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-400';
    }
  };

  const formatTime = (seconds) => {
    if (!seconds) return '0s';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };

  return (
    <div className="w-full space-y-4">
      {/* Main Progress Bar */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-sm font-semibold text-gray-700">
              {currentStage || 'Initializing...'}
            </h3>
            <p className="text-xs text-gray-500">
              {progress?.description || 'Starting valuation pipeline...'}
            </p>
          </div>
          <div className="text-right">
            <p className="text-lg font-bold text-gray-800">{progressPercent}%</p>
            <p className="text-xs text-gray-500">{formatTime(elapsedSeconds)}</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
          <div
            className={`h-full ${getStatusColor()} transition-all duration-300 ease-out`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Task Details */}
      {Object.keys(taskUpdates).length > 0 && (
        <div className="border-t pt-3">
          <h4 className="text-xs font-semibold text-gray-600 mb-2">Pipeline Tasks</h4>
          <div className="space-y-1.5">
            {Object.entries(taskUpdates).map(([taskName, taskStatus]) => (
              <div key={taskName} className="flex items-center justify-between text-xs">
                <span className="text-gray-700 capitalize">
                  {taskName.replace(/_/g, ' ')}
                </span>
                <div className="flex items-center gap-2">
                  {taskStatus.status === 'running' && (
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                  )}
                  {taskStatus.status === 'completed' && (
                    <span className="text-green-600">✓</span>
                  )}
                  {taskStatus.status === 'failed' && (
                    <span className="text-red-600">✗</span>
                  )}
                  <span className="text-gray-500 capitalize">{taskStatus.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Status Message */}
      <div className="text-center">
        <p className={`text-xs font-medium ${
          status === 'completed' ? 'text-green-600' :
          status === 'error' ? 'text-red-600' :
          'text-gray-600'
        }`}>
          {status === 'active' ? '⏳ Processing...' :
           status === 'completed' ? '✓ Complete!' :
           status === 'error' ? '✗ Failed' :
           status === 'connecting' ? '⟳ Connecting...' :
           'Disconnected'}
        </p>
      </div>
    </div>
  );
}

/**
 * Fallback: HTTP Progress Polling (for environments without WebSocket)
 */
export async function pollProgress(valuationId, onUpdate, maxAttempts = 120) {
  let attempts = 0;
  const pollInterval = setInterval(async () => {
    try {
      const response = await fetch(`/progress/${valuationId}`);
      if (response.ok) {
        const data = await response.json();
        onUpdate(data);

        if (data.type === 'complete' || data.type === 'error') {
          clearInterval(pollInterval);
        }
      }
    } catch (err) {
      console.error('Poll error:', err);
    }

    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(pollInterval);
    }
  }, 1000);

  return () => clearInterval(pollInterval);
}
