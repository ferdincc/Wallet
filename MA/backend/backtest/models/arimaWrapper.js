const { spawn } = require('child_process');
const path = require('path');

/**
 * Run ARIMA model Python script with given price series.
 *
 * @param {Array<{timestamp: string | number, close: number}>} data
 * @param {{ pythonPath?: string }} [options]
 * @returns {Promise<{ predicted_price?: number, confidence?: number, model_name: string, error?: string }>}
 */
function runArimaModel(data, options = {}) {
  const pythonPath = options.pythonPath || process.env.PYTHON_PATH || 'python';
  const scriptPath = path.join(__dirname, 'arimaModel.py');

  return new Promise((resolve) => {
    try {
      const proc = spawn(pythonPath, [scriptPath]);

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });

      proc.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
      });

      proc.on('error', (err) => {
        resolve({
          model_name: 'arima',
          predicted_price: null,
          confidence: 0,
          error: `Failed to start Python process: ${err.message}`,
        });
      });

      proc.on('close', (code) => {
        if (!stdout.trim()) {
          return resolve({
            model_name: 'arima',
            predicted_price: null,
            confidence: 0,
            error: stderr || `ARIMA process exited with code ${code}`,
          });
        }

        try {
          const parsed = JSON.parse(stdout);
          // Ensure model_name is always "arima"
          parsed.model_name = 'arima';
          resolve(parsed);
        } catch (e) {
          resolve({
            model_name: 'arima',
            predicted_price: null,
            confidence: 0,
            error: `Invalid JSON from ARIMA script: ${e.message}`,
            raw_output: stdout,
            stderr,
          });
        }
      });

      // Send input JSON
      proc.stdin.write(JSON.stringify(data || []));
      proc.stdin.end();
    } catch (err) {
      resolve({
        model_name: 'arima',
        predicted_price: null,
        confidence: 0,
        error: `Unexpected error running ARIMA: ${err.message}`,
      });
    }
  });
}

module.exports = {
  runArimaModel,
};

