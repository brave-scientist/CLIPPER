import React, { useEffect, useState } from 'react';
import { RefreshCw, ArrowLeft, CheckCircle2, XCircle, Clock, FileText, Database } from 'lucide-react';
import { fetchTestReport, TestReportEntry } from '../services/api';

interface TestReportProps {
  onBack: () => void;
}

export const TestReport: React.FC<TestReportProps> = ({ onBack }) => {
  const [entries, setEntries] = useState<TestReportEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchTestReport();
      setEntries(res.entries || []);
    } catch (err: any) {
      setError(err.message || 'Could not load test report.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, []);

  const getStepBadgeColor = (step: string) => {
    switch (step) {
      case 'import-file':
      case 'import-url':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'transcribe':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'highlights':
        return 'bg-purple-100 text-purple-800 border-purple-200';
      case 'export':
        return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      default:
        return 'bg-slate-100 text-slate-800 border-slate-200';
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto px-4 py-8 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-slate-900 text-white">
              Hidden Developer Tool
            </span>
            <span className="text-xs text-slate-500 font-mono">storage/test_log.json</span>
          </div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight mt-1">
            Execution Benchmarks & Test Report
          </h1>
          <p className="text-sm text-slate-500">
            Speed, file sizes, and status of recent import, transcribe, highlights, and export runs.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={loadReport}
            disabled={loading}
            className="px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-sm font-bold flex items-center gap-2 shadow-xs transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            onClick={onBack}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold flex items-center gap-2 shadow-sm transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to App</span>
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className="mb-6 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-sm font-medium">
          {error}
        </div>
      )}

      {/* Main Table Card */}
      <div className="bg-white rounded-3xl border border-slate-200/90 shadow-sm overflow-hidden">
        <div className="px-6 py-4 bg-slate-50/70 border-b border-slate-200/80 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-700">
            <Database className="w-4 h-4 text-slate-500" />
            <span>Last {entries.length} Benchmark Entries (Newest First)</span>
          </div>
          <span className="text-xs text-slate-400 font-medium">
            URL: <code className="bg-slate-200/60 px-1.5 py-0.5 rounded text-slate-600 font-mono">/#report</code>
          </span>
        </div>

        {loading ? (
          <div className="p-12 flex flex-col items-center justify-center text-slate-400 gap-3">
            <RefreshCw className="w-6 h-6 animate-spin text-blue-600" />
            <p className="text-sm font-medium">Loading benchmark logs...</p>
          </div>
        ) : entries.length === 0 ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
            <FileText className="w-8 h-8 text-slate-300" />
            <p className="text-base font-bold text-slate-600">No test logs recorded yet</p>
            <p className="text-sm max-w-md text-slate-400">
              Run an import, transcribe, highlights, or export operation in the app, and execution metrics will log here automatically.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase font-bold tracking-wider border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4">Step</th>
                  <th className="py-3 px-4">Duration</th>
                  <th className="py-3 px-4">File Size</th>
                  <th className="py-3 px-4">Result</th>
                  <th className="py-3 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                {entries.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3 px-4 text-xs font-mono text-slate-500 whitespace-nowrap">
                      {item.timestamp}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span
                        className={`inline-block px-2.5 py-1 rounded-lg text-xs font-bold border ${getStepBadgeColor(
                          item.step
                        )}`}
                      >
                        {item.step}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono font-bold whitespace-nowrap">
                      <span className="flex items-center gap-1.5 text-slate-900">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>{item.duration_sec.toFixed(2)}s</span>
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs text-slate-600 whitespace-nowrap">
                      {item.file_size || '-'}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      {item.result === 'ok' ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 text-xs font-bold bg-emerald-50 border border-emerald-200/80 px-2 py-0.5 rounded-md">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>OK</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-600 text-xs font-bold bg-rose-50 border border-rose-200/80 px-2 py-0.5 rounded-md">
                          <XCircle className="w-3.5 h-3.5" />
                          <span>ERROR</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-500 max-w-xs truncate" title={item.details}>
                      {item.details || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
